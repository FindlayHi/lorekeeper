import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hotkey  # noqa: E402

CTRL, ALT, SHIFT, WIN, SPACE, ESC, M4 = 0xA2, 0xA4, 0xA0, 0x5B, 0x20, 0x1B, 0x05


class Keyboard:
    """A fake keyboard: what the hook is told (send) and what Windows says is down (phys) can differ, as when a release goes to the lock screen."""

    def __init__(self, target):
        self.target, self.phys = target, set()

    def __call__(self, vk, up=False):
        r = self.target(vk, up)   # inside the hook the key's own state hasn't changed yet
        (self.phys.discard if up else self.phys.add)(vk)
        return r


def make(combo, active=True, kb=None):
    ev = []
    h = hotkey.Hotkey(combo, lambda: ev.append('down'), lambda: ev.append('up'), lambda: ev.append('cancel'), lambda: active)
    h._fire = lambda f, *a: f(*a)   # no threads in tests
    kb = kb or Keyboard(h._event)
    h.is_down = kb.phys.__contains__
    return h, ev, kb


def test_parse_and_names():
    assert hotkey.parse('ctrl+alt+space') == ({'ctrl', 'alt'}, SPACE)
    assert hotkey.parse('mouse4') == (set(), M4)
    assert hotkey.name({'alt', 'ctrl'}, SPACE) == 'ctrl+alt+space'
    assert hotkey.pretty('ctrl+alt+space') == 'Ctrl+Alt+Space' and hotkey.pretty('mouse5') == 'Mouse 5' and hotkey.pretty('f13') == 'F13'


def test_combo_fires_and_swallows():
    h, ev, k = make('ctrl+alt+space')
    assert not k(CTRL) and not k(ALT)
    assert k(SPACE) and k(SPACE)   # repeat swallowed too
    assert k(SPACE, True)
    assert ev == ['down', 'up']
    k(ALT, True)
    assert not k(SPACE)   # ctrl+space alone: not ours


def test_not_in_game_passes_through():
    h, ev, k = make('ctrl+alt+space', active=False)
    k(CTRL), k(ALT)
    assert not k(SPACE) and not k(SPACE, True) and ev == []


def test_mouse_button_allows_shift_held():
    h, ev, k = make('mouse4')
    k(SHIFT)   # sprinting with shift
    assert k(M4) and k(M4, True) and ev == ['down', 'up']


def test_record_new_hotkey():
    h, _, k = make('ctrl+alt+space')
    got = []
    h.recording = got.append
    k(CTRL)
    assert k(ord('Q')) and k(ord('Q'), True)   # the press and its release are swallowed
    assert got == ['ctrl+q'] and h.combo == 'ctrl+q'
    k(CTRL, True)
    h.recording = got.append
    assert not k(0x01)   # left click ignored while recording
    assert k(M4) and got[-1] == 'mouse4'


def test_stuck_win_after_lock_screen():
    """Win+L: the hook sees Win go down, the lock screen gets its release. The hotkey still works after unlocking."""
    h, ev, k = make('ctrl+alt+space')
    k(WIN), k(ord('L'))
    k.phys.clear()   # released on the secure desktop: no up events reach us
    k(CTRL), k(ALT)
    assert k(SPACE) and k(SPACE, True) and ev == ['down', 'up']


def test_stuck_shift_after_task_manager():
    """Ctrl+Shift+Esc: Task Manager (admin) gets the Ctrl and Shift releases."""
    h, ev, k = make('ctrl+alt+space')
    k(CTRL), k(SHIFT), k(ESC)
    k.phys.clear()
    k(CTRL), k(ALT)
    assert k(SPACE) and ev == ['down']


def test_record_ignores_stuck_modifier():
    h, _, k = make('ctrl+alt+space')
    k(SHIFT)
    k.phys.discard(SHIFT)
    got = []
    h.recording = got.append
    k(ord('Q'))
    assert got == ['q']


