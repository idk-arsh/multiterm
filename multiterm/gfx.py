"""Drawing primitives: rounded surfaces, gradients, glows, vector icons,
and a tiny frame-based animator. Everything is plain Tk canvas geometry."""
import math
import time
import tkinter.font as tkfont

from . import theme
from . import ui
from .theme import UI, mix

_FONTS = {}


def font(size=10, bold=False, family=None):
    """A cached font at the display scale. `size` stays in design points."""
    family = family or theme.ui_family()
    key = (family, size, bold, ui.SCALE)
    if key not in _FONTS:
        _FONTS[key] = (family, ui.font_px(size), "bold") if bold else             (family, ui.font_px(size))
    return _FONTS[key]


_MEASURE = {}


def measure(text, size=10, bold=False, family=None):
    """Real pixel width of a label. Guessing from len(text) clips."""
    family = family or theme.ui_family()
    key = (family, size, bold, ui.SCALE)
    if key not in _MEASURE:
        try:
            _MEASURE[key] = tkfont.Font(family=family, size=ui.font_px(size),
                                        weight="bold" if bold else "normal")
        except Exception:                              # noqa: BLE001
            return int(len(text) * size * 0.62 * ui.SCALE)
    return _MEASURE[key].measure(text)


# ------------------------------------------------------------------- shapes
def round_rect(cv, x0, y0, x1, y1, r, **kw):
    """A rounded rectangle drawn as a smoothed polygon."""
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = [
        x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
        x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
        x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
    ]
    return cv.create_polygon(pts, smooth=True, splinesteps=16, **kw)


def vgrad(cv, x0, y0, x1, y1, c1, c2, steps=28, tags=()):
    """Vertical gradient band built from horizontal strips."""
    h = y1 - y0
    if h <= 0:
        return
    steps = max(2, min(steps, int(h)))
    for i in range(steps):
        t0 = y0 + h * i / steps
        t1 = y0 + h * (i + 1) / steps + 1
        cv.create_rectangle(x0, t0, x1, t1, outline="",
                            fill=mix(c1, c2, i / (steps - 1)), tags=tags)


def hgrad(cv, x0, y0, x1, y1, c1, c2, steps=48, tags=()):
    w = x1 - x0
    if w <= 0:
        return
    steps = max(2, min(steps, int(w)))
    for i in range(steps):
        a = x0 + w * i / steps
        b = x0 + w * (i + 1) / steps + 1
        cv.create_rectangle(a, y0, b, y1, outline="",
                            fill=mix(c1, c2, i / (steps - 1)), tags=tags)


def round_vgrad(cv, x0, y0, x1, y1, r, c1, c2, tags=()):
    """Vertical gradient clipped to a rounded rectangle: each strip is inset
    by the corner circle, so the fill really does have round corners."""
    h = y1 - y0
    if h <= 0 or x1 <= x0:
        return
    r = max(0.0, min(r, (x1 - x0) / 2, h / 2))
    steps = max(2, min(72, int(h)))
    for i in range(steps):
        a = y0 + h * i / steps
        b = y0 + h * (i + 1) / steps + 0.8
        d = min(a - y0, y1 - b)
        if d < r:
            dx = r - math.sqrt(max(0.0, r * r - (r - max(0.0, d)) ** 2))
        else:
            dx = 0.0
        cv.create_rectangle(x0 + dx, a, x1 - dx, b, outline="",
                            fill=mix(c1, c2, i / (steps - 1)), tags=tags)


def glow(cv, x0, y0, x1, y1, r, color, bg, layers=5, spread=5, tags=()):
    """Soft halo around a rounded shape (concentric fading outlines)."""
    for i in range(layers, 0, -1):
        t = i / (layers + 1)
        pad = spread * i / layers
        round_rect(cv, x0 - pad, y0 - pad, x1 + pad, y1 + pad, r + pad,
                   fill="", outline=mix(bg, color, (1 - t) * 0.55), width=1,
                   tags=tags)


def chip(cv, x, y, text, fg, bg, font=("Segoe UI Semibold", 8), padx=7, pady=3,
         tags=(), radius=6):
    """Small rounded label. Returns its width."""
    tmp = cv.create_text(-999, -999, text=text, font=font, anchor="nw")
    bbox = cv.bbox(tmp)
    cv.delete(tmp)
    w = (bbox[2] - bbox[0]) + padx * 2
    h = (bbox[3] - bbox[1]) + pady * 2
    round_rect(cv, x, y, x + w, y + h, radius, fill=bg, outline="", tags=tags)
    cv.create_text(x + w / 2, y + h / 2, text=text, fill=fg, font=font,
                   tags=tags)
    return w, h


