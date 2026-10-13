"""Wiki text fetched before the model starts thinking: one DuckDuckGo search, then the top wiki pages' source.
Most questions are answered from this in one pass, skipping the model's own search-then-fetch round trips (~10 s)."""
import html, ipaddress, json, os, re, socket, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
import config

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
WIKIS = ('bg3.wiki', 'wiki.gg', 'fandom.com', 'fextralife.com', 'game8.co', 'wikia', 'wiki')   # earlier = preferred
# MediaWiki sites whose page source we can fetch (infoboxes keep quotes and stats): host pattern -> api.php path
SUB = r'[a-z0-9-]+(?:\.[a-z0-9-]+)*'   # a hostname's labels only: no '?', '#', '@' or ':' to smuggle another host in
APIS = {SUB + r'\.wiki\.gg': '/api.php', SUB + r'\.fandom\.com': '/api.php', r'bg3\.wiki': '/w/api.php', r'www\.poe2wiki\.net': '/api.php',
        r'stardewvalleywiki\.com': '/mediawiki/api.php', r'strategywiki\.org': '/w/api.php'}
MEDIAWIKI = re.compile(r'^https?://(' + '|'.join(APIS) + r')/wiki/([^?#]+)')


def check_url(url):
    """Only public https pages: search results are anyone's links, and must not point this PC at localhost or the LAN."""
    u = urllib.parse.urlparse(url)
    if u.scheme != 'https' or not u.hostname:
        raise ValueError(f'not fetching {url[:80]}')
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(u.hostname, u.port or 443, proto=socket.IPPROTO_TCP)}
    except OSError as e:
        raise ValueError(f'cannot resolve {u.hostname}') from e
    if not addrs or not all(ipaddress.ip_address(a.split('%')[0]).is_global for a in addrs):
        raise ValueError(f'not fetching {u.hostname}: it is not a public address')


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)   # a public page can still bounce to an internal one
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_Redirects)


def get(url, timeout=4):
    check_url(url)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    return _opener.open(req, timeout=timeout).read().decode('utf-8', 'replace')


def text_of(h):
    m = re.search(r'(?is)<main\b.*?</main>|<article\b.*?</article>', h)
    h = m.group(0) if m else h
    h = re.sub(r'(?is)<(script|style|noscript|svg|head|nav|header|footer|aside)\b.*?</\1>', ' ', h)
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', h)).split())


def search(q):
    page = get('https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(q), timeout=5)
    out = []
    for u in re.findall(r'class="result__a" href="([^"]+)"', page)[:8]:
        u = urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(u)).query).get('uddg', [u])[0]
        if u.startswith('http') and u not in out:
            out.append(u)
    return out


def rank(urls):
    def score(u):
        host = urllib.parse.urlparse(u).netloc
        return next((i for i, w in enumerate(WIKIS) if w in host), len(WIKIS))
    return sorted(urls, key=score)


def stems(text):
    """Content words in order, roughly stemmed ("botchlings" ~ "botchling"); repeats kept."""
    out = []
    for w in re.findall(r"[a-z][a-z']{3,}", text.lower()):
        if not re.fullmatch(STOP, w) and not re.fullmatch(GENERIC, w):
            w = re.sub(r"'s?$", '', w)
            out.append(w if re.search(r'(?:us|ss|is)$', w) else re.sub(r'(?:ing|ed|es|s)$', '', w))
    return out


def words(text):
    """The set of stems: for matching a question to sections."""
    return set(stems(text))


