"""app.log can be read after the fact: every line has a time, uncaught errors land in it, and neither log grows forever."""
import io, os, re, sys, tempfile, threading
os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lorekeeper  # noqa: E402

STAMP = re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ')


def test_every_line_starts_with_the_time_however_it_was_written():
    out = io.StringIO()
    s = lorekeeper.Stamped(out)
    print('game:', 'no window', file=s)   # print writes its pieces separately
    s.write('two\nlines\n')
    s.write('half a ')
    s.write('line\n')
    try:
        1 / 0
    except ZeroDivisionError:
        import traceback
        traceback.print_exc(file=s)
    lines = out.getvalue().splitlines()
    assert all(STAMP.match(l) for l in lines), lines
    assert [l[20:] for l in lines[:4]] == ['game: no window', 'two', 'lines', 'half a line']
    assert lines[-1].endswith('ZeroDivisionError: division by zero')
    assert s.getvalue == out.getvalue   # anything else is the file's own


def test_uncaught_errors_on_a_thread_reach_stderr_with_their_traceback(monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr(sys, 'stderr', lorekeeper.Stamped(out))
    monkeypatch.setattr(threading, 'excepthook', threading.excepthook)
    monkeypatch.setattr(sys, 'excepthook', sys.excepthook)
    lorekeeper.uncaught()

    def boom():
        raise RuntimeError('the hotkey thread broke')
    t = threading.Thread(target=boom, name='hotkey')
    t.start()
    t.join()
    try:
        raise ValueError('main broke')
    except ValueError:
        sys.excepthook(*sys.exc_info())
    text = out.getvalue()
    assert 'uncaught in thread hotkey:' in text and 'RuntimeError: the hotkey thread broke' in text and 'Traceback' in text
    assert 'ValueError: main broke' in text
    assert all(STAMP.match(l) for l in text.splitlines())


def test_a_big_log_keeps_its_newest_half_cut_at_a_line(tmp_path):
    p = tmp_path / 'log.jsonl'
    rows = [f'{{"n": {i}, "q": "where is the next boss"}}\n' for i in range(3000)]
    p.write_bytes(''.join(rows).encode())
    size = p.stat().st_size
    lorekeeper.trim(str(p), most=size - 1)
    kept = p.read_bytes().decode()
    assert kept.endswith(rows[-1]) and kept.splitlines()[0] in [r.strip() for r in rows]   # whole lines only
    assert size // 2 - 60 < len(kept) <= size // 2


def test_a_small_log_or_none_is_left_alone(tmp_path):
    p = tmp_path / 'app.log'
    p.write_text('one line\n', encoding='utf-8')
    lorekeeper.trim(str(p))
    lorekeeper.trim(str(tmp_path / 'missing.log'))
    assert p.read_text(encoding='utf-8') == 'one line\n'


def test_the_installed_build_writes_a_stamped_trimmed_app_log(tmp_path):
    """As PyInstaller runs it (sys.frozen): output and a thread's crash go to %APPDATA%/Lorekeeper/app.log, stamped."""
    import subprocess
    log = tmp_path / 'Lorekeeper' / 'app.log'
    log.parent.mkdir()
    log.write_bytes(b'old line\n' * 300_000)   # 2.7 MB: trimmed at startup
    code = ("import sys, threading; sys.frozen = True; sys.argv = ['Lorekeeper.exe']; import lorekeeper; print('hello'); "
            "t = threading.Thread(target=lambda: 1 / 0, name='hotkey'); t.start(); t.join()")
    env = {**os.environ, 'APPDATA': str(tmp_path), 'LOREKEEPER_DIR': str(tmp_path / 'cfg'), 'PYTHONUTF8': '1'}
    subprocess.run([sys.executable, '-c', code], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), env=env, timeout=120, check=True)
    data = log.read_bytes()
    assert len(data) < 1_100_000
    new = data.decode().split('old line\n')[-1].splitlines()
    assert new and all(STAMP.match(l) for l in new), new
    text = '\n'.join(new)
    assert '--- Lorekeeper starting' in text and 'hello' in text and 'uncaught in thread hotkey:' in text and 'ZeroDivisionError' in text
