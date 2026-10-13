"""The gate before a pack ships: every check must pass, and the result is written to lore/<slug>/AUDIT.md for the PR.
  python tools/lore/audit.py "Dead by Daylight"
Checks: sources.json is complete (hosts the app can read, license, terms); nothing is waiting in quarantine; no chunk
outside the allowlist or still looking like instructions (unless a person approved that exact text); the app's own loader
accepts the pack; the cart's pointer is this exact file in both cartridges.json copies; the questions meet the bar."""
import hashlib, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import clean, eval_lore, rag

MIN_QUESTIONS, MIN_NONE, MIN_RECALL, MAX_MB = 30, 5, 0.9, 20


def audit(game):
    rows, doc = [], read(os.path.join(work(game), 'sources.json'))

    def check(name, ok, detail=''):
        rows.append((name, bool(ok), detail))
        return ok
    bad = problems(doc)
    check('sources.json complete', not bad, '; '.join(bad))
    path = pack_path(game)
    if not check('pack exists', os.path.exists(path), path):
        return rows, None
    data = open(path, 'rb').read()
    pack = rag.load(data)
    if not check('the app accepts the pack (rag.load)', pack):
        return rows, None
    ok_hosts = hosts(doc)
    check('size', len(data) <= MAX_MB * 1e6, f'{len(data) / 1e6:.2f} MB (limit {MAX_MB})')
    qpath = os.path.join(work(game), 'quarantine.json')
    held = read(qpath) if os.path.exists(qpath) else None
    check('nothing waiting in quarantine', held == [], 'run clean.py' if held is None else f'{len(held)} chunk(s): read them, then list their hash under approved or rejected in reviewed.json')
    rpath = os.path.join(work(game), 'reviewed.json')
    approved = set(read(rpath).get('approved', [])) if os.path.exists(rpath) else set()
    stray = [c['url'] for c in pack['chunks'] + pack['entities'] if not (c['url'].startswith('local:') or c['url'].split('/')[2] in ok_hosts)]
    check('every chunk is from a listed source', not stray, f'{len(stray)}, e.g. {stray[:1]}')
    sus = [(c.get('title', c.get('name')), clean.flags(c['text'] + ' ' + c.get('title', c.get('name', '')), ok_hosts)) for c in pack['chunks'] + pack['entities']
           if clean.flags(c['text'] + ' ' + c.get('title', c.get('name', '')), ok_hosts) and hashlib.sha256(c['text'].encode('utf-8')).hexdigest()[:16] not in approved]
    check('no unapproved chunk looks like instructions', not sus, f'{len(sus)}, e.g. {sus[:1]}')
    lic = [s for s in doc['sources'] if not s.get('license')]
    check('every source has a license', not lic)
    nc = [s['host'] for s in doc['sources'] if re.search(r'(?i)\bNC\b', s.get('license', ''))]
    if nc:
        rows.append(('non-commercial licence (info)', True, f"{', '.join(nc)}: the text may be used only while Lorekeeper stays non-commercial, with attribution and the same licence"))
    ptr_ok, carts = True, []
    for p in ('assets/cartridges.json', 'docs/cartridges.json'):
        g = {k.lower(): v for k, v in read(p)['games'].items()}.get(game.lower(), {})
        carts.append(g.get('lore'))
    want = hashlib.sha256(data).hexdigest()
    check('cart points at this pack in both cartridges.json copies', all(c and c.get('sha256') == want for c in carts),
          'run build.py --apply' if not all(carts) else 'hash differs: run build.py --apply')
    qpath = os.path.join(work(game), 'questions.json')
    if check('questions.json exists', os.path.exists(qpath)):
        r = eval_lore.run(game)
        check(f'at least {MIN_QUESTIONS} questions and {MIN_NONE} that the pack should not answer', r['asked'] >= MIN_QUESTIONS and r['nones'] >= MIN_NONE,
              f"{r['asked']} questions, {r['nones']} 'none'")
        check(f'recall >= {MIN_RECALL}', r['recall'] >= MIN_RECALL, f"{r['recall']:.2f}")
        check('no false confidence on unanswerable questions', not r['false_hits'], f"{r['false_hits']} of {r['nones']}")
        rows.append(('answered from the pack (info)', True, f"{r['used']:.0%} of the answerable questions; the rest go to the live wiki"))
        return rows, (pack, r)
    return rows, (pack, None)


if __name__ == '__main__':
    game = sys.argv[1]
    rows, extra = audit(game)
    ok = all(r[1] for r in rows)
    lines = [f'# Lore audit: {game}', '', f'{time.strftime("%Y-%m-%d")}. **{"PASS" if ok else "FAIL"}**', '', '| check | result | detail |', '|---|---|---|']
    lines += [f"| {n} | {'ok' if g else 'FAIL'} | {d} |" for n, g, d in rows]
    if extra:
        pack, r = extra
        by = {}
        for c in pack['chunks']:
            by.setdefault(c['url'].split('/')[2] if c['url'].startswith('https') else 'local', []).append(c)
        lines += ['', '## Sources', '', '| host | license | chunks | pages |', '|---|---|---|---|']
        for s in read(os.path.join(work(game), 'sources.json'))['sources']:
            h = s.get('host') or 'local'
            lines.append(f"| {h} | {s['license']} | {len(by.get(h, []))} | {len({c['title'] for c in by.get(h, [])})} |")
        lines += ['', f"Terms read: " + '; '.join(f"{s.get('host', 'local')}: {s.get('terms', '')}" for s in read(os.path.join(work(game), 'sources.json'))['sources'])]
        lines += ['', f"Pack: version {pack.get('version', '?')}, built for game build {pack['build'] or 'unknown'}, trust {pack['trust']}, {len(pack['chunks'])} chunks."]
        if r:
            lines += ['', '## Questions', ''] + [f"- {'ok' if x['ok'] else 'FAIL'}: {x['q']} {x['note']}" for x in r['results']]
    with open(os.path.join(work(game), 'AUDIT.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    for n, g, d in rows:
        print('ok  ' if g else 'FAIL', n, d if not g or 'info' in n else '')
    print('PASS' if ok else 'FAIL', '->', os.path.join(work(game), 'AUDIT.md'))
    sys.exit(0 if ok else 1)
