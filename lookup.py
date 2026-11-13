"""Wiki text fetched before the model starts thinking: one DuckDuckGo search, then the top wiki pages' source.
Most questions are answered from this in one pass, skipping the model's own search-then-fetch round trips (~10 s)."""
import hashlib, html, ipaddress, json, os, re, socket, threading, time, urllib.parse, urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
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


def agent(url):
    """MediaWiki's API etiquette asks for a descriptive agent (a spoofed one gets tools blocked); plain pages and DuckDuckGo refuse unknown ones."""
    if not urllib.parse.urlparse(url).path.endswith('api.php'):
        return UA
    import telemetry
    return f'Lorekeeper/{telemetry.VERSION} (+https://lorekeeper-cgv.pages.dev/)'


MOST_BYTES = 8_000_000   # of any one page: a MediaWiki API answer stops at 8 MB by default, and a hostile page never ends


def read(url, timeout=4, most=MOST_BYTES, ua=None):
    """The bytes of a public https page, never more than `most`: a longer one is refused, not cut (half a JSON answer
    or half an image is no use), so a page can't fill memory or the cache."""
    check_url(url)
    req = urllib.request.Request(url, headers={'User-Agent': ua or agent(url)})
    with _opener.open(req, timeout=timeout) as r:
        data = r.read(most + 1)
    if len(data) > most:
        raise ValueError(f'not fetching {url[:80]}: it is over {most} bytes')
    return data


def get(url, timeout=4):
    return read(url, timeout).decode('utf-8', 'replace')


CACHE_FILES, PAGE_TTL, SEARCH_TTL = 200, 24 * 3600, 3600


def cached(url, ttl, timeout=4):
    """get(), remembered on disk for ttl seconds so the same question twice (or the same page twice) skips the network.
    Any trouble reading or writing the cache just means a fetch; get() still vets every URL it fetches."""
    d = os.path.join(config.DIR, 'cache')
    f = os.path.join(d, hashlib.sha1(url.encode('utf-8')).hexdigest() + '.txt')
    try:
        if time.time() - os.path.getmtime(f) < ttl:
            with open(f, encoding='utf-8') as fh:
                text = fh.read()
            if text:
                return text
    except (OSError, ValueError):
        pass
    text = get(url, timeout)
    try:
        if text:
            os.makedirs(d, exist_ok=True)
            with open(f, 'w', encoding='utf-8') as fh:
                fh.write(text)
            old = sorted((os.path.join(d, n) for n in os.listdir(d)), key=os.path.getmtime)
            for x in old[:max(0, len(old) - CACHE_FILES)]:
                os.remove(x)
    except OSError:
        pass
    return text


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
            j = json.loads(cached(api, PAGE_TTL))
            wt = j.get('parse', {}).get('wikitext', {}).get('*', '')
            wt = re.sub(r'\[\[(?:File|Image|Category):[^\]]*\]\]|<!--.*?-->|<ref[^>]*>.*?</ref>|<gallery>.*?</gallery>', '', wt, flags=re.S)
            if wt.strip():
                return relevant(wt.strip(), question, most)
        return relevant(text_of(cached(url, PAGE_TTL)), question, most)
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


TRIED, RETRY = '~tried:', 7 * 24 * 3600   # a failed guess is remembered as TRIED+game -> when; old apps read the file as game -> host strings and ignore the extra keys


_learning = threading.Lock()


def _learn(game, host):
    """Remember the game's wiki host, or ('') that guessing found none. The guess and the web search now run side by
    side: a guess that found nothing never wipes a host the search results just gave."""
    with _learning:
        h = _hosts()
        if not host and h.get(game.lower()):
            return
        h[game.lower()] = host
        if host:
            h.pop(TRIED + game.lower(), None)
        else:
            h[TRIED + game.lower()] = str(int(time.time()))
        os.makedirs(config.DIR, exist_ok=True)
        with open(HOSTS, 'w', encoding='utf-8') as f:
            json.dump(h, f, indent=1)


