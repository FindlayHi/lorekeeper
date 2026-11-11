import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import commands, listen  # noqa: E402

FRAME = listen.FRAME


def test_wake_word():
    assert listen.wake('Lorekeeper, what does this do?') == 'what does this do?'
    assert listen.wake('Hey Lore Keeper what synergy did I just get') == 'what synergy did I just get'
    assert listen.wake('Lord Keeper. Who is Ranni?') == 'Who is Ranni?'
    assert listen.wake('Lorekeeper.') == ''
    assert listen.wake('push left, I got the boss') is None
    assert listen.wake('the goalkeeper was great') is None


def frames(level, n, seed=0):
    rng = np.random.default_rng(seed)
    return [(rng.standard_normal(FRAME) * level).astype('float32') for _ in range(n)]


def test_segmenter_finds_one_utterance_in_noise():
    seg = listen.Segmenter()
    out = [seg.feed(f) for f in frames(0.002, 60) + frames(0.1, 40, 1) + frames(0.002, 40, 2)]
    clips = [c for c in out if c is not None]
    assert len(clips) == 1
    assert 40 * FRAME <= len(clips[0]) <= 60 * FRAME   # the speech, a little lead-in, little tail


def test_segmenter_ignores_a_click_and_adapts_to_hum():
    seg = listen.Segmenter()
    hum = frames(0.01, 700)   # a loud fan, longer than the 15 s cap: never an utterance
    assert all(seg.feed(f) is None for f in hum[:100] + frames(0.2, 2, 3) + hum[100:])
    assert seg.cur is None
    out = [seg.feed(f) for f in frames(0.15, 40, 4) + frames(0.01, 40, 5)]   # speech over the fan still counts
    assert sum(c is not None for c in out) == 1


def test_listen_commands():
    assert commands.parse('Stop listening.') == ('listen_off', '')
    assert commands.parse('listen mode on') == ('listen_on', '')


class Stream:
    opened = []

    def __init__(self, **kw):
        if Mic.broken:
            raise OSError('no such mic')
        self.kw, self.live = kw, False
        Stream.opened.append(self)

    def start(self):
        self.live = True

    def stop(self):
        self.live = False

    def close(self):
        pass


class Mic:
    broken = False
    mic = ''   # Windows' default: ears.device() needs no sounddevice for it


def listener(monkeypatch, front):
    monkeypatch.setitem(sys.modules, 'sounddevice', type(sys)('sounddevice'))
    sys.modules['sounddevice'].InputStream = Stream
    Stream.opened, Mic.broken = [], False
    return listen.Listener(Mic(), lambda q: None, lambda: False, front=lambda: front[0], grace_s=10)


def test_listen_mode_opens_the_mic_only_while_a_game_is_in_front(monkeypatch):
    front = [False]
    li = listener(monkeypatch, front)
    li.start()
    assert li.on and not li.hearing   # switched on at the desktop: the mic stays shut
    li.tick(100)
    assert not li.hearing
    front[0] = True
    li.tick(102)
    assert li.hearing and Stream.opened[-1].live
    front[0] = False
    li.tick(104)
    li.tick(110)
    assert li.hearing   # a quick alt-tab: not closed yet
    front[0] = True
    li.tick(112)
    front[0] = False
    li.tick(114)
    li.tick(122)
    assert li.hearing   # the grace starts over from the last time the game left
    li.tick(124)
    assert not li.hearing and not Stream.opened[-1].live and li.on   # closed, but listen mode is still on
    assert len(Stream.opened) == 1
    front[0] = True
    li.tick(126)
    assert li.hearing and len(Stream.opened) == 2
    li.stop()
    assert not li.on and not li.hearing and not Stream.opened[-1].live
    li.tick(128)
    assert not li.hearing   # off: a game in front doesn't open it


def test_changing_the_mic_reopens_in_a_game_and_waits_outside_one(monkeypatch):
    front = [True]
    li = listener(monkeypatch, front)
    li.start()
    assert li.hearing
    li.stop()
    li.start()   # the tray's use_mic
    assert li.on and li.hearing and len(Stream.opened) == 2 and not Stream.opened[0].live
    front[0] = False
    li.stop()
    li.start()
    assert li.on and not li.hearing


def test_a_mic_that_fails_to_open_is_logged_and_tried_on_the_next_game(monkeypatch, capsys):
    front = [False]
    li = listener(monkeypatch, front)
    li.start()
    Mic.broken, front[0] = True, True
    li.tick(100)
    li.tick(102)   # still the same game: not retried every tick
    assert not li.hearing and li.on and capsys.readouterr().out.count('mic:') == 1
    Mic.broken, front[0] = False, False
    li.tick(104)
    front[0] = True
    li.tick(106)
    assert li.hearing
