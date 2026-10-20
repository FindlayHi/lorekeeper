"""A small always-on-top box with the question and answer. It goes on a second monitor when there is one, since an
exclusive-fullscreen game covers its own screen. Click it to copy the answer. Tk lives on the main thread; other threads post.
It is drawn like the landing page's dialogue box: night navy, a stepped pixel border, a chunky offset shadow, and the
page's pixel font (assets/fonts, loaded privately for this process), one size throughout: pink for what you said, cream for
Lorekeeper's answer."""
import ctypes, os, queue, re, sys, tkinter as tk
import tkinter.font as tkfont
import win

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'fonts')
# docs/index.html's palette
BG, INK, DIM, PINK, SKY, GOLD = '#08082a', '#f2efe6', '#c8c4d8', '#ff8aa4', '#49c6ff', '#ffd23f'
INDIGO, LILAC, SHADOW = '#3b1f6e', '#b99bff', '#05051a'
KEY = '#ff00fe'          # painted where the window is see-through: the notched corners and around the shadow
PX = 4                   # one pixel of the pixel border, as on the page
TEXT_W = 420             # wrap width of the question and answer
PAD = 20
FONT, FALLBACK = ('VT323', -22), ('Consolas', -15)   # the page's pixel font (assets/fonts), in pixels
# A leading emoji names a state; the pixel fonts have no emoji, so it becomes a drawn icon instead of a box.
MIC = ('....nnnn....', '...nssssn...', '...nswssn...', '...nssssn...', '...nssssn...', '.n.nssssn.n.',
       '.n.nbbbbn.n.', '..n.nnnn.n..', '...nn..nn...', '.....nn.....', '.....nn.....', '...nnnnnn...')   # docs/img/mic.svg
STATES = {'🎧': 'mic', '👂': 'mic', '🎤': 'mic'}
EMOJI = re.compile('[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF️‍⃣]')


def plain(text):
    """(state, text without emoji): a state icon for a leading 🎧/👂, and no emoji left to render as boxes."""
    text = text or ''
    state = next((s for e, s in STATES.items() if text.lstrip().startswith(e)), None)
    return state, re.sub(r'  +', ' ', EMOJI.sub('', text)).strip()


def load_fonts():
    """Make the bundled TTFs usable by this process only (FR_PRIVATE), before Tk looks fonts up."""
    if sys.platform != 'win32' or not os.path.isdir(FONTS):
        return
    try:
        gdi = ctypes.WinDLL('gdi32')
        gdi.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        for f in os.listdir(FONTS):
            if f.lower().endswith('.ttf'):
                gdi.AddFontResourceExW(os.path.join(FONTS, f), 0x10, None)
    except Exception:
        pass


