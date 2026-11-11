"""A hung `claude -p` is killed and said plainly; one that keeps streaming is left alone."""
import io, json, os, queue, sys, tempfile, threading, time
os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest  # noqa: E402
import brain  # noqa: E402


class Proc:
    """A `claude -p` stand-in: stdout blocks until a line is put or it's killed, as a real pipe does."""

    def __init__(self):
        self.lines, self.returncode, self.killed = queue.Queue(), None, False
        self.stdin, self.errors = io.StringIO(), io.StringIO()
        self.stdout = iter(self.lines.get, None)

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):   # what brain.stop does to the process tree: the pipe closes and the read ends
        self.killed, self.returncode = True, 1
        self.lines.put(None)


def delta(text):
    return json.dumps({'type': 'stream_event', 'event': {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': text}}}) + '\n'


@pytest.fixture
def limits(monkeypatch):
    monkeypatch.setattr(brain, 'stop', lambda p: p.poll() is None and p.kill())
    monkeypatch.setattr(brain, 'IDLE_SECS', 0.3)
    monkeypatch.setattr(brain, 'ASK_SECS', 5)


def test_the_limits_are_a_minute_quiet_and_two_and_a_half_in_all():
    assert (brain.IDLE_SECS, brain.ASK_SECS) == (60, 150)


def test_silence_kills_it_and_says_so(limits):
    p = Proc()
    t = time.time()
    assert brain.ask(p, 'where is Malenia') == ('Claude Code took too long to answer.', 0)
    assert p.killed and time.time() - t < 3


def test_steady_streaming_is_never_cut_off(limits):
    p = Proc()

    def talk():
        for w in ['Malenia ', 'waits ', 'in ', 'the ', 'Haligtree.']:
            time.sleep(0.15)   # each gap under the idle limit, all of them well over it
            p.lines.put(delta(w))
        p.lines.put(json.dumps({'type': 'result', 'result': 'Malenia waits in the Haligtree.', 'total_cost_usd': 0.01}) + '\n')
        p.returncode = 0
        p.lines.put(None)
    threading.Thread(target=talk, daemon=True).start()
    heard = []
    assert brain.ask(p, 'where is Malenia', on_text=heard.append) == ('Malenia waits in the Haligtree.', 0.01)
    assert not p.killed and heard[-1] == 'Malenia waits in the Haligtree.'


def test_an_answer_that_never_ends_is_cut_at_the_total_limit(limits, monkeypatch):
    monkeypatch.setattr(brain, 'ASK_SECS', 0.8)
    p = Proc()
    stop = threading.Event()

    def babble():
        while not stop.is_set() and not p.killed:
            p.lines.put(delta('and '))
            time.sleep(0.05)
    threading.Thread(target=babble, daemon=True).start()
    t = time.time()
    try:
        assert brain.ask(p, 'tell me everything') == ('Claude Code took too long to answer.', 0)
    finally:
        stop.set()
    assert p.killed and 0.7 < time.time() - t < 3
