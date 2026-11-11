"""Which game is in front: the foreground exe matched against the games Steam, Epic, GOG, Battle.net, Xbox, EA and Ubisoft installed.

The index is [{name, id, source, dir}], cached in games.json and rebuilt when an exe matches nothing
(a game installed since). A pinned game (tray menu, or "I'm playing X") wins until the exe in front changes.
"""
import difflib, glob, json, os, re, sys, time
import config, romm, win

INDEX = os.path.join(config.DIR, 'games.json')
_missed = set()   # exes that matched nothing even after a rescan
PIN = os.path.join(config.DIR, 'pinned.json')
NOT_GAMES = re.compile(r'redistributable|runtime|steamvr|proton|dedicated server|soundtrack|\bsdk\b|benchmark|3dmark|wallpaper engine|^(battle\.net|ea app|ea desktop|origin|ubisoft connect|xbox|gaming services)$', re.I)
LAUNCHERS = re.compile(r'\\(steam|steamwebhelper|epicgameslauncher|galaxyclient|explorer|lorekeeper|python|pythonw|windowsterminal|chrome|msedge|firefox|discord|battle\.net|battle\.net launcher|eadesktop|eabackgroundservice|upc|ubisoftconnect|xboxpcapp|gamingservices|gamingservicesui)\.exe$', re.I)


def vdf(text):
    """Valve's KeyValues text (libraryfolders.vdf, appmanifest_*.acf) -> nested dicts."""
    root, stack, key = {}, [], None
    cur = root
    for tok in re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text):
        s, brace = tok
        if brace == '{':
            new = {}
            cur[key] = new
            stack.append(cur)
            cur, key = new, None
        elif brace == '}':
            cur = stack.pop() if stack else root
        elif key is None:
            key = s
        else:
            cur[key] = s.replace('\\\\', '\\')
            key = None
    return root


def _reg(root, path, name):
    try:
        import winreg
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except (OSError, ImportError):
        return ''


def steam_dir():
    if sys.platform == 'win32':
        import winreg
        d = _reg(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath')
        if d and os.path.isdir(d):
            return os.path.normpath(d)
    d = os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'Steam')
    return d if os.path.isdir(d) else ''


def steam_games(steam=None):
    steam = steam if steam is not None else steam_dir()
    if not steam:
        return []
    libs = {steam}
    try:
        with open(os.path.join(steam, 'steamapps', 'libraryfolders.vdf'), encoding='utf-8') as f:
            libs |= {v['path'] for v in vdf(f.read()).get('libraryfolders', {}).values() if isinstance(v, dict) and v.get('path')}
    except OSError:
        pass
    out = []
    for lib in {os.path.normcase(os.path.normpath(l)): l for l in sorted(libs)}.values():   # registry path is lower-case, the vdf's is not
        for acf in glob.glob(os.path.join(lib, 'steamapps', 'appmanifest_*.acf')):
            try:
                with open(acf, encoding='utf-8') as f:
                    a = vdf(f.read()).get('AppState', {})
            except OSError:
                continue
            if a.get('name') and a.get('installdir') and not NOT_GAMES.search(a['name']):
                out.append({'name': a['name'], 'id': a.get('appid', ''), 'source': 'steam',
                            'dir': os.path.join(lib, 'steamapps', 'common', a['installdir'])})
    return out


def epic_games(manifests=None):
    manifests = manifests or os.path.join(os.environ.get('ProgramData', r'C:\ProgramData'), 'Epic', 'EpicGamesLauncher', 'Data', 'Manifests')
    out = []
    for item in glob.glob(os.path.join(manifests, '*.item')):
        try:
            with open(item, encoding='utf-8') as f:
                m = json.load(f)
        except (OSError, ValueError):
            continue
        if m.get('DisplayName') and m.get('InstallLocation') and 'games' in [c.lower() for c in m.get('AppCategories', ['games'])]:
            out.append({'name': m['DisplayName'], 'id': m.get('AppName', ''), 'source': 'epic', 'dir': m['InstallLocation']})
    return out


def gog_games():
    if sys.platform != 'win32':
        return []
    import winreg
    out = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\GOG.com\Games') as k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                gid = winreg.EnumKey(k, i)
                sub = r'SOFTWARE\WOW6432Node\GOG.com\Games' + '\\' + gid
                name, path = _reg(winreg.HKEY_LOCAL_MACHINE, sub, 'gameName'), _reg(winreg.HKEY_LOCAL_MACHINE, sub, 'path')
                if name and path:
                    out.append({'name': name, 'id': gid, 'source': 'gog', 'dir': path})
    except OSError:
        pass
    return out


