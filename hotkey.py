"""Hold-to-talk hotkey through low-level keyboard and mouse hooks (WH_KEYBOARD_LL, WH_MOUSE_LL): they fire in
exclusive-fullscreen games too. Any key or mouse side button, with or without modifiers; set it from the tray.
If a game runs as administrator, Lorekeeper must too, or Windows keeps that game's input from it."""
import ctypes, sys, threading, time

VK = {'space': 0x20, 'esc': 0x1B, 'tab': 0x09, 'enter': 0x0D, 'backspace': 0x08, 'capslock': 0x14, '`': 0xC0, 'backquote': 0xC0,
      'insert': 0x2D, 'delete': 0x2E, 'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22, 'pause': 0x13, 'scrolllock': 0x91,
      'mouse3': 0x04, 'mouse4': 0x05, 'mouse5': 0x06,
      **{f'f{i}': 0x6F + i for i in range(1, 25)}, **{f'num{i}': 0x60 + i for i in range(10)},
      '-': 0xBD, '=': 0xBB, '[': 0xDB, ']': 0xDD, ';': 0xBA, "'": 0xDE, ',': 0xBC, '.': 0xBE, '/': 0xBF, '\\': 0xDC}
NAME = {v: k for k, v in reversed(list(VK.items()))}   # first name wins ('`' over 'backquote')
MOD_KEYS = {'ctrl': (0xA2, 0xA3, 0x11), 'alt': (0xA4, 0xA5, 0x12), 'shift': (0xA0, 0xA1, 0x10), 'win': (0x5B, 0x5C)}
MOD_OF = {vk: m for m, vks in MOD_KEYS.items() for vk in vks}
ORDER = ['ctrl', 'alt', 'shift', 'win']


def parse(combo):
    """"ctrl+alt+space" -> ({'ctrl', 'alt'}, 0x20). "mouse4" -> (set(), 0x05)."""
    parts = [p.strip().lower() for p in combo.replace(' ', '').split('+') if p.strip()]
    if not parts:
        raise ValueError('empty hotkey')
    mods, key = set(parts[:-1]), parts[-1]
    if mods - set(MOD_KEYS):
        raise ValueError(f'bad hotkey: {combo}')
    vk = VK.get(key) or (ord(key.upper()) if len(key) == 1 and key.isalnum() else None)
    if vk is None:
        raise ValueError(f'bad hotkey key: {key}')
    return mods, vk


def name(mods, vk):
    key = NAME.get(vk) or (chr(vk).lower() if 0x30 <= vk <= 0x5A else f'vk{vk}')
    return '+'.join([m for m in ORDER if m in mods] + [key])


def pretty(combo):
    """"ctrl+alt+space" -> "Ctrl+Alt+Space", "mouse4" -> "Mouse 4"."""
    return '+'.join(p.replace('mouse', 'Mouse ').title() if p.startswith('mouse') else p.upper() if len(p) <= 3 and p[0] == 'f' else p.title()
                    for p in combo.split('+'))


REHOOK_SECONDS = 300   # Windows silently drops a hook whose callback was once too slow; put it back this often
STUCK_SECONDS = 120    # nobody holds a question that long: the release went where we couldn't see it


def key_down(vk):
    """Is the key physically down right now? Windows' own answer, so a release we never saw (lock screen, UAC, an admin window) can't fool it."""
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


