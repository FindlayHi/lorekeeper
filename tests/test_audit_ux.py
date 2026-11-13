"""The audit's UX items: a hand edit of the settings file is taken up, not written over; a speech model that is still
downloading says so; a slow answer says what it is doing; and Claude Code's own error text is never read aloud."""
import io, json, os, sys, tempfile, threading, time, types
os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import brain, config, ears, firstrun, lorekeeper  # noqa: E402


@pytest.fixture
def where(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DIR', str(tmp_path))
    monkeypatch.setattr(config, 'FILE', str(tmp_path / 'config.json'))
    monkeypatch.setattr(config, 'BAD', str(tmp_path / 'config.bad.json'))
    monkeypatch.setattr(config, 'broken', '')
    return tmp_path


def edit(where, **settings):
    """The player saving the settings file from Notepad."""
    (where / 'config.json').write_text(json.dumps(settings), encoding='utf-8')
    config.changed(config.FILE)   # two saves within one clock tick


def on_disk(where):
    return json.loads((where / 'config.json').read_text(encoding='utf-8'))


# the settings file

def test_a_hand_edit_is_taken_up_without_a_restart(where):
    cfg = config.load()
    edit(where, boxSeconds=30, rate=4)
    assert config.refresh(cfg) == ({'boxSeconds', 'rate'}, set())
    assert cfg['boxSeconds'] == 30 and cfg['rate'] == 4
    assert config.refresh(cfg) == (set(), set())   # once


def test_a_tray_toggle_does_not_write_over_a_hand_edit(where):
    cfg = config.load()
    edit(where, boxSeconds=30)
    cfg['spoilers'] = True   # the tray's flip()
    config.save(cfg)
    assert on_disk(where) == {'boxSeconds': 30, 'spoilers': True} and cfg['boxSeconds'] == 30


def test_the_apps_own_change_to_the_same_setting_is_the_newer_one(where):
    cfg = config.load()
    edit(where, spoilers=False, rate=4)
    cfg['spoilers'] = True
    config.save(cfg)
    assert on_disk(where) == {'spoilers': True, 'rate': 4}
    assert config.refresh(cfg) == (set(), set())


def test_a_setting_removed_from_the_file_goes_back_to_its_default(where):
    edit(where, boxSeconds=30, myOwnKey='x')
    cfg = config.load()
    edit(where)
    assert config.refresh(cfg) == ({'boxSeconds', 'myOwnKey'}, set())
    assert cfg['boxSeconds'] == config.DEFAULTS['boxSeconds'] and 'myOwnKey' not in cfg


def test_an_edit_saved_half_typed_changes_nothing_and_is_kept_when_saved_over(where):
    edit(where, rate=4)
    cfg = config.load()
    (where / 'config.json').write_text('{"rate": 4, "boxSeconds": 3', encoding='utf-8')
    assert config.refresh(cfg) is None and cfg['rate'] == 4
    cfg['spoilers'] = True
    config.save(cfg)
    assert (where / 'config.bad.json').read_text(encoding='utf-8') == '{"rate": 4, "boxSeconds": 3'
    assert on_disk(where) == {'rate': 4, 'spoilers': True}


@pytest.mark.parametrize('key, value', [('boxSeconds', 'twelve'), ('box', 'yes'), ('rate', True), ('hotkey', 5), ('telemetry', 'no')])
def test_a_value_of_the_wrong_kind_is_left_out(where, key, value):
    cfg = config.load()
    edit(where, **{key: value, 'rate': 4} if key != 'rate' else {key: value})
    taken, wrong = config.refresh(cfg)
    assert wrong == {key} and cfg[key] == config.DEFAULTS[key]
    assert taken == ({'rate'} if key != 'rate' else set())
    assert config.refresh(cfg) == (set(), set())   # said once, not every two seconds


def test_settings_that_did_not_come_from_load_are_saved_as_they_are(where):
    edit(where, boxSeconds=30)
    config.save({**config.DEFAULTS, 'hotkey': 'mouse4'})
    assert on_disk(where) == {'hotkey': 'mouse4'}


# the running app follows the file

class Voice:
    def __init__(self):
        self.said, self.kind, self.edge_voice, self.rate, self.pitch, self.kokoro_voice = [], 'kokoro', '', 0, '', ''

    def say(self, text):
        self.said.append(text)

    def stop(self):
        pass

    def busy(self):
        return False


class Box:
    seconds = 12

    def __init__(self):
        self.shown = []

    def show(self, question='', answer='', stay=False, **_):
        self.shown.append((question, answer))

    def hide(self):
        pass


class Key:
    held = False

    def __init__(self, combo):
        self.combo = combo

    def set(self, combo):
        if combo == 'nonsense':
            raise ValueError(combo)
        self.combo = combo


class Listener:
    on, follow_s = False, 8


class Warm:
    dropped = 0

    def drop(self):
        self.dropped += 1

    def take(self, model, spoilers):
        return object()


class Ears:
    mic, getting, model = '', False, 'a model'

    def stop(self):
        return np.zeros(16000, dtype='float32')

    def text(self, audio, hint=''):
        return 'where is Malenia'


def app(cfg=None):
    a = lorekeeper.App.__new__(lorekeeper.App)
    a.cfg = cfg if cfg is not None else config.load()
    a._box, a.voice, a.warm, a.ears, a.listener = Box(), Voice(), Warm(), Ears(), Listener()
    a.hk, a.lk, a._bad_edit = Key('ctrl+alt+space'), Key('ctrl+alt+l'), False
    a.gen, a.down_at, a.game, a.looking, a.spoil_next, a.let_go = 1, 0, None, None, False, 0
    a.frames, a.seen, a.turns, a.last, a.last_q = [], '', [], '', ''
    a.hint = lambda: ''
    return a


def test_an_edit_reaches_the_voice_the_box_and_the_hotkey_and_the_box_says_so(where):
    a = app()
    edit(where, rate=4, boxSeconds=30, hotkey='mouse4', followUpSeconds=20, model='sonnet')
    a.reload()
    assert (a.voice.rate, a._box.seconds, a.hk.combo, a.listener.follow_s) == (4, 30, 'mouse4', 20)
    assert a.warm.dropped == 1   # the AI started ahead was the old model
    assert a._box.shown == [('Settings file', 'Now in use: boxSeconds, followUpSeconds, hotkey, model, rate.')]
    a.reload()
    assert len(a._box.shown) == 1


def test_a_mistake_in_the_file_is_said_once_and_the_settings_stay(where):
    a = app()
    (where / 'config.json').write_text('{"rate": 4,', encoding='utf-8')
    a.reload(), a.reload()
    assert len(a._box.shown) == 1 and 'mistake' in a._box.shown[0][1] and a.voice.rate == 0
    edit(where, rate=4)
    a.reload()
    assert a.voice.rate == 4 and a._box.shown[-1][1] == 'Now in use: rate.'


def test_a_hotkey_that_is_no_key_and_a_value_of_the_wrong_kind_leave_things_as_they_were(where, capsys):
    a = app()
    edit(where, hotkey='nonsense', boxSeconds='long')
    a.reload()
    assert a.hk.combo == 'ctrl+alt+space' and a._box.seconds == 12
    assert 'Left as it was, the value is the wrong kind: boxSeconds.' in a._box.shown[-1][1]


def test_picking_another_speech_model_keeps_the_old_one_until_the_new_one_is_ready(where, monkeypatch):
    made, gate = [], threading.Event()

    class New(Ears):
        def __init__(self, size, device, progress):
            self.size, self.ready, self.model = size, threading.Event(), None
            made.append(self)
    monkeypatch.setattr(ears, 'Ears', New)
    a = app()
    old = a.ears
    edit(where, whisper='small.en')
    a.reload()
    assert made[0].size == 'small.en' and a.ears is old   # still answering with the one that works
    made[0].model = 'small'
    made[0].ready.set()
    for _ in range(50):
        if a.ears is made[0]:
            break
        time.sleep(0.02)
    assert a.ears is made[0] and a.listener.ears is made[0]


# the speech model's download

def whisper(monkeypatch, model, cached):
    fake, utils = types.ModuleType('faster_whisper'), types.ModuleType('faster_whisper.utils')
    fake.WhisperModel, fake.utils = model, utils
    utils._MODELS = {'base.en': 'Systran/faster-whisper-base.en'}

    def download_model(size, local_files_only=False):
        if not cached:
            raise OSError('not in the cache')
    utils.download_model = download_model
    monkeypatch.setitem(sys.modules, 'faster_whisper', fake)
    monkeypatch.setitem(sys.modules, 'faster_whisper.utils', utils)


def test_a_model_being_downloaded_reports_its_progress_and_a_question_says_so_at_once(monkeypatch, tmp_path):
    gate, seen = threading.Event(), []
    whisper(monkeypatch, lambda *a, **k: gate.wait(5) and 'the model', cached=False)
    monkeypatch.setattr(ears, 'folder', lambda size: str(tmp_path))
    monkeypatch.setattr(ears, 'total', lambda size: 1000)
    (tmp_path / 'blobs').mkdir()
    (tmp_path / 'blobs' / 'abc.incomplete').write_bytes(b'x' * 400)
    e = ears.Ears('base.en', 'cpu', lambda done, total, finished=None: seen.append((done, total, finished)))
    for _ in range(100):
        if seen:
            break
        time.sleep(0.02)
    assert seen[0] == (400, 1000, None) and e.getting
    t = time.time()
    with pytest.raises(RuntimeError, match='still downloading'):
        e.text(np.zeros(16000, dtype='float32'))
    assert time.time() - t < 1   # not after a minute's wait
    gate.set()
    assert e.ready.wait(5)
    for _ in range(100):
        if seen[-1][2] is not None:
            break
        time.sleep(0.02)
    assert seen[-1] == (0, 0, True) and e.getting is False and e.model == 'the model'


def test_a_download_that_fails_is_reported_as_failed(monkeypatch, tmp_path):
    seen = []

    def model(*a, **k):
        raise OSError('no internet')
    whisper(monkeypatch, model, cached=False)
    monkeypatch.setattr(ears, 'folder', lambda size: str(tmp_path))
    monkeypatch.setattr(ears, 'total', lambda size: 0)
    e = ears.Ears('base.en', 'cpu', lambda *a: seen.append(a))
    assert e.ready.wait(5)
    for _ in range(100):
        if seen and seen[-1][2] is not None:
            break
        time.sleep(0.02)
    assert seen[-1] == (0, 0, False)


def test_a_model_already_on_this_pc_reports_nothing(monkeypatch):
    seen = []
    whisper(monkeypatch, lambda *a, **k: 'the model', cached=True)
    e = ears.Ears('base.en', 'cpu', lambda *a: seen.append(a))
    assert e.ready.wait(5) and e.getting is False and seen == []


def test_the_hotkey_says_the_model_is_downloading_instead_of_waiting(where):
    a = app()
    a.ears.getting = True
    a.ears.text = lambda *a: pytest.fail('not transcribed: there is no model yet')
    a.up()
    assert a.voice.said == [ears.WAIT] and a.warm.dropped


def test_the_progress_goes_to_the_box(where):
    a = app()
    a.speech_download(40_000_000, 100_000_000)
    a.speech_download(31 << 20, 0)
    a.speech_download(0, 0, True)
    a.speech_download(0, 0, False)
    assert [s[1].split(':')[-1].strip() if i < 2 else s[0] for i, s in enumerate(a._box.shown)] == [
        '40%.', '31 MB.', 'Speech model ready', 'Speech model download failed']


def test_the_voice_download_waits_for_the_speech_model(monkeypatch, tmp_path):
    order, a = [], types.SimpleNamespace(cfg={'ai': 'openai'}, ears=types.SimpleNamespace(getting=True), voice=types.SimpleNamespace())
    monkeypatch.setattr(firstrun, 'missing_models', lambda: ['kokoro'])
    monkeypatch.setattr(firstrun, 'download_models', lambda progress: order.append('voice') or True)
    box = Box()
    firstrun.run(a, box)
    time.sleep(0.7)
    assert order == [] and box.shown == []   # one download and one progress line at a time
    a.ears.getting = False
    for _ in range(100):
        if order:
            break
        time.sleep(0.05)
    assert order == ['voice']


# a slow answer says what it is doing

class Claude:
    """A `claude -p` whose output is these lines."""

    def __init__(self, lines, code=0, err=''):
        self.dir, self.returncode = None, code
        self.stdin, self.errors, self.stdout = io.StringIO(), io.StringIO(err), iter(json.dumps(j) + '\n' for j in lines)

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


def event(**e):
    return {'type': 'stream_event', 'event': e}


def test_ask_says_when_the_model_starts_a_search():
    tools = []
    p = Claude([event(type='content_block_start', content_block={'type': 'tool_use', 'name': 'WebSearch'}),
                event(type='content_block_start', content_block={'type': 'text', 'text': ''}),
                {'type': 'result', 'result': 'Stormveil.', 'total_cost_usd': 0}])
    assert brain.ask(p, 'where now', on_tool=tools.append)[0] == 'Stormveil.' and tools == ['WebSearch']


@pytest.fixture
def answering(where, monkeypatch):
    """An app whose answer comes from a fake wiki and a fake AI, each as slow as the test says."""
    a, slow = app(), {'wiki': 0, 'ai': 0}
    monkeypatch.setattr(lorekeeper, 'log', lambda row: None)
    monkeypatch.setattr(lorekeeper.romm, 'context', lambda g, q: '')
    monkeypatch.setattr(lorekeeper.lookup, 'wiki', lambda *a, **k: time.sleep(slow['wiki']) or 'wiki text')

    def ask(p, text, shots, on_text, keep, on_tool):
        a.box_before_ai = a._box.shown[-1] if a._box.shown else None
        on_tool('WebSearch')
        time.sleep(slow['ai'])
        on_text('Stormveil Castle. Go north.')
        return 'Stormveil Castle. Go north.', 0
    monkeypatch.setattr(brain, 'ask', ask)
    return a, slow


def test_the_box_says_what_is_taking_the_time(answering):
    a, _ = answering
    a.answer('where is Malenia', 1)
    shown = [s[1] for s in a._box.shown]
    assert shown[:3] == ['Checking the wiki…', 'Thinking…', 'Searching the web…'] and a.box_before_ai[1] == 'Thinking…'
    assert shown[-1].startswith('Stormveil Castle.') and 'Still looking.' not in a.voice.said


def test_a_long_wait_is_said_aloud_once(answering, monkeypatch):
    a, slow = answering
    monkeypatch.setattr(lorekeeper, 'STILL', 0.1)
    slow['ai'] = 0.4
    a.answer('where is Malenia', 1)
    assert a.voice.said[0] == 'Still looking.' and a.voice.said.count('Still looking.') == 1
    assert ' '.join(a.voice.said[1:]) == 'Stormveil Castle. Go north.'


def test_nothing_is_said_about_an_answer_the_player_has_moved_on_from(answering, monkeypatch):
    a, slow = answering
    monkeypatch.setattr(lorekeeper, 'STILL', 0.1)
    slow['wiki'] = 0.3
    a.gen = 2   # asked again meanwhile
    a.answer('where is Malenia', 1)
    assert a.voice.said == [] and a._box.shown == []


def test_a_failed_answer_is_not_followed_by_still_looking(answering, monkeypatch):
    a, _ = answering
    monkeypatch.setattr(lorekeeper, 'STILL', 0.1)
    monkeypatch.setattr(lorekeeper.lookup, 'wiki', lambda *a, **k: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        a.answer('where is Malenia', 1)
    time.sleep(0.3)
    assert a.voice.said == []


# Claude Code's errors

@pytest.mark.parametrize('err, said', [
    ('Invalid API key · Please run /login', 'Claude Code is signed out. Sign in from the tray: AI, Sign in to Claude.'),
    ('Claude AI usage limit reached|1731500000', "You've reached your Claude plan's limit for now. Try again later, or pick another AI in the tray."),
    ('API Error: 529 {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}', 'Claude is busy right now. Try again in a moment.'),
    ('API Error: Connection error. getaddrinfo ENOTFOUND api.anthropic.com', "Couldn't reach Claude. Check your internet connection."),
    ('TypeError: Cannot read properties of undefined (reading "x")\n    at file:///C:/Users/me/cli.js:1:2', "Claude Code couldn't answer that. Try again."),
])
def test_claude_codes_own_error_text_is_never_the_answer(err, said, capsys):
    assert brain.ask(Claude([], code=1, err=err), 'where now')[0] == said   # it wrote to stderr and exited
    as_result = Claude([{'type': 'result', 'is_error': True, 'result': err, 'total_cost_usd': 0}], code=1)
    assert brain.ask(as_result, 'where now')[0] == said                     # or gave it as its result
    assert err.strip()[:40] in capsys.readouterr().out                      # the log has the text itself


def test_a_real_answer_is_left_alone():
    p = Claude([{'type': 'result', 'is_error': False, 'result': 'You need to log in to the terminal at 429 Elm Street.', 'total_cost_usd': 0}])
    assert brain.ask(p, 'where now')[0] == 'You need to log in to the terminal at 429 Elm Street.'


# the README

def test_the_readme_says_it_is_english_only_and_names_the_tray_settings():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'README.md'), encoding='utf-8') as f:
        text = f.read()
    assert 'English only' in text
    for row in ('Speech model', 'Clip key', 'Speaking speed', 'Box stays for', 'Check every day'):
        assert f'**{row}**' in text and f"'{row}" in open(lorekeeper.__file__, encoding='utf-8').read()
