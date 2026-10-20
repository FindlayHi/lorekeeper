"""Download the pages a game's sources.json names -> lore/<slug>/raw/pages.jsonl (rendered HTML, revision id, time).
  python tools/lore/fetch.py "Dead by Daylight" [--max 2000] [--pause 1.0]
By default it reads the public article pages (/wiki/<Title>) and category listings only, never the API, because wikis such as
wiki.gg disallow api.php for crawlers in robots.txt. A source with "via": "api" reads the same rendered pages through api.php
instead (action=parse): Fandom's robots.txt allows api.php?action= and puts its article pages behind a check scripts can't pass.
Every URL is checked against the site's robots.txt first and goes through the app's lookup.check_url. One request at a time,
with a pause: wikis restrict fast crawlers.
A seed names pages by "category", "pages", or "linkedFrom" (the articles a list page links to, api only), and "in" keeps only
those also in one of the categories listed (Fandom's Borderlands wiki files every game's bosses under one "Bosses")."""
import html, os, sys, time, urllib.error, urllib.parse, urllib.request, urllib.robotparser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

pause = 1.0
_robots = {}


def robots(host, by_hand=None):
    """The site's robots.txt. One that can't be read stops the fetch (a 404 means there is none), unless sources.json has
    "robots": the rules a person read in a browser and copied, with when ({"read": "<date, where>", "lines": [...]})."""
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            lookup.check_url(f'https://{host}/robots.txt')
            rp.parse(lookup._opener.open(urllib.request.Request(f'https://{host}/robots.txt', headers={'User-Agent': UA}), timeout=20)
                     .read().decode('utf-8', 'replace').splitlines())
        except Exception as e:
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                rp.parse([])   # no robots.txt to obey
            elif by_hand and by_hand.get('lines'):
                print(f"{host}'s robots.txt can't be read by a script ({e}); using the rules read by hand {by_hand.get('read', '')}", flush=True)
                rp.parse(by_hand['lines'])
            else:
                raise PermissionError(f"{host}'s robots.txt can't be read ({e}): read it in a browser and copy its rules into sources.json "
                                      '"robots": {"read": "<date, where>", "lines": [...]}')
        _robots[host] = rp
    return _robots[host]


def get(host, path, by_hand=None):
    """One page of the wiki, if robots.txt allows it."""
    if not robots(host, by_hand).can_fetch(UA, path):
        raise PermissionError(f"{host}'s robots.txt disallows {path}")
    url = f'https://{host}{path}'
    lookup.check_url(url)
    time.sleep(pause)
    return lookup._opener.open(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=30).read(5_000_000).decode('utf-8', 'replace')


def api(src, **q):
    """One api.php call (action first: robots.txt rules name 'api.php?action=')."""
    path = '/api.php?' + urllib.parse.urlencode({'action': q.pop('action'), **q, 'format': 'json'})
    return json.loads(get(src['host'], path, src.get('robots')))


def quote(title):
    return urllib.parse.quote(title.replace(' ', '_'), safe=":/()_,.-~'!*")


_cats = {}


def members(src, category):
    """Every article in a category (title order)."""
    key = (src['host'], category)
    if key not in _cats:
        out, host = [], src['host']
        if src.get('via') == 'api':
            q = {'action': 'query', 'list': 'categorymembers', 'cmtitle': 'Category:' + category, 'cmnamespace': '0', 'cmlimit': '500'}
            while True:
                d = api(src, **q)
                out += [m['title'] for m in d.get('query', {}).get('categorymembers', [])]
                if 'continue' not in d:
                    break
                q.update(d['continue'])
        else:
            path = f"/wiki/Category:{quote(category)}"
            while path:
                page = get(host, path, src.get('robots'))
                box = page[page.find('id="mw-pages"'):] if 'id="mw-pages"' in page else ''
                box = box[:box.find('printfooter')] if 'printfooter' in box else box
                out += [html.unescape(t) for t in re.findall(r'<li><a href="/wiki/[^"]+" title="([^"]+)"', box)]
                nxt = re.search(r'<a href="(/wiki/Category:[^"]*[?&;]pagefrom=[^"]+)"[^>]*>next page', box)
                path = html.unescape(nxt[1]) if nxt else ''
        _cats[key] = out
    return _cats[key]