# -------------------------------------------------------------------- icons
def icon_folder(cv, x, y, s, color, tags=(), open_=False):
    """Folder glyph: a tab, a body, and a lighter flap when open."""
    h = s * 0.80
    tab_h = h * 0.26
    round_rect(cv, x, y, x + s * 0.48, y + tab_h * 1.9, 1.8, fill=color,
               outline="", tags=tags)
    round_rect(cv, x, y + tab_h, x + s, y + h, 2.4, fill=color, outline="",
               tags=tags)
    if open_:
        round_rect(cv, x + s * 0.05, y + h * 0.42, x + s, y + h, 2.2,
                   fill=mix(color, "#FFFFFF", 0.30), outline="", tags=tags)
    else:
        cv.create_line(x + s * 0.16, y + tab_h + h * 0.20,
                       x + s * 0.84, y + tab_h + h * 0.20,
                       fill=mix(color, "#000000", 0.35), tags=tags)


def icon_terminal(cv, x, y, s, color, tags=()):
    round_rect(cv, x, y, x + s, y + s * 0.86, 3, fill="", outline=color,
               width=1.2, tags=tags)
    cv.create_line(x + s * 0.22, y + s * 0.28, x + s * 0.42, y + s * 0.44,
                   x + s * 0.22, y + s * 0.60, fill=color, width=1.4,
                   joinstyle="round", capstyle="round", tags=tags)
    cv.create_line(x + s * 0.52, y + s * 0.62, x + s * 0.78, y + s * 0.62,
                   fill=color, width=1.4, capstyle="round", tags=tags)


def icon_plus(cv, cx, cy, s, color, tags=(), width=1.6):
    cv.create_line(cx - s, cy, cx + s, cy, fill=color, width=width,
                   capstyle="round", tags=tags)
    cv.create_line(cx, cy - s, cx, cy + s, fill=color, width=width,
                   capstyle="round", tags=tags)


def icon_close(cv, cx, cy, s, color, tags=(), width=1.4):
    cv.create_line(cx - s, cy - s, cx + s, cy + s, fill=color, width=width,
                   capstyle="round", tags=tags)
    cv.create_line(cx - s, cy + s, cx + s, cy - s, fill=color, width=width,
                   capstyle="round", tags=tags)


def icon_chevron(cv, cx, cy, s, color, tags=(), down=False, width=1.5):
    if down:
        pts = (cx - s, cy - s * 0.5, cx, cy + s * 0.5, cx + s, cy - s * 0.5)
    else:
        pts = (cx - s * 0.5, cy - s, cx + s * 0.5, cy, cx - s * 0.5, cy + s)
    cv.create_line(*pts, fill=color, width=width, capstyle="round",
                   joinstyle="round", tags=tags)


def icon_restart(cv, cx, cy, s, color, tags=()):
    cv.create_arc(cx - s, cy - s, cx + s, cy + s, start=40, extent=280,
                  style="arc", outline=color, width=1.4, tags=tags)
    cv.create_polygon(cx + s * 0.55, cy - s * 1.05, cx + s * 1.25, cy - s * 0.62,
                      cx + s * 0.42, cy - s * 0.35, fill=color, outline="",
                      tags=tags)


def icon_maximize(cv, cx, cy, s, color, tags=()):
    round_rect(cv, cx - s, cy - s * 0.82, cx + s, cy + s * 0.82, 2,
               fill="", outline=color, width=1.3, tags=tags)
    cv.create_line(cx - s, cy - s * 0.34, cx + s, cy - s * 0.34, fill=color,
                   width=1.3, tags=tags)


def icon_layout(cv, x, y, s, color, kind, tags=()):
    """Layout glyphs: auto / columns / rows / grid."""
    g = 1.6
    round_rect(cv, x, y, x + s, y + s, 2.5, fill="", outline=color, width=1.2,
               tags=tags)
    if kind == "Columns":
        cv.create_line(x + s / 2, y + g, x + s / 2, y + s - g, fill=color,
                       width=1.2, tags=tags)
    elif kind == "Rows":
        cv.create_line(x + g, y + s / 2, x + s - g, y + s / 2, fill=color,
                       width=1.2, tags=tags)
    elif kind in ("2 x 2", "Grid"):
        cv.create_line(x + s / 2, y + g, x + s / 2, y + s - g, fill=color,
                       width=1.2, tags=tags)
        cv.create_line(x + g, y + s / 2, x + s - g, y + s / 2, fill=color,
                       width=1.2, tags=tags)
    else:                                        # Auto
        cv.create_line(x + s * 0.55, y + g, x + s * 0.55, y + s - g, fill=color,
                       width=1.2, tags=tags)
        cv.create_line(x + s * 0.55, y + s / 2, x + s - g, y + s / 2, fill=color,
                       width=1.2, tags=tags)


def icon_broadcast(cv, cx, cy, s, color, tags=()):
    cv.create_oval(cx - s * 0.28, cy - s * 0.28, cx + s * 0.28, cy + s * 0.28,
                   fill=color, outline="", tags=tags)
    for k, ext in ((0.62, 120), (1.0, 120)):
        cv.create_arc(cx - s * k, cy - s * k, cx + s * k, cy + s * k,
                      start=-60, extent=ext, style="arc", outline=color,
                      width=1.3, tags=tags)
        cv.create_arc(cx - s * k, cy - s * k, cx + s * k, cy + s * k,
                      start=120, extent=ext, style="arc", outline=color,
                      width=1.3, tags=tags)


