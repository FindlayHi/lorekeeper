"""The game's screen, remembered, so questions can point back in time:
  recent: a frame a second for the last 5 s ("what synergy did I just get": the banner faded before the key went down)
  long:   a frame every 10 s for the last 10 min ("what did that sign say a few minutes ago")
  saved:  "remember this [as the vault code]": kept on disk per game until deleted
Recorded only while a game is in front and "Use the screen" is on (active()); once none has been for forget_s, the memory is dropped, so
"earlier" never reaches back across a stretch spent in a browser or on the desktop.
DXGI duplication (dxcam) sees most fullscreen games where GDI gets black. Frames are kept as JPEG bytes (~100 KB),
in memory; only the ones sent with a question touch disk (temp, deleted after)."""
import collections, io, os, re, tempfile, threading, time

WANTS = re.compile(r"\b(this|that|these|those|here|on (?:my |the )?screen|just (?:got|get|picked|pick(?:ed)? up|found|find|unlocked|unlock|looted|triggered|activated|equipped)|"
                   r"i'?m (?:looking at|holding|fighting|hovering)|what am i|earlier|before(?!\s+(?!that\b|this\b)[a-z])|ago|a while back|back there|previous(?:ly)?|"
                   r"(?:i )?saved|remembered|right now|(?:have|got) equipped|equipped right now|do i have|my (?:perks?|loadout|build|inventory|items?|stats|skills?|hand))\b", re.I)
JUST = re.compile(r'\bjust\b|\ba (?:second|moment|sec) ago\b|\bthat (?:popped|came) up\b', re.I)
NUM = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
       'few': 3, 'couple': 2, 'couple of': 2}
AGO = re.compile(r'\b(\d+|an?|one|two|three|four|five|six|seven|eight|nine|ten|few|couple(?: of)?)\s+(second|sec|minute|min)s?\s+ago\b', re.I)
EARLIER = re.compile(r'\b(earlier|before(?!\s+(?!that\b|this\b)[a-z])|a while (?:ago|back)|back there|previous(?:ly)?)\b', re.I)
SAVED = re.compile(r'\b(saved|remembered|the (?:screen|one|thing|spot|map|code|clue) i (?:saved|kept))\b', re.I)
WIDE, LONG_WIDE = 1280, 1024
SAME = object()   # Screen._grab: the screen is as it was at the last frame kept


def wants(question):
    return bool(WANTS.search(question))


def jpeg(img, wide=WIDE):
    if img.width > wide:
        img = img.resize((wide, round(img.height * wide / img.width)))
    b = io.BytesIO()
    img.convert('RGB').save(b, 'JPEG', quality=78)
    return b.getvalue()


