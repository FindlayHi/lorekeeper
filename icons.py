"""Things on screen named only by an icon (Dead by Daylight perks, add-ons, items): a model can't name them from the
art, so they're found and matched against the game's wiki icons here, offline, and named in the question.
  carts:   cartridges, per game: which wiki and which icon sets, the shape each sits in on screen, and where on the
           HUD it sits. Kept in cartridges.json on the site (fetched at startup), so a game is added without a release;
           assets/cartridges.json is the fallback.
  regions: where a cart says a set sits (a box from a screen corner, in screen heights, and the slot's size: the
           HUD, the lobby), every icon's art is slid over that box: the art matches over any background (sand).
           Status rings also need a ring round them; add-ons need their item.
  anywhere: for a set with no region, a coloured patch of that shape with an empty edge ->
           a slot (diamonds: turned 45 deg into squares; summed-area tables). A slot dimmed on cooldown is placed from
           its cluster of four.
  match:   the slot's light-grey art against every icon of that shape, normalised correlation (right ~0.9+, wrong <0.8).
Icons come from the wiki once per set (perks ~13 s) and are kept as one small file each."""
import hashlib, io, json, os, re, threading, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image, ImageFilter
import lookup, rag

URL = 'https://lorekeeper-cgv.pages.dev/cartridges.json'
BUNDLED = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'cartridges.json')
SHAPES = {'diamond': (1.0, 1.1, 1.2, 1.3),   # icon scales: the icon's square is a little bigger than the diamond it sits in
          'square': (0.8, 0.9, 1.0, 1.1, 1.2),
          'ring': (0.5, 0.58, 0.66)}           # status effects: the art sits well inside its coloured ring
EDGE = {'diamond': (0.7, 0.15), 'square': (0.5, 0.08)}   # fill just inside the edge, at least; just outside, at most.
# Squares: an item's dark fill is patchy and its art reaches the edge, but nothing sits right outside it.
HOST = re.compile(r'[a-z0-9-]+\.wiki\.gg|[a-z0-9-]+\.fandom\.com')   # a cart can only point at a game wiki
PREFIX = re.compile(r'[A-Za-z0-9]+_?')
R = 48                     # matching resolution
BLUR = ImageFilter.GaussianBlur(1.2)   # line art is thin: a pixel off would miss it
SURE = {'diamond': 0.88, 'square': 0.85, 'ring': 0.85}   # a match is this good (wrong ones < 0.8); squares also need a square beside them
CLEAR = 0.93               # status art this good needs no ring round it (junk over sand is < 0.88)
MARGIN = 0.05              # and better than the next icon (Dark Sense vs Kindred), unless that one looks alike: then both
SIZES = {'diamond': (1.0,), 'square': (0.96, 1.02, 1.08), 'ring': (0.95, 1.05)}   # a square's patchy fill makes it look a little small
WIDE = 1280                # finding works at this width
PAGES = 6                  # wiki pages fetched for what was read


# cartridges

def valid(doc):
    """A cartridges document -> {game name lowercased: cart}, keeping only well-formed entries (it comes off the network)."""
    out = {}
    for name, r in (doc.get('games') or {}).items() if isinstance(doc, dict) else ():
        try:
            sets = [{'kind': s['kind'], 'prefix': s['prefix'], 'shape': s['shape'], 'regions': _regions(s.get('regions', [])),
                     'needs': s['needs'] if re.fullmatch(r'[a-z -]{2,30}', str(s.get('needs', ''))) else ''}
                    for s in r['sets'] if s['shape'] in SHAPES and PREFIX.fullmatch(s['prefix']) and re.fullmatch(r'[a-z -]{2,30}', s['kind'])]
            if HOST.fullmatch(r['host']) and sets:
                out[name.lower()] = {'host': r['host'], 'sets': sets, 'asks': [a for a in r.get('asks', []) if re.fullmatch(r'[a-z -]{2,30}', a)],
                                   'lore': rag.pointer(r.get('lore'))}
        except (KeyError, TypeError):
            pass
    return out