def icon_dots(cv, cx, cy, s, color, tags=()):
    """Three dots in a row: the 'more' affordance."""
    r = max(1.1, s * 0.24)
    for dx in (-s * 0.75, 0.0, s * 0.75):
        cv.create_oval(cx + dx - r, cy - r, cx + dx + r, cy + r, fill=color,
                       outline="", tags=tags)


def icon_expand(cv, cx, cy, s, color, tags=()):
    """Two diagonal arrows pointing out of the corners (maximise)."""
    kw = dict(fill=color, width=1.3, capstyle="round", joinstyle="round",
              tags=tags)
    a = s * 0.9
    h = s * 0.55
    cv.create_line(cx - a, cy + a, cx - a * 0.15, cy + a * 0.15, **kw)
    cv.create_line(cx - a, cy + a - h, cx - a, cy + a, cx - a + h, cy + a, **kw)
    cv.create_line(cx + a, cy - a, cx + a * 0.15, cy - a * 0.15, **kw)
    cv.create_line(cx + a - h, cy - a, cx + a, cy - a, cx + a, cy - a + h, **kw)


def icon_sidebar(cv, cx, cy, s, color, tags=()):
    """Window outline with a left panel."""
    round_rect(cv, cx - s, cy - s * 0.78, cx + s, cy + s * 0.78, 2.2, fill="",
               outline=color, width=1.2, tags=tags)
    cv.create_line(cx - s * 0.3, cy - s * 0.78, cx - s * 0.3, cy + s * 0.78,
                   fill=color, width=1.2, tags=tags)


def icon_tab(cv, cx, cy, s, color, tags=()):
    """Window outline with a tab notch and a small plus: new tab."""
    round_rect(cv, cx - s, cy - s * 0.78, cx + s, cy + s * 0.78, 2.2, fill="",
               outline=color, width=1.2, tags=tags)
    cv.create_line(cx - s, cy - s * 0.3, cx + s, cy - s * 0.3, fill=color,
                   width=1.2, tags=tags)
    cv.create_line(cx - s * 0.25, cy - s * 0.78, cx - s * 0.25, cy - s * 0.3,
                   fill=color, width=1.2, tags=tags)
    icon_plus(cv, cx, cy + s * 0.25, s * 0.28, color, tags=tags, width=1.2)


def icon_menu(cv, cx, cy, s, color, tags=()):
    for dy in (-s * 0.6, 0, s * 0.6):
        cv.create_line(cx - s, cy + dy, cx + s, cy + dy, fill=color, width=1.5,
                       capstyle="round", tags=tags)


def logo(cv, x, y, s, tags=()):
    """App mark: gradient tile with a terminal caret."""
    c1 = mix(UI["accent"], "#000000", 0.30)
    c2 = mix(UI["accent2"], "#000000", 0.30)
    round_rect(cv, x, y, x + s, y + s, s * 0.28, fill=c1, outline="", tags=tags)
    for i in range(10):
        t = i / 9
        round_rect(cv, x, y + s * t * 0.9, x + s, y + s, s * 0.28,
                   fill=mix(c1, c2, t), outline="", tags=tags)
    cv.create_line(x + s * 0.28, y + s * 0.33, x + s * 0.48, y + s * 0.5,
                   x + s * 0.28, y + s * 0.67, fill="#FFFFFF", width=1.7,
                   capstyle="round", joinstyle="round", tags=tags)
    cv.create_line(x + s * 0.56, y + s * 0.68, x + s * 0.74, y + s * 0.68,
                   fill="#FFFFFF", width=1.7, capstyle="round", tags=tags)


# ---------------------------------------------------------------- animation
class Animator:
    """Frame-stepped tweens. apply(value) is called with an eased 0..1 float."""

    def __init__(self):
        self._tweens = {}

    def add(self, key, ms, apply, on_done=None):
        self._tweens[key] = [time.monotonic(), ms / 1000.0, apply, on_done]
        apply(0.0)

    def cancel(self, key):
        self._tweens.pop(key, None)

    def step(self):
        if not self._tweens:
            return False
        now = time.monotonic()
        done = []
        for key, (t0, dur, apply, on_done) in list(self._tweens.items()):
            t = 1.0 if dur <= 0 else min(1.0, (now - t0) / dur)
            eased = 1 - (1 - t) ** 3          # ease-out cubic
            try:
                apply(eased)
            except Exception:                 # noqa: BLE001
                done.append(key)
                continue
            if t >= 1.0:
                done.append(key)
                if on_done:
                    on_done()
        for key in done:
            self._tweens.pop(key, None)
        return True
