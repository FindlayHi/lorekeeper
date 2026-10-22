"""The font options: the answer box's own font falls back to the app-wide one, and a font Windows lacks falls back to the pixel font."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import box, config  # noqa: E402


def test_defaults_are_the_pixel_font():
    assert box.font_spec(config.DEFAULTS) == ('', 0)
    assert box.font_spec(config.DEFAULTS, popup=True) == ('', 0)


def test_box_follows_the_global_font_until_it_has_its_own():
    cfg = {'font': 'Arial', 'fontSize': 20, 'boxFont': '', 'boxFontSize': 0}
    assert box.font_spec(cfg) == ('Arial', 20)
    assert box.font_spec(cfg, popup=True) == ('Arial', 20)
    cfg.update(boxFont='Consolas')
    assert box.font_spec(cfg, popup=True) == ('Consolas', 20)   # the size is still inherited
    assert box.font_spec(cfg) == ('Arial', 20)                  # the tray ignores the box's own
    cfg.update(boxFontSize=30)
    assert box.font_spec(cfg, popup=True) == ('Consolas', 30)


def test_bad_values_mean_default():
    assert box.font_spec({'font': None, 'fontSize': 'big'}) == ('', 0)
    assert box.font_spec({'fontSize': -18}) == ('', 18)   # a negative size means pixels in Tk; take it as written


def test_unknown_family_falls_back():
    import tkinter as tk
    root = tk.Tk()
    try:
        fam, size = box.pick_font(root, 'No Such Font 9000', 0)
        assert fam in (box.FONT[0], box.FALLBACK[0]) and size < 0
        assert box.pick_font(root, 'No Such Font 9000', 30)[1] == -30
    finally:
        root.destroy()


def test_default_is_the_bundled_pixel_font():
    import tkinter as tk
    box.load_fonts()
    root = tk.Tk()
    try:
        assert box.pick_font(root, '', 0)[0] == box.FONT[0]   # not the Consolas fallback
    finally:
        root.destroy()
