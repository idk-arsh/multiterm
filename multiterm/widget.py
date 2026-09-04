"""Tk canvas terminal view.

Renders a Screen incrementally (only rows the emulator marked dirty), encodes
key events into VT input, and draws the in-pane furniture: a rounded shaded
card, an overlay scrollbar you can drag, a jump-to-bottom pill, a copy chip
for selections and a find bar with match highlighting.
"""
import tkinter as tk
import tkinter.font as tkfont

from . import gfx, theme, ui
from .theme import UI, mix
from .vt import (F_BOLD, F_DIM, F_HIDDEN, F_ITALIC, F_REVERSE, F_STRIKE,
                 F_UNDER)

CTRL = 0x0004
SHIFT = 0x0001
ALT = 0x20000

PAD_X = 12          # design pixels; apply_scale() adjusts these
PAD_Y = 10
RADIUS = 9
SB_W = 6


def apply_scale():
    """Re-derive the pane's own metrics for the display scale."""
    global PAD_X, PAD_Y, RADIUS, SB_W
    PAD_X, PAD_Y = ui.px(12), ui.px(10)
    RADIUS, SB_W = ui.px(9), ui.px(6)
BLINK_MS = 530

# cell styles used when grouping runs
ST_NORMAL, ST_SEL, ST_MATCH, ST_CUR = 0, 1, 2, 3

_KEYS = {"Up": "A", "Down": "B", "Right": "C", "Left": "D",
         "Home": "H", "End": "F"}
_TILDE = {"Insert": 2, "Delete": 3, "Prior": 5, "Next": 6,
          "F5": 15, "F6": 17, "F7": 18, "F8": 19,
          "F9": 20, "F10": 21, "F11": 23, "F12": 24}
_SS3 = {"F1": "P", "F2": "Q", "F3": "R", "F4": "S"}
_APP_CHORDS = ("T", "N", "W", "B", "M", "E", "D", "S",
               "PLUS", "UNDERSCORE", "QUESTION")


