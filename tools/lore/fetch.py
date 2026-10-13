"""Download the pages a game's sources.json names -> lore/<slug>/raw/pages.jsonl (rendered HTML, revision id, time).
  python tools/lore/fetch.py "Dead by Daylight" [--max 2000] [--pause 1.0]
Reads the public article pages (/wiki/<Title>) and category listings only, never the API, because wikis such as
wiki.gg disallow api.php for crawlers in robots.txt. Every URL is checked against the site's robots.txt first and
goes through the app's lookup.check_url. One request at a time, with a pause: wiki.gg restricts fast crawlers."""
import html, os, sys, time, urllib.error, urllib.parse, urllib.request, urllib.robotparser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

pause = 1.0
_robots = {}


def robots(host):
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            lookup.check_url(f'https://{host}/robots.txt')
            rp.parse(lookup._opener.open(urllib.request.Request(f'https://{host}/robots.txt', headers={'User-Agent': UA}), timeout=20)
                     .read().decode('utf-8', 'replace').splitlines())
        except Exception:
            rp.parse([])   # no robots.txt to obey
        _robots[host] = rp
    return _robots[host]


def get(host, path):
    """One page of the wiki, if robots.txt allows it."""
    if not robots(host).can_fetch(UA, path):
        raise PermissionError(f"{host}'s robots.txt disallows {path}")
    url = f'https://{host}{path}'
    lookup.check_url(url)
    time.sleep(pause)
    return lookup._opener.open(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=30).read(5_000_000).decode('utf-8', 'replace')


def quote(title):
    return urllib.parse.quote(title.replace(' ', '_'), safe=":/()_,.-~'!*")


def titles(host, seed, most):
    """The page titles a seed names (a category's article listing, pages of 200)."""
    most = min(most, seed.get('limit', most))
    if seed.get('pages'):
        return list(seed['pages'])[:most]
    out, path = [], f"/wiki/Category:{quote(seed['category'])}"
    while path and len(out) < most:
        page = get(host, path)
        box = page[page.find('id="mw-pages"'):] if 'id="mw-pages"' in page else ''
        box = box[:box.find('printfooter')] if 'printfooter' in box else box
        out += [html.unescape(t) for t in re.findall(r'<li><a href="/wiki/[^"]+" title="([^"]+)"', box)]
        nxt = re.search(r'<a href="(/wiki/Category:[^"]*[?&;]pagefrom=[^"]+)"[^>]*>next page', box)
        path = html.unescape(nxt[1]) if nxt else ''
    return out[:most]


def page(host, title):
    """A title -> {title, revid, html}, or None when the wiki has no such page."""
    try:
        h = get(host, '/wiki/' + quote(title))
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
                ts = [t for t in titles(s['host'], sd, most) if (s['host'], t) not in seen]
            except PermissionError as e:
                sys.exit(str(e) + ': ask the site, or drop it from sources.json')
            print(s['host'], sd.get('category') or 'pages', len(ts), 'pages', flush=True)
            for n, t in enumerate(ts):
                p = page(s['host'], t)
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
