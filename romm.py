"""RomM (https://romm.app): your self-hosted retro library tells Lorekeeper which game you're playing, its walkthroughs answer
"where do I go", and your progress notes are kept on the game in RomM too.

Connect: tray → Connect RomM… → approve the code in RomM (device pairing; no password typed here). The token lives in
Windows Credential Manager (Lorekeeper/romm). Scopes: roms.read, roms.user.write (notes), me.read."""
import json, re, threading, time, urllib.error, urllib.parse, urllib.request
import brain, config

SCOPES = ['roms.read', 'roms.user.write', 'me.read']
NOTE_TITLE = 'Lorekeeper'
EMULATORS = re.compile(r'\\(retroarch|dolphin|duckstation|pcsx2(?:-qt)?|ppsspp\w*|rpcs3|cemu|ryujinx|yuzu|suyu|citra\w*|lime3ds|azahar|melonds|'
                       r'mgba|mesen\w*|snes9x\w*|bsnes|higan|ares|mednafen|flycast|redream|xemu|xenia\w*|mame\w*|fceux|nestopia|'
                       r'project64|simple64|desmume|visualboyadvance\w*|vba\w*|epsxe|bizhawk|emuhawk|dosbox\w*|scummvm|pico-8|xroar|'
                       r'vita3k|shadps4|eden|citron|sudachi|torzu)(?:[-_.][\w.-]*)?\.exe$', re.I)   # duckstation-qt-x64-ReleaseLTCG.exe too
_cache, _lock = {}, threading.Lock()


# settings: the address in config.json, the token in Credential Manager

def url():
    return (config.load().get('rommUrl') or '').rstrip('/')


def token():
    try:
        import keyring
        return keyring.get_password('Lorekeeper', 'romm') or ''
    except Exception:
        return ''


def connected():
    return bool(url() and token())


def forget():
    try:
        import keyring
        keyring.delete_password('Lorekeeper', 'romm')
    except Exception:
        pass


def _same_server(old, new):
    """Is a redirect still the RomM it started at? The same origin, or the same host moving from http to https
    (a proxy in front of RomM does that)."""
    o, n = urllib.parse.urlsplit(old), urllib.parse.urlsplit(new)
    return brain.origin(old) == brain.origin(new) or bool(
        o.hostname and o.hostname == n.hostname and (o.scheme, n.scheme) == ('http', 'https'))


class _TokenStaysHome(urllib.request.HTTPRedirectHandler):
    """A redirect to another server goes without the token: urllib would carry the Authorization header along."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and not _same_server(req.full_url, newurl):
            for h in [h for h in new.headers if h.lower() == 'authorization']:
                del new.headers[h]
        return new


_open = urllib.request.build_opener(_TokenStaysHome).open


def _http(method, path, body=None, auth=True, base=None, timeout=6):
    req = urllib.request.Request((base or url()) + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'Lorekeeper',
                                          **({'Authorization': 'Bearer ' + token()} if auth else {})})
    with _open(req, timeout=timeout) as r:
        data = r.read()
        return json.loads(data) if data and 'json' in r.headers.get('Content-Type', '') else data.decode('utf-8', 'replace')


def api(path, **q):
    q = {k: v for k, v in q.items() if v is not None}
    return _http('GET', path + ('?' + urllib.parse.urlencode(q, doseq=True) if q else ''))


# pairing

def approve_link(base, r):
    """The page to approve the code on, opened in the browser. The server names its path, but only a path on itself:
    "@evil.example/x" stuck on the address would open another site, so anything else gets RomM's usual page."""
    path = r.get('verification_path_complete')
    link = base + path if isinstance(path, str) and re.fullmatch(r'/[^\s\\]*', path) and not path.startswith('//') else ''
    if link and brain.origin(link) == brain.origin(base):
        return link
    return base + '/pair/device?user_code=' + urllib.parse.quote(str(r['user_code']), safe='')


