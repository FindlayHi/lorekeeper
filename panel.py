"""The tray menu, drawn like the landing page: Windows' own menu can't take the site's fonts or colours, so a click on the
tray book opens this pixel panel instead (the native menu stays as the fallback).

Rows are Items: an action, an on/off switch (check), a radio choice, or a sub-menu (sub) that opens as a flyout beside
the panel, the way menus do. Mouse and keys both work: ↑↓ move, Enter/Space choose, → opens a flyout, ← or Esc closes
it, Esc on the main panel or a click elsewhere closes everything. Switches and radio choices keep the menu open (it's a
settings panel); actions close it."""
import tkinter as tk
import tkinter.font as tkfont
from box import BG, INK, DIM, PINK, SKY, GOLD, INDIGO, LILAC, SHADOW, KEY, PX, FONT, font_spec, pick_font

W, FLY_W = 340, 300
ROW = 30   # the least a row is, at the usual size; a bigger font makes rows (and the panel) taller and wider
HOVER = '#1b1452'


class Item:
    def __init__(self, label, action=None, check=None, radio=None, sub=None, enabled=True, header=False, note=None):
        self.label, self.action, self.check, self.radio, self.sub = label, action, check, radio, sub
        self.enabled, self.header, self.note = enabled, header, note

    def text(self):
        return self.label() if callable(self.label) else self.label

    def is_enabled(self):
        return self.enabled() if callable(self.enabled) else self.enabled

    def selectable(self):
        return not self.header and self.is_enabled() and bool(self.action or self.sub)


def fit(text, font, width):
    """The text, cut with … so it never runs past the panel's edge."""
    f = tkfont.Font(font=font)
    if f.measure(text) <= width:
        return text
    while text and f.measure(text + '…') > width:
        text = text[:-1]
    return text.rstrip() + '…'


