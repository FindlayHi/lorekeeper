"""Lore: a game's curated knowledge (wiki sections with their source), checked before the live wiki lookup.

A cartridge may point at a lore pack (a zip of json: manifest + chunks). It comes off the network or from the player,
so it is data only and read strictly: size caps, a hash that must match, no pickles, no paths."""
import hashlib, io, json, math, os, re, threading, urllib.request, zipfile

import config, lookup

DIR = config.DIR   # where a player's packs are kept
SITE = 'https://lorekeeper-cgv.pages.dev/'
FILE = re.compile(r'lore/[a-z0-9-]{1,60}\.zip')   # a pointer can only name a pack in the site's lore folder
SHA = re.compile(r'[0-9a-f]{64}')
MAX_ZIP = 40_000_000      # bytes, packed
MAX_CHUNKS = 60_000
MAX_ENTITIES = 20_000
ENTITY_TEXT = 2500        # characters of one thing's entry handed to the model
ENTITIES = 4              # things named in one question that are looked up
MAX_TEXT = 4000           # characters in one chunk
TRUST = ('official', 'community', 'local')
KINDS = ('item', 'boss', 'quest', 'mechanic', 'build', 'lore', 'perk', 'status', 'power')
SURE = 0.5                # the best chunk must hold this share of what the question asks about, else the live wiki is asked
TOP = 5
BUDGET = 5000             # characters handed to the model, as lookup.wiki's pages are
STALE = 'This game has had a patch since this lore was gathered, so numbers here may be out of date.'


def pointer(lore):
    """A cart's lore pointer -> {file, sha256, version, build} or None. It comes off the network."""
    try:
        if FILE.fullmatch(lore['file']) and SHA.fullmatch(lore['sha256']):
            return {'file': lore['file'], 'sha256': lore['sha256'], 'version': int(lore.get('version', 1)),
                    'build': str(lore.get('builtForBuild', ''))[:40]}
    except (KeyError, TypeError, ValueError):
        pass
    return None


def _url(url, trust):
    """A chunk's source: an https page, or for the player's own pack a file name ('local:my-guide.md')."""
    ok = re.fullmatch(r'https://[a-z0-9.-]+/[^\s]{0,400}', str(url)) or (trust == 'local' and re.fullmatch(r'local:[\w .-]{1,80}', str(url)))
    return str(url) if ok else ''


def load(data, sha=None):
    """A pack's bytes -> {game, trust, sources, chunks, build}, or None when anything about it is wrong."""
    if len(data) > MAX_ZIP:
        return None
    if sha and hashlib.sha256(data).hexdigest() != sha:
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            if 'lore.json' not in names or 'chunks.jsonl' not in names or any(not re.fullmatch(r'[A-Za-z0-9_.-]{1,40}', n) or n.startswith('.') for n in names):
                return None   # flat files only: no folders, no paths
            if any(i.file_size > 4 * MAX_ZIP for i in z.infolist()):
                return None
            man = json.loads(z.read('lore.json'))
            lines = z.read('chunks.jsonl').decode('utf-8').splitlines()
            elines = z.read('entities.jsonl').decode('utf-8').splitlines() if 'entities.jsonl' in names else []
        if man.get('schema') != 1 or man.get('trust') not in TRUST or len(lines) > MAX_CHUNKS:
            return None
        chunks = []
        for ln in lines:
            c = json.loads(ln)
            text, url = str(c['text'])[:MAX_TEXT], _url(c['url'], man['trust'])
            if text.strip() and url:
                chunks.append({'id': str(c['id'])[:80], 'url': url, 'title': str(c.get('title', ''))[:120],
                               'section': str(c.get('section', ''))[:120], 'text': text, 'fetched': str(c.get('fetched', ''))[:20],
                               'kind': c.get('kind') if c.get('kind') in KINDS else 'lore'})
        if not chunks or len(elines) > MAX_ENTITIES:
            return None
        ents = []
        for ln in elines:
            e = json.loads(ln)
            text, url = str(e['text'])[:ENTITY_TEXT], _url(e['url'], man['trust'])
            if text.strip() and url and str(e['name']).strip():
                ents.append({'name': str(e['name'])[:80], 'url': url, 'kind': e.get('kind') if e.get('kind') in KINDS else 'lore', 'text': text,
                             'aliases': [str(a)[:60] for a in e.get('aliases', [])[:8]] if isinstance(e.get('aliases'), list) else []})
        return {'game': str(man.get('game', ''))[:80], 'trust': man['trust'], 'version': int(man.get('version', 0)), 'build': str(man.get('builtForBuild', ''))[:40],
                'sources': [str(s.get('host', ''))[:80] for s in man.get('sources', []) if isinstance(s, dict)][:50],
                'chunks': chunks, 'index': _index(chunks), 'entities': ents, 'names': _names(ents)}
    except (KeyError, TypeError, ValueError, OSError, zipfile.BadZipFile, UnicodeDecodeError):
        return None