class Box:
    def __init__(self, seconds=12):
        load_fonts()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True, '-alpha', 0.93)
        try:
            self.root.attributes('-transparentcolor', KEY)
            self.bg = KEY
        except tk.TclError:   # no colour keying: the corners and shadow sit on a plain dark square instead
            self.bg = SHADOW
        self.root.configure(bg=self.bg)
        # one font at one size for every word in the box, as the page's dialogue; colour alone tells who is talking
        self.font = tkfont.Font(self.root, font=FONT if FONT[0] in tkfont.families(self.root) else FALLBACK)
        self.line = self.font.metrics('linespace')
        self.c = tk.Canvas(self.root, bg=self.bg, highlightthickness=0, bd=0)
        self.c.pack()
        self.root.bind('<Button-1>', self._click)
        self.seconds, self.q, self.hide_at, self.blink_at = seconds, queue.Queue(), None, None
        self.question = self.answer = ''
        self.title = False
        self.action, self.hint = None, ''   # a click runs action (labelled hint) instead of copying
        self.root.after(50, self._pump)

    # any thread
    def show(self, question='', answer='', stay=False, title=False, on_click=None, hint=''):
        """title: the first line is Lorekeeper's own heading ("Lorekeeper is ready"), not something the player said.
        on_click: what clicking the box does instead of copying the answer (hint: its label, e.g. 'CLICK TO UPDATE')."""
        self.q.put((question, answer, stay, title, on_click, hint))

    def hide(self):
        self.q.put(None)

    # Tk thread
    def _pump(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item is None:
                    self._withdraw()
                    continue
                question, answer, stay, title, self.action, self.hint = item
                if question:
                    self.question, self.title = question, title
                self.answer = answer
                self._draw()
                self._place()
                self.root.deiconify()
                self.root.lift()
                self._blink(start=True)
                if self.hide_at:
                    self.root.after_cancel(self.hide_at)
                self.hide_at = None if stay else self.root.after(self.seconds * 1000, self._withdraw)
        except queue.Empty:
            pass
        self.root.after(50, self._pump)

    def _pixels(self, grid, x, y, k, colours, tags=()):
        for j, row in enumerate(grid):
            for i, ch in enumerate(row):
                if ch in colours:
                    self.c.create_rectangle(x + i * k, y + j * k, x + i * k + k, y + j * k + k, fill=colours[ch], width=0, tags=tags)

    def _arrow(self, x, y, colour, k=2):
        """The page's pixel ▸ (the fonts lack it): 3 wide, 5 tall, in k-pixel steps."""
        self._pixels(('x..', 'xx.', 'xxx', 'xx.', 'x..'), x, y, k, {'x': colour})

    def _draw(self):
        c = self.c
        c.delete('all')
        state, q = plain(self.question)
        _, a = plain(self.answer)
        done = bool(a.strip('.… '))            # a real answer, not the '…' while thinking
        x0, y0 = PX, PX                         # the navy panel's top-left; the border sits in the PX around it
        f, mid = self.font, (self.line - 10) // 2   # mid: where a 10-pixel drawn mark sits centred on a line of text
        tag_w = max(f.measure(t) for t in ('YOU', 'LK')) + 5 + 6 + 12   # tag, gap, ▸, gap
        tx = x0 + PAD + tag_w                   # text column, hanging past the YOU ▸ / LK ▸ tags and the mic
        iw = PAD + tag_w + TEXT_W + PAD
        # contents first, then the panel sized to fit them, lowered underneath
        y = y0 + 12
        self._pixels(('..x..', '.xxx.', 'xxxxx', '.xxx.', '..x..'), x0 + PAD, y + mid, 2, {'x': LILAC})   # the page's ◆
        c.create_text(x0 + PAD + 16, y, text='LOREKEEPER', font=f, fill=LILAC, anchor='nw')
        if done:
            c.create_text(x0 + iw - PAD, y, text=self.hint if self.action else 'CLICK TO COPY', font=f,
                          fill=GOLD if self.action else LILAC, anchor='ne')
        y += self.line + 8
        rule_y = y
        y += PX + 14
        if q:
            if state == 'mic':
                self._pixels(MIC, x0 + PAD, y + max(0, (self.line - 24) // 2), 2, {'n': INK, 's': SKY, 'b': '#2f6bff', 'w': INK})
            elif self.title:   # Lorekeeper's own heading: no YOU tag
                pass
            else:
                c.create_text(x0 + PAD, y, text='YOU', font=f, fill=PINK, anchor='nw')   # 'YOU ▸', as on the page
                self._arrow(x0 + PAD + f.measure('YOU') + 5, y + mid, PINK)
            t = c.create_text(x0 + PAD if self.title else tx, y, text=q, font=f, fill=LILAC if self.title else SKY if state else PINK,
                              anchor='nw', width=TEXT_W + (tag_w if self.title else 0))
            y = max(c.bbox(t)[3], y + (24 if state == 'mic' else 0)) + 10
        if a:
            c.create_text(x0 + PAD, y, text='LK', font=f, fill=SKY, anchor='nw')
            self._arrow(x0 + PAD + f.measure('LK') + 5, y + mid, SKY)
            t = c.create_text(tx, y, text=a, font=f, fill=INK, anchor='nw', width=TEXT_W)
            y = c.bbox(t)[3] + 6
        ih = y - y0 + 18
        if done:   # the page's gold ▼, blinking under a finished answer
            self._pixels(('xxxxx', '.xxx.', '..x..'), x0 + iw - PAD - 10, y0 + ih - 16, 2, {'x': GOLD}, 'more')
        # panel, border and shadow, below everything drawn so far
        x1, y1 = x0 + iw, y0 + ih
        under = [c.create_rectangle(x0 + dx, y0 + dy, x1 + dx, y1 + dy, fill=SHADOW, width=0)   # box-shadow: 8px 12px, 12px 8px
                 for dx, dy in ((2 * PX, 3 * PX), (3 * PX, 2 * PX))]
        under += [c.create_rectangle(*r, fill=INK, width=0)   # the border, with its corners notched out
                  for r in ((x0, 0, x1, y0), (x0, y1, x1, y1 + PX), (0, y0, x0, y1), (x1, y0, x1 + PX, y1))]
        under += [c.create_rectangle(x0, y0, x1, y1, fill=BG, width=0),
                  c.create_rectangle(x0, rule_y, x1, rule_y + PX, fill=INDIGO, width=0)]
        for item in reversed(under):   # bottom to top: shadow, border, panel, rule
            c.tag_lower(item)
        c.config(width=x1 + 3 * PX, height=y1 + 3 * PX)

    def _blink(self, start=False):
        if self.blink_at:
            self.root.after_cancel(self.blink_at)
        if not start:
            self.c.itemconfig('more', state='hidden' if self.c.itemcget('more', 'state') != 'hidden' else 'normal')
        self.blink_at = self.root.after(550, self._blink)

    def _withdraw(self):
        if self.blink_at:
            self.root.after_cancel(self.blink_at)
            self.blink_at = None
        self.root.withdraw()

    def _place(self):
        self.root.update_idletasks()
        mons = win.monitors() or [(0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight(), True)]
        x, y, w, h, _ = next((m for m in mons if not m[4]), mons[0])   # a second monitor if there is one
        bw, bh = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        self.root.geometry(f'+{x + w - bw - 24}+{y + h - bh - 24}')

    def _click(self, _):
        action, self.action = self.action, None
        if action:
            self._withdraw()
            return action()
        self.root.clipboard_clear()
        self.root.clipboard_append(self.answer)
        self._withdraw()

    def run(self):
        self.root.mainloop()

    def quit(self):
        self.root.after(0, self.root.destroy)
