"""The audit's wasted work: lookups queued behind each other's timeouts, an AI started for a tap, files re-read every
two seconds, walkthrough text fetched again each run, and unchanged frames encoded again each second."""
import json, os, sys, tempfile, threading, time
os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest  # noqa: E402
from PIL import Image  # noqa: E402
import capture, config, games, lookup, lorekeeper, romm  # noqa: E402


# the wiki lookup: one deadline

@pytest.fixture
def wiki(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DIR', str(tmp_path))
    monkeypatch.setattr(lookup, 'HOSTS', str(tmp_path / 'wikis.json'))
    monkeypatch.setattr(lookup, 'FIND_SECS', 0.4)
    monkeypatch.setattr(lookup, 'WIKI_SECS', 0.8)
    monkeypatch.setattr(lookup, 'page', lambda url, question='', most=5000: 'text of ' + url)
    monkeypatch.setattr(lookup, 'strategywiki', lambda q, game: '')
    monkeypatch.setattr(lookup, 'search', lambda q: [])
    monkeypatch.setattr(lookup, 'guess_host', lambda game: '')
    return monkeypatch


def slow(secs, result):
    def fn(*a, **k):
        time.sleep(secs)
        return result
    return fn


def test_the_lookups_run_side_by_side(wiki):
    wiki.setattr(lookup, 'site_search', slow(0.25, ['https://terraria.wiki.gg/wiki/Zenith']))
    wiki.setattr(lookup, 'strategywiki', slow(0.25, 'https://strategywiki.org/wiki/Terraria/Bosses'))
    wiki.setattr(lookup, 'page', slow(0.25, 'text'))
    t = time.time()
    out = lookup.wiki('how do I beat the Moon Lord with the Zenith', 'Terraria')
    assert out.count('Source: ') == 2 and time.time() - t < 0.7   # one after another: 1 s


def test_a_slow_wiki_is_given_up_on_at_the_deadline(wiki):
    wiki.setattr(lookup, 'site_search', slow(5, ['https://terraria.wiki.gg/wiki/Zenith']))
    wiki.setattr(lookup, 'strategywiki', slow(5, 'https://strategywiki.org/wiki/Terraria/Bosses'))
    t = time.time()
    assert lookup.wiki('how do I beat the Moon Lord', 'Terraria') == ''   # the model searches instead
    assert time.time() - t < 1.5


def test_a_slow_page_is_left_out_and_the_quick_one_kept(wiki):
    wiki.setattr(lookup, 'site_search', lambda *a: ['https://terraria.wiki.gg/wiki/Zenith', 'https://terraria.wiki.gg/wiki/Slow'])
    wiki.setattr(lookup, 'page', lambda url, question='', most=5000: (time.sleep(5 if 'Slow' in url else 0), 'text')[1])
    t = time.time()
    assert lookup.wiki('what does the Zenith do', 'Terraria') == 'Source: https://terraria.wiki.gg/wiki/Zenith\ntext'
    assert time.time() - t < 1.5


def test_a_known_wiki_that_answers_is_not_also_searched_on_the_web(wiki):
    web = []
    wiki.setattr(lookup, 'search', lambda q: web.append(q) or [])
    wiki.setattr(lookup, 'site_search', lambda *a: ['https://terraria.wiki.gg/wiki/Zenith'])
    assert lookup.wiki('what does the Zenith do', 'Terraria') and web == []
    wiki.setattr(lookup, 'site_search', lambda *a: [])   # it found nothing: now the web is asked
    lookup.wiki('what does the Zenith do', 'Terraria')
    assert len(web) == 1


def test_an_unknown_games_wiki_is_learned_from_the_web_search_while_the_guess_runs(wiki):
    wiki.setattr(lookup, 'guess_host', slow(0.2, ''))
    wiki.setattr(lookup, 'search', lambda q: ['https://newgame.wiki.gg/wiki/Sword', 'https://forum.example/t/1'])
    assert lookup.wiki('what does the Sword do', 'Newgame').startswith('Source: https://newgame.wiki.gg/wiki/Sword')
    time.sleep(0.4)   # the guess comes back empty-handed, later
    assert lookup.known_host('Newgame') == 'newgame.wiki.gg'


# StrategyWiki: kept on disk

def test_strategywiki_text_is_fetched_once_and_kept_for_the_next_run(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DIR', str(tmp_path))
    monkeypatch.setattr(lookup, '_sw_pages', {})
    monkeypatch.setattr(lookup, '_sw_text', {})
    titles = [f'Chrono Trigger/Chapter {i}' for i in range(120)]
    asked = []

    def get(url, timeout=4):
        asked.append(url)
        if 'list=allpages' in url:
            return json.dumps({'query': {'allpages': [{'title': t} for t in titles]}})
        got = [t for t in titles if t.replace(' ', '%20').replace('/', '%2F') in url or t in lookup.urllib.parse.unquote(url)]
        return json.dumps({'query': {'pages': {str(i): {'title': t, 'revisions': [{'slots': {'main': {'*': 'The Masamune is on Denadoro' if t.endswith(' 77') else 'nothing'}}}]}
                                               for i, t in enumerate(got)}}})
    monkeypatch.setattr(lookup, 'get', get)
    want = 'https://strategywiki.org/wiki/Chrono_Trigger/Chapter_77'
    assert lookup.strategywiki('where is the Masamune', 'Chrono Trigger') == want
    assert len(asked) == 4   # the list of pages, then their text in three batches
    monkeypatch.setattr(lookup, '_sw_pages', {})   # the app restarted
    monkeypatch.setattr(lookup, '_sw_text', {})
    assert lookup.strategywiki('where is the Masamune', 'Chrono Trigger') == want
    assert len(asked) == 4


def test_a_failed_batch_is_asked_for_again_not_remembered_as_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DIR', str(tmp_path))
    monkeypatch.setattr(lookup, '_sw_pages', {'Chrono Trigger': ['Chrono Trigger/Chapter 1']})
    monkeypatch.setattr(lookup, '_sw_text', {})
    monkeypatch.setattr(lookup, 'get', lambda url, timeout=4: (_ for _ in ()).throw(OSError('timed out')))
    with pytest.raises(OSError):
        lookup.strategywiki('where is the Masamune', 'Chrono Trigger')
    assert 'Chrono Trigger' not in lookup._sw_text


# a tap

class Warm:
    def __init__(self):
        self.started, self.dropped = [], 0

    def prime(self, model, spoilers, wanted=lambda: True):
        if wanted():
            self.started.append(model)

    def drop(self):
        self.dropped += 1


class Ears:
    def start(self):
        pass

    def stop(self):
        return None

    def text(self, audio, hint=''):
        return ''


class Voice:
    def stop(self):
        pass

    def say(self, text):
        pass

    def busy(self):
        return False


def pressed(monkeypatch):
    monkeypatch.setattr(lorekeeper.games, 'current', lambda: (None, ''))
    a = lorekeeper.App.__new__(lorekeeper.App)
    a.cfg = {**config.DEFAULTS, 'box': False, 'screen': False}
    a._box, a.voice, a.warm, a.ears = None, Voice(), Warm(), Ears()
    a.gen, a.down_at, a.let_go, a.game, a._pin, a.looking = 0, 0, 0, None, None, None
    a.listener = type('L', (), {'on': False})()
    a.hint = lambda: ''
    a.look = lambda *_: None
    a.down()
    return a


def test_a_tap_starts_no_ai(monkeypatch):
    a = pressed(monkeypatch)
    time.sleep(0.1)
    a.up()   # let go at once: it only silenced the voice
    time.sleep(lorekeeper.TAP + 0.2)
    assert a.warm.started == []


def test_holding_the_key_still_starts_it_ahead(monkeypatch):
    a = pressed(monkeypatch)
    time.sleep(lorekeeper.TAP + 0.2)   # still held, still talking
    assert a.warm.started == ['haiku']


def test_esc_while_held_starts_none_either(monkeypatch):
    a = pressed(monkeypatch)
    a.cancel()
    time.sleep(lorekeeper.TAP + 0.2)
    assert a.warm.started == []


# files asked for every two seconds

def test_a_file_is_parsed_again_only_when_it_changes(tmp_path, monkeypatch):
    f = tmp_path / 'games.json'
    f.write_text('[{"name": "Hades"}]')
    parsed = []
    real = json.load
    monkeypatch.setattr(config.json, 'load', lambda fh: parsed.append(1) or real(fh))
    for _ in range(5):
        assert config.read_json(str(f)) == [{'name': 'Hades'}]
    assert len(parsed) == 1
    f.write_text('[{"name": "Hades"}, {"name": "Hades II"}]')   # edited by hand, or by another Lorekeeper
    assert len(config.read_json(str(f))) == 2 and len(parsed) == 2
    f.unlink()
    with pytest.raises(OSError):
        config.read_json(str(f))


def test_our_own_writes_are_seen_at_once(tmp_path, monkeypatch):
    monkeypatch.setattr(games, 'PIN', str(tmp_path / 'pinned.json'))
    monkeypatch.setattr(config, 'DIR', str(tmp_path))
    monkeypatch.setattr(config, 'FILE', str(tmp_path / 'config.json'))
    for name in ('Hades', 'Hadez', 'Hadex'):   # the same size, written within one tick of the clock
        games.pin({'name': name})
        assert games.pinned()['game']['name'] == name
    games.unpin()
    assert games.pinned() is None
    for key in ('mouse4', 'mouse5'):
        config.save({**config.DEFAULTS, 'hotkey': key})
        assert config.load()['hotkey'] == key
    cfg = config.load()
    cfg['hotkey'] = 'changed by the caller'
    assert config.load()['hotkey'] == 'mouse5'   # each caller gets its own copy of the settings


def test_the_romm_token_is_not_read_from_the_credential_store_on_every_poll(monkeypatch):
    reads = []
    ring = type('Ring', (), {'get_password': lambda self, *a: reads.append(a) or 'tok', 'delete_password': lambda self, *a: None})()
    monkeypatch.setitem(sys.modules, 'keyring', ring)
    monkeypatch.setattr(romm, '_token', [0, ''])
    assert [romm.token() for _ in range(10)] == ['tok'] * 10 and len(reads) == 1
    romm.forget()
    monkeypatch.setattr(ring, 'get_password', lambda *a: None, raising=False)
    assert romm.token() == ''   # disconnected: not remembered past that


# unchanged frames

class NoThread:
    def __init__(self, *a, **kw):
        pass

    def start(self):
        pass


@pytest.fixture
def screen(monkeypatch):
    monkeypatch.setattr(capture.threading, 'Thread', NoThread)   # the test drives tick()
    s = capture.Screen(long_every=3)
    encoded = []
    real = capture.jpeg
    monkeypatch.setattr(capture, 'jpeg', lambda img, wide=capture.WIDE: encoded.append(wide) or real(img, wide))
    s.encoded = encoded
    return s


def test_an_unchanged_screen_is_kept_without_encoding_it_again(screen):
    shots = iter([Image.new('RGB', (64, 36), 'red')] + [capture.SAME] * 7)
    screen._grab = lambda: next(shots)
    for t in range(100, 108):
        screen.tick(t)
    assert screen.encoded == [capture.WIDE, capture.LONG_WIDE]   # the one real frame, at its two sizes
    assert [t for t, _ in screen.recent] == [103, 104, 105, 106, 107] and len({data for _, data in screen.recent}) == 1
    assert [t for t, _ in screen.long] == [100, 103, 106] and len({data for _, data in screen.long}) == 1


def test_a_change_between_long_frames_is_not_lost(screen):
    red, blue = Image.new('RGB', (64, 36), 'red'), Image.new('RGB', (64, 36), 'blue')
    shots = iter([red, blue, capture.SAME, capture.SAME])
    screen._grab = lambda: next(shots)
    for t in range(100, 104):
        screen.tick(t)
    first, second = (Image.open(capture.io.BytesIO(data)).getpixel((5, 5)) for _, data in screen.long)
    assert first[0] > 200 and second[2] > 200   # the long frame at 103 shows the blue screen, not the red one again


def test_the_key_down_grab_reuses_the_last_frame_when_nothing_changed(screen):
    shots = iter([Image.new('RGB', (64, 36), 'red'), capture.SAME])
    screen._grab = lambda: next(shots)
    screen.tick(100)
    del screen.encoded[:]
    frames = screen.now()
    assert screen.encoded == [] and frames[-1][1] == frames[0][1] and screen.full.size == (64, 36)


def test_a_frame_grabbed_at_key_down_is_what_unchanged_means_next(screen):
    red, blue = Image.new('RGB', (64, 36), 'red'), Image.new('RGB', (64, 36), 'blue')
    shots = iter([red, blue, capture.SAME])
    screen._grab = lambda: next(shots)
    screen.tick(100)
    screen.now()        # the screen had turned blue; this grab is sent with the question, not kept
    screen.tick(101)    # "nothing changed" since that grab
    assert Image.open(capture.io.BytesIO(screen.recent[-1][1])).getpixel((5, 5))[2] > 200


def test_nothing_is_kept_from_before_a_forget(screen):
    shots = iter([Image.new('RGB', (64, 36), 'red'), capture.SAME])
    screen._grab = lambda: next(shots)
    screen.tick(100)
    screen.forget()     # Use the screen was switched off
    screen.tick(101)
    assert not screen.recent and not screen.long
