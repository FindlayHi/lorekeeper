"""A failed answer is said and shown, logged, and leaves the app ready for the next press; a stale one stays silent."""
import os, sys, tempfile, time
os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
import lorekeeper  # noqa: E402


class Voice:
    def __init__(self):
        self.said, self.stopped = [], 0

    def say(self, text):
        self.said.append(text)

    def stop(self):
        self.stopped += 1

    def busy(self):
        return False


class Box:
    def __init__(self):
        self.shown = []

    def show(self, question='', answer='', stay=False, **_):
        self.shown.append((question, answer, stay))

    def hide(self):
        self.shown.append('hide')


class Warm:
    dropped = 0

    def drop(self):
        self.dropped += 1


class Ears:
    def __init__(self, text):
        self._text = text

    def stop(self):
        return np.zeros(16000, dtype='float32')

    def text(self, audio, hint=''):
        if isinstance(self._text, Exception):
            raise self._text
        return self._text


class Listener:
    on = False


def app(heard='where is Malenia'):
    a = lorekeeper.App.__new__(lorekeeper.App)   # no mic, voice or screen: fakes for what up/heard/handle touch
    a.cfg = {'box': True, 'boxWhileSpeaking': False}
    a._box, a.voice, a.warm, a.ears, a.listener = Box(), Voice(), Warm(), Ears(heard), Listener()
    a.gen, a.down_at, a.game, a.looking, a.spoil_next = 1, 0, None, None, False
    a.hint = lambda: ''
    a.look = lambda *_: None
    return a


def test_an_answer_that_raises_is_said_and_the_box_is_released(monkeypatch, capsys):
    a = app()
    monkeypatch.setattr(a, 'answer', lambda q, gen: (_ for _ in ()).throw(BrokenPipeError(32, 'The pipe is being closed')))
    a.up()   # the hotkey thread: must not raise
    said = a.voice.said[-1]
    assert said == 'Something went wrong answering that. Try again. The pipe is being closed.'
    assert a._box.shown[-1] == ('', said, False)   # not stuck on "…" with stay=True
    assert a.warm.dropped and 'BrokenPipeError' in capsys.readouterr().err   # the traceback goes to the log


def test_the_speech_step_failing_is_caught_too(capsys):
    a = app(RuntimeError("The speech model isn't ready: it downloads the first time, check your connection"))
    a.up()
    assert a.voice.said[-1].endswith("The speech model isn't ready: it downloads the first time, check your connection.")
    assert 'Traceback' in capsys.readouterr().err


def test_listen_mode_failures_are_caught_the_same_way(monkeypatch):
    a = app()
    monkeypatch.setattr(lorekeeper.games, 'current', lambda: (None, ''))
    monkeypatch.setattr(lorekeeper.icons, 'asks', lambda *a: False)
    monkeypatch.setattr(a, 'answer', lambda q, gen: 1 / 0)
    a.heard('where is Malenia')
    assert a.gen == 2 and a.voice.said == [lorekeeper.FAILED]   # a bug's message is never read out


def test_a_stale_failure_stays_silent(monkeypatch):
    a = app()

    def boom(q, gen):
        a.gen += 1   # the player pressed again meanwhile
        raise ConnectionResetError('gone')
    monkeypatch.setattr(a, 'answer', boom)
    a.up()
    assert a.voice.said == [] and all(s == 'hide' or s[1] != lorekeeper.FAILED for s in a._box.shown)


def test_the_next_press_works_after_a_failure(monkeypatch):
    a = app()
    calls = []

    def answer(q, gen):
        calls.append(q)
        if len(calls) == 1:
            raise OSError('x')
    monkeypatch.setattr(a, 'answer', answer)
    a.up()
    a.gen += 1
    a.down_at = time.time() - 1
    a.up()
    assert calls == ['where is Malenia', 'where is Malenia']


def test_only_plain_short_reasons_are_said():
    r = lorekeeper.reason
    assert r(RuntimeError('Claude Code took too long to answer.')) == 'Claude Code took too long to answer.'
    assert r(AttributeError("'NoneType' object has no attribute 'transcribe'")) == ''
    assert r(KeyError('name')) == ''
    assert r(FileNotFoundError(2, 'No such file or directory', 'C:\\Users\\x\\a.json')) == 'No such file or directory'
    assert r(RuntimeError('see https://example.com')) == '' and r(RuntimeError('x' * 200)) == ''
