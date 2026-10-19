"""Every module parses, including the ones no other test imports (lorekeeper.py, the tray app itself)."""
import glob, os
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize('path', sorted(glob.glob(os.path.join(ROOT, '*.py'))), ids=os.path.basename)
def test_module_compiles(path):
    with open(path, encoding='utf-8') as f:
        compile(f.read(), path, 'exec')