def pair(base, on_code, on_done):
    """Device pairing in the background: on_code(user_code, approve_url) at once, then on_done(username or None, error)."""
    base = base.strip().rstrip('/')
    if not re.match(r'https?://', base):
        base = 'http://' + base

    def run():
        try:
            import platform
            r = _http('POST', '/api/auth/device/init', {'client_device_identifier': 'lorekeeper-' + platform.node().lower(),
                                                        'name': f'Lorekeeper on {platform.node()}', 'client': 'Lorekeeper',
                                                        'platform': 'Windows', 'client_version': '1.0', 'requested_scopes': SCOPES},
                      auth=False, base=base)
        except Exception as e:
            return on_done(None, f"Couldn't reach RomM at {base}: {e}")
        on_code(r['user_code'], approve_link(base, r))
        end = time.time() + r.get('expires_in', 600)
        while time.time() < end:
            time.sleep(r.get('interval', 5))
            try:
                t = _http('POST', '/api/auth/device/token', {'device_code': r['device_code']}, auth=False, base=base)
            except urllib.error.HTTPError as e:
                if e.code in (400, 401, 403, 428):   # still waiting for the approval (or declined: it then expires)
                    detail = e.read().decode('utf-8', 'replace')
                    if 'denied' in detail.lower():
                        return on_done(None, 'The request was declined in RomM.')
                    continue
                return on_done(None, f'RomM said {e.code}.')
            except Exception:
                continue
            if t.get('access_token'):
                import keyring
                keyring.set_password('Lorekeeper', 'romm', t['access_token'])
                cfg = config.load()
                cfg['rommUrl'] = base
                config.save(cfg)
                try:
                    me = api('/api/users/me').get('username', '')
                except Exception:
                    me = ''
                return on_done(me or 'you', '')
        on_done(None, 'The code expired before it was approved. Try again.')
    threading.Thread(target=run, daemon=True).start()


# which game

def clean_title(title):
    """Game-name candidates from an emulator window title: 'RetroArch Snes9x 1.62 || Super Metroid (USA)' -> ['Super Metroid']."""
    out = []
    for part in re.split(r'\s*(?:\|\||\||—|–| - |::)\s*', title):
        part = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', part).strip(' .-')   # (USA) [!] (GMSE01)
        part = re.sub(r'\b(?:FPS|VPS|speed)\s*[:=]?\s*[\d.%]+.*$', '', part, flags=re.I).strip()
        if re.fullmatch(r'[\d.\s]+(?:fps|vps|%|ms)?', part, re.I):   # "60 FPS", "100%"
            continue
        if len(part) < 3 or re.search(r'\b(retroarch|dolphin|duckstation|pcsx2|ppsspp|rpcs3|cemu|ryujinx|yuzu|citra|melonds|mgba|mesen|snes9x|'
                                      r'bsnes|flycast|xemu|mame|fceux|project64|desmume|bizhawk|emuhawk|dosbox|scummvm|v\d|\d+\.\d+|'
                                      r'jit\w*|vulkan|opengl|direct3d|d3d1\d|hle|lle|interpreter|paused|running)\b', part, re.I):
            continue
        out.append(part)
    return out


def _game(rom):
    plat = rom.get('platform_display_name') or rom.get('platform_custom_name') or rom.get('platform_slug') or ''
    return {'name': rom.get('name') or rom.get('fs_name_no_tags') or '?', 'id': str(rom['id']), 'source': 'romm', 'dir': '', 'platform': plat}


def last_played(within_hours=8):
    """The game RomM says you're playing now, or played most recently today -> game dict or None."""
    r = api('/api/roms', order_by='last_played', order_dir='desc', last_played='true', limit=3)
    for rom in r.get('items', r) if isinstance(r, dict) else r:
        ru = rom.get('rom_user') or {}
        if ru.get('now_playing'):
            return _game(rom)
        lp = ru.get('last_played')
        if lp:
            try:
                from datetime import datetime, timezone
                t = datetime.fromisoformat(lp.replace('Z', '+00:00'))
                if (datetime.now(timezone.utc) - (t if t.tzinfo else t.replace(tzinfo=timezone.utc))).total_seconds() < within_hours * 3600:
                    return _game(rom)
            except ValueError:
                pass
    return None


def find(name):
    """The RomM game best matching a name -> game dict or None."""
    r = api('/api/roms', search_term=name, limit=5)
    items = r.get('items', r) if isinstance(r, dict) else r
    if not items:
        return None
    key = lambda s: re.sub(r'[^a-z0-9]', '', (s or '').lower())
    exact = [x for x in items if key(x.get('name')) == key(name) or key(x.get('fs_name_no_tags')) == key(name)]
    return _game((exact or items)[0])


