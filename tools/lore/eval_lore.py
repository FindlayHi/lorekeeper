"""Does the pack answer real questions? Does it bring back the right page and facts, and stay quiet on ones it can't answer?
  python tools/lore/eval_lore.py "Dead by Daylight" [--min 0.9]      (from the repo root)
lore/<slug>/questions.json:
  {"q": "what does Lithe do", "page": "Lithe", "must": ["rushed vault", "+50 % haste"]}
  {"q": "who is the best streamer", "none": true}
It runs what the app runs (rag.retrieve + rag.render), so the text checked is the text the model would be given.
  page  the page (or list of pages) the answer lives on: its entry or one of its chunks must come back. Preferred: a page name
        can't be matched by accident the way a common word can.
  must  phrases (any case) the returned text must contain. Use ones that belong to this answer: a number with its unit and
        subject ("+50 % haste"), a name, an exact value. "haste" or "aura" alone appears on dozens of pages.
  none  nothing in the pack answers this: the app must fall back to the live wiki.
Write questions the way a player says them aloud, from the game and not from the pack, and don't tune chunking on the ones
you gate with. Gate: recall >= --min, no false hits on the 'none' questions."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import rag


def run(game, pack=None):
    pack = pack or rag.load(open(pack_path(game), 'rb').read())
    qs = read(os.path.join(work(game), 'questions.json'))
    res = []
    for q in qs:
        t = time.time()
        got = rag.retrieve(pack, q['q'])
        text = rag.render(got).lower()
        ms = (time.time() - t) * 1000
        if q.get('none'):
            res.append({'q': q['q'], 'none': True, 'ok': not got['sure'], 'ms': ms, 'note': 'would answer from the pack' if got['sure'] else ''})
            continue
        pages = {e['name'].lower() for e in got['entities']} | {c['title'].lower() for _, c in got['hits']}
        want = [q['page']] if isinstance(q.get('page'), str) else list(q.get('page', []))
        miss = [f'page {p}' for p in want if p.lower() not in pages] + [m for m in q.get('must', []) if m.lower() not in text]
        res.append({'q': q['q'], 'none': False, 'ok': not miss and got['sure'], 'sure': got['sure'], 'ms': ms,
                    'note': ('missing: ' + ', '.join(miss)) if miss else ('' if got['sure'] else 'found, but not sure enough to be used'),
                    'top': (got['entities'][0]['name'] if got['entities'] else got['hits'][0][1]['title'] if got['hits'] else '')})
    ans = [r for r in res if not r['none']]
    non = [r for r in res if r['none']]
    return {'results': res, 'asked': len(ans), 'recall': sum(r['ok'] for r in ans) / max(1, len(ans)),
            'used': sum(r['sure'] for r in ans) / max(1, len(ans)), 'nones': len(non), 'false_hits': sum(not r['ok'] for r in non),
            'ms': sum(r['ms'] for r in res) / max(1, len(res))}


if __name__ == '__main__':
    game = sys.argv[1]
    arg = lambda n, d: sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d
    r = run(game)
    for x in r['results']:
        print('ok  ' if x['ok'] else 'FAIL', x['q'], '|', x.get('top', ''), x['note'])
    print(f"recall {r['recall']:.2f} of {r['asked']}; answered from the pack {r['used']:.2f}; "
          f"false hits {r['false_hits']}/{r['nones']}; {r['ms']:.1f} ms a question")
    sys.exit(0 if r['recall'] >= float(arg('--min', 0.9)) and not r['false_hits'] else 1)