class Pane:
    """One pixel window of rows. The main menu is a Pane; a sub-menu is another, beside it."""

    def __init__(self, menu, items_fn, width, title='', status=None):
        self.menu, self.items_fn, self.width, self.title, self.status = menu, items_fn, width, title, status
        self.sel, self.rows = None, []
        w = self.win = tk.Toplevel(menu.root)
        w.withdraw()
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        try:
            w.attributes('-transparentcolor', KEY)
            bg = KEY
        except tk.TclError:
            bg = SHADOW
        w.configure(bg=bg)
        self.c = tk.Canvas(w, bg=bg, highlightthickness=0, bd=0)
        self.c.pack()
        self.c.bind('<Motion>', self._hover)
        self.c.bind('<Button-1>', self._click)
        self.c.bind('<Leave>', lambda e: self.menu.left(self))
        for k, f in (('<Escape>', lambda e: self.menu.escape(self)), ('<Up>', lambda e: self._move(-1)), ('<Down>', lambda e: self._move(1)),
                     ('<Return>', lambda e: self.choose()), ('<space>', lambda e: self.choose()), ('<Right>', lambda e: self.choose(True)),
                     ('<Left>', lambda e: self.menu.escape(self, left=True)), ('<BackSpace>', lambda e: self.menu.escape(self, left=True))):
            w.bind(k, f)
        w.bind('<FocusIn>', lambda e: self.menu.focused())
        w.bind('<FocusOut>', lambda e: self.menu.root.after(120, self.menu.maybe_close))
        self.draw()

    def size(self):
        self.win.update_idletasks()
        return self.c.winfo_reqwidth(), self.c.winfo_reqheight()

    def show(self, x, y):
        self.win.geometry(f'+{int(x)}+{int(y)}')
        self.win.deiconify()
        self.win.lift()

    def destroy(self):
        self.win.destroy()

    def contains(self, x, y):
        wx, wy = self.win.winfo_rootx(), self.win.winfo_rooty()
        return wx <= x < wx + self.win.winfo_width() and wy <= y < wy + self.win.winfo_height()

    # drawing
    def draw(self):
        m, c = self.menu, self.c
        c.delete('all')
        items = self.items_fn()
        self.rows = []   # (top, bottom, item)
        x0, y0 = PX, PX
        x1 = x0 + self.width
        y = y0 + 14
        self._pixels(('..x..', '.xxx.', 'xxxxx', '.xxx.', '..x..'), x0 + 18, y, 2, LILAC)
        c.create_text(x0 + 34, y + 1, text=self.title, font=m.f_head, fill=LILAC, anchor='nw')
        y += 20
        if self.status:
            playing, key = self.status()
            c.create_text(x0 + 18, y, text=playing, font=m.f_row, fill=SKY, anchor='nw', width=self.width - 36)
            y = c.bbox('all')[3] + 2
            c.create_text(x0 + 18, y, text=key, font=m.f_small, fill=DIM, anchor='nw', width=self.width - 36)
            y = c.bbox('all')[3] + 10
        rule_y = y
        y += PX + 6
        for it in items:
            if it.header:
                y += 12
                c.create_text(x0 + 18, y + 4, text=it.text(), font=m.f_head, fill=PINK, anchor='nw')
                y += 22
                continue
            i, top, on = len(self.rows), y, it.is_enabled()
            c.create_rectangle(x0 + 4, top, x1 - 4, top + m.row, fill=BG, width=0, tags=(f'bg{i}',))
            right = x1 - 16
            room = (right - 50 if it.check is not None else right - 36 if (it.radio is not None or it.sub is not None)
                    else right - 70 if it.note else right) - (x0 + 18)
            c.create_text(x0 + 18, top + m.row // 2, text=fit(it.text(), m.f_row, room), font=m.f_row, fill=INK if on else DIM,
                          anchor='w', tags=(f'tx{i}',))
            if it.check is not None:
                self._switch(right - 34, top + (m.row - 14) // 2, bool(it.check()), on)
            elif it.radio is not None:
                self._radio(right - 12, top + (m.row - 10) // 2, bool(it.radio()))
            elif it.sub is not None:
                self._pixels(('x..', 'xx.', 'xxx', 'xx.', 'x..'), right - 8, top + (m.row - 10) // 2, 2, LILAC)
            elif it.note:
                c.create_text(right, top + m.row // 2, text=it.note() if callable(it.note) else it.note, font=m.f_small, fill=DIM, anchor='e')
            self.rows.append((top, top + m.row, it))
            y += m.row
        y1 = y + 10
        under = [c.create_rectangle(x0 + dx, y0 + dy, x1 + dx, y1 + dy, fill=SHADOW, width=0) for dx, dy in ((2 * PX, 3 * PX), (3 * PX, 2 * PX))]
        under += [c.create_rectangle(*r, fill=INK, width=0) for r in ((x0, 0, x1, y0), (x0, y1, x1, y1 + PX), (0, y0, x0, y1), (x1, y0, x1 + PX, y1))]
        under += [c.create_rectangle(x0, y0, x1, y1, fill=BG, width=0), c.create_rectangle(x0, rule_y, x1, rule_y + PX, fill=INDIGO, width=0)]
        for item in reversed(under):
            c.tag_lower(item)
        c.config(width=x1 + 3 * PX, height=y1 + 3 * PX)
        if self.sel is not None and self.sel < len(self.rows):
            self._paint(self.sel, True)

    def _pixels(self, grid, x, y, k, colour):
        for j, row in enumerate(grid):
            for i, ch in enumerate(row):
                if ch == 'x':
                    self.c.create_rectangle(x + i * k, y + j * k, x + i * k + k, y + j * k + k, fill=colour, width=0)

    def _switch(self, x, y, on, enabled):
        """A pixel toggle: sky with the knob right when on, indigo with it left when off."""
        self.c.create_rectangle(x, y, x + 34, y + 14, fill=(SKY if on else INDIGO) if enabled else '#2a2550', outline=INK, width=2)
        kx = x + 20 if on else x + 2
        self.c.create_rectangle(kx + 1, y + 3, kx + 11, y + 11, fill=INK if enabled else DIM, width=0)

    def _radio(self, x, y, on):
        self.c.create_rectangle(x, y, x + 10, y + 10, outline=LILAC, width=2)
        if on:
            self.c.create_rectangle(x + 3, y + 3, x + 7, y + 7, fill=GOLD, width=0)

    # selection
    def _row_at(self, y):
        return next((i for i, (a, b, it) in enumerate(self.rows) if a <= y < b and it.selectable()), None)

    def _paint(self, i, on):
        self.c.itemconfig(f'bg{i}', fill=HOVER if on else BG)
        self.c.itemconfig(f'tx{i}', fill=GOLD if on else (INK if self.rows[i][2].is_enabled() else DIM))

    def set_sel(self, i):
        if i == self.sel:
            return
        if self.sel is not None and self.sel < len(self.rows):
            self._paint(self.sel, False)
        self.sel = i
        if i is not None:
            self._paint(i, True)

    def item(self):
        return self.rows[self.sel][2] if self.sel is not None and self.sel < len(self.rows) else None

    def _hover(self, e):
        i = self._row_at(e.y)
        self.set_sel(i)
        self.menu.hovered(self, self.item())

    def _click(self, e):
        i = self._row_at(e.y)
        if i is not None:
            self.set_sel(i)
            self.choose()

    def _move(self, d):
        ok = [i for i, (_, _, it) in enumerate(self.rows) if it.selectable()]
        if ok:
            cur = ok.index(self.sel) if self.sel in ok else (-1 if d > 0 else 0)
            self.set_sel(ok[(cur + d) % len(ok)])

    def choose(self, only_subs=False):
        it = self.item()
        if not it:
            return
        if it.sub is not None:
            return self.menu.fly(self, focus=True)
        if not only_subs and it.action:
            self.menu.run(self, it)


class Panel:
    """Panel(root, items_fn, status_fn): items_fn() -> [Item] for the main menu; status_fn() -> (playing, hotkeys) lines."""

    def __init__(self, root, items_fn, status_fn, cfg=dict):
        self.root, self.items_fn, self.status_fn, self.cfg = root, items_fn, status_fn, cfg
        self.main = self.flyout = None
        self.fly_for = None   # the main-menu row the flyout belongs to
        self.had_focus, self.away, self.timer = False, 0, None

    # any thread
    def open(self, x=None, y=None):
        self.root.after(0, lambda: self._open(x, y))

    # Tk thread
    def _open(self, x, y):
        self.close()
        family, size = pick_font(self.root, *font_spec(self.cfg()), plain=-14)
        pixel = family == FONT[0]
        px = abs(size)
        self.f_row = (family, -px)
        self.f_small = (family, -round(px * 18 / 22))
        have = set(tkfont.families(self.root))
        if pixel and 'Press Start 2P' in have:
            self.f_head = ('Press Start 2P', -8)
        else:   # a font of your own for the headings too, a little smaller and bold
            self.f_head = (family, -round(px * 0.6), 'bold') if not pixel else ('Consolas', -11, 'bold')
        self.row = max(ROW, tkfont.Font(font=self.f_row).metrics('linespace') + 8)
        self.scale = max(1, px / abs(FONT[1])) if pixel else max(1, px / 15)   # wider panels for bigger text
        self.w, self.fly_w = round(W * self.scale), round(FLY_W * self.scale)
        self.had_focus, self.away = False, 0
        self.main = Pane(self, self.items_fn, self.w, 'LOREKEEPER', self.status_fn)
        cw, ch = self.main.size()
        if x is None:
            x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
        sx, sy = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        px = min(max(0, x - cw + 8), sx - cw - self.fly_w + 16)   # leave room on the right for a sub-menu to open there
        py = y - ch - 6 if y - ch - 6 > 0 else min(y + 6, sy - ch)   # above the cursor (the tray is at the bottom), else below
        self.main.show(px, py)
        try:   # a tray click lets this process take the foreground; without it Esc and click-away can't work
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(int(self.main.win.frame(), 16))
        except Exception:
            pass
        self.main.win.focus_force()
        self.timer = self.root.after(1000, self._watch)

    def close(self):
        self.close_flyout()
        if self.main:
            self.main.destroy()
            self.main = None
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None

    def close_flyout(self):
        if self.flyout:
            self.flyout.destroy()
            self.flyout = self.fly_for = None

    def panes(self):
        return [p for p in (self.main, self.flyout) if p]

    # the flyout
    def fly(self, pane, focus=False):
        """Open the sub-menu of the main menu's selected row beside it: to the right, or the left if the screen ends first."""
        it = pane.item()
        if pane is not self.main or not it or it.sub is None:
            return
        if self.fly_for is it and self.flyout:
            if focus:
                self.flyout.win.focus_force()
                self.flyout._move(1)
            return
        self.close_flyout()
        self.fly_for = it
        self.flyout = Pane(self, it.sub, self.fly_w, it.text().upper())
        fw, fh = self.flyout.size()
        mx, my = self.main.win.winfo_rootx(), self.main.win.winfo_rooty()
        top = my + self.main.rows[self.main.sel][0] - 40   # level with the row it came from
        sx, sy = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        right = mx + self.main.win.winfo_width() - 16   # over the main menu's border and shadow, clear of its text
        fx = right if right + fw <= sx else max(0, mx - fw + 16)
        self.flyout.show(fx, max(0, min(top, sy - fh - 8)))
        self.flyout.win.lift(self.main.win)   # over the main menu's edge, like a real flyout
        if focus:
            self.flyout.win.focus_force()
            self.flyout._move(1)

    def hovered(self, pane, it):
        if pane is not self.main:
            return
        if it and it.sub is not None:
            if self.fly_for is not it:
                self.root.after(180, lambda: self.main and self.main.item() is it and self.fly(self.main))
        elif it is not None:
            self.close_flyout()

    def left(self, pane):
        """The mouse left a pane: clear its highlight, except the main menu's row whose flyout is open."""
        if pane is self.main and self.flyout:
            return
        pane.set_sel(None)

    # choosing
    def run(self, pane, it):
        keep = it.check is not None or it.radio is not None
        if not keep:
            self.close()
        try:
            it.action()
        except Exception as e:
            print('menu:', e)
        if keep:
            for p in self.panes():
                p.draw()

    def escape(self, pane, left=False):
        if pane is self.flyout:
            self.close_flyout()
            if self.main:
                self.main.win.focus_force()
        elif not left:
            self.close()

    # closing when you click elsewhere
    def focused(self):
        self.had_focus = True

    def maybe_close(self):
        if self.main and self.had_focus and self.main.win.focus_get() is None:
            self.close()

    def _watch(self):
        """If the menu never got focus (Windows can refuse), close it once the mouse has been away from it for 4 s."""
        self.timer = None
        if not self.main:
            return
        x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
        inside = any(p.contains(x, y) for p in self.panes())
        self.away = 0 if inside else self.away + 1
        if self.away >= 4 and not self.had_focus:
            return self.close()
        self.timer = self.root.after(1000, self._watch)
