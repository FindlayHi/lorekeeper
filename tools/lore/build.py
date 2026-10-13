"""chunks.jsonl -> the pack: docs/lore/<slug>.zip, and the pointer the game's cart needs.
  python tools/lore/build.py "Dead by Daylight" [--version N] [--build <steam build or news id>] [--trust official|community|local] [--apply]
--apply writes the pointer into the game's entry in assets/cartridges.json and docs/cartridges.json (the cart must exist:
see the lorekeeper-cart skill). The zip is byte-for-byte the same for the same chunks, so its hash only moves when the lore does."""
import hashlib, io, os, sys, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import rag


def manifest(game, doc, chunks, version, build, trust, ents=()):
    by = {}
    for c in chunks:
        host = c['url'].split('/')[2] if c['url'].startswith('https://') else 'local'
        by.setdefault(host, set()).add(c['title'])
    out = []
    for s in doc['sources']:
        host = s.get('host') or 'local'
        out.append({'id': host, 'host': host, 'kind': s.get('kind', 'wiki'), 'license': s['license'], 'terms': s.get('terms', ''),
                    'pages': len(by.get(host, ())), 'fetchedAt': max([c['fetched'] for c in chunks if host in c['url'] or host == 'local'] or [''])})
    return {'schema': 1, 'game': game, 'version': version, 'trust': trust, 'builtAt': time.strftime('%Y-%m-%d'), 'steamAppId': doc.get('steamAppId', 0),
            'builtForBuild': build, 'embed': None, 'sources': out, 'chunks': len(chunks), 'entities': len(ents)}


def zipped(man, chunks, ents=()):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        files = [('lore.json', json.dumps(man, indent=1, ensure_ascii=False)),
                 ('chunks.jsonl', '\n'.join(json.dumps(c, ensure_ascii=False, sort_keys=True) for c in chunks))]
        if ents:
            files.append(('entities.jsonl', '\n'.join(json.dumps(e, ensure_ascii=False, sort_keys=True) for e in ents)))
        for name, data in files:
            z.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data.encode('utf-8'))   # fixed timestamp: same lore, same hash
    return buf.getvalue()


def apply(game, ptr):
    for path in ('assets/cartridges.json', 'docs/cartridges.json'):
        carts = read(path)
        key = next((k for k in carts['games'] if k.lower() == game.lower()), None)
        if not key:
            sys.exit(f'no cart for {game!r} in {path}: build its cart first (lorekeeper-cart skill)')
        carts['games'][key]['lore'] = ptr
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(carts, f, indent=1, ensure_ascii=False)
            f.write('\n')


if __name__ == '__main__':
    game = sys.argv[1]
    arg = lambda n, d: sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d
    doc = sources(game)
    trust = arg('--trust', 'official')
    chunks = [json.loads(ln) for ln in open(os.path.join(work(game), 'chunks.jsonl'), encoding='utf-8').read().splitlines() if ln]
    epath = os.path.join(work(game), 'entities.jsonl')
    ents = [json.loads(ln) for ln in open(epath, encoding='utf-8').read().splitlines() if ln] if os.path.exists(epath) else []
    ok = hosts(doc)
    stray = [c for c in chunks + ents if not (c['url'].startswith('local:') or c['url'].split('/')[2] in ok)]
    if stray:
        sys.exit(f"{len(stray)} chunks come from hosts not in sources.json, e.g. {stray[0]['url']}: run clean.py again")
    out = pack_path(game) if trust != 'local' else os.path.join(work(game), slug(game) + '.local.zip')   # a player's pack stays out of the site folder
    prev = rag.load(open(out, 'rb').read()) if os.path.exists(out) else None
    version = int(arg('--version', 0)) or (prev and int(prev.get('version', 0)) + 1) or 1
    data = zipped(manifest(game, doc, chunks, version, arg('--build', ''), trust, ents), chunks, ents)
    pack = rag.load(data)
    if not pack:
        sys.exit('the pack fails rag.load: the app would refuse it')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'wb') as f:
        f.write(data)
    ptr = {'file': f'lore/{slug(game)}.zip', 'sha256': hashlib.sha256(data).hexdigest(), 'version': version, 'builtForBuild': arg('--build', '')}
    print(f"{out}: {len(pack['chunks'])} chunks, {len(pack['entities'])} entries, {len(data) / 1e6:.2f} MB\ncart pointer: " + json.dumps(ptr))
    if '--apply' in sys.argv and trust != 'local':
        apply(game, ptr)
        print('written to assets/cartridges.json and docs/cartridges.json')