def _tints(ts):
    """A region's tints: a slot whose fill is in this hue range (degrees, may wrap past 360) is that other kind
    (Dead by Daylight, the row left of the perks: a perk's art on teal is a buff it gives you, on red a debuff).
    A region with tints only holds tinted slots. Not the equipped perks: red there is a perk's own timer."""
    try:
        return [{'hue': [float(t['hue'][0]) % 360, float(t['hue'][1]) % 360], 'kind': t['kind']} for t in ts
                if re.fullmatch(r'[a-z -]{2,40}', t['kind'])]
    except (KeyError, TypeError, ValueError, IndexError):
        return []


ANCHORS = ('tl', 'tr', 'bl', 'br')


def _regions(gs):
    """A set's regions: {'anchor': corner, 'x': [near, far], 'y': [near, far], 'size': slot width}, all in screen
    heights from that corner (the HUD scales with the height and keeps to its corners on a wide screen), and the
    screen it's on ('hud', 'lobby'...: one is up at a time), its tints and how sure a match must be, if set."""
    out = []
    for g in gs[:8] if isinstance(gs, list) else ():
        try:
            x, y, d = [float(v) for v in g['x']], [float(v) for v in g['y']], float(g['size'])
            screen = g.get('screen', 'hud')
            if (g['anchor'] in ANCHORS and len(x) == len(y) == 2 and 0 <= x[0] < x[1] <= 4 and 0 <= y[0] < y[1] <= 1 and 0.01 <= d <= 0.3
                    and isinstance(screen, str) and re.fullmatch(r'[a-z]{2,20}', screen)):
                sure = min(0.99, max(0.8, float(g.get('sure', 0))))   # stricter than the shape's own, when art there is easily faked
                out.append({'anchor': g['anchor'], 'x': x, 'y': y, 'size': d, 'screen': screen, 'tints': _tints(g.get('tints', [])), 'sure': sure})
        except (KeyError, TypeError, ValueError):
            pass
    return out


def _read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return valid(json.load(f))
    except (OSError, ValueError):
        return {}


_carts, _lock = None, threading.Lock()


def carts(folder):
    """The cached cartridges from the site, else the ones shipped with the app."""
    global _carts
    if _carts is None:
        _carts = _read(os.path.join(folder, 'cartridges.json')) or _read(BUNDLED)
    return _carts


def refresh(folder):
    """Fetch the site's cartridges into the cache (startup, background). Returns the games it knows."""
    global _carts
    doc = json.loads(lookup.get(URL, timeout=10))
    got = valid(doc)
    if got:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, 'cartridges.json'), 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=1)
        _carts = got
    return got


def cart(game, folder):
    return carts(folder).get((game or {}).get('name', '').lower())


def asks(question, game, folder):
    """Is the question about what these icons show (perks, add-ons...), screen words or not?"""
    r = cart(game, folder)
    words = [s['kind'] for s in r['sets']] + r['asks'] if r else []
    return bool(words) and bool(re.search(r'\b(?:' + '|'.join(re.escape(w.rstrip('s')) for w in words) + r')s?\b', question, re.I))


# icons: from the wiki, once per set

def _slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def _bank_path(folder, game, r, s):
    tag = hashlib.sha1(f"{r['host']}|{s['prefix']}".encode()).hexdigest()[:8]   # a changed cart: a new download
    return os.path.join(folder, 'icons', _slug(game['name']), f"{_slug(s['kind'])}-{tag}.npz")


def _api(host, **q):
    return json.loads(lookup.get(f'https://{host}/api.php?' + urllib.parse.urlencode({'format': 'json', **q}), timeout=15))


def _name(file, pages, prefix='IconPerks'):
    """IconPerks_hexNoOneEscapesDeath.png + the pages using it -> ('Hex: No One Escapes Death', True: a page's title)."""
    stem = re.sub(r'(?i)^' + re.escape(prefix.rstrip('_')) + r'[ _]?|\.png$', '', file)
    key = re.sub(r'[^a-z0-9]', '', stem.lower())
    for p in pages:
        if re.sub(r'[^a-z0-9]', '', p.lower()) == key:
            return p, True
    words = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', re.split('[ _]', stem)[0]).strip()
    return ' '.join(w[:1].upper() + w[1:] for w in words.split()), False


