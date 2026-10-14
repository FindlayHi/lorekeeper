import hashlib, io, os, sys, tempfile
os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest  # noqa: E402
import updater  # noqa: E402

GOOD = updater.DOWNLOADS + 'v9.9.9/Lorekeeper-Setup.exe'
BODY = b'MZ pretend installer' * 1000


class Resp(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def serve(monkeypatch, sha_text, body=BODY):
    """urlopen answers the .sha256 URL with sha_text and the installer URL with body."""
    def fake(req, timeout=None):
        url = req.full_url
        if url.endswith('.sha256'):
            return Resp(sha_text.encode())
        r = Resp(body)
        r.headers = {'Content-Length': str(len(body))}
        return r
    monkeypatch.setattr(updater.urllib.request, 'urlopen', fake)


def test_only_this_repos_release_assets_are_trusted():
    assert updater.trusted(GOOD)
    for bad in ('http://github.com/FindlayHi/lorekeeper/releases/download/v1/x.exe',
                'https://evil.example/FindlayHi/lorekeeper/releases/download/v1/x.exe',
                'https://github.com/FindlayHi/lorekeeper/releases/latest/x.exe',
                'https://github.com.evil.example/FindlayHi/lorekeeper/releases/download/v1/x.exe',
                'https://github.com/someone-else/lorekeeper/releases/download/v1/x.exe', '', None):
        assert not updater.trusted(bad), bad


def test_download_refuses_an_untrusted_url(monkeypatch):
    monkeypatch.setattr(updater.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('must not touch the network'))
    with pytest.raises(ValueError):
        updater.download('https://evil.example/Lorekeeper-Setup.exe')


def test_download_keeps_a_file_that_matches_its_checksum(monkeypatch):
    serve(monkeypatch, hashlib.sha256(BODY).hexdigest().upper() + '  Lorekeeper-Setup.exe\n')   # sha256sum format, any case
    path = updater.download(GOOD)
    try:
        assert open(path, 'rb').read() == BODY
        assert os.path.basename(path) == updater.ASSET
        assert os.path.basename(os.path.dirname(path)).startswith('lorekeeper-update-')   # its own folder, not a fixed temp name
    finally:
        os.remove(path)
        os.rmdir(os.path.dirname(path))


def test_download_deletes_a_file_that_does_not_match(monkeypatch):
    made = []
    real = tempfile.mkdtemp
    monkeypatch.setattr(updater.tempfile, 'mkdtemp', lambda **k: made.append(real(**k)) or made[-1])
    serve(monkeypatch, hashlib.sha256(b'something else').hexdigest())
    with pytest.raises(ValueError, match='checksum'):
        updater.download(GOOD)
    assert made and not os.path.exists(made[0])   # nothing left behind to run


@pytest.mark.parametrize('text', ['', 'not a hash', 'abc123', '<html>404</html>'])
def test_download_refuses_a_missing_or_garbled_checksum(monkeypatch, text):
    serve(monkeypatch, text)
    with pytest.raises(ValueError):
        updater.download(GOOD)


def test_installer_does_not_kill_itself():
    """The updater starts the installer as our child, so closing Lorekeeper's process tree (/T) would end the install."""
    iss = open(os.path.join(os.path.dirname(updater.__file__), 'packaging', 'lorekeeper.iss'), encoding='utf-8').read()
    kills = [line for line in iss.splitlines() if 'taskkill' in line and 'Lorekeeper.exe' in line]
    assert kills and not any(' /T' in line for line in kills)