def guess_host(game):
    """<game>.wiki.gg, else <game>.fandom.com, if either answers as a MediaWiki -> host or ''. Both asked at once."""
    base = re.sub(r'[^a-z0-9]', '', game.lower())

    def answers(host):
        try:
            j = json.loads(get(f'https://{host}/api.php?action=query&meta=siteinfo&format=json', timeout=3))
            return bool(j.get('query', {}).get('general'))
        except Exception:
            return False
    hosts = (f'{base}.wiki.gg', f'{base}.fandom.com')
    with ThreadPoolExecutor(len(hosts)) as ex:
        return next((h for h, ok in zip(hosts, ex.map(answers, hosts)) if ok), '')


def cart_host(game, folder):
    """The wiki host the game's cartridge names (carts update from the site, no release needed), if we can serve it."""
    if not folder:
        return ''
    try:
        import icons   # here, not at the top: icons imports lookup
        host = (icons.cart({'name': game}, folder) or {}).get('host') or ''
    except Exception:
        return ''
    return host if isinstance(host, str) and re.fullmatch(SUB, host) and any(re.fullmatch(p, host) for p in APIS) else ''


def _gave_up_recently(h, g):
    """A wiki search that found nothing is not retried for a week; a bare '' with no date (older app) counts as stale."""
    try:
        return time.time() - int(h.get(TRIED + g)) < RETRY
    except (TypeError, ValueError):
        return False


def known_host(game, folder=''):
    """The game's wiki host if no request is needed to know it: its cartridge's, known, or learned. Else ''."""
    g = game.lower()
    if host := cart_host(game, folder):
        return host
    if g in KNOWN:
        return KNOWN[g]
    h = _hosts()
    return h[g] if h.get(g) and re.fullmatch(SUB, h[g]) else ''   # a host saved by an older version, from a search result, is checked again


def host_for(game, urls=(), folder=''):
    """The game's wiki host: its cartridge's, known, learned, seen in search results, or guessed (again after a week)."""
    g = game.lower()
    if host := known_host(game, folder):
        return host
    h = _hosts()
    for u in urls:
        m = MEDIAWIKI.match(u)
        if m:
            _learn(game, m[1])
            return m[1]
    if g not in h or not h[g] and not _gave_up_recently(h, g):   # guess once per game, again a week after a miss
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
        j = json.loads(cached(api + '&redirects=1&titles=' + urllib.parse.quote('|'.join(cands)), SEARCH_TTL)).get('query', {})
        real = {p['title'] for p in j.get('pages', {}).values() if 'missing' not in p and 'invalid' not in p}
        moved = {r['from']: r['to'] for r in j.get('redirects', [])} | {nm['from']: nm['to'] for nm in j.get('normalized', [])}
        for c in cands:
            t = moved.get(moved.get(c, c), moved.get(c, c))
            if t in real and url(t) not in out:
                out.append(url(t))
    terms = ' '.join(re.sub(STOP, ' ', re.sub(r"[^\w' ]", ' ', question), flags=re.I).split())
    if len(out) < n and terms:
        j = json.loads(cached(api + f'&list=search&srlimit={n}&srsearch=' + urllib.parse.quote(terms), SEARCH_TTL))
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
    if game not in _sw_pages:   # kept on disk for a day too: the next session doesn't ask again
        j = json.loads(cached(api + '&list=allpages&aplimit=500&apprefix=' + urllib.parse.quote(game + '/'), PAGE_TTL, timeout=4))
        _sw_pages[game] = [p['title'] for p in j.get('query', {}).get('allpages', [])]
    url = lambda t: 'https://strategywiki.org/wiki/' + urllib.parse.quote(t.replace(' ', '_'))
    best = max(_sw_pages[game], key=lambda t: len(nouns & words(t.split('/', 1)[1])), default='')
    if best and nouns & words(best.split('/', 1)[1]):
        return url(best)
    if not _sw_pages[game]:
        return ''   # StrategyWiki has no guide for this game (or a different title for it)
    # its search doesn't index page text well: load the game's pages once and look for the nouns. Up to three batches,
    # asked for at once and kept on disk for a day; in memory only once all of them are in.
    if game not in _sw_text:
        titles = _sw_pages[game][:150]

        def batch(i):
            j = json.loads(cached(api + '&prop=revisions&rvprop=content&rvslots=main&titles='
                                  + urllib.parse.quote('|'.join(titles[i:i + 50])), PAGE_TTL, timeout=8))
            revs = ((pg['title'], (pg.get('revisions') or [{}])[0]) for pg in j.get('query', {}).get('pages', {}).values())
            return {t: (rev.get('slots', {}).get('main', {}).get('*') or rev.get('*') or '').lower() for t, rev in revs}
        starts = range(0, len(titles), 50)
        with ThreadPoolExecutor(len(starts)) as ex:
            parts = list(ex.map(batch, starts))
        _sw_text[game] = {t: text for part in parts for t, text in part.items()}
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