def _hklm_subkeys(path):
    """{subkey: {value: data}} under HKLM\\path, merged from the 32- and 64-bit registry views (installers write to either)."""
    if sys.platform != 'win32':
        return {}
    import winreg
    out = {}
    for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | view) as k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    sub = winreg.EnumKey(k, i)
                    with winreg.OpenKey(k, sub) as s:
                        vals = dict(winreg.EnumValue(s, j)[:2] for j in range(winreg.QueryInfoKey(s)[1]))
                    out.setdefault(sub, vals)
        except OSError:
            pass
    return out


def _entry(name, gid, source, d):
    """One index row, or None for a launcher, runtime or nameless/dirless entry (NOT_GAMES applies to every source)."""
    name, d = (name or '').strip(), (d or '').strip().strip('"')
    if not name or not d or NOT_GAMES.search(name):
        return None
    return {'name': name, 'id': gid, 'source': source, 'dir': os.path.normpath(d)}


UNINSTALL = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'


def battle_net_games(reg=_hklm_subkeys):
    """Blizzard games: each has an Uninstall key whose UninstallString runs Battle.net's own uninstaller (--uid=<product>)."""
    out = []
    for sub, v in reg(UNINSTALL).items():
        uid = re.search(r'--uid=(\S+)', str(v.get('UninstallString', '')))
        if uid and 'blizzard uninstaller' in v['UninstallString'].lower() and uid.group(1) != 'battle.net':
            out.append(_entry(v.get('DisplayName') or sub, uid.group(1), 'battlenet', v.get('InstallLocation')))
    return [g for g in out if g]


def gaming_roots(drives=None):
    """Folders Xbox installs games into: the name each drive's .GamingRoot records (RGBX, a version, then UTF-16 text), else XboxGames."""
    if drives is None:
        drives = [f'{c}:\\' for c in 'CDEFGHIJKLMNOPQRSTUVWXYZ' if _fixed(f'{c}:\\')]
    roots = []
    for d in drives:
        name = 'XboxGames'
        try:
            with open(os.path.join(d, '.GamingRoot'), 'rb') as f:
                raw = f.read()
            if raw[:4] == b'RGBX' and raw[8:].decode('utf-16-le', 'ignore').strip('\0 '):
                name = raw[8:].decode('utf-16-le', 'ignore').strip('\0 ')
        except OSError:
            pass
        if os.path.isdir(os.path.join(d, name)):
            roots.append(os.path.join(d, name))
    return roots


def _fixed(root):
    """True for a local hard drive (not optical, network or removable), so we never wake a card reader."""
    try:
        import ctypes
        return ctypes.windll.kernel32.GetDriveTypeW(root) == 3
    except (AttributeError, OSError):
        return False


def xbox_games(drives=None):
    """Game Pass / Xbox app installs: <root>\\<Game>\\Content holds the exe; folders without Content (GameSave, leftovers) are skipped."""
    out = []
    for root in gaming_roots(drives):
        for g in sorted(glob.glob(os.path.join(root, '*'))):
            content = os.path.join(g, 'Content')
            if os.path.isdir(content):
                out.append(_entry(os.path.basename(g), os.path.basename(g), 'xbox', content))
    return [g for g in out if g]


def ea_games(reg=_hklm_subkeys):
    """EA app installs: SOFTWARE\\EA Games\\<game> (or Electronic Arts) with an 'Install Dir'; the key name is the title unless DisplayName says better."""
    out = []
    for path in (r'SOFTWARE\EA Games', r'SOFTWARE\Electronic Arts'):
        for sub, v in reg(path).items():
            out.append(_entry(v.get('DisplayName') or sub, sub, 'ea', v.get('Install Dir')))
    return [g for g in out if g]


def ubisoft_games(reg=_hklm_subkeys):
    """Ubisoft Connect installs: Ubisoft\\Launcher\\Installs\\<id> has InstallDir only, so the title is the Uninstall key 'Uplay Install <id>' else the folder name."""
    names = {sub: v.get('DisplayName') for sub, v in reg(UNINSTALL).items()}
    out = []
    for gid, v in reg(r'SOFTWARE\Ubisoft\Launcher\Installs').items():
        d = v.get('InstallDir', '')
        out.append(_entry(names.get(f'Uplay Install {gid}') or os.path.basename(os.path.normpath(d.replace('/', os.sep))), gid, 'ubisoft', d))
    return [g for g in out if g]


