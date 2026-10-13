"""Fetched pages -> chunks: wikitext to plain text, split by section, instruction-like text held back for review.
  python tools/lore/clean.py "Dead by Daylight"
Writes lore/<slug>/chunks.jsonl and quarantine.json. A chunk that looks like it is talking to the model (or hides
something) is left out until a person reads it and lists its hash under "approved" in lore/<slug>/reviewed.json.
Chunks are ~100-300 words, with the infobox (stats) as a chunk of its own."""
import hashlib, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from htmltext import html_text

MAXW, MINW = 300, 80
KEEP = {'icon', 'iconlink', 'nowrap', 'tooltip', 'c', 'plural', 'sfn', 'abbr', 'lang', 'convert', 'ft', 'item', 'perk'}   # templates whose text is the point
SUSPECT = [(re.compile(p, re.I), why) for p, why in (
    (r'\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|your|these)\b.{0,30}\b(instruction|prompt|rule|message|context)', 'tells the model to ignore its instructions'),
    (r'\b(system prompt|new instructions|jailbreak|developer mode)\b|\byou are now (?:an? |the )?(?:assistant|ai|chatbot|unrestricted|dan|jailbroken)\b|\b(?:act as|pretend to be|pretend you are) (?:an? |the )?(?:assistant|ai|chatbot|language model|dan|unrestricted)\b', 'addresses the model'),
    (r'\b(assistant|claude|chatgpt|gpt-?\d|language model|ai model)\b.{0,40}\b(should|must|will|always|never)\b', 'addresses the model'),
    (r'(?i)\b(send|post|upload|exfiltrate|email|fetch|visit|open|browse)\b.{0,40}\b(https?://|url|link)', 'asks for a request to a link'),
    (r'[A-Za-z0-9+/]{100,}={0,2}', 'a long encoded blob'),
    (r'[\U000e0000-\U000e007f\u202a-\u202e\u2066-\u2069]', 'hidden or direction-changing characters'),   # zero-width spaces are stripped by htmltext (wikis are full of them); tag characters and bidi controls can hide or reorder text
    (r'<\s*(script|iframe|object|embed|style)\b', 'markup that runs'),
)]
URL = re.compile(r'https?://([^/\s)]+)')


def template(m):
    """One innermost {{template}} -> its text. Infoboxes become 'key: value' lines between markers; most others vanish."""
    parts = [p.strip() for p in m[1].split('|')]
    name = parts[0].lower().replace('_', ' ')
    named = [(k.strip(), v.strip()) for k, _, v in (p.partition('=') for p in parts[1:] if '=' in p) if v.strip()]
    if name.startswith(('infobox', 'info box')) or name.endswith('infobox'):
        return '\n@@INFOBOX@@\n' + '\n'.join(f'{k}: {v}' for k, v in named) + '\n@@END@@\n'
    if name in KEEP:
        return ' '.join(p for p in parts[1:] if '=' not in p and p)
    return ''


def plain(wt):
    """Wikitext -> readable text (headings kept as '== X ==' lines)."""
    wt = re.sub(r'<!--.*?-->', '', wt, flags=re.S)
    wt = re.sub(r'<ref[^>/]*/>|<ref[^>]*>.*?</ref>|<gallery.*?</gallery>|<(script|style)\b.*?</\1>', '', wt, flags=re.S | re.I)
    wt = re.sub(r'\[\[(?:File|Image|Category|Media):[^\]]*\]\]', '', wt, flags=re.I)
    for _ in range(30):   # innermost first
        new = re.sub(r'\{\{([^{}]*)\}\}', lambda m: template(m), wt)
        if new == wt:
            break
        wt = new
    wt = re.sub(r'\{\|.*?\|\}', table, wt, flags=re.S)
    wt = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', wt)
    wt = re.sub(r'\[https?://\S+ ([^\]]+)\]|\[https?://\S+\]', lambda m: m[1] or '', wt)
    wt = re.sub(r"'{2,5}", '', wt)
    wt = re.sub(r'<br\s*/?>', ' ', wt, flags=re.I)
    wt = re.sub(r'</?[a-zA-Z][^>]*>', '', wt)
    wt = re.sub(r'(?m)^[*#:;]+\s*', '- ', wt)
    wt = re.sub(r'__[A-Z]+__|\{\{|\}\}', '', wt)
    return re.sub(r'[ \t]+', ' ', re.sub(r'\n{3,}', '\n\n', wt)).strip()


