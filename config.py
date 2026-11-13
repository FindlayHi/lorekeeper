"""Where Lorekeeper keeps its files, and its settings (config.json, edited by hand or from the tray)."""
import json, os, shutil, tempfile, time

HOME = os.path.expanduser('~')
DIR = os.environ.get('LOREKEEPER_DIR') or os.path.join(os.environ.get('APPDATA') or os.path.join(HOME, '.config'), 'Lorekeeper')   # tests point it elsewhere
FILE = os.path.join(DIR, 'config.json')
BAD = os.path.join(DIR, 'config.bad.json')   # a config.json that couldn't be read, kept for the player to fix or copy from
MODELS = os.path.join(os.environ.get('LOCALAPPDATA') or DIR, 'Lorekeeper', 'models')   # big files: not roamed

DEFAULTS = {
    'hotkey': 'ctrl+alt+space',  # hold to talk, let go to ask; any key or mouse4/mouse5 (tray → Hotkey)
    'hotkeyEverywhere': False,   # False: the hotkey only acts while a game is in front, and passes through everywhere else,
                                 # so another app that uses the same shortcut (another voice assistant, say) still gets it there
    'listen': False,             # listen mode: no key to hold, start with "Lorekeeper, …"
    'listenKey': 'ctrl+alt+l',   # turns listen mode on and off
    'followUpSeconds': 8,        # after an answer, this long to ask a follow-up without the wake word
    'ai': 'claude',              # who answers: claude (Claude Code on your Claude plan) or openai (any OpenAI-compatible server; tray → AI)
    'model': 'haiku',            # Claude Code: quick answers; "in detail" asks use deepModel
    'deepModel': 'sonnet',
    'aiUrl': '',                 # openai: the server, e.g. http://localhost:11434/v1 (Ollama), http://localhost:1234/v1 (LM Studio)
    'aiModel': '',               # openai: the model for quick answers (tray → AI lists the server's)
    'aiDeepModel': '',           # openai: for "in detail" and gear math; '' = aiModel
    'mic': '',                   # a microphone by name (tray → Microphone); '' = Windows' default input
    'whisper': 'base.en',        # base.en is quick on CPU; small.en hears names better
    'whisperDevice': 'cpu',      # cuda with an NVIDIA card and the CUDA libraries
    'voice': 'kokoro',           # kokoro: neural, on this PC; edge: Microsoft online; sapi: Windows' own (robotic)
    'kokoroVoice': 'af_nicole:0.5,bf_isabella:0.5',   # tray → Voice; or any kokoro voice or blend "a:0.5,b:0.5"
    'edgeVoice': 'en-GB-SoniaNeural',
    'pitch': '-8Hz',             # edge only: lower = throatier
    'rate': 0,                   # speed, -10..10
    'box': True,                 # show the question and answer in a small box too
    'boxSeconds': 12,
    'font': '',                  # a font family for the whole app, tray and answer box ('' = the bundled pixel font; tray → Reset font)
    'fontSize': 0,               # its size in pixels (0 = the usual size for that font)
    'boxFont': '',               # the answer box's own font; '' = follow 'font'
    'boxFontSize': 0,            # the answer box's own size; 0 = follow 'fontSize'
    'uiScale': 0,                # size of the box and tray as a multiple (1.5 = 150%); 0 = follow the monitor's Windows scale
    'boxWhileSpeaking': False,   # True: the box stays up while Lorekeeper is still talking, so you can read along; boxSeconds start after
    'spoilers': False,           # True: answers ignore your progress notes
    'screen': True,              # "what is this item" sends a screenshot
    'lore': True,                # answer from the game's lore pack first (if its cartridge has one), the live wiki after
    'checkUpdates': True,        # once a day, ask GitHub whether there's a newer release (tray → Update when there is)
    'rommUrl': '',               # set by tray → RomM → Connect RomM… (the token is in Windows Credential Manager)
    'telemetry': None,           # anonymous install/daily-use counts (telemetry.py): None = not asked yet, asked once on first run
    'posthogKey': 'phc_CpjGEfKDMnBjL6dxg6Dwb8cBDUJAKRdj64ivGH3by5fB',   # PostHog project API key: write-only, safe to publish
    'posthogHost': 'https://us.i.posthog.com',
    'clipKeys': 'ctrl+f10',              # "clip it" presses this: Steam → Game Recording → "Save the last 30 seconds" (set it to Ctrl+F10), or Game Bar's win+alt+g
}


broken = ''   # why config.json couldn't be read this run, if it couldn't: main() tells the player once
BROKEN = "Your settings file couldn't be read, so defaults are in use. The old one is kept as config.bad.json."


_read = {}   # path -> ((mtime, size), parsed)