def dedupe(games):
    """One row per game: where Steam and the EA app both list it, keep the copy whose folder exists, then the earlier source."""
    best = {}
    for i, g in enumerate(games):
        k = key(g['name'])
        rank = (not os.path.isdir(g['dir']), i)
        if k not in best or rank < best[k][0]:
            best[k] = (rank, g)
    return [g for _, g in sorted(best.values(), key=lambda b: b[0][1])]


def _sources():
    return [('steam', steam_games), ('epic', epic_games), ('gog', gog_games), ('battlenet', battle_net_games),
            ('xbox', xbox_games), ('ea', ea_games), ('ubisoft', ubisoft_games)]


def build():
    games = []
    for name, src in _sources():
        try:
            games += [g for g in src() if not NOT_GAMES.search(g['name'])]
        except Exception as e:   # a launcher we cannot read must not blind us to the rest
            print(f'games: {name} scan failed: {e}')
    games = dedupe(games)
    os.makedirs(config.DIR, exist_ok=True)
    with open(INDEX, 'w', encoding='utf-8') as f:
        json.dump(games, f, indent=1)
    return games


def index():
    try:
        with open(INDEX, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return build()


def _under(path, d):
    path, d = os.path.normcase(os.path.normpath(path)), os.path.normcase(os.path.normpath(d))
    return path.startswith(d + os.sep)


def key(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def match(exe, title, games):
    """The game that exe belongs to (deepest install folder wins), else one whose name is in the window title."""
    if exe:
        hits = [g for g in games if _under(exe, g['dir'])]
        if hits:
            return max(hits, key=lambda g: len(g['dir']))
    t = key(title)
    named = [g for g in games if len(key(g['name'])) >= 4 and key(g['name']) in t]
    return max(named, key=lambda g: len(g['name'])) if named else None


def find(words, games):
    """The installed game the user named ("I'm playing elden ring"), else a made-up entry with their words."""
    k = key(words)
    if not k:
        return None
    exact = [g for g in games if key(g['name']) == k]
    part = [g for g in games if k in key(g['name']) or key(g['name']) in k]
    close = difflib.get_close_matches(k, [key(g['name']) for g in games], n=1, cutoff=0.75)
    hit = (exact or part or [g for g in games if close and key(g['name']) == close[0]] or [None])[0]
    return hit or {'name': ' '.join(w.capitalize() if w.islower() else w for w in words.split()), 'id': '', 'source': 'named', 'dir': ''}


def pin(game, exe=''):
    """Stick to this game until the exe in front changes (exe='': until unpinned)."""
    os.makedirs(config.DIR, exist_ok=True)
    with open(PIN, 'w', encoding='utf-8') as f:
        json.dump({'game': game, 'exe': exe, 'at': time.time()}, f)


def unpin():
    try:
        os.remove(PIN)
    except OSError:
        pass


def pinned():
    try:
        with open(PIN, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def current(exe=None, title=None):
    """(game or None, exe in front). Pinned game first, then the index, rebuilt once if a non-launcher exe misses."""
    if exe is None:
        exe, title = win.front()
    p = pinned()
    if p and (not p['exe'] or not exe or LAUNCHERS.search(exe) or os.path.normcase(p['exe']) == os.path.normcase(exe)):
        return p['game'], exe   # alt-tabbed to Discord or a browser: still that game
    if p:
        unpin()   # a different game is in front now
    games = index()
    g = match(exe, title or '', games)
    if not g and exe and not LAUNCHERS.search(exe) and not romm.EMULATORS.search(exe) and exe not in _missed:
        _missed.add(exe)   # a game installed since the index was built? rescan once per app, not every few seconds
        g = match(exe, title or '', build())
    if not g:
        g = romm.current(exe, title)   # an emulator or the RomM web player: RomM knows the game
    if not g and exe and romm.EMULATORS.search(exe):   # no RomM: the emulator's window title names the game
        names = romm.clean_title(title or '')
        if names:
            g = {'name': names[0], 'id': '', 'source': 'emulator', 'dir': ''}
    return g, exe
