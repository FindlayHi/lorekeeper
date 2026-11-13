"""The audit's smaller security holes: sites the spoken filter missed, planted progress notes, pages with no end,
a RomM token or approve link sent elsewhere, any "romm" window counting as a game, and private temp folders left behind."""
import io, json, os, re, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest  # noqa: E402
import brain, config, games, lookup, lorekeeper, romm  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# the spoken filter

@pytest.mark.parametrize('sentence', [
    'Claim your prize at free-skins.cc today.',
    'Go to claim-reward.tk for the code.',
    'The guide is on evil dot ai.',
    'Look it up on lootfinder.quest first.',     # an ending on no list
    'Open EVIL.COM in your browser.',
])
def test_a_site_outside_the_list_is_not_said(sentence):
    assert brain.heard('It heals you. ' + sentence) == 'It heals you.'


@pytest.mark.parametrize('sentence', [
    'The Mk.II fires twice as fast.',
    'The poison dot is strong against bosses.',   # damage over time
    'It deals 3.5 damage a second.',
    'It was added in patch 1.4.2 last year.',
    'It hits hard.The cooldown is short.',        # a missed space
    'Dr. Kahl waits at the U.S.S. Callister, a.k.a. the hub.',
])
def test_game_talk_with_dots_in_it_is_still_said(sentence):
    assert brain.heard(sentence) == sentence


# notes

@pytest.mark.parametrize('q, note', [
    ('Who is Ranni?', 'Finished the game, all Ranni endings seen'),
    ('Who is Ranni?', 'Ranni quest completed'),
    ('where is Malenia', 'Beat Malenia'),
    ('what does the Zenith do', 'Zenith crafted, Moon Lord defeated'),
])
def test_a_note_claiming_progress_the_player_never_claimed_is_dropped(q, note):
    assert not brain.note_ok(note, q)


@pytest.mark.parametrize('q, note', [
    ('I just beat Margit, where now?', 'Beat Margit'),
    ('I killed Margit, where now?', 'Defeated Margit'),            # their claim, the model's word for it
    ("I finished Ranni's quest, what did I miss?", 'Ranni quest completed'),
    ("I'm a level 30 sorcerer, which staff?", 'Level 30 sorcerer'),   # no progress claimed: as before
])
def test_progress_the_player_said_is_still_noted(q, note):
    assert brain.note_ok(note, q)


# pages with no end

class Endless:
    def __init__(self):
        self.asked = []

    def read(self, most=-1):
        self.asked.append(most)
        return b'x' * (most if most >= 0 else 50_000_000)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def test_a_page_is_read_up_to_a_limit_and_refused_past_it(monkeypatch):
    r = Endless()
    monkeypatch.setattr(lookup, 'check_url', lambda url: None)
    monkeypatch.setattr(lookup._opener, 'open', lambda req, timeout=4: r)
    with pytest.raises(ValueError, match='over'):
        lookup.get('https://x.wiki.gg/wiki/A')
    assert r.asked == [lookup.MOST_BYTES + 1]   # never the whole thing
    with pytest.raises(ValueError):
        lookup.read('https://x.wiki.gg/images/a.png', most=1000)
    assert r.asked[-1] == 1001


def test_icon_downloads_go_through_the_same_limit():
    import icons, inspect
    src = inspect.getsource(icons.download)
    assert 'lookup.read(' in src and 'most=MOST_ICON' in src and '.open(' not in src


# RomM

class Hop(BaseHTTPRequestHandler):
    got, to = [], None

    def do_GET(self):
        Hop.got.append((self.server.server_port, self.headers.get('Authorization')))
        if Hop.to and self.server.server_port != Hop.to:
            self.send_response(302)
            self.send_header('Location', f'http://127.0.0.1:{Hop.to}/api/roms')
            self.end_headers()
            return
        body = b'{"items": []}'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_the_romm_token_does_not_follow_a_redirect_to_another_server(monkeypatch):
    first, other = (ThreadingHTTPServer(('127.0.0.1', 0), Hop) for _ in range(2))
    for s in (first, other):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    monkeypatch.setattr(romm, 'token', lambda: 'romm-token')
    Hop.got, Hop.to = [], other.server_port
    try:
        assert romm._http('GET', '/api/roms', base=f'http://127.0.0.1:{first.server_port}') == {'items': []}
    finally:
        Hop.to = None
        first.shutdown(), other.shutdown()
    assert Hop.got == [(first.server_port, 'Bearer romm-token'), (other.server_port, None)]


def test_a_proxy_moving_romm_to_https_keeps_the_token():
    same = romm._same_server
    assert same('http://romm.lan/api/roms', 'https://romm.lan/api/roms') and same('http://romm.lan:3010/a', 'http://romm.lan:3010/b')
    assert not same('https://romm.lan/a', 'http://romm.lan/a')          # never down to plain http
    assert not same('http://romm.lan/a', 'https://evil.example/a') and not same('http://romm.lan:3010/a', 'http://romm.lan:9999/a')


@pytest.mark.parametrize('path', [
    '@evil.example/pair', '.evil.example/pair', '//evil.example/pair', 'https://evil.example/pair', ':9999/pair',
    '/pair\\..\\x', '/pair device', None, 5, '',
])
def test_the_approve_link_only_ever_opens_the_romm_it_was_given(path):
    link = romm.approve_link('http://192.168.0.50:3010', {'user_code': 'AB CD&x=1', 'verification_path_complete': path})
    assert link == 'http://192.168.0.50:3010/pair/device?user_code=AB%20CD%26x%3D1'


