"""Is assets/cartridges.json right? Every set and region must survive icons.valid() (what the app keeps of a cart
fetched off the network), and docs/cartridges.json (what the site serves) must be the same file.
  python tools/cart/check.py            (from the repo root)"""
import json, os, sys
sys.path.insert(0, os.getcwd())
import icons

doc = json.load(open('assets/cartridges.json', encoding='utf-8'))
ok = json.load(open('docs/cartridges.json', encoding='utf-8')) == doc
if not ok:
    print('docs/cartridges.json differs from assets/cartridges.json: copy it over')
kept = icons.valid(doc)
for name, raw in doc.get('games', {}).items():
    got = kept.get(name.lower())
    if not got:
        print(f'{name}: dropped whole (host must be *.wiki.gg or *.fandom.com, and at least one good icon set or a lore pointer)'); ok = False
        continue
    kinds = {s['kind']: s for s in got['sets']}
    for s in raw.get('sets', []):
        k = s.get('kind')
        if k not in kinds:
            print(f'{name}: set {k!r} dropped (kind a-z, prefix like IconPerks_, shape diamond|square|ring)'); ok = False
        elif len(kinds[k]['regions']) != len(s.get('regions', [])):
            print(f'{name}: {k}: {len(s["regions"]) - len(kinds[k]["regions"])} region(s) dropped (anchor tl|tr|bl|br, '
                  'x/y as [near, far] in screen heights, size 0.01-0.3, screen a-z)'); ok = False
    print(f"{name}: {', '.join(f'{k} ({len(v['regions'])} regions)' for k, v in kinds.items()) or 'no icon sets'}"
          + (f", lore {got['lore']['file']}" if got['lore'] else ''))
print('ok' if ok else 'NOT ok')
sys.exit(0 if ok else 1)