def table(m):
    """A wikitext table -> one line per row, cells joined with ' | '."""
    rows, out = re.split(r'\n\|-[^\n]*', m[0]), []
    for r in rows:
        cells = []
        for ln in r.splitlines():
            if ln.startswith(('{|', '|}', '|+')):
                continue
            if ln[:1] in '|!':
                for c in re.split(r'\|\||!!', ln[1:]):
                    cells.append(c.split('|', 1)[-1].strip() if '|' in c and '[[' not in c.split('|', 1)[0] else c.strip())
            elif cells:
                cells[-1] += ' ' + ln.strip()
        if any(cells):
            out.append(' | '.join(c for c in cells if c))
    return '\n' + '\n'.join(out) + '\n'


def sections(text, skip=()):
    """Plain text -> [(heading path, body)]; the lead is 'Overview'. Infoboxes come out as their own 'Infobox' entry."""
    out, path, buf = [], [], []
    skip = {x.lower() for x in skip}

    def flush():
        body = '\n'.join(buf).strip()
        buf.clear()
        if body and not any(p.lower() in skip for p in path):
            out.append((' > '.join(path) or 'Overview', body))
    for ln in text.splitlines():
        h = re.fullmatch(r'(={2,4})\s*(.+?)\s*\1', ln.strip())
        if ln.strip() == '@@INFOBOX@@':
            flush(); path.append('Infobox')
        elif ln.strip() == '@@END@@':
            flush(); path.remove('Infobox') if 'Infobox' in path else None
        elif h:
            flush()
            path[:] = [x for x in path if x != 'Infobox'][:len(h[1]) - 2] + [h[2]]
        else:
            buf.append(ln)
    flush()
    return out


def chunks_of(title, secs):
    """[(path, body)] -> [(section label, text)]: small neighbours merge, big sections split on paragraphs."""
    out, cur, curw, label = [], [], 0, ''

    def emit():
        if cur:
            out.append((label, '\n\n'.join(cur)))
        cur.clear()
    for path, body in secs:
        if path.endswith('Infobox'):
            emit(); curw = 0
            out.append(('Infobox', body))
            continue
        for para in [p for p in re.split(r'\n\s*\n', body) if p.strip()]:
            w = len(para.split())
            if cur and curw + w > MAXW:
                emit(); curw = 0
            if not cur:
                label = path
            cur.append(para if path == label else f'{path.split(" > ")[-1]}: {para}')
            curw += w
            if curw >= MINW and path != label:
                emit(); curw = 0
    emit()
    return [(s, t) for s, t in out if len(t.split()) >= 3]


def flags(text, ok_hosts):
    """Why this chunk should be read by a person before it goes in; [] when nothing looks wrong."""
    why = [w for rx, w in SUSPECT if rx.search(text)]
    why += [f'links to {h}' for h in {m[1].lower() for m in URL.finditer(text)} if h not in ok_hosts]
    return sorted(set(why))


def make(title, section, text, url, kind, fetched, rev):
    h = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
    return {'id': hashlib.sha1(f'{url}|{section}|{h}'.encode()).hexdigest()[:12], 'url': url, 'title': title, 'section': section,
            'text': text, 'kind': kind, 'fetched': fetched, 'rev': rev, 'hash': h}


def user_chunks(s):
    """A player's own folder of md/txt guides -> chunks (url 'local:<file>')."""
    now = time.strftime('%Y-%m-%d')
    for name in sorted(os.listdir(s['folder'])):
        if name.lower().endswith(('.md', '.txt')):
            with open(os.path.join(s['folder'], name), encoding='utf-8', errors='replace') as f:
                text = f.read()
            text = re.sub(r'(?m)^#{1,4}\s*(.+?)\s*#*$', lambda m: f'== {m[1]} ==', text)
            for sec, t in chunks_of(name, sections(text)):
                yield make(name, sec, t, 'local:' + re.sub(r'[^\w .-]', '_', name)[:80], 'lore', now, 0)


ENTITY_CHARS = 2500
OR_NAME = re.compile(r'\bor "((?:The )?[^"\n]{3,40})"')   # 'Sally Smithson or "The Nurse" is one of 44 Killers'


def drop_lines(text, patterns):
    """Lines the wiki repeats on every page of a kind (page boilerplate) that say nothing."""
    rx = [re.compile(p) for p in patterns]
    return '\n'.join(ln for ln in text.splitlines() if not any(r.match(ln.strip()) for r in rx))