BROWSERS = re.compile(r'\\(chrome|msedge|firefox|brave|opera|vivaldi)\.exe$', re.I)
# A tab whose page is named RomM: the whole title, or RomM at either end of it ("Super Metroid | RomM - Google Chrome").
# Spelled as RomM spells itself, and not just anywhere: "how to install romm - YouTube" is not the web player.
PLAYER = re.compile(r'(?:^|[|·•—–-]\s)RomM(?=$|:|\s[|·•—–-])')


def player(exe, title):
    """Is this window the RomM web player: a browser on a RomM page?"""
    return bool(BROWSERS.search(exe or '') and PLAYER.search(title or ''))


def current(exe, title):
    """For an emulator or the RomM web player in front: the game, from RomM -> dict or None. Cached a minute per window."""
    if not (EMULATORS.search(exe or '') or player(exe, title)) or not connected():   # the cheap check first: this runs every 2 s
        return None
    k = (exe, title)
    with _lock:
        hit = _cache.get(k)
        if hit and time.time() - hit[0] < 60:
            return hit[1]
    g = None
    try:
        if EMULATORS.search(exe or ''):
            for cand in clean_title(title or ''):
                g = find(cand)
                if g:
                    break
        g = g or last_played()
    except Exception as e:
        print('romm:', e)
    with _lock:
        _cache[k] = (time.time(), g)
    return g


# walkthroughs and notes

def walkthroughs(game, most=3):
    """[(file name, text)] of the game's RomM walkthroughs (GameFAQs imports and uploads are plain text)."""
    rom = api(f"/api/roms/{game['id']}")
    out = []
    for f in rom.get('files') or []:
        if f.get('category') == 'walkthrough' and len(out) < most:
            try:
                text = _http('GET', f"/api/roms/{game['id']}/files/content/{urllib.parse.quote(f['file_name'])}", timeout=10)
                out.append((f['file_name'], text if isinstance(text, str) else json.dumps(text)))
            except Exception as e:
                print('romm walkthrough:', e)
    return out


def notes(game):
    """The player's own RomM notes on this game (not Lorekeeper's), as text for the prompt."""
    try:
        items = api(f"/api/roms/{game['id']}/notes")
    except Exception:
        return ''
    items = items.get('items', items) if isinstance(items, dict) else items
    return '\n'.join(f"{n.get('title') or 'Note'}: {n.get('content', '').strip()}" for n in items or []
                     if n.get('title') != NOTE_TITLE and n.get('content'))[:2000]


def save_notes(game, text):
    """Keep Lorekeeper's progress notes on the game in RomM, as one note titled "Lorekeeper"."""
    try:
        items = api(f"/api/roms/{game['id']}/notes")
        items = items.get('items', items) if isinstance(items, dict) else items
        mine = next((n for n in items or [] if n.get('title') == NOTE_TITLE), None)
        body = {'title': NOTE_TITLE, 'content': text, 'is_public': False, 'tags': ['lorekeeper']}
        if mine:
            _http('PUT', f"/api/roms/{game['id']}/notes/{mine['id']}", body)
        else:
            _http('POST', f"/api/roms/{game['id']}/notes", body)
    except Exception as e:
        print('romm notes:', e)


_walk = {}   # rom id -> [(name, text)], once per session


def context(game, question):
    """For a RomM game: the parts of its RomM walkthroughs that match the question, and the player's own notes on it."""
    if not game or game.get('source') != 'romm' or not connected():
        return ''
    import lookup
    out = []
    try:
        if game['id'] not in _walk:
            _walk[game['id']] = walkthroughs(game)
        for name, text in _walk[game['id']][:2]:
            out.append(f'Source: walkthrough "{name}" from the player\'s RomM\n' + lookup.relevant(text, question, 4000))
    except Exception as e:
        print('romm walkthroughs:', e)
    mine = notes(game)
    if mine:
        out.append("The player's own notes on this game in RomM:\n" + mine)
    return '\n\n'.join(out)
