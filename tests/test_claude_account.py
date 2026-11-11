"""Whether Claude Code answers on the player's plan: `claude auth status` read into what the tray and first run say."""
import json, os, subprocess, sys, tempfile
os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest  # noqa: E402
import brain, firstrun  # noqa: E402


@pytest.fixture
def status(monkeypatch):
    """Set the `claude auth status` output a test wants; None means no Claude Code at all."""
    said = {'out': ''}
    monkeypatch.setattr(brain.shutil, 'which', lambda n: None if said['out'] is None else 'claude')
    monkeypatch.setattr(brain.subprocess, 'run', lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, said['out'], ''))

    def say(out):
        said['out'] = out if out is None or isinstance(out, str) else json.dumps(out)
    return say


@pytest.mark.parametrize('out, want', [
    (None, ('missing', '')),
    ({'loggedIn': False, 'authMethod': 'none'}, ('signed-out', '')),
    ({'loggedIn': True, 'authMethod': 'claude.ai', 'subscriptionType': 'max', 'email': 'p@example.com'}, ('plan', 'max')),
    ({'loggedIn': True, 'authMethod': 'claude.ai'}, ('plan', '')),
    ({'loggedIn': True, 'authMethod': 'api_key', 'apiKeySource': 'ANTHROPIC_API_KEY'}, ('api-key', 'ANTHROPIC_API_KEY')),
    ("error: unknown command 'auth'", ('unknown', '')),   # a Claude Code from before `claude auth`
    ('[]', ('unknown', '')),
])
def test_claude_state(status, out, want):
    status(out)
    assert brain.claude_state() == want


def test_the_email_never_reaches_what_the_tray_shows(status):
    status({'loggedIn': True, 'authMethod': 'claude.ai', 'subscriptionType': 'pro', 'email': 'p@example.com'})
    assert 'p@example.com' not in repr(brain.claude_state())


def test_sign_in_is_the_plan_not_console_billing(monkeypatch):
    ran = []
    monkeypatch.setattr(firstrun.subprocess, 'Popen', lambda cmd, **k: ran.append(cmd))
    firstrun.sign_in_claude()
    firstrun.install_claude()
    assert all('auth login --claudeai' in cmd[-1] for cmd in ran)
    assert '-NoExit' not in ran[0] and '-NoExit' in ran[1]   # sign-in closes itself; the installer stays so errors show


class Box:
    def __init__(self):
        self.said = []

    def show(self, *a, **k):
        self.said.append(a)


def test_the_watcher_says_signed_in_once(monkeypatch):
    states = iter([('signed-out', ''), ('plan', 'pro')])
    monkeypatch.setattr(brain, 'claude_state', lambda: next(states))
    box, done = Box(), []
    monkeypatch.setattr(firstrun.threading, 'Thread', lambda target, daemon: type('T', (), {'start': lambda self: target()})())
    firstrun.wait_for_sign_in(box, lambda: done.append(1), every=0)
    assert box.said == [('Claude Code', 'Signed in (Pro). Hold the hotkey in a game and ask.')]
    assert done == [1] and not firstrun._watching.is_set()
