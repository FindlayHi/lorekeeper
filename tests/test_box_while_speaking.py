"""The answer box can stay up while Lorekeeper is still talking (tray: Keep it up while talking)."""
import os, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lorekeeper  # noqa: E402


class Voice:
    def __init__(self):
        self.talking = threading.Event()

    def say(self, text):
        self.talking.set()

    def busy(self):
        return self.talking.is_set()


class Box:
    def __init__(self):
        self.calls = []

    def show(self, question='', answer='', stay=False, title=False, **_):
        self.calls.append(('show', answer, stay))

    def linger(self):
        self.calls.append(('linger',))


def app(**cfg):
    a = lorekeeper.App.__new__(lorekeeper.App)   # no mic, voice or screen: only what show_said uses
    a.cfg, a._box, a.voice, a.gen = {'box': True, 'boxWhileSpeaking': True, **cfg}, Box(), Voice(), 1
    return a


def wait_for(cond, secs=3):
    end = time.time() + secs
    while not cond() and time.time() < end:
        time.sleep(0.02)
    return cond()


def test_the_box_stays_until_the_voice_is_done_then_counts_down():
    a = app()
    a.voice.say('The Monarch drops from Killavolt.')
    a.show_said('where does the Monarch drop', 'The Monarch drops from Killavolt.')
    assert a._box.calls == [('show', 'The Monarch drops from Killavolt.', True)]
    time.sleep(0.3)
    assert ('linger',) not in a._box.calls   # still talking: no countdown yet
    a.voice.talking.clear()
    assert wait_for(lambda: ('linger',) in a._box.calls)


def test_a_new_question_takes_the_box_over():
    a = app()
    a.voice.say('A long answer.')
    a.show_said('q', 'A long answer.')
    a.gen += 1   # the hotkey went down, or listen mode heard a new question
    a.voice.talking.clear()
    time.sleep(0.5)
    assert ('linger',) not in a._box.calls


def test_off_or_silent_the_box_counts_down_as_before():
    a = app(boxWhileSpeaking=False)
    a.voice.say('Hi.')
    a.show_said('q', 'Hi.')
    b = app()   # nothing being said (a shown-only line such as "Clipped")
    b.show_said('q', 'Clipped.')
    assert a._box.calls == [('show', 'Hi.', False)] and b._box.calls == [('show', 'Clipped.', False)]
    c = app(box=False)
    c.show_said('q', 'Hi.')
    assert c._box.calls == []