def norm(s):
    return ' '.join(re.findall(r'[a-z0-9]+', str(s).lower()))


def _names(ents):
    """What a question can call each thing -> its position in ents: the name, the name after a prefix ("Hex: Ruin" ~ "Ruin"),
    without "The", and its aliases. A shorthand two things share is dropped. A name is at least 4 characters; an alias,
    which a person chose, at least 2 ("DS")."""
    found = {}
    for i, e in enumerate(ents):
        full = norm(e['name'])
        keys = {full: 4, norm(e['name'].split(':', 1)[-1]): 4, re.sub(r'^the ', '', full): 4}
        keys.update({norm(a): 2 for a in e['aliases']})
        for k, least in keys.items():
            if len(k) >= least:
                found.setdefault(k, set()).add(i)
    return {k: min(v) for k, v in found.items() if len(v) == 1 or k in {norm(e['name']) for e in ents}}


def find(pack, question, names=()):
    """The things the question names -> [entity], in the order asked (at most ENTITIES). names: things already known
    to be meant (read from the screen's icons), taken exactly."""
    q, out, spans = ' ' + norm(question) + ' ', [], []
    for k, i in pack['names'].items():
        at = q.find(f' {k} ')
        if at >= 0:
            spans.append((at, at + len(k), i))
    spans = [x for x in spans if not any(o[2] != x[2] and o[0] <= x[0] and x[1] <= o[1] and o[1] - o[0] > x[1] - x[0] for o in spans)]   # "Spirit" inside "Spirit Fury"
    for i in [pack['names'].get(norm(n)) for n in names] + [x[2] for x in sorted(spans)]:
        if i is not None and i not in out:
            out.append(i)
    return [pack['entities'][i] for i in out[:ENTITIES]]


K1, B, HEAD = 1.2, 0.75, 3   # BM25; the title and section count 3 times


FILLER = {'many', 'much', 'have', 'come', 'when', 'next', 'there', 'will', 'would', 'could', 'been', 'were', 'also', 'just', 'really', 'like'}   # question words that name no topic
LIVE = re.compile(r"\b(next|latest|newest|upcoming|currently|today|tonight|tomorrow|yesterday|right now|this (?:week|month|year)|release date|patch (?:date|time)|when (?:is|does|will|did))\b", re.I)


def stems(text):
    """lookup.stems with "med-kit" ~ "medkit" ("Med-Kits" is a page; no 3-letter word survives otherwise), minus question filler."""
    return [w for w in lookup.stems(re.sub(r'(?<=[a-z])-(?=[a-z])', '', str(text).lower())) if w not in FILLER]


def _index(chunks):
    """BM25 statistics over each chunk: word counts (title and section words count extra) and the chunk's own length."""
    docs, heads = [], []
    for c in chunks:
        head = set(stems(f"{c['title']} {c['section']}"))
        tf = {}
        for w in stems(c['text']):
            tf[w] = tf.get(w, 0) + 1
        for w in stems(f"{c['title']} {c['section']}"):
            tf[w] = tf.get(w, 0) + HEAD
        docs.append(tf)
        heads.append(head)
    df = {}
    for d in docs:
        for w in d:
            df[w] = df.get(w, 0) + 1
    n = len(docs)
    lens = [sum(d.values()) for d in docs]
    return {'docs': docs, 'heads': heads, 'lens': lens, 'avg': (sum(lens) / n) if n else 1,
            'idf': {w: math.log(1 + (n - k + 0.5) / (k + 0.5)) for w, k in df.items()}}


def search(pack, question, top=TOP):
    """The chunks that best match the question -> [(score, chunk)], best first (BM25)."""
    q = set(stems(question))
    ix = pack['index']
    scored = []
    for i, (tf, ln) in enumerate(zip(ix['docs'], ix['lens'])):
        sc = sum(ix['idf'][w] * tf[w] * (K1 + 1) / (tf[w] + K1 * (1 - B + B * ln / ix['avg'])) for w in q if w in tf)
        if sc > 0:
            scored.append((sc, i))
    return [(sc, pack['chunks'][i]) for sc, i in sorted(scored, key=lambda x: -x[0])[:top]]