def _art(data):
    """Icon PNG bytes -> its art on black, 96 x 96 uint8."""
    im = Image.open(io.BytesIO(data)).convert('LA').resize((96, 96), Image.LANCZOS)
    l, a = (np.asarray(c, dtype=np.float32) for c in im.split())
    return (l * a / 255).astype(np.uint8)


def download(game, folder, r, s):
    """Every icon of one set from the game's wiki -> its bank file. Slow (hundreds of images): off the main thread."""
    files, cont = {}, {}
    while True:
        d = _api(r['host'], action='query', generator='allimages', gaiprefix=s['prefix'], gailimit='500',
                 prop='imageinfo|fileusage', iiprop='url', funamespace='0', fulimit='500', **cont)
        for p in d.get('query', {}).get('pages', {}).values():
            f = files.setdefault(p['title'].split(':', 1)[1], {'pages': []})
            if p.get('imageinfo'):
                f['url'] = p['imageinfo'][0]['url']
            f['pages'] += [u['title'] for u in p.get('fileusage', [])]
        if 'continue' not in d:
            break
        cont = d['continue']
    want = sorted(k for k, v in files.items() if v.get('url', '').startswith(f"https://{r['host']}/"))

    def fetch(k):
        try:
            lookup.check_url(files[k]['url'])
            req = urllib.request.Request(files[k]['url'], headers={'User-Agent': lookup.UA})
            return _art(lookup._opener.open(req, timeout=15).read())
        except Exception:
            return None   # one bad file doesn't lose the set
    with ThreadPoolExecutor(6) as ex:
        arts = list(ex.map(fetch, want))
    keep = [i for i, a in enumerate(arts) if a is not None]
    if not keep:
        raise ValueError(f"no {s['kind']} icons on {r['host']}")
    path = _bank_path(folder, game, r, s)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    named = [_name(want[i], files[want[i]]['pages'], s['prefix']) for i in keep]
    np.savez_compressed(path + '.tmp.npz', art=np.stack([arts[i] for i in keep]),
                        names=np.array([n for n, _ in named]), paged=np.array([p for _, p in named]))
    os.replace(path + '.tmp.npz', path)
    return path