def entity_of(title, text, skip, aliases, start=None):
    """One page -> the entry for the thing it is about: its sections in order (minus cosmetics, lore...), cut at ENTITY_CHARS.
    start: a regex for the line an entry begins at in the lead (killers' pages open with a long journal quote before their stats)."""
    if start:
        m = re.search(start, text, re.M)
        if m and (text.find('\n== ') < 0 or m.start() < text.find('\n== ')):
            text = text[m.start():]
    parts = []
    for path, body in sections(text, skip):
        parts.append(body if path in ('Overview', 'Infobox') else f'{path}\n{body}')
    out, used = [], 0
    for para in '\n\n'.join(parts).split('\n\n'):
        if used + len(para) > ENTITY_CHARS and out:
            break
        out.append(para[:ENTITY_CHARS])
        used += len(para)
    body = '\n\n'.join(out).strip()
    auto = OR_NAME.findall(body[:1500])
    return body, sorted(set(auto) | set(aliases.get(title, [])))


def run(game):
    """lore/<slug>/raw/pages.jsonl -> chunks.jsonl, entities.jsonl and quarantine.json; returns the counts."""
    doc = sources(game)
    ok_hosts, skip = hosts(doc), {x for s in doc['sources'] for x in s.get('skipSections', [])}
    eskip = skip | {x for s in doc['sources'] for x in s.get('entitySkipSections', [])}
    ekinds = {x for s in doc['sources'] for x in s.get('entityKinds', [])}
    drops = [x for s in doc['sources'] for x in s.get('dropLines', [])]
    aliases = {k: v for s in doc['sources'] for k, v in s.get('aliases', {}).items()}
    start = next((s['entityStart'] for s in doc['sources'] if s.get('entityStart')), None)
    rpath = os.path.join(work(game), 'reviewed.json')
    reviewed = read(rpath) if os.path.exists(rpath) else {}
    approved, rejected = set(reviewed.get('approved', [])), set(reviewed.get('rejected', []))
    chunks, ents, held, seen = [], [], [], set()
    pages_file = os.path.join(work(game), 'raw', 'pages.jsonl')
    pages = [json.loads(ln) for ln in open(pages_file, encoding='utf-8').read().splitlines() if ln] if os.path.exists(pages_file) else []

    def admit(hash_, text, title, section, url, put):
        if hash_ in rejected:
            return
        why = flags(text + ' ' + title, ok_hosts)
        if why and hash_ not in approved:
            held.append({'hash': hash_, 'why': why, 'title': title, 'section': section, 'url': url, 'text': text[:600]})
        else:
            put()
    allc = []
    for p in pages:
        text = drop_lines(html_text(p['html']) if 'html' in p else plain(p['text']), drops)
        for sec, t in chunks_of(p['title'], sections(text, skip)):
            allc.append(make(p['title'], sec, t, p['url'], p['kind'], p['fetched'], p['revid']))
        if p['kind'] in ekinds:
            body, names = entity_of(p['title'], text, eskip, aliases, start)
            if len(body.split()) >= 3:
                h = hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]
                admit(h, body, p['title'], 'entry', p['url'], lambda p=p, body=body, names=names, h=h: ents.append(
                    {'name': p['title'], 'kind': p['kind'], 'aliases': names, 'text': body, 'url': p['url'], 'fetched': p['fetched'], 'rev': p['revid'], 'hash': h}))
    for s in doc['sources']:
        if s.get('kind') == 'user':
            allc += list(user_chunks(s))
    for c in allc:
        if c['hash'] in seen:
            continue
        seen.add(c['hash'])
        admit(c['hash'], c['text'], c['title'], c['section'], c['url'], lambda c=c: chunks.append(c))
    for name, rows in (('chunks.jsonl', chunks), ('entities.jsonl', ents)):
        with open(os.path.join(work(game), name), 'w', encoding='utf-8') as f:
            f.write('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows))
    write(os.path.join(work(game), 'quarantine.json'), held)
    return {'pages': len(pages), 'chunks': len(chunks), 'entities': len(ents), 'held': len(held)}


if __name__ == '__main__':
    n = run(sys.argv[1])
    print(f"{n['pages']} pages -> {n['chunks']} chunks, {n['entities']} entries; {n['held']} held back for review" + (' (see quarantine.json)' if n['held'] else ''))
