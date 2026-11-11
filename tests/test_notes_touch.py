"""Opening a game's notes from the tray makes the file with its heading only: no "notes opened" line for the AI to read."""
import os, sys, tempfile
os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import notes  # noqa: E402

GAME = {'name': 'Elden Ring'}


def test_touch_makes_a_heading_only_file_that_reads_as_no_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(notes, 'FOLDER', str(tmp_path / 'games'))
    p = notes.touch(GAME)
    assert p == notes.path(GAME) and open(p, encoding='utf-8').read() == '# Elden Ring\n\n'
    assert notes.read(GAME) == '' and notes.names(GAME) == []


def test_touch_leaves_existing_notes_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(notes, 'FOLDER', str(tmp_path / 'games'))
    notes.add(GAME, 'just beat Margit')
    notes.touch(GAME)
    notes.add(GAME, 'Sorcerer build')
    text = open(notes.path(GAME), encoding='utf-8').read()
    assert text.count('# Elden Ring') == 1
    lines = notes.read(GAME).splitlines()
    assert len(lines) == 2 and lines[0].endswith('just beat Margit') and lines[1].endswith('Sorcerer build')


def test_the_tray_no_longer_writes_a_notes_opened_line():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lorekeeper.py'), encoding='utf-8').read()
    assert 'notes opened' not in src and src.count('notes.touch(app.game)') == 2