def linked(src, title):
    """The articles a page links to (a list page: 'List of shields in Borderlands 3')."""
    if src.get('via') != 'api':
        raise SystemExit('"linkedFrom" needs a source with "via": "api"')
    out, q = [], {'action': 'query', 'prop': 'links', 'titles': title, 'plnamespace': '0', 'pllimit': '500', 'redirects': '1'}
    while True:
        d = api(src, **q)
        for p in d.get('query', {}).get('pages', {}).values():
            out += [x['title'] for x in p.get('links', [])]
        if 'continue' not in d:
            return out
        q.update(d['continue'])


def titles(src, seed, most):
    """The page titles a seed names."""
    most = min(most, seed.get('limit', most))
    if seed.get('pages'):
        out = list(seed['pages'])
    elif seed.get('linkedFrom'):
        out = linked(src, seed['linkedFrom'])
    else:
        out = members(src, seed['category'])
    if seed.get('in'):
        keep = {t for c in seed['in'] for t in members(src, c)}
        out = [t for t in out if t in keep]
    return list(dict.fromkeys(out))[:most]


def page(src, title):
    """A title -> {title, revid, html}, or None when the wiki has no such page."""
    if src.get('via') == 'api':
        p = api(src, action='parse', page=title, prop='text|revid', redirects='1', disabletoc='1').get('parse')
        if not p or not p.get('revid') or 'mw-parser-output' not in p['text']['*']:
            return None
        return {'title': p['title'], 'revid': int(p['revid']), 'html': p['text']['*']}
    try:
        h = get(src['host'], '/wiki/' + quote(title), src.get('robots'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    rev = re.search(r'"wgCurRevisionId":(\d+)', h)
    real = re.search(r'"wgTitle":"((?:[^"\\]|\\.)*)"', h)
    if not rev or 'mw-parser-output' not in h or int(rev[1]) == 0:
        return None
    return {'title': json.loads('"' + real[1] + '"') if real else title, 'revid': int(rev[1]), 'html': h}


if __name__ == '__main__':
    game = sys.argv[1]
    arg = lambda n, d: sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d
    most, pause = int(arg('--max', 2000)), float(arg('--pause', 1.0))
    doc = sources(game)
    raw, now = os.path.join(work(game), 'raw', 'pages.jsonl'), time.strftime('%Y-%m-%d')
    os.makedirs(os.path.dirname(raw), exist_ok=True)
    out = [json.loads(ln) for ln in open(raw, encoding='utf-8').read().splitlines() if ln] if os.path.exists(raw) and '--fresh' not in sys.argv else []
    seen = {(p['host'], p['title']) for p in out}   # a stopped crawl carries on from what it has (--fresh starts over)
    if out:
        print(len(out), 'pages already fetched; continuing')
    elif os.path.exists(raw):
        os.remove(raw)
    for s in doc['sources']:
        if s.get('kind') == 'user':
            continue
        for sd in s['seeds']:
            try:
                ts = [t for t in titles(s, sd, most) if (s['host'], t) not in seen]
            except PermissionError as e:
                sys.exit(str(e) + ': ask the site, or drop it from sources.json')
            print(s['host'], sd.get('category') or sd.get('linkedFrom') or 'pages', len(ts), 'pages', flush=True)
            for n, t in enumerate(ts):
                p = page(s, t)
                if not p or (s['host'], p['title']) in seen:
                    continue
                seen.add((s['host'], p['title']))
                out.append({**p, 'host': s['host'], 'url': f"https://{s['host']}/wiki/{quote(p['title'])}", 'kind': sd.get('kind', 'lore'), 'fetched': now})
                with open(raw, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(out[-1], ensure_ascii=False) + '\n')
                if n % 25 == 24:
                    print('  ', n + 1, '/', len(ts), flush=True)
            if len(out) >= most:
                break
    print(len(out), 'pages ->', raw)