def share(pack, question, chunk):
    """How much of the question the chunk covers, 0-1: the weight of the question's words found in it over that of all of
    them, a word the pack has never seen counting as the rarest (so "who is the best streamer" is not a hit on "best").
    0 unless the chunk's title or section holds one of the question's words: the answer lives on a page about the topic."""
    ix = pack['index']
    i = pack['chunks'].index(chunk)
    q = set(stems(question))
    top = max(ix['idf'].values(), default=0)
    total = sum(ix['idf'].get(w, top) for w in q)
    if not q & ix['heads'][i]:
        return 0
    return sum(ix['idf'][w] for w in q if w in ix['docs'][i]) / total if total else 0


def retrieve(pack, question, names=()):
    """What the pack holds for the question -> {'entities': things it names, 'hits': [(score, chunk)], 'sure': bool}.
    Named things are exact and always sure. Search results are sure only when one chunk covers enough of the question."""
    ents = find(pack, question, names)
    hits = search(pack, question)
    near = bool(hits) and share(pack, question, hits[0][1]) >= SURE and not LIVE.search(question)   # a question about now or next is not in a snapshot
    return {'entities': ents, 'hits': hits if near and not ents else [], 'sure': bool(ents) or near}   # a named thing's entry is the answer: no loosely related extras


def render(got, stale=False):
    """What retrieve found -> text for the prompt, as lookup.wiki's pages: 'Source: url' then the words."""
    out, used, seen = [], 0, set()
    blocks = ([(e['url'], e['name'], e['text']) for e in got['entities']]
              + [(c['url'], c['title'] + (f" / {c['section']}" if c['section'] else ''), c['text']) for _, c in got['hits']])
    for url, head, text in blocks:
        if (url, head) in seen or (used + len(text) > BUDGET and out):
            continue
        if url in {u for u, _, _ in blocks[:len(got['entities'])]} and head not in {h for u, h, _ in blocks[:len(got['entities'])]}:
            continue   # a named thing's entry already covers its page
        seen.add((url, head))
        out.append(f'Source: {url}\n{head}\n{text}')
        used += len(text)
    return ('\n\n'.join(out) + (f'\n\n({STALE})' if stale else '')) if out else ''


# the packs a player has, per game

_packs, _lock = {}, threading.Lock()


def _path(folder, game, local=False):
    """lore/<game>.zip is the cart's pack, downloaded; lore/<game>.local.zip is one the player dropped in."""
    return os.path.join(folder, 'lore', re.sub(r'[^a-z0-9]+', '-', game.lower()).strip('-') + ('.local' if local else '') + '.zip')


def _download(url):
    lookup.check_url(url)
    req = urllib.request.Request(url, headers={'User-Agent': lookup.UA})
    return lookup._opener.open(req, timeout=30).read(MAX_ZIP + 1)


def get(game, ptr, folder, fetch=True):
    """The game's pack: the player's own (dropped in the lore folder as <game>.local.zip, never 'official') else the
    cart's, downloaded once and checked against the cart's hash every time. None when there isn't one or it fails the checks."""
    key = (game or '').lower()
    with _lock:
        if key in _packs:
            return _packs[key]
    pack, mine, path = None, _path(folder, game or '', True), _path(folder, game or '')
    try:
        if os.path.exists(mine):
            with open(mine, 'rb') as f:
                pack = load(f.read())
            pack = pack if pack and pack['trust'] != 'official' else None   # a file anyone can drop in cannot claim to be ours
        if not pack and ptr:
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    pack = load(f.read(), ptr['sha256'])
            if not pack and fetch:
                data = _download(SITE + ptr['file'])
                pack = load(data, ptr['sha256'])
                if pack:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, 'wb') as f:
                        f.write(data)
    except (OSError, ValueError):
        pack = None
    with _lock:
        _packs[key] = pack
    return pack


def context(game, ptr, question, folder=None, build=None, fetch=True, names=()):
    """What the game's lore says about the question, as prompt text; '' when there's no pack or nothing sure,
    and the live wiki is asked. build: the installed game's Steam buildid, to tell the model the lore may be old.
    names: things read from the screen's icons, looked up exactly."""
    pack = get(game, ptr, folder or DIR, fetch)
    got = retrieve(pack, question, names) if pack else None
    if not got or not got['sure']:
        return ''
    return render(got, stale=bool(build and pack['build'] and build != pack['build']))


def entry(game, ptr, name, folder=None, fetch=True):
    """One thing's entry by its exact name (a perk read from the screen) -> text, or ''."""
    pack = get(game, ptr, folder or DIR, fetch)
    got = find(pack, name, [name]) if pack else []
    return render({'entities': got[:1], 'hits': []}) if got and norm(got[0]['name']) == norm(name) else ''