class Bank:
    """One set's icon art at matching size, normalised, for every scale: (icons, scales, pixels)."""
    def __init__(self, art, names, shape='diamond', kind='', paged=None, regions=(), needs=''):
        self.names, self.shape, self.kind = [str(n) for n in names], shape, kind
        self.regions = _regions(list(regions))   # where on screen the cart says it sits; none: anywhere
        self.needs = needs              # a kind that must be seen too (add-ons: the item they're on)
        self.paged = list(paged) if paged is not None else [False] * len(self.names)   # name is a wiki page's title
        stack = []
        for a in art:
            im = Image.fromarray(a)
            row = []
            for k in SHAPES[shape]:
                side = round(R * k)
                out = Image.new('L', (R, R))
                out.paste(im.resize((side, side), Image.LANCZOS), ((R - side) // 2, (R - side) // 2))
                row.append(np.asarray(out.filter(BLUR), dtype=np.float32)[MASKS[shape]])
            stack.append(row)
        self.v = _norm(np.stack(stack))
        k = len(SHAPES[shape]) // 2
        self.like = self.v[:, k] @ self.v[:, k].T   # icon vs icon: the wiki has some art twice under two names


_banks, _busy = {}, set()


def banks(game, folder):
    """The game's icon sets that are ready; the rest start downloading here, in the background."""
    r = cart(game, folder)
    out = []
    for s in r['sets'] if r else ():
        path = _bank_path(folder, game, r, s)
        with _lock:
            if path not in _banks and os.path.exists(path):
                try:
                    with np.load(path) as z:
                        _banks[path] = Bank(z['art'], z['names'], s['shape'], s['kind'], z['paged'] if 'paged' in z else None)
                except Exception as e:
                    print('icons:', path, e)
                    os.remove(path)
            if path in _banks:
                b = _banks[path]
                b.regions, b.needs = s.get('regions', []), s.get('needs', '')   # the cart may have changed
                out.append(b)
            elif path not in _busy:
                _busy.add(path)
                threading.Thread(target=_fetch_bg, args=(game, folder, r, s, path), daemon=True).start()
    return out


def _fetch_bg(game, folder, r, s, path):
    try:
        download(game, folder, r, s)
    except Exception as e:
        print('icons:', s['kind'], e)
    finally:
        with _lock:
            _busy.discard(path)


def prefetch(gs, folder):
    """At startup: the site's cartridges, then icons for the games installed here."""
    try:
        refresh(folder)
    except Exception as e:
        print('icons: cartridges:', e)
    for g in gs:
        banks(g, folder)


# finding the slots

def _mask(shape, n=R):
    y, x = np.mgrid[0:n, 0:n] + 0.5 - n / 2
    if shape == 'diamond':
        return (np.abs(x) + np.abs(y)) < 0.92 * n / 2
    if shape == 'ring':
        return (x * x + y * y) < (0.34 * n) ** 2   # inside the ring
    return (x * x + y * y) < (0.44 * n) ** 2   # square: the middle; its corners carry badges ("+", key prompts)


MASKS = {s: _mask(s) for s in SHAPES}


def _norm(v):
    v = v - v.mean(-1, keepdims=True)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-6)


def fill(img):
    """How coloured each pixel is, 0..1: a slot's rarity fill, lit or dimmed. Chroma, not saturation: dark noise has high S."""
    a = np.asarray(img, dtype=np.float32)
    hi, lo = a.max(2), a.min(2)
    return np.clip((hi - lo - 8) / 10, 0, 1) * (hi < 220) * ((hi - lo) * 255 > 70 * hi)


def _squares(a, ns, f, edge=EDGE['diamond']):
    """Squares of fill with an empty edge in the mask a -> [(score, x, y, n)] in units f times a's pixels."""
    ii = np.pad(a, ((1, 0), (1, 0))).cumsum(0).cumsum(1)

    def sums(n):   # sum over the n x n square at every top-left
        return ii[n:, n:] - ii[:-n, n:] - ii[n:, :-n] + ii[:-n, :-n]
    found = []
    for n in ns:
        b, g = max(2, n // 9), max(2, n // 8)
        N = n + 2 + 2 * g   # outside: 1 px gap, then a ring g wide
        outer = sums(N)
        h, w = outer.shape
        sq = sums(n)[g + 1:g + 1 + h, g + 1:g + 1 + w]
        core = sums(n - 2 * b)[g + 1 + b:g + 1 + b + h, g + 1 + b:g + 1 + b + w]
        band = (sq - core) / (n * n - (n - 2 * b) ** 2)   # just inside the edge: fill, the art doesn't reach it
        ys, xs = np.nonzero(band > edge[0])
        if not len(ys):
            continue
        gap = sums(n + 2)[g:g + h, g:g + w][ys, xs]
        ring = (outer[ys, xs] - gap) / (N * N - (n + 2) ** 2)   # just outside: not
        ok = ring < edge[1]
        s = band[ys, xs][ok] - ring[ok]
        found += [(v, (x + g + 1 + n / 2) * f, (y + g + 1 + n / 2) * f, n * f) for v, y, x in zip(s, ys[ok], xs[ok])]
    return found


def vivid(img):
    """Strongly coloured pixels, 0..1: a status ring (chroma ~150) stands out from sand or brick (~70) here."""
    a = np.asarray(img, dtype=np.float32)
    return np.clip((a.max(2) - a.min(2) - 95) / 20, 0, 1)


_kernels = {}


def _kernel(shape, lo, hi):
    """The FFT of a ring lo <= r < hi centred on (0, 0), for an image this shape, normalised."""
    key = (shape, lo, hi)
    if key not in _kernels:
        H, W = shape
        y, x = np.mgrid[0:H, 0:W]
        d = np.hypot(np.minimum(y, H - y), np.minimum(x, W - x))   # distance from the corner, wrapped
        k = ((d >= lo) & (d < hi)).astype(np.float32)
        _kernels[key] = np.fft.rfft2(k / k.sum()).astype(np.complex64)
    return _kernels[key]


def rings(img, most=12):
    """Vivid rings with nothing vivid just outside or inside (status effects) -> [(cx, cy, D)] in img pixels."""
    scale = WIDE / 2 / img.width   # half width: rings are bold, and the filters stay small (~30 MB, kept)
    small = img.convert('RGB').resize((WIDE // 2, round(img.height * scale)), Image.BOX)
    a = vivid(small)
    F = np.fft.rfft2(a).astype(np.complex64)
    found = []
    for r in range(5, 18):
        t = max(1.5, r * 0.22)
        band = np.fft.irfft2(F * _kernel(a.shape, r - t, r), s=a.shape)   # the ring
        out = np.fft.irfft2(F * _kernel(a.shape, r + 1, r + 1 + max(2, r * 0.3)), s=a.shape)
        inner = np.fft.irfft2(F * _kernel(a.shape, 0, max(1, r - t - 1.5)), s=a.shape)
        s = band - np.maximum(out, inner)
        ys, xs = np.nonzero((band > 0.55) & (out < 0.15) & (inner < 0.2))
        found += [(s[i, j], j, i, r) for i, j in zip(ys, xs)]
    found.sort(reverse=True)
    keep = []
    for s, cx, cy, r in found:
        if all(np.hypot(cx - kx, cy - ky) > r + kr for _, kx, ky, kr in keep):
            keep.append((s, cx, cy, r))
        if len(keep) >= most:
            break
    return [(cx / scale, cy / scale, 2 * r / scale) for _, cx, cy, r in keep]


def hue(img, slot, shape='diamond'):
    """The main hue of a slot's fill, in degrees, or None when it isn't coloured. Inside the shape only: a purple
    perk over red blood is purple."""
    cx, cy, D = slot
    c = img.crop((round(cx - D / 2), round(cy - D / 2), round(cx + D / 2), round(cy + D / 2))).convert('RGB').resize((R, R))
    m = (fill(c) > 0.5) & _mask(shape, R) & (np.asarray(c).min(2) < 150)   # not the light art
    if m.sum() < 10:
        return None
    hsv = np.asarray(c.convert('HSV'), dtype=np.float32)[m]
    ang = hsv[:, 0] / 255 * 2 * np.pi
    return float(np.degrees(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())) % 360)


def _ringed(img, slot):
    """Is there a coloured ring round this art (a status effect), not just colour everywhere (sand)? Chroma in a band
    at 0.38-0.54 of the width out from the middle against the art's ground inside and the screen outside."""
    cx, cy, D = slot
    c = np.asarray(img.crop((round(cx - D), round(cy - D), round(cx + D), round(cy + D))).convert('RGB').resize((96, 96)), dtype=np.float32)
    ch = c.max(2) - c.min(2)
    y, x = np.mgrid[0:96, 0:96] + 0.5 - 48
    d = np.hypot(x, y) / 48   # in widths: the crop is two wide

    def at(lo, hi):
        return ch[(d >= lo) & (d < hi)].mean()
    return max(at(0.38, 0.46), at(0.46, 0.54)) - max(at(0.30, 0.38), at(0.62, 0.75)) > 20


def _in(h, lo, hi):
    return lo <= h <= hi if lo <= hi else h >= lo or h <= hi


def slots(img, shape='diamond', most=16):
    """Patches of colour in this shape with a clear edge -> [(cx, cy, D)] in img pixels, D = the shape's width.
    Small ones at WIDE, big ones at half that (4x fewer pixels, same answer)."""
    if shape == 'ring':
        return rings(img)
    scale = WIDE / img.width
    small = img.convert('RGB').resize((WIDE, round(img.height * scale)))
    turn = shape == 'diamond'
    m = Image.fromarray((fill(small) * 255).astype(np.uint8))
    r = m.rotate(45, expand=True, resample=Image.BILINEAR) if turn else m
    a = np.asarray(r, dtype=np.float32) / 255
    half = np.asarray(r.resize((r.width // 2, r.height // 2), Image.BOX), dtype=np.float32) / 255
    found = _squares(a, range(14, 40), 1, EDGE[shape]) + _squares(half, range(20, 38), 2, EDGE[shape])
    found.sort(reverse=True)
    keep = []
    for s, x, y, n in found:
        if all(abs(x - kx) > (n + kn) * 0.4 or abs(y - ky) > (n + kn) * 0.4 for _, kx, ky, kn in keep):
            keep.append((s, x, y, n))
        if len(keep) >= most:
            break
    out = []
    if turn:
        c, t = np.array([r.width / 2, r.height / 2]), np.radians(45)
        rot = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])   # undo PIL's counter-clockwise turn
        for _, x, y, n in keep:
            ox, oy = rot @ (np.array([x, y]) - c) + [small.width / 2, small.height / 2]
            out.append((ox / scale, oy / scale, n * np.sqrt(2) / scale))
        return out + _complete(out)
    return [(x / scale, y / scale, n / scale) for _, x, y, n in keep]


def _complete(found):
    """Perks sit four to a cluster, in a diamond. A dimmed one (on cooldown) can hide from slots(): two neighbours
    that match place the other corners, and the icon match decides whether a perk is really there."""
    extra = []
    for i, (ax, ay, ad) in enumerate(found):
        for bx, by, bd in found[i + 1:]:
            dx, dy = bx - ax, by - ay
            if abs(ad - bd) > 0.12 * ad or not 0.4 * ad < abs(dx) < 1.0 * ad or abs(abs(dx) - abs(dy)) > 0.15 * ad:
                continue
            for sgn in (1, -1):   # the square on either side of the A-B edge
                px, py = -dy * sgn, dx * sgn
                for x, y in ((ax + px, ay + py), (bx + px, by + py)):
                    if all(abs(x - fx) > 0.3 * ad or abs(y - fy) > 0.3 * ad for fx, fy, _ in found + extra):
                        extra.append((x, y, (ad + bd) / 2))
    return extra


def _art_at(img, cx, cy, D, shape):
    h = D / 2
    c = img.crop((round(cx - h), round(cy - h), round(cx + h), round(cy + h))).convert('RGB').resize((R, R), Image.LANCZOS)
    c = Image.fromarray(np.asarray(c).min(2)).filter(BLUR)   # light grey art on a coloured fill: bright in every channel
    return np.asarray(c, dtype=np.float32)[MASKS[shape]]


def match(img, slot, bank):
    """(name, score, runner-up's score, runner-up's name, how alike their art is) for the icon in this slot,
    nudged a little for a loose fit. Of identical art under two names, the one that is a wiki page's title."""
    cx, cy, D = slot
    best = None
    for z in SIZES[bank.shape]:
        for dx in (-0.04, 0, 0.04):
            for dy in (-0.04, 0, 0.04):
                s = (bank.v @ _norm(_art_at(img, cx + dx * D, cy + dy * D, D * z, bank.shape))).max(1)
                if best is None or s.max() > best[0].max():
                    best = (s,)
    s = best[0]
    order = np.argsort(s)[::-1]
    i = order[0]
    twins = [i] + [j for j in order[1:8] if bank.like[i, j] > 0.97]   # the same art: the same thing, not a rival
    rest = [j for j in order[1:] if bank.like[i, j] <= 0.97][:1]
    name = bank.names[min(twins, key=lambda j: (not bank.paged[j], len(bank.names[j])))]
    if not rest:
        return name, float(s[i]), 0.0, '', 0.0
    j = rest[0]
    other = bank.names[min([j] + [k for k in order[:12] if bank.like[j, k] > 0.97], key=lambda k: (not bank.paged[k], len(bank.names[k])))]
    return name, float(s[i]), float(s[j]), other, float(bank.like[i, j])


def _judge(img, slot, bs, sure, tints=()):
    """The best icon for this slot across the banks of its shape, if it's a match -> (kind, name, score) or None.
    tints: the slot must be one of these colours, and is that kind."""
    got = [(b.kind,) + match(img, slot[:3], b) for b in bs if b.shape == slot[3]]
    if not got:
        return None
    kind, name, s, second, other, alike = max(got, key=lambda g: g[2])
    if slot[3] == 'ring' and s < CLEAR and not _ringed(img, slot[:3]):   # gold on sand: no ring to see, but the art is clear
        return None
    runner = max([second] + [g[2] for g in got if g[0] != kind])   # next best across the sets too
    if s < sure or (s - runner < MARGIN and not (runner == second and alike > 0.8)):
        return None
    if s - runner < MARGIN:
        name = f'{name} (or {other}: they look alike)'
    if not tints:
        return kind, name, s
    h = hue(img, slot[:3], slot[3])
    tinted = next((t['kind'] for t in tints if h is not None and _in(h, *t['hue'])), None)
    return (tinted, name, s) if tinted else None


# the HUD: where a cart says a set sits

STEP = 2      # matching pixels between tries: match() then nudges the best ones into place
LIKELY = 0.6  # a spot this good is worth judging
COARSE = {'diamond': 1.2, 'square': 1.1, 'ring': 0.58}   # the icon scale that fits the HUD's slots best
ZOOM = (0.92, 1.0, 1.08)   # slot sizes tried round the region's: the HUD scale setting, art drawn a little big


def _box(size, g):
    """A region (screen heights from its corner) -> (x0, y0, x1, y1) in pixels."""
    W, H = size
    (a, b), (c, d) = g['x'], g['y']
    x0, x1 = (W - b * H, W - a * H) if g['anchor'][1] == 'r' else (a * H, b * H)
    y0, y1 = (H - d * H, H - c * H) if g['anchor'][0] == 'b' else (c * H, d * H)
    return round(max(0, x0)), round(max(0, y0)), round(min(W, x1)), round(min(H, y1))


def hud(img, g, bank, most=8):
    """Every icon's art slid over this HUD region, at about the region's slot size -> the best spots [(cx, cy, D)].
    The art is light, so it matches over sand or pillars, where a slot's coloured edge is lost."""
    x0, y0, x1, y1 = _box(img.size, g)
    D = g['size'] * img.height
    v = bank.v[:, SHAPES[bank.shape].index(COARSE[bank.shape])]   # one icon scale here; match() tries them all
    found = []
    for z in ZOOM:
        f = R / (D * z)
        w, h = round((x1 - x0) * f), round((y1 - y0) * f)
        if w < R or h < R:
            continue
        c = img.crop((x0, y0, x1, y1)).convert('RGB').resize((w, h), Image.LANCZOS)
        a = np.asarray(Image.fromarray(np.asarray(c).min(2)).filter(BLUR), dtype=np.float32)
        win = sliding_window_view(a, (R, R))[::STEP, ::STEP]
        gy, gx = win.shape[:2]
        best = (_norm(win.reshape(gy * gx, R, R)[:, MASKS[bank.shape]]) @ v.T).max(1).reshape(gy, gx)
        around = sliding_window_view(np.pad(best, 2, constant_values=-1), (5, 5)).max((2, 3))
        ys, xs = np.nonzero(best >= around)   # peaks: one strong spot's neighbours don't crowd out the next slot
        for yy, xx in zip(ys, xs):
            found.append((float(best[yy, xx]), x0 + (xx * STEP + R / 2) / f, y0 + (yy * STEP + R / 2) / f, D * z))
    found.sort(reverse=True)
    keep = []
    for sc, cx, cy, d in found:
        if sc < LIKELY or len(keep) >= most:
            break
        if all(np.hypot(cx - kx, cy - ky) > 0.6 * d for kx, ky, _ in keep):
            keep.append((cx, cy, d))
    return keep


def find(img, bs):
    """What these icon banks see on this screen -> [{'kind', 'name', 'score', 'at': (cx, cy, D), 'shape'}], top to
    bottom. A set with HUD regions is looked for there; one without, anywhere on screen."""
    out = []

    def taken(slot):
        return any(abs(slot[0] - o['at'][0]) < slot[2] / 3 and abs(slot[1] - o['at'][1]) < slot[2] / 3 for o in out)

    def add(slot, j):
        out.append({'kind': j[0], 'name': j[1], 'score': round(j[2], 3), 'at': tuple(round(v) for v in slot[:3]), 'shape': slot[3]})
    screens = {}
    for b in bs:
        for g in b.regions:
            got = screens.setdefault(g['screen'], [])
            for slot in hud(img, g, b):
                j = _judge(img, slot + (b.shape,), [b], max(SURE[b.shape], g['sure']), g['tints'])
                if j and not any(abs(slot[0] - o['at'][0]) < slot[2] / 3 and abs(slot[1] - o['at'][1]) < slot[2] / 3 for o in got):
                    got.append({'kind': j[0], 'name': j[1], 'score': round(j[2], 3), 'at': tuple(round(v) for v in slot), 'shape': b.shape})
    best = max(screens.values(), key=len, default=[])   # one screen is up: the HUD or the lobby, and a few strays on the other
    twice = {(o['kind'], o['name']) for o in best if sum((p['kind'], p['name']) == (o['kind'], o['name']) for p in best) > 1}
    out += [o for o in best if (o['kind'], o['name']) not in twice]   # one of each in a loadout: a row of one icon is a texture
    needs, seen = {b.kind: b.needs for b in bs}, {o['kind'] for o in out} | {''}
    out = [o for o in out if needs.get(o['kind'], '') in seen]   # add-ons with no item: a menu's icons
    rest = [b for b in bs if not b.regions]
    for shape in dict.fromkeys(b.shape for b in rest):
        found = slots(img, shape)
        for slot in found:
            if taken(slot):
                continue
            if shape == 'square' and not any(o is not slot and 0.3 < o[2] / slot[2] < 3 and np.hypot(o[0] - slot[0], o[1] - slot[1]) < 2.5 * max(o[2], slot[2])
                                             for o in found):
                continue   # an item's add-ons sit beside it: a lone square is a sign, a wall, a status icon
            j = _judge(img, slot + (shape,), rest, SURE[shape])
            if j:
                add(slot + (shape,), j)
    return sorted(out, key=lambda p: (round(p['at'][1] * 2 / max(p['at'][2], 1)), p['at'][0]))


def text(img, game, folder, question=''):
    """For the question: what's on screen, read from its icons, and each thing's entry in the game's lore pack, else its wiki page;
    or why not, or ''."""
    r = cart(game, folder)
    if not r or img is None:
        return ''
    bs = banks(game, folder)
    if not bs:
        return 'Icons for this game are still downloading from its wiki, so nothing on screen could be read from them this time.'
    seen = find(img, bs)
    if not seen:
        return ''
    by = {}
    for p in seen:
        by.setdefault(p['kind'], [])
        if p['name'] not in by[p['kind']]:
            by[p['kind']].append(p['name'])
    names = [n for ns in by.values() for n in ns][:PAGES]
    with ThreadPoolExecutor(4) as ex:
        pages = list(ex.map(lambda n: (r['lore'] and rag.entry(game['name'], r['lore'], n)) or lookup.page(f"https://{r['host']}/wiki/" + urllib.parse.quote(n.replace(' ', '_')), question, 1200), names))
    return ('On screen, read from their icons (exact names; trust these over the screenshot): '
            + '; '.join(f"{k}: {', '.join(ns)}" for k, ns in by.items())
            + ''.join(f'\n\n{n} (wiki):\n{p}' for n, p in zip(names, pages) if p))
