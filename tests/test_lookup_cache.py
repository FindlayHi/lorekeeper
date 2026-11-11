import json, os, sys, tempfile, time
os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest  # noqa: E402
import config, icons, lookup, telemetry  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DIR', str(tmp_path))
    monkeypatch.setattr(lookup, 'HOSTS', str(tmp_path / 'wikis.json'))
    monkeypatch.setattr(lookup, 'guess_host', lambda game: '')
    return tmp_path


def with_cart(monkeypatch, host):
    monkeypatch.setattr(icons, 'cart', lambda game, folder: {'host': host} if host else None)


# 1. the cart's wiki host

def test_the_cart_host_beats_known_and_learned(home, monkeypatch):
    with_cart(monkeypatch, 'terraria-new.wiki.gg')
    (home / 'wikis.json').write_text('{"terraria": "old.wiki.gg"}')
    assert lookup.host_for('Terraria', folder=str(home)) == 'terraria-new.wiki.gg'
    assert lookup.host_for('Terraria') == 'terraria.wiki.gg'   # no folder, no cart: KNOWN as before


@pytest.mark.parametrize('host', ['evil.example', 'evil.example?x=.fandom.com', '', None, 5])
def test_a_cart_host_we_cannot_serve_is_skipped(home, monkeypatch, host):
    with_cart(monkeypatch, host)
    assert lookup.host_for('Terraria', folder=str(home)) == 'terraria.wiki.gg'


def test_wiki_passes_its_folder_to_host_for(monkeypatch):
    seen = []
    monkeypatch.setattr(lookup, 'host_for', lambda game, urls=(), folder='': seen.append(folder) or '')
    monkeypatch.setattr(lookup, 'search', lambda q: [])
    lookup.wiki('q', 'Game', folder='/some/folder')
    assert seen == ['/some/folder']


# 2. a failed guess expires

def test_a_failed_guess_is_not_retried_for_a_week(home, monkeypatch):
    calls = []
    monkeypatch.setattr(lookup, 'guess_host', lambda game: calls.append(game) or '')
    assert lookup.host_for('Nogame') == '' and lookup.host_for('Nogame') == ''
    assert calls == ['Nogame']
    h = json.loads((home / 'wikis.json').read_text())
    assert h['nogame'] == '' and all(isinstance(v, str) for v in h.values())   # an older app still reads it
    h[lookup.TRIED + 'nogame'] = str(int(time.time()) - 8 * 24 * 3600)
    (home / 'wikis.json').write_text(json.dumps(h))
    monkeypatch.setattr(lookup, 'guess_host', lambda game: 'nogame.wiki.gg')
    assert lookup.host_for('Nogame') == 'nogame.wiki.gg'
    assert lookup.TRIED + 'nogame' not in json.loads((home / 'wikis.json').read_text())


def test_a_legacy_empty_host_is_expired(home, monkeypatch):
    (home / 'wikis.json').write_text('{"oldgame": ""}')
    monkeypatch.setattr(lookup, 'guess_host', lambda game: 'oldgame.wiki.gg')
    assert lookup.host_for('Oldgame') == 'oldgame.wiki.gg'


# 3. the disk cache

def test_a_page_is_fetched_once_then_read_from_disk(home, monkeypatch):
    seen = []
    monkeypatch.setattr(lookup, 'get', lambda url, timeout=4: seen.append(url) or '{"parse": {"wikitext": {"*": "Zenith text"}}}')
    assert lookup.page('https://terraria.wiki.gg/wiki/Zenith') == lookup.page('https://terraria.wiki.gg/wiki/Zenith') == 'Zenith text'
    assert len(seen) == 1 and len(os.listdir(home / 'cache')) == 1


def test_entries_expire_and_search_is_shorter_than_pages(home, monkeypatch):
    seen = []
    monkeypatch.setattr(lookup, 'get', lambda url, timeout=4: seen.append(url) or 'x')
    lookup.cached('https://a.wiki.gg/api.php?q=1', lookup.SEARCH_TTL)
    f = home / 'cache' / os.listdir(home / 'cache')[0]
    os.utime(f, (time.time() - 2 * 3600,) * 2)
    lookup.cached('https://a.wiki.gg/api.php?q=1', lookup.PAGE_TTL)   # 2 h old: fine for a page
    assert len(seen) == 1
    lookup.cached('https://a.wiki.gg/api.php?q=1', lookup.SEARCH_TTL)   # too old for a search
    assert len(seen) == 2


def test_a_corrupt_entry_is_a_miss(home, monkeypatch):
    monkeypatch.setattr(lookup, 'get', lambda url, timeout=4: 'fresh')
    lookup.cached('https://a.wiki.gg/p', 99)
    f = home / 'cache' / os.listdir(home / 'cache')[0]
    f.write_bytes(b'\xff\xfe\x00bad')
    assert lookup.cached('https://a.wiki.gg/p', 99) == 'fresh'
    f.write_text('')
    assert lookup.cached('https://a.wiki.gg/p', 99) == 'fresh'


def test_the_cache_keeps_about_two_hundred_files(home, monkeypatch):
    monkeypatch.setattr(lookup, 'get', lambda url, timeout=4: 'x')
    monkeypatch.setattr(lookup, 'CACHE_FILES', 5)
    for i in range(9):
        lookup.cached(f'https://a.wiki.gg/p{i}', 99)
    assert len(os.listdir(home / 'cache')) == 5


def test_an_uncached_fetch_is_still_vetted(home, monkeypatch):
    monkeypatch.setattr(lookup._opener, 'open', lambda *a, **k: pytest.fail('must not be fetched'))
    with pytest.raises(ValueError):
        lookup.cached('https://127.0.0.1/api.php', 99)


# 4. the User-Agent

def test_api_calls_say_who_they_are_and_pages_keep_the_browser_agent():
    assert lookup.agent('https://terraria.wiki.gg/api.php?action=query') == f'Lorekeeper/{telemetry.VERSION} (+https://lorekeeper-cgv.pages.dev/)'
    assert lookup.agent('https://bg3.wiki/w/api.php?x=1').startswith('Lorekeeper/')
    assert lookup.agent('https://terraria.wiki.gg/wiki/Zenith') == lookup.UA
    assert lookup.agent('https://html.duckduckgo.com/html/?q=api.php') == lookup.UA


def test_get_sends_that_agent(monkeypatch):
    monkeypatch.setattr(lookup, 'check_url', lambda url: None)
    sent = []
    class R:
        def read(self): return b'ok'
    monkeypatch.setattr(lookup._opener, 'open', lambda req, timeout=4: sent.append(req.get_header('User-agent')) or R())
    lookup.get('https://x.wiki.gg/api.php')
    lookup.get('https://x.wiki.gg/wiki/A')
    assert sent[0].startswith('Lorekeeper/') and sent[1] == lookup.UA