class TerminalView(tk.Frame):
    def __init__(self, master, session, settings, on_focus=None):
        super().__init__(master, bd=0, highlightthickness=0)
        self.session = session
        self.settings = settings
        self.on_focus = on_focus
        self.router = None

        self._apply_theme_colors(settings.get("theme", theme.DEFAULT_THEME))
        self.card_bg = UI["border_soft"]
        self.canvas = tk.Canvas(self, bg=self.card_bg, highlightthickness=0,
                                bd=0, takefocus=1, cursor="xterm")
        self.canvas.pack(fill="both", expand=True)
        self._set_font(settings.get("font_family") or theme.mono_family(),
                       settings.get("font_size", 11))

        self.view_offset = 0
        self.scroll_target = 0
        self.sel_anchor = None
        self.sel_head = None
        self.blink_on = True
        self.hovering = False

        self.find_open = False
        self.find_query = ""
        self.matches = {}          # line index -> [(x0, x1), ...]
        self.match_list = []       # [(line index, x0)]
        self.match_pos = -1

        self._prev_sel = None
        self.last_render = 0.0
        self._card_sig = None
        self._last_sb = 0
        self._need_full = True
        self._ovl_sig = None
        self._ovl_hits = []
        self._sb_drag = False
        self._cursor_items = ()
        self._last_cursor = None
        self._last_size = (0, 0)
        self._focused = False
        self._rows_drawn = 0

        c = self.canvas
        c.bind("<Configure>", self._on_configure)
        c.bind("<Key>", self._on_key)
        c.bind("<FocusIn>", self._on_focus_in)
        c.bind("<FocusOut>", self._on_focus_out)
        c.bind("<Enter>", self._on_enter)
        c.bind("<Leave>", self._on_leave)
        c.bind("<Motion>", self._on_motion)
        c.bind("<Button-1>", self._on_click)
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_release)
        c.bind("<Double-Button-1>", self._on_double)
        c.bind("<Button-3>", self._on_right_click)
        c.bind("<MouseWheel>", self._on_wheel)

    # ---------------------------------------------------------------- theme
    def _apply_theme_colors(self, name):
        th = theme.get(name)
        self.pal = theme.build_palette(name)
        self.bg = th["bg"]
        self.fg = th["fg"]
        self.cursor_color = th["cursor"]
        self.sel_bg = th["sel"]
        self.bg_top = self.bg
        self.match_bg = mix(self.bg, UI["warn"], 0.35)
        self.cur_match_bg = mix(self.bg, UI["accent"], 0.65)

    def set_theme(self, name):
        self.settings["theme"] = name
        self._apply_theme_colors(name)
        self.canvas.delete("all")
        self._cursor_items = ()
        self._need_full = True
        self._ovl_sig = None
        self.render()

    def set_card_bg(self, color):
        """Colour showing through the rounded corners (the pane's border)."""
        if color == self.card_bg:
            return
        self.card_bg = color
        self.canvas.config(bg=color)
        self._need_full = True

    # ----------------------------------------------------------------- font
    def _set_font(self, family, size):
        pxs = ui.font_px(size)      # negative == pixels, scaled by us
        self.font = tkfont.Font(family=family, size=pxs)
        self.font_b = tkfont.Font(family=family, size=pxs, weight="bold")
        self.font_i = tkfont.Font(family=family, size=pxs, slant="italic")
        self.font_bi = tkfont.Font(family=family, size=pxs, weight="bold",
                                   slant="italic")
        self.ui_font = gfx.font(8)
        self.cw = max(1, self.font.measure("M"))
        line = self.font.metrics("linespace")
        self.leading = max(1, round(abs(pxs) * 0.20))
        self.ch = line + self.leading
        self.text_dy = self.leading // 2

    def set_font_size(self, size):
        size = max(6, min(40, int(size)))
        self.settings["font_size"] = size
        self._set_font(self.settings.get("font_family") or theme.mono_family(),
                       size)
        self.canvas.delete("all")
        self._cursor_items = ()
        self._resize_session()
        self._need_full = True
        self._ovl_sig = None
        self.render()

    # ------------------------------------------------------------- geometry
    def grid_size_px(self):
        w = self.canvas.winfo_width() - 2 * PAD_X
        h = self.canvas.winfo_height() - 2 * PAD_Y
        return max(2, w // self.cw), max(1, h // self.ch)

    def _on_configure(self, _e=None):
        size = (self.canvas.winfo_width(), self.canvas.winfo_height())
        if size == self._last_size:
            return
        self._last_size = size
        self._resize_session()
        self.canvas.delete("row")
        self._need_full = True
        self._ovl_sig = None
        self.render()

    def _resize_session(self):
        cols, rows = self.grid_size_px()
        self.session.resize(cols, rows)
        self._need_full = True

    # ---------------------------------------------------------------- focus
    def focus_terminal(self):
        self.canvas.focus_set()

    def _on_focus_in(self, _e=None):
        self._focused = True
        self.blink_on = True
        self._last_cursor = None
        self._need_full = True
        if self.on_focus:
            self.on_focus(self)
        self.render()

    def _on_focus_out(self, _e=None):
        self._focused = False
        self._last_cursor = None
        self._need_full = True
        self.render()

    def _on_enter(self, _e=None):
        self.hovering = True
        self._draw_overlays()

    def _on_leave(self, _e=None):
        self.hovering = False
        self._draw_overlays()

    # ------------------------------------------------------------ colouring
    def _color(self, c, default):
        if c is None:
            return default
        if isinstance(c, tuple):
            return "#%02X%02X%02X" % c
        if 0 <= c < len(self.pal):
            return self.pal[c]
        return default

    def _resolve(self, attr, style):
        fg, bg, flags = attr
        f = self._color(fg, self.fg)
        b = self._color(bg, self.bg)
        if flags & F_BOLD and isinstance(fg, int) and fg < 8:
            f = self.pal[fg + 8]
        if flags & F_REVERSE:
            f, b = b, f
        if flags & F_DIM:
            f = mix(f, b, 0.45)
        if flags & F_HIDDEN:
            f = b
        if style == ST_SEL:
            b = self.sel_bg
        elif style == ST_MATCH:
            b = self.match_bg
        elif style == ST_CUR:
            b, f = self.cur_match_bg, "#FFFFFF"
        if style and f == b:
            f = self.fg
        return f, b

    def _font_for(self, flags):
        if flags & F_BOLD and flags & F_ITALIC:
            return self.font_bi
        if flags & F_BOLD:
            return self.font_b
        if flags & F_ITALIC:
            return self.font_i
        return self.font

    # ------------------------------------------------------------ selection
    def _sel_range(self):
        if self.sel_anchor is None or self.sel_head is None:
            return None
        a, b = self.sel_anchor, self.sel_head
        if a > b:
            a, b = b, a
        return None if a == b else (a, b)

    def _row_styles(self, line_idx, cols):
        """Per-cell style list, or None when the row is plain."""
        styles = None
        rng = self._sel_range()
        if rng:
            (y0, x0), (y1, x1) = rng
            if y0 <= line_idx <= y1:
                start = x0 if line_idx == y0 else 0
                end = x1 if line_idx == y1 else cols
                if start < end:
                    styles = [ST_NORMAL] * cols
                    for i in range(max(0, start), min(cols, end)):
                        styles[i] = ST_SEL
        hits = self.matches.get(line_idx)
        if hits:
            if styles is None:
                styles = [ST_NORMAL] * cols
            cur = self.match_list[self.match_pos] if 0 <= self.match_pos < len(
                self.match_list) else None
            for a, b in hits:
                st = ST_CUR if cur == (line_idx, a) else ST_MATCH
                for i in range(max(0, a), min(cols, b)):
                    if styles[i] != ST_SEL:
                        styles[i] = st
        return styles

    # ------------------------------------------------------------ rendering
    def max_offset(self):
        scr = self.session.screen
        return max(0, scr.total_lines() - scr.rows)

    def render(self, force=False):
        scr = self.session.screen
        c = self.canvas

        sb = len(scr.scrollback)
        if self.view_offset > 0 and sb > self._last_sb:
            grow = sb - self._last_sb
            self.view_offset = min(self.max_offset(), self.view_offset + grow)
            self.scroll_target = min(self.max_offset(), self.scroll_target + grow)
        self._last_sb = sb

        h = c.winfo_height()
        rows = min(scr.rows, max(1, (h - 2 * PAD_Y) // self.ch))
        sel = self._sel_range()
        full = (force or self._need_full or scr.full_dirty
                or rows != self._rows_drawn or sel != self._prev_sel
                or self.view_offset > 0 or self.matches)
        dirty = scr.dirty
        scr.dirty = set()
        scr.full_dirty = False
        self._need_full = False
        self._prev_sel = sel
        self._rows_drawn = rows

        total = scr.total_lines()
        first = max(0, total - scr.rows - self.view_offset)

        if full:
            c.delete("row")
            self._draw_card()
            todo = range(rows)
        else:
            todo = [y for y in dirty if y < rows]
            if not todo:
                self._draw_cursor(scr, rows)
                return

        for i in todo:
            idx = first + i
            line_chars, line_attrs = scr.line(idx)
            self._draw_row(i, line_chars, line_attrs,
                           self._row_styles(idx, len(line_chars)),
                           clear=not full)
        self._draw_cursor(scr, rows)
        self._draw_overlays()

    def _draw_card(self):
        """Shaded, rounded background for the terminal itself.

        Cached: it only costs anything when the size, theme or focus colour
        actually changes, so streaming output never repaints it."""
        c = self.canvas
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 4 or h < 4:
            return
        sig = (w, h, self.bg, self.bg_top, self.card_bg, self._focused)
        if sig == self._card_sig:
            return
        self._card_sig = sig
        c.delete("card")
        c.create_rectangle(0, 0, w, h, fill=self.bg, outline="", tags="card")
        c.tag_lower("card")

    def _draw_row(self, y, chars, attrs, styles, clear=True):
        c = self.canvas
        tag = "r%d" % y
        if clear:
            c.delete(tag)
        n = len(chars)
        ypx = PAD_Y + y * self.ch
        ty = ypx + self.text_dy
        i = 0
        ns = len(styles) if styles else 0
        while i < n:
            attr = attrs[i]
            style = styles[i] if i < ns else ST_NORMAL
            j = i + 1
            while j < n:
                if attrs[j] != attr or (styles[j] if j < ns else ST_NORMAL) != style:
                    break
                j += 1
            f, b = self._resolve(attr, style)
            x0 = PAD_X + i * self.cw
            x1 = PAD_X + j * self.cw
            if b != self.bg:
                c.create_rectangle(x0, ypx, x1, ypx + self.ch, fill=b,
                                   outline="", tags=("row", tag))
            seg = "".join(chars[i:j])
            if seg.strip():
                c.create_text(x0, ty, text=seg, anchor="nw", fill=f,
                              font=self._font_for(attr[2]), tags=("row", tag))
                if attr[2] & F_UNDER:
                    yy = ypx + self.ch - self.leading // 2 - 1
                    c.create_line(x0, yy, x1, yy, fill=f, tags=("row", tag))
                if attr[2] & F_STRIKE:
                    yy = ypx + self.ch // 2
                    c.create_line(x0, yy, x1, yy, fill=f, tags=("row", tag))
            i = j

    def _draw_cursor(self, scr, rows):
        c = self.canvas
        show = (scr.cursor_visible and self.view_offset == 0
                and self.session.is_alive() and scr.y < rows
                and (self.blink_on or not self._focused))
        state = (show, scr.x, scr.y, self._focused)
        if state == self._last_cursor:
            return
        self._last_cursor = state
        for item in self._cursor_items:
            c.delete(item)
        self._cursor_items = ()
        if not show:
            return
        x0 = PAD_X + scr.x * self.cw
        y0 = PAD_Y + scr.y * self.ch
        x1, y1 = x0 + self.cw, y0 + self.ch
        if self._focused:
            rect = gfx.round_rect(c, x0, y0, x1, y1, 2,
                                  fill=self.cursor_color, outline="")
            items = [rect]
            ch = scr.chars[scr.y][scr.x] if scr.x < scr.cols else " "
            if ch.strip():
                items.append(c.create_text(x0, y0 + self.text_dy, text=ch,
                                           anchor="nw", fill=self.bg,
                                           font=self.font))
            self._cursor_items = tuple(items)
        else:
            self._cursor_items = (gfx.round_rect(
                c, x0 + 1, y0 + 1, x1 - 1, y1 - 1, 2, fill="",
                outline=mix(self.cursor_color, self.bg, 0.4), width=1),)

    # ------------------------------------------------------------ overlays
    def _draw_overlays(self):
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        if w < 40 or h < 40:
            return
        scr = self.session.screen
        max_off = self.max_offset()
        track_y0, track_y1 = PAD_Y, h - PAD_Y
        track_h = track_y1 - track_y0
        thumb_h = thumb_y = 0
        if max_off > 0:
            thumb_h = max(ui.px(30), track_h * scr.rows / float(scr.total_lines()))
            thumb_y = track_y0 + (track_h - thumb_h) * (
                1.0 - self.view_offset / float(max_off))
        sig = (w, h, int(thumb_y), int(thumb_h), max_off > 0,
               self.view_offset > 0, self.hovering, self._focused,
               bool(self._sel_range()), self.find_open, self.find_query,
               self.match_pos, len(self.match_list))
        if sig == self._ovl_sig:
            return
        self._ovl_sig = sig
        c.delete("ovl")
        self._ovl_hits = []

        # ---- scrollbar
        if max_off > 0:
            ty = thumb_y
            x1 = w - ui.px(5)
            x0 = x1 - SB_W
            strong = self.hovering or self._sb_drag or self.view_offset > 0
            gfx.round_rect(c, x0, track_y0, x1, track_y1, SB_W / 2,
                           fill=mix(self.bg, "#FFFFFF", 0.05 if strong else 0.02),
                           outline="", tags="ovl")
            gfx.round_rect(c, x0, ty, x1, ty + thumb_h, SB_W / 2,
                           fill=mix(self.bg, "#FFFFFF", 0.32 if strong else 0.14),
                           outline="", tags="ovl")
            self._ovl_hits.append((w - ui.px(16), 0, w, h, "scrollbar"))

        # ---- jump to bottom
        if self.view_offset > 0:
            label = "↓  jump to latest"
            bw = gfx.measure(label, 8, True) + ui.px(26)
            bx = (w - bw) / 2
            by = h - PAD_Y - ui.px(30)
            gfx.round_rect(c, bx, by, bx + bw, by + ui.px(26), ui.px(13),
                           fill=mix(self.bg, "#FFFFFF", 0.12),
                           outline=mix(self.bg, "#FFFFFF", 0.22), tags="ovl")
            c.create_text(bx + bw / 2, by + ui.px(13), text=label,
                          fill=self.fg,
                          font=(theme.ui_family(), 8, "bold"), tags="ovl")
            self._ovl_hits.append((bx, by, bx + bw, by + ui.px(26), "jump"))

        # ---- copy chip for the current selection
        if self._sel_range():
            label = "⧉  copy"
            bw = gfx.measure(label, 8) + ui.px(26)
            bx, by = PAD_X, h - PAD_Y - ui.px(30)
            gfx.round_rect(c, bx, by, bx + bw, by + ui.px(26), ui.px(13),
                           fill=mix(self.bg, "#FFFFFF", 0.12),
                           outline=mix(self.bg, "#FFFFFF", 0.22), tags="ovl")
            c.create_text(bx + bw / 2, by + ui.px(13), text=label, fill=self.fg,
                          font=(theme.ui_family(), 8), tags="ovl")
            self._ovl_hits.append((bx, by, bx + bw, by + ui.px(26), "copy"))

        # ---- find bar
        if self.find_open:
            bw = ui.px(250)
            bx = w - bw - ui.px(14)
            by = PAD_Y
            gfx.round_rect(c, bx, by, bx + bw, by + ui.px(30), ui.px(9),
                           fill=mix(self.bg, "#FFFFFF", 0.09),
                           outline=UI["border_hi"], tags="ovl")
            c.create_text(bx + 12, by + 15, text="⌕", anchor="w",
                          fill=UI["text_dim"],
                          font=(theme.ui_family(), 10), tags="ovl")
            shown = self.find_query or "find in pane…"
            c.create_text(bx + 28, by + 15, text=shown[:24], anchor="w",
                          fill=self.fg if self.find_query else UI["muted"],
                          font=(theme.mono_family(), 9), tags="ovl")
            count = ("%d/%d" % (self.match_pos + 1, len(self.match_list))
                     if self.match_list else ("0/0" if self.find_query else ""))
            c.create_text(bx + bw - 34, by + 15, text=count, anchor="e",
                          fill=UI["muted"], font=(theme.ui_family(), 8),
                          tags="ovl")
            gfx.icon_close(c, bx + bw - 15, by + 15, 4, UI["muted"], tags="ovl")
            self._ovl_hits.append((bx + bw - 26, by, bx + bw, by + 30, "find_close"))
        c.tag_raise("ovl")

    def _overlay_at(self, x, y):
        for x0, y0, x1, y1, key in self._ovl_hits:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return key
        return None

    # ------------------------------------------------------------ find
    def toggle_find(self):
        self.find_open = not self.find_open
        if not self.find_open:
            self.find_query = ""
            self.matches = {}
            self.match_list = []
            self.match_pos = -1
        self._need_full = True
        self._ovl_sig = None
        self.render()

    def _run_find(self):
        self.matches = {}
        self.match_list = []
        self.match_pos = -1
        q = self.find_query.lower()
        if len(q) < 1:
            return
        scr = self.session.screen
        for idx in range(scr.total_lines()):
            text = "".join(scr.line(idx)[0]).lower()
            start = 0
            hits = []
            while True:
                pos = text.find(q, start)
                if pos < 0:
                    break
                hits.append((pos, pos + len(q)))
                self.match_list.append((idx, pos))
                start = pos + max(1, len(q))
            if hits:
                self.matches[idx] = hits
        if self.match_list:
            self.match_pos = len(self.match_list) - 1
            self._reveal_match()

    def _reveal_match(self):
        if not (0 <= self.match_pos < len(self.match_list)):
            return
        idx = self.match_list[self.match_pos][0]
        scr = self.session.screen
        total = scr.total_lines()
        want = total - scr.rows - max(0, idx - scr.rows // 2)
        self.view_offset = self.scroll_target = max(0, min(self.max_offset(), want))

    def find_step(self, delta):
        if not self.match_list:
            return
        self.match_pos = (self.match_pos + delta) % len(self.match_list)
        self._reveal_match()
        self._need_full = True
        self.render()

    # ------------------------------------------------------------ scrolling
    def animate_scroll(self):
        if self.view_offset == self.scroll_target:
            return False
        diff = self.scroll_target - self.view_offset
        step = diff if abs(diff) <= 2 else int(diff * 0.4) or (1 if diff > 0 else -1)
        self.view_offset += step
        self.render(force=True)
        return True

    def scroll(self, lines):
        self.scroll_target = max(0, min(self.max_offset(),
                                        self.scroll_target + lines))

    def scroll_to_bottom(self):
        self.scroll_target = 0
        if self.view_offset:
            self.view_offset = 0
            self.render(force=True)

    def _on_wheel(self, e):
        step = 3 if abs(e.delta) < 200 else 6
        self.scroll(step if e.delta > 0 else -step)
        return "break"

    # ------------------------------------------------------- mouse / select
    def _cell_at(self, e):
        scr = self.session.screen
        total = scr.total_lines()
        first = max(0, total - scr.rows - self.view_offset)
        col = max(0, min(scr.cols, int((e.x - PAD_X) // self.cw)))
        row = max(0, int((e.y - PAD_Y) // self.ch))
        return first + row, col

    def _scroll_from_mouse(self, y):
        h = self.canvas.winfo_height()
        track_y0, track_y1 = PAD_Y, h - PAD_Y
        scr = self.session.screen
        thumb_h = max(ui.px(30), (track_y1 - track_y0) * scr.rows /
                      float(max(1, scr.total_lines())))
        span = max(1.0, (track_y1 - track_y0) - thumb_h)
        frac = min(1.0, max(0.0, (y - track_y0 - thumb_h / 2) / span))
        self.view_offset = self.scroll_target = round(self.max_offset() * (1 - frac))
        self.render(force=True)

    def _on_motion(self, e):
        over = self._overlay_at(e.x, e.y)
        self.canvas.config(cursor="hand2" if over in ("jump", "copy", "find_close")
                           else "xterm")

    def _on_click(self, e):
        self.focus_terminal()
        hit = self._overlay_at(e.x, e.y)
        if hit == "jump":
            self.scroll_to_bottom()
            return "break"
        if hit == "copy":
            self.copy()
            self.clear_selection()
            return "break"
        if hit == "find_close":
            self.toggle_find()
            return "break"
        if hit == "scrollbar":
            self._sb_drag = True
            self._scroll_from_mouse(e.y)
            return "break"
        self.sel_anchor = self._cell_at(e)
        self.sel_head = self.sel_anchor
        self.render()
        return "break"

    def _on_drag(self, e):
        if self._sb_drag:
            self._scroll_from_mouse(e.y)
            return "break"
        if self.sel_anchor is None:
            return "break"
        self.sel_head = self._cell_at(e)
        if e.y < PAD_Y:
            self.scroll(1)
        elif e.y > self.canvas.winfo_height() - PAD_Y:
            self.scroll(-1)
        self.render()
        return "break"

    def _on_release(self, _e):
        self._sb_drag = False
        return "break"

    def _on_double(self, e):
        if self._overlay_at(e.x, e.y):
            return "break"
        idx, col = self._cell_at(e)
        chars = self.session.screen.line(idx)[0]
        if col >= len(chars):
            return "break"
        stop = " \t\"'`()[]{}<>|;:,"
        a = b = col
        while a > 0 and chars[a - 1] not in stop:
            a -= 1
        while b < len(chars) and chars[b] not in stop:
            b += 1
        self.sel_anchor, self.sel_head = (idx, a), (idx, b)
        self.render()
        return "break"

    def _on_right_click(self, _e):
        if self._sel_range():
            self.copy()
            self.clear_selection()
        else:
            self.paste()
        return "break"

    def clear_selection(self):
        if self.sel_anchor or self.sel_head:
            self.sel_anchor = self.sel_head = None
            self.render()

    def selected_text(self):
        rng = self._sel_range()
        if not rng:
            return ""
        (y0, x0), (y1, x1) = rng
        scr = self.session.screen
        out = []
        for idx in range(y0, y1 + 1):
            chars = scr.line(idx)[0]
            s = x0 if idx == y0 else 0
            e = x1 if idx == y1 else len(chars)
            out.append("".join(chars[s:e]).rstrip())
        return "\n".join(out)

    def copy(self):
        txt = self.selected_text()
        if txt:
            self.clipboard_clear()
            self.clipboard_append(txt)
        return bool(txt)

    def paste(self):
        try:
            txt = self.clipboard_get()
        except tk.TclError:
            return
        txt = txt.replace("\r\n", "\r").replace("\n", "\r")
        if self.session.screen.bracketed_paste:
            txt = "\x1b[200~" + txt + "\x1b[201~"
        self.send(txt)

    # ----------------------------------------------------------------- keys
    def send(self, data):
        self.scroll_to_bottom()
        if self.router:
            self.router(self, data)
        else:
            self.session.write(data)

    def _mods(self, state):
        m = 1
        if state & SHIFT:
            m += 1
        if state & ALT:
            m += 2
        if state & CTRL:
            m += 4
        return m

    def _find_key(self, e):
        """Keystrokes go to the find bar while it is open."""
        ks = e.keysym
        if ks == "Escape":
            self.toggle_find()
            return True
        if ks in ("Return", "KP_Enter"):
            self.find_step(-1 if e.state & SHIFT else 1)
            return True
        if ks == "BackSpace":
            self.find_query = self.find_query[:-1]
            self._run_find()
            self._need_full = True
            self._ovl_sig = None
            self.render()
            return True
        if e.char and e.char.isprintable():
            self.find_query += e.char
            self._run_find()
            self._need_full = True
            self._ovl_sig = None
            self.render()
            return True
        return False

    def _on_key(self, e):
        ks = e.keysym
        state = e.state
        ctrl = bool(state & CTRL)
        shift = bool(state & SHIFT)
        alt = bool(state & ALT)

        if ks in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L",
                  "Alt_R", "Win_L", "Win_R", "Caps_Lock", "??"):
            return "break"

        if ctrl and not shift and ks in ("f", "F"):
            self.toggle_find()
            return "break"
        if self.find_open and not ctrl and self._find_key(e):
            return "break"

        if not self.session.is_alive() and ks in ("Return", "KP_Enter"):
            self.session.restart()
            self.view_offset = self.scroll_target = 0
            self._need_full = True
            self.render()
            return "break"

        if ctrl and shift and ks in ("C", "c"):
            self.copy()
            return "break"
        if ctrl and shift and ks in ("V", "v"):
            self.paste()
            return "break"
        if shift and ks == "Insert":
            self.paste()
            return "break"
        if shift and ks == "Prior":
            self.scroll(self.session.screen.rows - 2)
            return "break"
        if shift and ks == "Next":
            self.scroll(-(self.session.screen.rows - 2))
            return "break"

        if ctrl and shift and ks.upper() in _APP_CHORDS:
            return None
        if (ctrl and ks == "Tab") or ks == "F11":
            return None
        if alt and ks in "123456789":
            return None

        self.clear_selection()
        mods = self._mods(state)

        if ks in _KEYS:
            letter = _KEYS[ks]
            if mods > 1:
                self.send("\x1b[1;%d%s" % (mods, letter))
            elif self.session.screen.app_cursor_keys:
                self.send("\x1bO" + letter)
            else:
                self.send("\x1b[" + letter)
            return "break"
        if ks in _TILDE:
            num = _TILDE[ks]
            self.send("\x1b[%d~" % num if mods == 1 else "\x1b[%d;%d~" % (num, mods))
            return "break"
        if ks in _SS3:
            self.send("\x1bO" + _SS3[ks] if mods == 1
                      else "\x1b[1;%d%s" % (mods, _SS3[ks]))
            return "break"
        if ks in ("Return", "KP_Enter"):
            self.send("\r")
            return "break"
        if ks == "BackSpace":
            self.send("\x08" if ctrl else "\x7f")
            return "break"
        if ks == "Tab":
            self.send("\t")
            return "break"
        if ks == "ISO_Left_Tab":
            self.send("\x1b[Z")
            return "break"
        if ks == "Escape":
            self.send("\x1b")
            return "break"

        ch = e.char
        if ch:
            self.send("\x1b" + ch if alt and not ctrl else ch)
            return "break"
        if ctrl and len(ks) == 1:
            o = ord(ks.upper())
            if 64 <= o <= 95:
                self.send(chr(o - 64))
                return "break"
        return "break"

    def blink_tick(self, on):
        if on != self.blink_on:
            self.blink_on = on
            if self._focused:
                self._draw_cursor(self.session.screen, self._rows_drawn or 1)