class Screen:
    def __init__(self, keep=5, long_every=10, long_keep=60, active=lambda: True, forget_s=60):
        self.recent = collections.deque(maxlen=keep)       # (time, jpeg bytes)
        self.long = collections.deque(maxlen=long_keep)
        self.long_every, self.active, self.cam, self.lock = long_every, active, None, threading.Lock()
        self.forget_s, self.last_long, self.away = forget_s, 0, None   # away: since when no game has been in front
        self.fresh = False   # has the screen changed since the last long frame?
        self.unkept = None   # a frame grabbed at key-down (now()) that the next tick hasn't kept yet
        self.full = None   # the key-down grab at full size: perk icons are too small in the 1280 copies
        threading.Thread(target=self._loop, daemon=True).start()

    def _grab(self):
        """The screen now as a PIL image; SAME when it hasn't changed since the last frame kept; or None (all black)."""
        from PIL import Image, ImageGrab
        img = None
        try:
            if self.cam is None:
                import dxcam
                self.cam = dxcam.create(output_color='RGB')
            if self.cam:
                a = self.cam.grab()   # None when nothing changed since the last grab
                if a is not None:
                    img = Image.fromarray(a)
                elif self.recent:
                    return SAME
        except Exception:
            self.cam = False   # no DXGI here: GDI from now on
        if img is None:
            img = ImageGrab.grab()
        return None if img.getbbox() is None else img   # all black: a fullscreen game that hides from both

    def _loop(self):
        while True:
            try:
                self.tick(time.time())
            except Exception as e:
                print('screen:', e)
            time.sleep(1)

    def tick(self, now):
        """One second: a frame if a game is in front; if none has been for forget_s, forget them all
        (a quick alt-tab to read a message keeps them)."""
        if not self.active():
            self.away = self.away or now
            if now - self.away > self.forget_s:
                with self.lock:
                    self.recent.clear()
                    self.long.clear()
            return
        self.away = None
        img = self._grab()
        if img is SAME and self.unkept is not None:
            img = self.unkept   # unchanged since the key-down grab, which was never kept: that is the screen now
        self.unkept = None
        if img is None:
            return
        with self.lock:
            if img is SAME and not self.recent:
                return   # forgotten since the grab: the next changed frame starts the memory again
            # an unchanged screen (a menu, a paused game) is the last frame again: the same bytes, nothing decoded or encoded
            self.recent.append((now, self.recent[-1][1] if img is SAME else jpeg(img)))
            self.fresh = self.fresh or img is not SAME
            if now - self.last_long >= self.long_every:
                if img is SAME and self.long and not self.fresh:
                    small = self.long[-1][1]
                else:
                    small = jpeg(self._last() if img is SAME else img, LONG_WIDE)
                self.long.append((now, small))
                self.last_long, self.fresh = now, False

    def _last(self):
        """The newest kept frame, decoded."""
        from PIL import Image
        return Image.open(io.BytesIO(self.recent[-1][1]))

    def forget(self):
        """Drop every remembered frame now ("Use the screen" was switched off)."""
        with self.lock:
            self.recent.clear()
            self.long.clear()
        self.full = self.unkept = None

    def now(self):
        """Grab one this instant (at key-down) -> every remembered frame, oldest first, ending with it: [(time, jpeg)]."""
        try:
            img = self._grab()
        except Exception:
            img = None
        if img is not None and img is not SAME and self.active():
            self.unkept = img   # the next tick may be told "nothing changed" since this grab, not since its own last frame
        with self.lock:
            same = self.recent[-1][1] if img is SAME and self.recent else None   # unchanged: the last frame's own bytes
            if img is SAME:
                img = self._last() if same else None
            out = sorted(set(self.long) | set(self.recent))
        self.full = img
        return out + ([(time.time(), same or jpeg(img))] if img is not None else [])

    @staticmethod
    def pick(frames, question, most=4):
        """The frames this question is about -> [(time, jpeg)], newest last.
        "2 minutes ago": the three nearest then. "earlier": six spread over the history. "just": the last few. Else: now."""
        if not frames:
            return []
        t_end = frames[-1][0]
        m = AGO.search(question)
        if m:
            n = int(m[1]) if m[1].isdigit() else NUM.get(m[1].lower(), 1)
            target = t_end - n * (60 if m[2].lower().startswith('min') else 1)
            near = sorted(frames, key=lambda f: abs(f[0] - target))[:3]
            return sorted(near) + [frames[-1]] if frames[-1] not in near else sorted(near)
        if EARLIER.search(question):
            older = [f for f in frames if t_end - f[0] > 8]
            step = max(1, len(older) // 6)
            return older[::-1][::step][:6][::-1] + [frames[-1]]
        if JUST.search(question):
            return frames[-most:]
        return frames[-1:]

    @staticmethod
    def files(frames, question):
        """The picked frames as temp jpegs -> [(path, label)]."""
        pick = Screen.pick(frames, question)
        if not pick:
            return []
        t_end, out = pick[-1][0], []
        for t, data in pick:
            fd, path = tempfile.mkstemp(prefix='lorekeeper-shot-', suffix='.jpg')
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            ago = round(t_end - t)
            out.append((path, 'Screen when the key went down:' if t == t_end else
                        f'Screen {ago} s before that:' if ago < 90 else f'Screen {round(ago / 60)} min before that:'))
        return out


# "remember this": saved screens, per game

def saved_dir(folder, game):
    return os.path.join(folder, re.sub(r'[^a-z0-9]+', '-', game['name'].lower()).strip('-'), 'saved')


def save_shot(folder, game, data, label=''):
    d = saved_dir(folder, game)
    os.makedirs(d, exist_ok=True)
    label = re.sub(r'[^\w -]+', '', label).strip()[:60]
    path = os.path.join(d, time.strftime('%Y-%m-%d %H%M%S') + (f' - {label}' if label else '') + '.jpg')
    with open(path, 'wb') as f:
        f.write(data)
    return path


def saved_for(folder, game, question, most=3):
    """Saved screens the question points at: label words in common, else (if it says "saved") the newest -> [(path, label)]."""
    d = saved_dir(folder, game) if game else ''
    if not d or not os.path.isdir(d):
        return []
    files = sorted(f for f in os.listdir(d) if f.endswith('.jpg'))
    words = set(re.findall(r'[a-z0-9]{3,}', question.lower())) - {'the', 'what', 'did', 'say', 'saved', 'that', 'this', 'remembered', 'was'}
    hits = [f for f in files if words & set(re.findall(r'[a-z0-9]{3,}', f.lower().split(' - ', 1)[-1]))] if ' - ' in ''.join(files) else []
    if not hits and SAVED.search(question):
        hits = files[-most:]
    return [(os.path.join(d, f), f'Saved screen "{f[:-4].split(" - ", 1)[-1]}" ({f[:10]}):') for f in hits[-most:]]