class Hotkey:
    """on_down() when the combo goes down, on_up() when its key comes up, on_cancel() for Esc while held.
    active(): is it ours right now? When not (no game in front), the key passes through to whatever else uses the same combo.
    is_down(vk): the real keyboard, asked at the moment the key goes down; tests pass a fake. Hooks(...) runs it."""

    def __init__(self, combo, on_down, on_up, on_cancel=lambda: None, active=lambda: True, is_down=key_down):
        self.set(combo)
        self.on_down, self.on_up, self.on_cancel, self.active, self.is_down = on_down, on_up, on_cancel, active, is_down
        self.held, self.held_at, self.recording = False, 0, None

    def set(self, combo):
        self.mods, self.vk = parse(combo)
        self.combo = name(self.mods, self.vk)
        self._mouse_update()

    def record(self, done):
        """The next key or mouse button pressed (with its modifiers) becomes the hotkey; done(combo or None for Esc)."""
        def finish(combo):
            self._mouse_update()
            done(combo)
        self.recording = finish
        self._mouse_update()

    def _wants_mouse(self):
        return self.vk in (0x04, 0x05, 0x06) or bool(getattr(self, 'recording', None))

    def _mouse_update(self):
        """The mouse hook sees every mouse move, so it is only on while a mouse button is (or may become) the hotkey."""
        owner = getattr(self, '_owner', None)
        if owner and owner._tid:
            ctypes.windll.user32.PostThreadMessageW(owner._tid, 0x8001, 0, 0)   # WM_APP+1: the hook thread re-checks

    def _mods_down(self):
        """Modifiers down now, from the real keyboard, not from the releases we happened to see."""
        return {m for m, vks in MOD_KEYS.items() if any(self.is_down(k) for k in vks)}

    def _fire(self, f, *a):
        threading.Thread(target=f, args=a, daemon=True).start()

    def _event(self, vk, up):
        """True = swallow it (the game never sees our hotkey)."""
        if self.recording and not up and vk not in MOD_OF:
            done, self.recording = self.recording, None
            if vk == 0x1B:
                self._fire(done, None)
            elif vk in (0x01, 0x02):   # left/right click can't be the hotkey
                self.recording = done
                return False
            else:
                self.set(name(self._mods_down(), vk))
                self._fire(done, self.combo)
            self._swallow_up = vk
            return True
        if up and getattr(self, '_swallow_up', None) == vk:
            self._swallow_up = None
            return True
        if vk == self.vk:
            if not up and not self.held:
                mods = self._mods_down()
                if not (mods >= self.mods and (not self.mods or mods == self.mods)) or not self.active():
                    return False
                self.held, self.held_at = True, time.monotonic()
                self._fire(self.on_down)
                return True
            if up and self.held:
                self.held = False
                self._fire(self.on_up)
                return True
            return self.held   # key repeat while held
        if vk == 0x1B and not up and self.held:
            self.held = False
            self._fire(self.on_cancel)
            return True
        return False

    def unstick(self, now):
        """Held for minutes: its release went where we can't see (Win+L mid-question). Cancel, don't ask.
        By time, not GetAsyncKeyState: we swallow the hotkey's own key, so Windows never marks it down."""
        if self.held and now - self.held_at > STUCK_SECONDS:
            self.held = False
            self._fire(self.on_cancel)