POINTING = set(stems(   # words that point at the screen or back in time, and name nothing to look up
    'screen earlier right while back previous previously looking holding hovering fighting equipped saved remembered picked '
    'found unlocked looted triggered activated have loadout inventory stats hand this that these those thing called named '
    'says said means minutes seconds moment couple than much many'))


def named(question):
    """The words of the question that name what it's about, as stems; empty when it only points ("what is this?",
    "what did I just get?"), which the screen answers and a search can't."""
    return words(question) - VERBS - POINTING - {'where', 'what', 'next'}


FIND_SECS, WIKI_SECS = 4, 6   # finding the pages, and all of wiki(): the player is waiting, and past this the model's own search is quicker


def _go(fn, *args):
    """fn(*args) on a thread of its own -> its Future. A daemon thread: a request still out never holds up quitting."""
    f = Future()

    def run():
        try:
            f.set_result(fn(*args))
        except Exception as e:
            f.set_exception(e)
    threading.Thread(target=run, daemon=True).start()
    return f


def _by(future, deadline, default):
    """The future's result if it's in by the deadline and didn't fail, else default. What comes in late still fills
    the caches (the pages on disk, the game's wiki host), so the next question is quick."""
    try:
        return future.result(timeout=max(0, deadline - time.time()))
    except Exception:
        return default


def wiki(question, game, pages=2, folder='', progress=''):
    """'Source: <url>\n<text>' blocks for the prompt, or '' when the search finds nothing (the model searches itself).
    progress: the player's latest notes. "Where do I go next?" names nothing, so their last place or item is what to look up.
    The lookups run side by side under one deadline (WIKI_SECS), not one after another with a timeout each: whatever
    isn't in by then is left out, and the model searches for what's missing."""
    if progress and not words(question) - VERBS - {'where', 'what', 'next'}:
        question = question + ' ' + ' '.join(progress.strip().splitlines()[-2:])
    start = time.time()
    found_by, done_by = start + FIND_SECS, start + WIKI_SECS
    host = known_host(game, folder) if game else ''

    def on_wiki():   # the wiki's own search; a wiki not known yet is guessed first
        h = host or host_for(game, folder=folder)
        return site_search(h, question, pages, game) if h else []
    web = lambda: _go(search, query(question, game))
    # at once: the wiki's search, the walkthrough, and (only while the game's wiki isn't known) the web search
    site = _go(on_wiki) if game else None
    found = None if host else web()
    guide = _go(strategywiki, question, game) if game and GUIDE_WORDS.search(question) else None   # "where do I go", "how do I beat": a walkthrough says it best
    urls = _by(site, found_by, []) if site else []
    if not urls:
        found = _by(found or web(), found_by, [])   # the wiki's search found nothing: the web's
        if game and not host:
            for m in filter(None, map(MEDIAWIKI.match, found)):
                _learn(game, m[1])   # learn the wiki for next time
                break
        urls = rank(found)[:pages]
    guide = _by(guide, found_by, '') if guide else ''
    if guide and guide not in urls:
        urls = urls[:pages] + [guide]
    mine = own_guides(question, game, folder) if game and folder else ''
    if not urls:
        return mine
    texts = [_by(f, done_by, '') for f in [_go(page, u, question) for u in urls]]
    return '\n\n'.join([f'Source: {u}\n{t}' for u, t in zip(urls, texts) if t] + ([mine] if mine else []))