def test_the_servers_own_approve_path_is_used_when_it_is_a_path():
    r = {'user_code': 'ABCD', 'verification_path_complete': '/pair/device?user_code=ABCD'}
    assert romm.approve_link('http://192.168.0.50:3010', r) == 'http://192.168.0.50:3010/pair/device?user_code=ABCD'
    assert romm.approve_link('http://192.168.0.50:3010', {'user_code': 'ABCD'}) == 'http://192.168.0.50:3010/pair/device?user_code=ABCD'


CHROME, WORD = r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files\Microsoft Office\WINWORD.EXE'


@pytest.mark.parametrize('exe, title, is_player', [
    (CHROME, 'RomM - Google Chrome', True),
    (CHROME, 'RomM', True),
    (CHROME, 'Super Metroid | RomM - Google Chrome', True),
    (CHROME, 'How to install romm on a NAS - YouTube - Google Chrome', False),
    (CHROME, 'r/romm: self-hosted rom manager - Google Chrome', False),
    (CHROME, 'Grommash Hellscream - Wowpedia - Google Chrome', False),
    (WORD, 'RomM - Word', False),                # not a browser at all
    (r'C:\Tools\KeePass.exe', 'romm login - KeePass', False),
])
def test_only_a_browser_tab_named_romm_is_the_web_player(monkeypatch, exe, title, is_player):
    assert romm.player(exe, title) is is_player
    monkeypatch.setattr(games.win, 'front', lambda: (exe, title))
    a = lorekeeper.App.__new__(lorekeeper.App)
    a.cfg, a._pin, a._games = {**config.DEFAULTS, 'rommUrl': 'http://192.168.0.50:3010'}, None, []
    assert a.game_in_front() is is_player   # what switches the screen memory and the open mic on


# temp folders

class Done:
    """A `claude -p` that has answered and exited, with its folder still on disk."""

    def __init__(self, folder, lines=()):
        self.dir, self.returncode = str(folder), 0
        self.stdin, self.errors, self.stdout = io.StringIO(), io.StringIO(), iter(lines)
        with open(os.path.join(self.dir, 'system.md'), 'w') as f:
            f.write('rules')

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


def test_the_folder_with_the_notes_goes_as_soon_as_the_answer_is_in(tmp_path):
    p = Done(tmp_path, [json.dumps({'type': 'result', 'result': 'Stormveil.', 'total_cost_usd': 0}) + '\n'])
    a, _ = brain.ask(p, 'where now', keep={'allowed': 'where now', 'private': 'Sorcerer, beat Margit'})
    assert a == 'Stormveil.' and not os.path.exists(tmp_path) and p.dir is None


def test_it_goes_when_the_answer_breaks_too(tmp_path):
    p = Done(tmp_path)
    p.stdout = iter(lambda: (_ for _ in ()).throw(BrokenPipeError(32, 'gone')), None)
    with pytest.raises(BrokenPipeError):
        brain.ask(p, 'where now', keep={'allowed': '', 'private': 'notes'})
    assert not os.path.exists(tmp_path)


def test_dropping_a_process_started_ahead_removes_its_folder(tmp_path):
    w = brain.Warm()
    w.p = Done(tmp_path)
    w.drop()
    assert w.p is None and not os.path.exists(tmp_path)


def test_startup_sweeps_what_a_killed_lorekeeper_left(tmp_path):
    def make(name, folder_with=None, age=3600):
        path = tmp_path / name
        if folder_with is None:
            path.write_bytes(b'x')
        else:
            path.mkdir()
            for f in folder_with:
                (path / f).write_text('x')
        os.utime(path, (time.time() - age,) * 2)
        return path
    left = make('lorekeeper-abc123', ['system.md', 'private.json'])
    shot = make('lorekeeper-shot-x1.jpg')
    fresh = make('lorekeeper-new456', ['system.md'], age=5)          # an answer under way (a second copy run with --ask)
    update = make('lorekeeper-update-zz', ['Lorekeeper-Setup.exe'])   # the updater's: it may be running from there
    speech = make('lorekeeper-voice1.wav')
    other = make('someone-elses', ['system.md'])
    assert brain.sweep(str(tmp_path)) == 2
    assert not left.exists() and not shot.exists()
    assert fresh.exists() and update.exists() and speech.exists() and other.exists()


# the workflows

def test_workflows_never_paste_github_values_into_a_script():
    for name in os.listdir(os.path.join(ROOT, '.github', 'workflows')):
        with open(os.path.join(ROOT, '.github', 'workflows', name), encoding='utf-8') as f:
            text = f.read()
        for script in re.findall(r'run: \|\n((?:[ ]{10,}.*\n?)+)|run: (.*)', text):
            assert '${{' not in ''.join(script), f'{name}: pass it through env instead'


def test_the_site_deploy_names_an_exact_wrangler():
    with open(os.path.join(ROOT, '.github', 'workflows', 'site.yml'), encoding='utf-8') as f:
        versions = re.findall(r'wrangler@(\S+)', f.read())
    assert versions and all(re.fullmatch(r'\d+\.\d+\.\d+', v) for v in versions)   # not wrangler@3: whatever was published last