def test_held_extra_modifier_still_blocks():
    h, ev, k = make('ctrl+alt+space')
    k(CTRL), k(ALT), k(SHIFT)   # really held: ctrl+alt+shift+space is someone else's
    assert not k(SPACE) and ev == []
    k(SHIFT, True)
    k(SPACE, True)
    assert k(SPACE) and ev == ['down']


def test_extra_modifier_seen_by_windows_but_not_us_still_blocks():
    """The real keyboard decides both ways: a modifier down that the hook missed still counts."""
    h, ev, k = make('ctrl+alt+space')
    k(CTRL), k(ALT)
    k.phys.add(WIN)
    assert not k(SPACE) and ev == []


def test_esc_while_held_cancels():
    h, ev, k = make('ctrl+alt+space')
    k(CTRL), k(ALT), k(SPACE)
    assert k(ESC) and ev == ['down', 'cancel'] and not h.held
    assert not k(SPACE, True)   # the release after a cancel is the game's again


def two():
    """The talk key and the listen key on one dispatcher, sharing one fake keyboard."""
    talk, tev, _ = make('ctrl+alt+space')
    listen, lev, _ = make('ctrl+alt+l')
    hooks = hotkey.Hooks(talk, listen)
    k = Keyboard(hooks.event)
    talk.is_down = listen.is_down = k.phys.__contains__
    return hooks, talk, tev, listen, lev, k


def test_one_dispatcher_serves_both():
    hooks, talk, tev, listen, lev, k = two()
    k(CTRL), k(ALT)
    assert k(SPACE) and k(SPACE) and k(SPACE)   # key repeat while held: swallowed
    assert k(SPACE, True) and tev == ['down', 'up'] and lev == []
    assert k(ord('L')) and k(ord('L'), True) and lev == ['down', 'up'] and tev == ['down', 'up']
    assert not k(ord('Q')) and not k(ord('Q'), True)   # anything else reaches the game


def test_esc_cancels_through_dispatcher():
    hooks, talk, tev, listen, lev, k = two()
    k(CTRL), k(ALT), k(SPACE)
    assert k(ESC) and tev == ['down', 'cancel'] and lev == []


def test_recording_one_does_not_fire_the_other():
    hooks, talk, tev, listen, lev, k = two()
    got = []
    talk.record(got.append)
    k(CTRL), k(ALT)
    assert k(ord('L')) and k(ord('L'), True)   # the listen key's combo, typed as the new talk key
    assert got == ['ctrl+alt+l'] and talk.combo == 'ctrl+alt+l' and lev == [] and tev == []


def test_recording_listen_key_while_talk_is_first():
    hooks, talk, tev, listen, lev, k = two()
    got = []
    listen.record(got.append)
    k(CTRL), k(ALT)
    assert k(SPACE) and k(SPACE, True)   # the talk combo, typed as the new listen key: talk must not start
    assert got == ['ctrl+alt+space'] and tev == [] and lev == []


def test_mouse_hook_wanted_by_any_binding():
    hooks, talk, tev, listen, lev, k = two()
    assert not hooks.wants_mouse()
    listen.set('mouse5')
    assert hooks.wants_mouse()


def test_rehook_waits_while_held_or_recording():
    hooks, talk, tev, listen, lev, k = two()
    assert hooks.tick()
    k(CTRL), k(ALT), k(SPACE)
    assert not hooks.tick() and tev == ['down']   # mid-question: leave the hook alone
    k(SPACE, True)
    assert hooks.tick()
    listen.record(lambda c: None)
    assert not hooks.tick()


def test_stuck_hold_is_cancelled_by_the_timer():
    """Win+L while holding the talk key: its release is never seen. The timer cancels it rather than asking."""
    hooks, talk, tev, listen, lev, k = two()
    k(CTRL), k(ALT), k(SPACE)
    now = talk.held_at
    assert not hooks.tick(now + 10) and tev == ['down']   # a long question is fine
    assert hooks.tick(now + hotkey.STUCK_SECONDS + 1) and tev == ['down', 'cancel'] and not talk.held
