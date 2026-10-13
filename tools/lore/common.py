"""Shared by the lore tools: where a game's work lives, its sources.json, and the wiki hosts a pack may be built from.
Run the tools from the repo root: python tools/lore/<tool>.py <game> ..."""
import json, os, re, sys
sys.path.insert(0, os.getcwd())
import lookup

UA = 'Lorekeeper-loremaker/0.1 (https://github.com/FindlayHi/lorekeeper)'
LICENSES = re.compile(r'CC[ -]BY(?:-SA|-NC|-NC-SA)?[ -]\d\.\d|CC0|public domain|permission: .{5,}|own: .{5,}', re.I)


def slug(game):
    return re.sub(r'[^a-z0-9]+', '-', game.lower()).strip('-')


def work(game):
    """lore/<slug>/: sources.json, questions.json, AUDIT.md (committed); raw/ and chunks.jsonl (not)."""
    return os.path.join('lore', slug(game))


def pack_path(game):
    return os.path.join('docs', 'lore', slug(game) + '.zip')


def wiki_ok(host):
    """Only wikis the app itself fetches from (lookup.APIS): the build cannot be pointed anywhere else."""
    return any(re.fullmatch(h, host) for h in lookup.APIS)


def read(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)


def problems(src):
    """sources.json -> what's wrong with it, as sentences. Empty when it can be built from."""
    out = []
    if not isinstance(src, dict) or not isinstance(src.get('sources'), list) or not src['sources']:
        return ['sources.json needs a "sources" list']
    for i, s in enumerate(src['sources']):
        n = f"source {i + 1} ({s.get('host') or s.get('folder') or '?'})"
        if s.get('kind') == 'user':
            if not os.path.isdir(s.get('folder', '')):
                out.append(f"{n}: folder {s.get('folder')!r} is not a directory")
            if not s.get('license', '').lower().startswith('own'):
                out.append(f"{n}: a player's own files are licensed 'own: <who wrote them>'")
            continue
        if not wiki_ok(s.get('host', '')):
            out.append(f"{n}: host must be a MediaWiki site the app can read (lookup.APIS: *.wiki.gg, *.fandom.com, ...)")
        if not LICENSES.fullmatch(s.get('license', '')):
            out.append(f"{n}: license missing or not recognised (e.g. 'CC BY-SA 3.0'; 'permission: <who, where>' if the site gave it)")
        if len(s.get('terms', '')) < 20 or s['terms'].startswith('TODO'):
            out.append(f"{n}: 'terms' must say when you read the site's terms and what they allow (one sentence)")
        if not s.get('seeds'):
            out.append(f"{n}: no seeds (what to take: {{'category': 'Perks', 'kind': 'mechanic'}} or {{'pages': [...], 'kind': 'item'}})")
        for sd in s.get('seeds', []):
            if not (sd.get('category') or sd.get('pages')) or 'TODO' in json.dumps(sd):
                out.append(f"{n}: a seed needs a real 'category' or 'pages'")
    return out


def sources(game):
    path = os.path.join(work(game), 'sources.json')
    if not os.path.exists(path):
        sys.exit(f'{path} not found: python tools/lore/sources.py init "{game}" --host <wiki host>')
    doc = read(path)
    bad = problems(doc)
    if bad:
        sys.exit('\n'.join(['sources.json:'] + ['  ' + b for b in bad]))
    return doc


def hosts(doc):
    return {s['host'] for s in doc['sources'] if s.get('host')}