def read_json(path):
    """A JSON file, parsed again only when the file has changed (its time or size): the game watcher asks for the
    settings, the games index and the pinned game every couple of seconds. Raises what open and json.load raise.
    The caller gets the shared copy and must not change it."""
    st = os.stat(path)
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _read.get(path)
    if hit and hit[0] == stamp:
        return hit[1]
    with open(path, encoding='utf-8-sig') as f:   # -sig: Notepad may have saved it with a BOM
        data = json.load(f)
    _read[path] = (stamp, data)
    return data


def changed(path):
    """We just wrote or removed this file ourselves: read it afresh next time, whatever its time says (two writes in
    the same clock tick can share one)."""
    _read.pop(path, None)


class Settings(dict):
    """The settings as load() gives them. base: what the file said when these were last read from it or written to it,
    which is how a hand edit made since is told from a change made in the app."""
    base = None
    odd = None   # {key: a value in the file of the wrong kind}, already reported: said once, not at every look


def load():
    """The settings over the defaults. One that won't parse is copied to config.bad.json before anything saves over it."""
    global broken
    try:
        cfg = read_json(FILE)
        if not isinstance(cfg, dict):
            raise ValueError('not a JSON object')
        s = Settings({**DEFAULTS, **cfg})
    except FileNotFoundError:
        s = Settings(DEFAULTS)
    except (OSError, ValueError) as e:
        broken = f'{type(e).__name__}: {e}'
        print(f'config.json unreadable, using defaults ({broken}); kept as {BAD}', flush=True)
        keep_bad()
        s = Settings(DEFAULTS)
    s.base = dict(s)
    return s


def keep_bad():
    try:
        shutil.copyfile(FILE, BAD)
    except OSError as e:
        print('config.bad.json:', e, flush=True)


def fits(key, value):
    """Is this the kind of value the setting takes (a number for boxSeconds, true or false for box)? A hand edit that
    isn't is left out, so a typo can't break the box or the voice. A key Lorekeeper doesn't know is let through."""
    d = DEFAULTS.get(key, value)
    if d is None:
        return value is None or isinstance(value, bool)
    if isinstance(d, bool) or isinstance(value, bool):
        return isinstance(d, bool) and isinstance(value, bool)
    if isinstance(d, (int, float)):
        return isinstance(value, (int, float))
    return isinstance(value, type(d))


def refresh(cfg):
    """Take a hand edit of the settings file into the running settings: every key the file now says differently from
    when these were last read or written, unless the app has changed that key itself since (the app's change is the
    newer one). -> (the keys taken, the keys whose new value is the wrong kind and was left out), or None while the
    file can't be read (an edit saved half-typed). Settings that didn't come from load() are left alone."""
    base = getattr(cfg, 'base', None)
    if base is None:
        return set(), set()
    try:
        now = read_json(FILE)
        if not isinstance(now, dict):
            return None
    except FileNotFoundError:
        now = {}
    except (OSError, ValueError):
        return None
    now = {**DEFAULTS, **now}
    taken, wrong, odd = set(), set(), cfg.odd or {}
    cfg.odd = {k: v for k, v in now.items() if not fits(k, v)}
    for k in set(now) | set(base):
        if k in cfg.odd:
            if k not in odd or odd[k] != cfg.odd[k]:
                wrong.add(k)
            now[k] = base.get(k, DEFAULTS.get(k))   # as if the file still said what it did
        elif now.get(k) == base.get(k):
            continue
        elif cfg.get(k) == base.get(k):
            taken.add(k)
            if k in now:
                cfg[k] = now[k]
            else:
                cfg.pop(k, None)
    cfg.base = now
    return taken, wrong


def write(path, text):
    """The whole file or none of it: written beside, then swapped in, so a crash or a full disk mid-write leaves the old one."""
    folder = os.path.dirname(path) or '.'
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=os.path.basename(path) + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        for i in range(5):   # Windows: a virus scanner or an editor can hold the old file for a moment
            try:
                return os.replace(tmp, path)
            except PermissionError:
                if i == 4:
                    raise
                time.sleep(0.1)
    finally:
        changed(path)
        if os.path.exists(tmp):
            os.remove(tmp)


def save(cfg):
    """Only what differs from the defaults. A hand edit made since the file was last read is taken in first, not
    written over: a tray toggle saves the running settings, and the edit would be gone."""
    if refresh(cfg) is None:
        keep_bad()   # the file can't be read right now: what is in it is kept beside it
    write(FILE, json.dumps({k: v for k, v in cfg.items() if DEFAULTS.get(k) != v}, indent=1))
    if getattr(cfg, 'base', None) is not None:
        cfg.base = {**DEFAULTS, **cfg}
