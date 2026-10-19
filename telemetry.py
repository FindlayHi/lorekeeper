"""Anonymous usage counts: how many installs, and how many are used each day. Nothing about play ever leaves.

Sent, to PostHog: a random install id (made here, tied to nothing), the event ("installed" once, "active" at most once a
day), the app version and commit, the Windows version, whether listen mode / RomM are on, which voice engine, and which
kind of AI answers (claude, ollama, lmstudio, openai or custom: never its address or model).
Never: games, questions, answers, notes, paths, names, hardware. Asked once on first run (nothing is sent before a yes);
change it any time in the tray ("Share anonymous usage counts") or config.json, or set DO_NOT_TRACK. With no posthogKey
nothing is sent and nothing is asked.
"""
import json, os, platform, threading, time, urllib.request, uuid
import config

VERSION = '0.1.13'
FILE = os.path.join(config.DIR, 'telemetry.json')   # {"id", "active": last day counted}
EVERY = 3 * 3600          # a tray app runs for days: check the day this often
QUESTION = ('Share anonymous usage counts?\n\n'
            'Lorekeeper would send a random id, the app and Windows version, and which features are on, '
            'so its maker can see how many people use it.\n\n'
            'Never your games, questions, answers or anything you say. You can change this any time in the tray.')


def _dnt():
    return os.environ.get('DO_NOT_TRACK', '').strip() not in ('', '0')   # the cross-tool opt-out (consoledonottrack.com)


def allowed(cfg):
    """Only after an explicit yes (telemetry is True, not merely unset), with a key, and no DO_NOT_TRACK."""
    return cfg.get('telemetry') is True and bool(cfg.get('posthogKey')) and not _dnt()


def should_ask(cfg):
    """First run: never asked (None), there is somewhere to send to, and DO_NOT_TRACK isn't set."""
    return cfg.get('telemetry') is None and bool(cfg.get('posthogKey')) and not _dnt()


def _load():
    try:
        with open(FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(st):
    os.makedirs(config.DIR, exist_ok=True)
    with open(FILE, 'w', encoding='utf-8') as f:
        json.dump(st, f)


def _commit(root=os.path.dirname(os.path.abspath(__file__))):
    git = os.path.join(root, '.git')
    try:
        if os.path.isfile(git):   # a worktree: ".git" names the real folder
            git = open(git, encoding='utf-8').read().split('gitdir:', 1)[1].strip()
        head = open(os.path.join(git, 'HEAD'), encoding='utf-8').read().strip()
        if not head.startswith('ref: '):
            return head[:7]
        ref = head[5:]
        if os.path.exists(os.path.join(git, 'commondir')):
            git = os.path.join(git, open(os.path.join(git, 'commondir'), encoding='utf-8').read().strip())
        if os.path.exists(os.path.join(git, ref)):
            return open(os.path.join(git, ref), encoding='utf-8').read().strip()[:7]
        for line in open(os.path.join(git, 'packed-refs'), encoding='utf-8'):
            if line.rstrip().endswith(' ' + ref):
                return line[:7]
    except (OSError, IndexError):
        pass
    return ''


def _windows():
    try:
        build = int(platform.version().split('.')[2])
    except (IndexError, ValueError):
        return platform.system() or 'unknown', ''
    return ('Windows 11' if build >= 22000 else 'Windows 10'), str(build)


def props(cfg):
    """Everything an event carries besides its name and the install id. Keep this list in step with the README."""
    os_name, build = _windows()
    return {'version': VERSION, 'commit': _commit(), 'os': os_name, 'os_build': build,
            'listen': bool(cfg.get('listen')), 'romm': bool(cfg.get('rommUrl')), 'voice': cfg.get('voice') or '',
            'ai': __import__('brain').kind(cfg),
            '$process_person_profile': False, '$geoip_disable': True, '$lib': 'lorekeeper'}


def send(cfg, event, distinct_id, properties):
    """One event to PostHog's capture API. Quick, and silent on any failure."""
    body = json.dumps({'api_key': cfg['posthogKey'], 'event': event, 'distinct_id': distinct_id, 'properties': properties}).encode()
    req = urllib.request.Request(cfg.get('posthogHost', config.DEFAULTS['posthogHost']).rstrip('/') + '/i/v0/e/', body,
                                 {'Content-Type': 'application/json', 'User-Agent': 'lorekeeper'})
    try:
        urllib.request.urlopen(req, timeout=5).close()
    except Exception:
        pass


def ping(cfg, sender=None):
    """"installed" the first time, "active" once a day. Returns the events sent (for tests)."""
    if not allowed(cfg):
        return []
    st, today, events = _load(), time.strftime('%Y-%m-%d'), []
    if not st.get('id'):
        st['id'] = uuid.uuid4().hex
        events.append('installed')
    if st.get('active') != today:
        st['active'] = today
        events.append('active')
    if not events:
        return []
    _save(st)   # before sending: a failed send loses that day's count, it never repeats it
    p = props(cfg)
    for e in events:
        (sender or send)(cfg, e, st['id'], p)
    return events


def start(cfg, wait=0):
    """In the background: wait (first run), then count today and each new day while the app runs. Reads cfg live,
    so unticking the tray box stops it from the next check."""
    def run():
        time.sleep(wait)
        while True:
            try:
                ping(cfg)
            except Exception:
                pass
            time.sleep(EVERY)
    threading.Thread(target=run, daemon=True).start()
