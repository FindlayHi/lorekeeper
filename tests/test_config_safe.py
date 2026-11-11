"""Settings are never lost: saved whole or not at all, and a file that won't parse is kept and reported, not silently replaced."""
import json, os, sys, tempfile
os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest  # noqa: E402
import config  # noqa: E402


@pytest.fixture
def where(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DIR', str(tmp_path))
    monkeypatch.setattr(config, 'FILE', str(tmp_path / 'config.json'))
    monkeypatch.setattr(config, 'BAD', str(tmp_path / 'config.bad.json'))
    monkeypatch.setattr(config, 'broken', '')
    return tmp_path


def test_save_then_load_keeps_only_the_changes(where):
    config.save({**config.DEFAULTS, 'hotkey': 'mouse4', 'telemetry': False})
    assert json.loads((where / 'config.json').read_text(encoding='utf-8')) == {'hotkey': 'mouse4', 'telemetry': False}
    assert config.load()['hotkey'] == 'mouse4' and not config.broken
    assert [p.name for p in where.iterdir()] == ['config.json']   # no temp file left behind


def test_a_failed_save_leaves_the_old_file_whole(where, monkeypatch):
    config.save({'hotkey': 'mouse4'})
    monkeypatch.setattr(config.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError(28, 'No space left on device')))
    with pytest.raises(OSError):
        config.save({'hotkey': 'mouse5'})
    assert config.load()['hotkey'] == 'mouse4'
    assert [p.name for p in where.iterdir()] == ['config.json']


def test_a_held_file_is_retried(where, monkeypatch):
    real, tries = os.replace, []

    def flaky(a, b):
        tries.append(1)
        if len(tries) < 3:
            raise PermissionError(13, 'in use')
        real(a, b)
    monkeypatch.setattr(config.os, 'replace', flaky)
    config.write(config.FILE, '{"hotkey": "mouse4"}')
    assert len(tries) == 3 and config.load()['hotkey'] == 'mouse4'


def test_a_broken_file_is_kept_reported_and_defaults_used(where, capsys):
    (where / 'config.json').write_text('{"hotkey": "mouse4", "telemetry": false,', encoding='utf-8')   # cut off mid-write
    cfg = config.load()
    assert cfg == config.DEFAULTS and config.broken
    assert (where / 'config.bad.json').read_text(encoding='utf-8') == '{"hotkey": "mouse4", "telemetry": false,'
    assert 'config.json unreadable' in capsys.readouterr().out
    assert 'config.bad.json' in config.BROKEN


def test_not_an_object_counts_as_broken_and_a_missing_file_does_not(where):
    assert config.load() == config.DEFAULTS and not config.broken   # first run
    (where / 'config.json').write_text('[1, 2]', encoding='utf-8')
    assert config.load() == config.DEFAULTS and config.broken


def test_a_notepad_bom_is_fine(where):
    (where / 'config.json').write_bytes('﻿{"hotkey": "mouse4"}'.encode('utf-8'))
    assert config.load()['hotkey'] == 'mouse4' and not config.broken