class Hooks:
    """One hook thread for every hotkey: each keystroke in a game goes through one Python callback, not one per hotkey.
    A binding that is recording sees keys first, so the combo being typed can't also set off another hotkey."""

    def __init__(self, *bindings):
        self.bindings, self._tid = list(bindings), None
        for b in self.bindings:
            b._owner = self

    def event(self, vk, up):
        """True = swallow it. In order, recorders first; the first binding that swallows it keeps it from the rest."""
        return any(b._event(vk, up) for b in sorted(self.bindings, key=lambda b: not b.recording))

    def wants_mouse(self):
        return any(b._wants_mouse() for b in self.bindings)

    def busy(self):
        """Mid-press or recording: re-hooking now could lose the release."""
        return any(b.held or b.recording or getattr(b, '_swallow_up', None) for b in self.bindings)

    def tick(self, now=None):
        """The timer: clear stuck holds, then say whether it's safe to re-install the hooks."""
        for b in self.bindings:
            b.unstick(time.monotonic() if now is None else now)
        return not self.busy()

    def run(self):
        """Blocks: installs the hooks and pumps messages. Run it on its own thread."""
        from ctypes import wintypes as W
        user32 = ctypes.windll.user32

        class KB(ctypes.Structure):
            _fields_ = [('vkCode', W.DWORD), ('scanCode', W.DWORD), ('flags', W.DWORD), ('time', W.DWORD), ('dwExtraInfo', ctypes.c_size_t)]

        class MS(ctypes.Structure):
            _fields_ = [('pt', W.POINT), ('mouseData', W.DWORD), ('flags', W.DWORD), ('time', W.DWORD), ('dwExtraInfo', ctypes.c_size_t)]
        LRESULT = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, W.WPARAM, W.LPARAM)
        user32.CallNextHookEx.argtypes = [W.HHOOK, ctypes.c_int, W.WPARAM, W.LPARAM]
        user32.CallNextHookEx.restype = LRESULT
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, W.HINSTANCE, W.DWORD]
        user32.SetWindowsHookExW.restype = W.HHOOK
        user32.UnhookWindowsHookEx.argtypes = [W.HHOOK]
        user32.SetTimer.restype = ctypes.c_size_t
        user32.SetTimer.argtypes = [W.HWND, ctypes.c_size_t, W.UINT, ctypes.c_void_p]

        def keys(code, wparam, lparam):
            if code == 0:
                kb = ctypes.cast(lparam, ctypes.POINTER(KB)).contents
                if not kb.flags & 0x10:   # LLKHF_INJECTED: ignore keys apps type, ours included
                    try:
                        if self.event(kb.vkCode, wparam in (0x0101, 0x0105)):   # WM_KEYUP, WM_SYSKEYUP
                            return 1
                    except Exception as e:
                        print('hotkey:', e, file=sys.stderr)
            return user32.CallNextHookEx(None, code, wparam, lparam)

        BUTTONS = {0x0201: (0x01, False), 0x0202: (0x01, True), 0x0204: (0x02, False), 0x0205: (0x02, True),
                   0x0207: (0x04, False), 0x0208: (0x04, True)}   # left, right, middle down/up

        def mouse(code, wparam, lparam):
            if code == 0:
                ms = ctypes.cast(lparam, ctypes.POINTER(MS)).contents
                hit = BUTTONS.get(wparam)
                if wparam in (0x020B, 0x020C):   # side buttons: which one is in mouseData's high word
                    hit = (0x05 if ms.mouseData >> 16 == 1 else 0x06, wparam == 0x020C)
                if hit and not ms.flags & 0x01:   # LLMHF_INJECTED
                    try:
                        if self.event(*hit):
                            return 1
                    except Exception as e:
                        print('hotkey:', e, file=sys.stderr)
            return user32.CallNextHookEx(None, code, wparam, lparam)
        self._procs = HOOKPROC(keys), HOOKPROC(mouse)   # keep references, or they are collected and the hooks crash
        khook = user32.SetWindowsHookExW(13, self._procs[0], None, 0)
        if not khook:
            raise OSError('could not install the keyboard hook')
        mhook = None

        def sync():
            nonlocal mhook
            if self.wants_mouse() and not mhook:
                mhook = user32.SetWindowsHookExW(14, self._procs[1], None, 0)
            elif not self.wants_mouse() and mhook:
                user32.UnhookWindowsHookEx(mhook)
                mhook = None

        def rehook():
            """Unhook and hook again: a hook Windows dropped comes back, one it kept just moves to the front."""
            nonlocal khook, mhook
            user32.UnhookWindowsHookEx(khook)
            khook = user32.SetWindowsHookExW(13, self._procs[0], None, 0) or khook
            if mhook:
                user32.UnhookWindowsHookEx(mhook)
                mhook = None
            sync()
        msg = W.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)   # this thread now has a queue for PostThreadMessage
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        user32.SetTimer(None, 0, REHOOK_SECONDS * 1000, None)   # no window: WM_TIMER comes to this thread's queue
        sync()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x8001:
                sync()
            elif msg.message == 0x0113:   # WM_TIMER
                try:
                    if self.tick():
                        rehook()
                except Exception as e:
                    print('hotkey:', e, file=sys.stderr)
            else:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))


def press(combo):
    """Types a key combo through SendInput (Steam's clip key, Game Bar's Win+Alt+G). The hook ignores injected keys."""
    from ctypes import wintypes as W
    mods, vk = parse(combo)

    class KI(ctypes.Structure):
        _fields_ = [('wVk', W.WORD), ('wScan', W.WORD), ('dwFlags', W.DWORD), ('time', W.DWORD), ('dwExtraInfo', ctypes.c_size_t)]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [('ki', KI), ('pad', ctypes.c_byte * 32)]
        _anonymous_ = ('u',)
        _fields_ = [('type', W.DWORD), ('u', _U)]
    keys = [MOD_KEYS[m][-1] for m in ORDER if m in mods] + [vk]
    seq = [(k, 0) for k in keys] + [(k, 2) for k in reversed(keys)]   # 2 = KEYEVENTF_KEYUP
    arr = (INPUT * len(seq))(*[INPUT(type=1, ki=KI(wVk=k, dwFlags=f)) for k, f in seq])
    ctypes.windll.user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))