def relevant(text, question, most=5000, lead=1500):
    """The page's opening (infobox: quote, stats) plus the sections that best match the question, in page order.
    Long pages (quest walkthroughs) keep the step being asked about instead of only the top."""
    if len(text) <= most:
        return text
    want = words(question)
    parts = re.split(r'(?m)^(=+[^=\n]+=+)\s*$', text)   # [lead, heading, body, heading, body, ...]
    if len(parts) > 2:
        secs = [(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
    else:   # plain page text: fixed-size chunks
        secs = [('', text[i:i + 900]) for i in range(lead, len(text), 900)]
        parts = [text[:lead]]
    def score(sec):
        h, body = sec
        return 3 * len(want & words(h)) + sum(body.lower().count(w) for w in want)
    head = parts[0][:lead]
    room, keep = most - len(head), set()
    for i in sorted(range(len(secs)), key=lambda i: -score(secs[i])):
        if score(secs[i]) == 0 or room <= 200:
            break
        h, body = secs[i]
        piece = (h + '\n' + body.strip())[:room]
        keep.add((i, piece))
        room -= len(piece)
    return head + ''.join('\n\n' + piece for _, piece in sorted(keep))


def page(url, question='', most=5000):
    """A wiki page's source (infoboxes keep the quote/flavor text and stats), else the page as plain text;
    cut to the parts that answer the question."""
    m = MEDIAWIKI.match(url)
    try:
        if m:
            api_path = next(p for h, p in APIS.items() if re.fullmatch(h, m[1]))
            api = f'https://{m[1]}{api_path}?action=parse&format=json&prop=wikitext&redirects=1&page=' + urllib.parse.quote(m[2], safe="%:/()_,.-~'")
            j = json.loads(get(api))
            wt = j.get('parse', {}).get('wikitext', {}).get('*', '')
            wt = re.sub(r'\[\[(?:File|Image|Category):[^\]]*\]\]|<!--.*?-->|<ref[^>]*>.*?</ref>|<gallery>.*?</gallery>', '', wt, flags=re.S)
            if wt.strip():
                return relevant(wt.strip(), question, most)
        return relevant(text_of(get(url)), question, most)
    except Exception:
        return ''


KNOWN = {"baldur's gate 3": 'bg3.wiki', 'enter the gungeon': 'enterthegungeon.wiki.gg', 'hades': 'hades.fandom.com',
         'hades ii': 'hades.fandom.com', 'terraria': 'terraria.wiki.gg', 'risk of rain 2': 'riskofrain2.wiki.gg',
         'dead by daylight': 'deadbydaylight.wiki.gg', 'deep rock galactic': 'deeprockgalactic.wiki.gg', 'subnautica 2': 'subnautica.fandom.com',
         'stardew valley': 'stardewvalleywiki.com', 'the binding of isaac: rebirth': 'bindingofisaacrebirth.wiki.gg',
         'the witcher 3: wild hunt': 'witcher.fandom.com', 'the witcher 3': 'witcher.fandom.com', 'cyberpunk 2077': 'cyberpunk.fandom.com',
         'hollow knight': 'hollowknight.wiki.gg', 'hollow knight: silksong': 'hollowknight.wiki.gg', 'path of exile 2': 'www.poe2wiki.net',
         'borderlands 3': 'borderlands.fandom.com', 'borderlands 2': 'borderlands.fandom.com', 'borderlands: the pre-sequel': 'borderlands.fandom.com',
         'borderlands game of the year enhanced': 'borderlands.fandom.com', 'borderlands 4': 'borderlands.fandom.com',
         'the elder scrolls v: skyrim special edition': 'elderscrolls.fandom.com', 'fallout 4': 'fallout.fandom.com', 'starfield': 'starfield.fandom.com'}
HOSTS = os.path.join(config.DIR, 'wikis.json')   # learned: game name -> its MediaWiki host ('' = none found)
STOP = r"\b(what|whats|does|do|is|are|the|a|an|did|i|just|get|got|me|tell|about|how|can|should|where|who|which|my|to|of|in|for|it|this|that|please|ok|okay|hey)\b"


def api_path(host):
    return next((p for h, p in APIS.items() if re.fullmatch(h, host)), '/api.php')


def _hosts():
    try:
        with open(HOSTS, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _learn(game, host):
    h = _hosts()
    h[game.lower()] = host
    os.makedirs(config.DIR, exist_ok=True)
    with open(HOSTS, 'w', encoding='utf-8') as f:
        json.dump(h, f, indent=1)


def guess_host(game):
    """<game>.wiki.gg, then <game>.fandom.com, if either answers as a MediaWiki -> host or ''."""
    base = re.sub(r'[^a-z0-9]', '', game.lower())
    for host in (f'{base}.wiki.gg', f'{base}.fandom.com'):
        try:
            j = json.loads(get(f'https://{host}/api.php?action=query&meta=siteinfo&format=json', timeout=3))
            if j.get('query', {}).get('general'):
                return host
        except Exception:
            pass
    return ''


def host_for(game, urls=()):
    """The game's wiki host: known, learned, seen in search results, or guessed once."""
    g = game.lower()
    if g in KNOWN:
        return KNOWN[g]
    h = _hosts()
    if h.get(g) and re.fullmatch(SUB, h[g]):   # a host saved by an older version, from a search result, is checked again
        return h[g]
    for u in urls:
        m = MEDIAWIKI.match(u)
        if m:
            _learn(game, m[1])
            return m[1]
    if g not in h:   # guess once per game
        found = guess_host(game)
        _learn(game, found)
        return found
    return ''


GENERIC = r"\b(perks?|power|item|items|synergy|synergies|skills?|abilit(?:y|ies)|spells?|builds?|weapon|armou?r|boss|quest|location|lore|killer|survivor|add-?ons?|effect|work|works|mean|good|best|better|use)\b"


def titles(question):
    """Page titles the question may name, likeliest first: its capitalized runs ("Dead Hard"), then its key words."""
    q = re.sub(r"[^\w' -]", ' ', question)
    runs = [r for r in re.findall(r"\b[A-Z][\w'-]*(?:\s+(?:of|the|de|du)?\s*[A-Z][\w'-]*)*", q) if r.lower() not in ('i', 'what', 'who', 'how')]
    key = ' '.join(re.sub(GENERIC, ' ', re.sub(STOP, ' ', q, flags=re.I), flags=re.I).split())
    out = []
    for t in runs + [key, key.title()] + [f'The {r}' for r in runs]:   # "The Nurse" is how DBD titles killers
        t = re.sub(GENERIC, ' ', t, flags=re.I)
        t = ' '.join(t.split())
        if t and t not in out:
            out.append(t)
    return out[:8]


def site_search(host, question, n=2, game=''):
    """The wiki's own API: names in the question that are page titles first, then its full-text search. ~0.3 s, no captchas."""
    api = f'https://{host}{api_path(host)}?format=json&action=query'
    url = lambda t: f"https://{host}/wiki/{urllib.parse.quote(t.replace(' ', '_'))}"
    out = []
    cands = titles(question)
    if game:   # series wikis title an item per game: "Flakker (Borderlands 3)" before "Flakker"
        cands = [f'{t} ({game})' for t in cands[:3]] + cands
        cands = cands[:10]
    if cands:
        j = json.loads(get(api + '&redirects=1&titles=' + urllib.parse.quote('|'.join(cands)), timeout=4)).get('query', {})
        real = {p['title'] for p in j.get('pages', {}).values() if 'missing' not in p and 'invalid' not in p}
        moved = {r['from']: r['to'] for r in j.get('redirects', [])} | {nm['from']: nm['to'] for nm in j.get('normalized', [])}
        for c in cands:
            t = moved.get(moved.get(c, c), moved.get(c, c))
            if t in real and url(t) not in out:
                out.append(url(t))
    terms = ' '.join(re.sub(STOP, ' ', re.sub(r"[^\w' ]", ' ', question), flags=re.I).split())
    if len(out) < n and terms:
        j = json.loads(get(api + f'&list=search&srlimit={n}&srsearch=' + urllib.parse.quote(terms), timeout=4))
        out += [url(r['title']) for r in j.get('query', {}).get('search', []) if url(r['title']) not in out]
    return out[:n]


def query(question, game):
    q = re.sub(STOP, ' ', question, flags=re.I)
    return f"{game} wiki {' '.join(q.split())}" if game else ' '.join(q.split())


GUIDE_WORDS = re.compile(r"\b(where|next|how do i|how to|get to|find|reach|beat|defeat|solve|puzzle|stuck|walkthrough|guide|"
                         r"what do i|go now|open|unlock|key|door|switch|dungeon|level|chapter|area|boss|route|path)\b", re.I)
GUIDES = 'guides'   # <notes folder>/<game>/guides/*.txt: the player's own saved FAQs


VERBS = {'beat', 'defeat', 'kill', 'get', 'reach', 'find', 'after', 'before', 'into', 'past', 'next', 'now', 'there', 'here', 'go',
         'going', 'stuck', 'solve', 'open', 'unlock', 'need', 'want', 'have', 'from', 'with', 'then', 'walkthrough', 'guide'}
_sw_pages, _sw_text = {}, {}


def strategywiki(question, game):
    """The game's StrategyWiki walkthrough page for this question ('<Game>/<Area>'), or ''. Text guides for thousands of games.
    Its own search wants every word on the page, so: the game's page titles first, then its key nouns within the game."""
    api = 'https://strategywiki.org/w/api.php?format=json&action=query'
    nouns = {w for w in words(question) if w not in VERBS}
    if not nouns:
        return ''
    if game not in _sw_pages:
        j = json.loads(get(api + '&list=allpages&aplimit=500&apprefix=' + urllib.parse.quote(game + '/'), timeout=4))
        _sw_pages[game] = [p['title'] for p in j.get('query', {}).get('allpages', [])]
    url = lambda t: 'https://strategywiki.org/wiki/' + urllib.parse.quote(t.replace(' ', '_'))
    best = max(_sw_pages[game], key=lambda t: len(nouns & words(t.split('/', 1)[1])), default='')
    if best and nouns & words(best.split('/', 1)[1]):
        return url(best)
    if not _sw_pages[game]:
        return ''   # StrategyWiki has no guide for this game (or a different title for it)
    # its search doesn't index page text well: load the game's pages once (batched, cached) and look for the nouns
    if game not in _sw_text:
        _sw_text[game] = {}
        titles = _sw_pages[game][:150]
        for i in range(0, len(titles), 50):
            j = json.loads(get(api + '&prop=revisions&rvprop=content&rvslots=main&titles=' + urllib.parse.quote('|'.join(titles[i:i + 50])), timeout=8))
            for pg in j.get('query', {}).get('pages', {}).values():
                rev = (pg.get('revisions') or [{}])[0]
                _sw_text[game][pg['title']] = (rev.get('slots', {}).get('main', {}).get('*') or rev.get('*') or '').lower()
    score = lambda t: sum(_sw_text[game][t].count(n) for n in nouns)
    hit = max(_sw_text[game], key=score, default='')
    return url(hit) if hit and score(hit) else ''


def own_guides(question, game, folder, most=4000):
    """The best-matching parts of text guides the player saved for this game -> 'Source: …' block or ''."""
    d = os.path.join(folder, re.sub(r'[^a-z0-9]+', '-', game.lower()).strip('-'), GUIDES)
    if not os.path.isdir(d):
        return ''
    out = []
    for f in sorted(os.listdir(d)):
        if f.lower().endswith(('.txt', '.md')):
            try:
                text = open(os.path.join(d, f), encoding='utf-8', errors='replace').read()
            except OSError:
                continue
            out.append(f'Source: your guide {f}\n' + relevant(text, question, most // max(1, len(out) + 1)))
    return '\n\n'.join(out[:2])


def wiki(question, game, pages=2, folder='', progress=''):
    """progress: the player's latest notes. "Where do I go next?" names nothing, so their last place or item is what to look up."""
    if progress and not words(question) - VERBS - {'where', 'what', 'next'}:
        question = question + ' ' + ' '.join(progress.strip().splitlines()[-2:])
    """'Source: <url>\n<text>' blocks for the prompt, or '' when the search finds nothing (the model searches itself)."""
    urls = []
    host = host_for(game) if game else ''
    if host:
        try:
            urls = site_search(host, question, pages, game)
        except Exception:
            urls = []
    if not urls:
        try:
            found = search(query(question, game))
        except Exception:
            found = []
        if game and not host and found:
            host_for(game, found)   # learn the wiki for next time
        urls = rank(found)[:pages]
    guide = ''
    if game and GUIDE_WORDS.search(question):   # "where do I go", "how do I beat": a walkthrough says it best
        try:
            guide = strategywiki(question, game)
        except Exception:
            guide = ''
        if guide and guide not in urls:
            urls = urls[:pages] + [guide]
    mine = own_guides(question, game, folder) if game and folder else ''
    if not urls:
        return mine
    with ThreadPoolExecutor(len(urls)) as ex:
        texts = list(ex.map(lambda u: page(u, question), urls))
    return '\n\n'.join([f'Source: {u}\n{t}' for u, t in zip(urls, texts) if t] + ([mine] if mine else []))
