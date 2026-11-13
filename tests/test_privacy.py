"""The screen is remembered, and the mic open, only while a game is really in front."""
import os, sys, tempfile

os.environ['LOREKEEPER_DIR'] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image  # noqa: E402
import capture, config, games, lorekeeper  # noqa: E402


HADES, CHROME = r'D:\Steam\steamapps\common\Hades\x64\Hades.exe', r'C:\Program Files\Google\Chrome\Application\chrome.exe'


class NoThread:
    def __init__(self, *a, **kw):
        pass

    def start(self):
        pass


def screen(monkeypatch, front):
    monkeypatch.setattr(capture.threading, 'Thread', NoThread)   # no background loop: the test drives tick()
    s = capture.Screen(active=lambda: front[0])
    s._grab = lambda: Image.new('RGB', (64, 36), 'red')
    return s


def test_frames_are_recorded_only_while_a_game_is_in_front(monkeypatch):
    front = [True]
    s = screen(monkeypatch, front)
    for t in range(100, 103):
        s.tick(t)
    front[0] = False   # alt-tabbed to a browser
    for t in range(103, 130):
        s.tick(t)
    assert [f[0] for f in s.recent] == [100, 101, 102] and [f[0] for f in s.long] == [100]


def test_a_quick_alt_tab_keeps_the_memory_a_long_one_forgets_it(monkeypatch):
    front = [True]
    s = screen(monkeypatch, front)
    for t in range(100, 120):
        s.tick(t)
    front[0] = False
    for t in range(120, 175):   # under a minute away: reading a message
        s.tick(t)
    assert len(s.recent) == 5 and len(s.long) == 2
    front[0] = True
    s.tick(175)
    front[0] = False
    for t in range(176, 240):   # over a minute away
        s.tick(t)
    assert not s.recent and not s.long
    with s.lock:
        assert capture.Screen.pick(sorted(set(s.long) | set(s.recent)), 'what did that say earlier') == []
    front[0] = True
    s.tick(240)
    assert [f[0] for f in s.recent] == [240]   # back in a game: a fresh memory


def app(monkeypatch, exe, title='', everywhere=False, pin=None):
    monkeypatch.setattr(games.win, 'front', lambda: (exe, title))
    a = lorekeeper.App.__new__(lorekeeper.App)   # no mic, voice or screen: only what the checks use
    a.cfg, a._pin, a._games = {**config.DEFAULTS, 'hotkeyEverywhere': everywhere}, pin, {}
    monkeypatch.setattr(games, 'match', lambda exe, title, idx: {'name': 'Hades'} if exe.endswith('\\Hades.exe') else None)
    return a


def test_game_in_front_ignores_hotkey_everywhere(monkeypatch):
    assert app(monkeypatch, HADES).game_in_front()
    for exe in (CHROME, r'C:\Windows\explorer.exe', r'C:\Users\me\AppData\Local\Discord\app-1.0\Discord.exe', ''):
        a = app(monkeypatch, exe, everywhere=True)
        assert a.in_game() and not a.game_in_front()   # the hotkey works everywhere; the screen and mic don't follow it
    assert not app(monkeypatch, CHROME, pin={'game': {'name': 'Hades'}, 'exe': HADES}).game_in_front()   # a pinned game, but a browser in front


KEEPASS, EMU = r'C:\Program Files\KeePass\KeePass.exe', r'C:\Games\odd-launcher\play.exe'


def test_a_pinned_game_counts_only_in_its_own_window(monkeypatch):
    pin = {'game': {'name': 'Chrono Trigger'}, 'exe': EMU, 'sticky': True}
    assert app(monkeypatch, EMU, pin=pin).game_in_front()
    for exe in (KEEPASS, r'C:\Program Files\BraveSoftware\brave.exe', r'C:\Program Files\Microsoft Office\WINWORD.EXE'):
        a = app(monkeypatch, exe, pin=pin)
        assert not a.game_in_front() and not a.in_game()   # no screen memory, no mic, no hotkey over a password manager


def test_a_game_picked_in_the_tray_has_no_window_until_the_hotkey_is_used_there(monkeypatch):
    games.pin({'name': 'Chrono Trigger'})   # tray: no window known
    try:
        assert not app(monkeypatch, CHROME, pin=games.pinned()).in_game()
        a = app(monkeypatch, EMU, pin=games.pinned())
        assert a.in_game() and not a.game_in_front()   # the hotkey works; nothing is watched or heard yet
        a._pin = games.bind(EMU)   # what App.down does
        assert a._pin['exe'] == EMU and a.game_in_front()
        assert games.current(KEEPASS, 'Passwords')[0]['name'] == 'Chrono Trigger' and games.pinned()   # still pinned after an alt-tab
        assert not app(monkeypatch, KEEPASS, pin=games.pinned()).game_in_front()
    finally:
        games.unpin()


def test_use_the_screen_off_records_nothing_and_forgets(monkeypatch):
    front = [True]
    s = screen(monkeypatch, front)
    for t in range(100, 112):
        s.tick(t)
    assert s.recent and s.long
    s.forget()   # the tray's Use the screen, unticked
    assert not s.recent and not s.long and s.full is None
    import inspect
    assert "self.cfg['screen']" in inspect.getsource(lorekeeper.App.__init__).split('capture.Screen(')[1].split('\n')[0]


def test_listen_mode_ignores_audio_outside_a_game_even_with_hotkey_everywhere(monkeypatch):
    class Voice:
        def busy(self):
            return False
    a = app(monkeypatch, CHROME, everywhere=True)
    a.voice, a._spoke_at, a.hk = Voice(), 0, None
    assert a.listen_muted()
    monkeypatch.setattr(games.win, 'front', lambda: (HADES, ''))
    assert not a.listen_muted()


def test_the_app_wires_the_screen_and_mic_to_a_game_in_front(monkeypatch):
    import brain, capture as cap, ears, listen, voice
    got = {}
    monkeypatch.setattr(brain, 'use', lambda cfg: None)
    monkeypatch.setattr(brain, 'Warm', lambda: None)
    monkeypatch.setattr(voice, 'Voice', lambda *a: None)
    monkeypatch.setattr(ears, 'Ears', lambda *a: type('E', (), {})())
    monkeypatch.setattr(cap, 'Screen', lambda **kw: got.setdefault('screen', kw))
    monkeypatch.setattr(listen, 'Listener', lambda *a, **kw: got.setdefault('listener', kw))
    monkeypatch.setattr(lorekeeper.threading, 'Thread', NoThread)
    monkeypatch.setattr(games, 'index', lambda: {})
    monkeypatch.setattr(games, 'pinned', lambda: None)
    monkeypatch.setattr(games, 'match', lambda exe, title, idx: None)
    monkeypatch.setattr(games.win, 'front', lambda: (CHROME, ''))
    a = lorekeeper.App({**config.DEFAULTS, 'listen': False, 'hotkeyEverywhere': True})
    a.game = {'name': 'Hades'}   # sticky after an alt-tab to the browser
    assert not got['screen']['active']() and not got['listener']['front']()
