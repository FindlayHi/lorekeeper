"""Start and check a game's sources.json.
  python tools/lore/sources.py init "Dead by Daylight" --host deadbydaylight.wiki.gg
  python tools/lore/sources.py check "Dead by Daylight"
sources.json says what a pack is built from; nothing outside it can get in. Fill in each source's seeds, license and
terms by hand, after reading the site's terms of use."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

if __name__ == '__main__':
    cmd, game = sys.argv[1], sys.argv[2]
    path = os.path.join(work(game), 'sources.json')
    if cmd == 'init':
        host = sys.argv[sys.argv.index('--host') + 1]
        if os.path.exists(path):
            sys.exit(f'{path} exists')
        write(path, {'game': game, 'steamAppId': 0, 'sources': [{
            'host': host, 'license': 'CC BY-SA 3.0', 'terms': 'TODO: read the site terms on <date>; they say <what> about copying text',
            'seeds': [{'category': 'TODO', 'kind': 'mechanic', 'limit': 300}, {'pages': ['TODO'], 'kind': 'item'}],
            'skipSections': ['Gallery', 'References', 'See also', 'External links', 'Navigation', 'Videos']}]})
        print('wrote', path, '- fill in the TODOs (tools/cart/wiki_probe.py', host, 'lists categories)')
    else:
        bad = problems(read(path))
        print('\n'.join(bad) or 'ok')
        sys.exit(1 if bad else 0)
