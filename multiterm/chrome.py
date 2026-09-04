"""Canvas-drawn application chrome: sidebar, top bar, tab strip, command bar,
status bar, and the header and footer of every pane card. Every surface is
painted by hand so the whole window shares one visual language: flat dark
surfaces, hairline borders, one warm accent per card, nothing glowing."""
import os
import tkinter as tk

from . import gfx, theme
from .theme import UI, mix
from .ui import px

UIF = theme.ui_family()


def f(size, bold=False):
    """Font tuple at the current display scale (size stays in design pt)."""
    return gfx.font(size, bold, UIF)


def apply_scale():
    """Re-derive every structural size for the current display scale."""
    Sidebar.WIDTH = px(240)
    Sidebar.ROW_WS = px(34)
    Sidebar.ROW_FOLDER = px(30)
    Sidebar.ROW_SECTION = px(30)
    HeaderBar.H = px(50)
    TabStrip.H = px(40)
    PaneHeader.H = px(36)
    PaneFooter.H = px(28)
    CommandBar.H = px(58)
    StatusBar.H = px(28)


measure = gfx.measure

LAYOUT_LABELS = {"Auto": "Auto", "Columns": "Columns", "Rows": "Rows",
                 "2 x 2": "Grid"}


def fit(text, size, max_w, bold=False):
    """Truncate with an ellipsis so the label really fits in max_w pixels."""
    if max_w <= 0:
        return ""
    if measure(text, size, bold) <= max_w:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid] + "…", size, bold) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo] + "…") if lo else ""


def short_path(path, limit=40):
    """~/dev/project style path, trimmed from the left at a separator."""
    if not path:
        return ""
    home = os.path.expanduser("~")
    p = path
    if os.path.normcase(p).startswith(os.path.normcase(home)):
        p = "~" + p[len(home):]
    p = p.replace("\\", "/")
    if len(p) <= limit:
        return p
    tail = p[-(limit - 1):]
    cut = tail.find("/")
    return "…" + (tail[cut:] if 0 <= cut < len(tail) - 1 else tail)


class _HitCanvas(tk.Canvas):
    """Canvas with rectangle hit-testing and hover tracking."""

    def __init__(self, master, **kw):
        super().__init__(master, highlightthickness=0, bd=0, **kw)
        self._hits = []
        self._hover = None
        self._pressed = None
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", lambda _e: self.redraw())

    def hit(self, x, y):
        for x0, y0, x1, y1, key in reversed(self._hits):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return key
        return None

    def _set_hover(self, key):
        if key != self._hover:
            self._hover = key
            self.redraw()
            self.config(cursor="hand2" if key else "")

    def _on_motion(self, e):
        self._set_hover(self.hit(e.x, e.y))

    def _on_press(self, e):
        self._pressed = self.hit(e.x, e.y)
        if self._pressed:
            self.redraw()

    def _on_release(self, e):
        key = self.hit(e.x, e.y)
        was, self._pressed = self._pressed, None
        self.redraw()
        if key and key == was:
            self.activate(key, e)

    def activate(self, key, event):
        pass

    def redraw(self):
        pass

    # helpers -------------------------------------------------------------
    def add_hit(self, x0, y0, x1, y1, key):
        self._hits.append((x0, y0, x1, y1, key))

    def state(self, key):
        if self._pressed == key:
            return "press"
        if self._hover == key:
            return "hover"
        return "idle"

    def _ibtn(self, x, cy, key, draw, size, w=None, tone=None):
        """Square icon button with its left edge at x. Returns the right edge."""
        w = w or px(28)
        st = self.state(key)
        if st != "idle":
            gfx.round_rect(self, x, cy - w / 2, x + w, cy + w / 2, px(7),
                           fill=UI["raised"], outline="")
        col = tone or (UI["text"] if st != "idle" else UI["muted"])
        draw(self, x + w / 2, cy, size, col)
        self.add_hit(x, cy - w / 2, x + w, cy + w / 2, key)
        return x + w

    def _ibtn_r(self, right, cy, key, draw, size, w=None, tone=None):
        """Same, anchored by its right edge. Returns the left edge."""
        w = w or px(28)
        self._ibtn(right - w, cy, key, draw, size, w, tone)
        return right - w


# --------------------------------------------------------------------- side
class Sidebar(_HitCanvas):
    """Workspaces and the folders inside them. Pinned ones sit on top."""

    WIDTH = 240
    ROW_WS = 34
    ROW_FOLDER = 30
    ROW_SECTION = 30

    def __init__(self, master, store, callbacks):
        super().__init__(master, width=self.WIDTH, bg=UI["sidebar"])
        self.store = store
        self.cb = callbacks
        self.offset = 0
        self.active_ws = None
        self._dirty = False
        self._content_h = 0
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-3>", self._context)
        self.bind("<Double-Button-1>", self._double)

    def mark_dirty(self):
        """Redraw once, soon. Used when the set of open folders changes."""
        if not self._dirty:
            self._dirty = True
            self.after_idle(self._flush)

    def _flush(self):
        self._dirty = False
        try:
            self.redraw()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ geometry
    def rows(self):
        out = [("title", None, None)]
        pinned = [w for w in self.store.items if getattr(w, "pinned", False)]
        rest = [w for w in self.store.items if not getattr(w, "pinned", False)]

        def emit(ws):
            out.append(("ws", ws, None))
            if ws.expanded:
                entries = ws.entries()
                for p in entries[:24]:
                    out.append(("folder", ws, p))
                if not entries:
                    out.append(("empty", ws, None))

        if pinned:
            out.append(("section", None, "Pinned"))
            for w in pinned:
                emit(w)
            if rest:
                out.append(("section", None, "Folders"))
        for w in rest:
            emit(w)
        out.append(("add", None, None))
        return out

    def _row_h(self, kind):
        return {"title": px(46), "section": self.ROW_SECTION,
                "ws": self.ROW_WS, "folder": self.ROW_FOLDER,
                "empty": px(24), "add": px(40)}[kind]

    def _open_paths(self):
        try:
            return self.cb["open_paths"]() if "open_paths" in self.cb else set()
        except Exception:                              # noqa: BLE001
            return set()

    # ------------------------------------------------------------- drawing
    def redraw(self):
        self.delete("all")
        self._hits = []
        w = self.winfo_width() or self.WIDTH
        h = self.winfo_height() or 600
        self.create_rectangle(0, 0, w, h, fill=UI["sidebar"], outline="")
        self.create_line(w - 1, 0, w - 1, h, fill=UI["border_soft"])

        self._open = self._open_paths()
        y = -self.offset
        for kind, ws, path in self.rows():
            rh = self._row_h(kind)
            if y + rh > 0 and y < h:
                getattr(self, "_draw_" + kind)(w, y, rh, ws, path)
            y += rh
        self._content_h = y + self.offset

        # the title stays put while the list scrolls under it
        th = self._row_h("title")
        self.create_rectangle(0, 0, w - 1, th - px(4), fill=UI["sidebar"],
                              outline="")
        self._draw_title(w, 0, th, None, None)

    def _draw_title(self, w, y, h, _ws, _p):
        self.create_text(px(16), y + h / 2, text="Workspaces", anchor="w",
                         fill=UI["text_dim"], font=f(10))
        self._ibtn_r(w - px(10), y + h / 2, ("add_ws", None), gfx.icon_plus,
                     px(5), w=px(26))

    def _draw_section(self, w, y, h, _ws, label):
        self.create_text(px(16), y + h / 2 + px(3), text=label, anchor="w",
                         fill=UI["muted"], font=f(9))

    def _draw_ws(self, w, y, h, ws, _p):
        key = ("ws", ws)
        st = self.state(key)
        okey = ("open_ws", ws)
        ost = self.state(okey)
        active = ws is self.active_ws
        if active:
            gfx.round_rect(self, px(8), y + 2, w - px(8), y + h - 2, px(8),
                           fill=UI["raised"], outline="")
        elif st != "idle" or ost != "idle":
            gfx.round_rect(self, px(8), y + 2, w - px(8), y + h - 2, px(8),
                           fill=mix(UI["sidebar"], UI["raised"], 0.6), outline="")
        cy = y + h / 2
        gfx.icon_chevron(self, px(20), cy, px(3.5), UI["muted"], down=ws.expanded)
        missing = not ws.exists()
        try:
            n = len(ws.entries())
        except Exception:                              # noqa: BLE001
            n = 0
        right_w = px(40)
        name = fit(ws.name, 10, w - px(32) - right_w - px(12), True)
        self.create_text(px(32), cy, text=name, anchor="w",
                         fill=UI["err"] if missing else UI["text"],
                         font=f(10, True))
        self.add_hit(px(8), y, w - right_w, y + h, key)

        if st != "idle" or ost != "idle" or active:
            # open-everything arrow replaces the count while you are near
            bx = w - px(22)
            if ost != "idle":
                gfx.round_rect(self, bx - px(11), cy - px(11), bx + px(11),
                               cy + px(11), px(6), fill=UI["border"], outline="")
            col = UI["text"] if ost != "idle" else UI["text_dim"]
            self.create_polygon(bx - px(3), cy - px(5), bx + px(4), cy,
                                bx - px(3), cy + px(5), fill=col, outline="")
            self.add_hit(bx - px(12), y, bx + px(12), y + h, okey)
        elif n:
            label = str(n)
            bw = measure(label, 8) + px(12)
            gfx.round_rect(self, w - px(14) - bw, cy - px(8), w - px(14),
                           cy + px(8), px(5), fill=UI["panel"], outline="")
            self.create_text(w - px(14) - bw / 2, cy, text=label,
                             fill=UI["muted"], font=f(8))

    def _draw_folder(self, w, y, h, ws, path):
        key = ("folder", ws, path)
        st = self.state(key)
        if st != "idle":
            gfx.round_rect(self, px(8), y + 1, w - px(8), y + h - 1, px(7),
                           fill=mix(UI["sidebar"], UI["raised"], 0.6), outline="")
        cy = y + h / 2
        is_open = os.path.normcase(os.path.abspath(path)) in self._open
        r = px(2.5)
        self.create_oval(px(37) - r, cy - r, px(37) + r, cy + r,
                         fill=UI["ok"] if is_open else UI["border_hi"],
                         outline="")
        name = os.path.basename(path.rstrip("\\/")) or path
        runs = ws.command_for(path) if hasattr(ws, "command_for") else ""
        right_w = px(28)
        chip_w = 0
        if st == "idle" and runs:
            label = fit(runs, 8, px(78))
            chip_w = measure(label, 8) + px(12)
            gfx.round_rect(self, w - px(14) - chip_w, cy - px(8), w - px(14),
                           cy + px(8), px(5), fill=UI["panel"], outline="")
            self.create_text(w - px(14) - chip_w / 2, cy, text=label,
                             fill=UI["muted"], font=f(8))
            right_w = chip_w + px(8)
        self.create_text(px(48), cy,
                         text=fit(name, 10, w - px(48) - right_w - px(12)),
                         anchor="w",
                         fill=UI["text"] if (st != "idle" or is_open)
                         else UI["text_dim"], font=f(10))
        if st != "idle":
            gfx.icon_plus(self, w - px(22), cy, px(4.5), UI["text_dim"])
        self.add_hit(px(8), y, w - px(8), y + h, key)

    def _draw_empty(self, w, y, h, _ws, _p):
        self.create_text(px(48), y + h / 2, text="no sub-folders", anchor="w",
                         fill=UI["muted"], font=f(9))

    def _draw_add(self, w, y, h, _ws, _p):
        key = ("add_ws", None)
        st = self.state(key)
        if st != "idle":
            gfx.round_rect(self, px(8), y + px(4), w - px(8), y + h - px(4),
                           px(8), fill=mix(UI["sidebar"], UI["raised"], 0.6),
                           outline="")
        cy = y + h / 2
        col = UI["text"] if st != "idle" else UI["muted"]
        gfx.icon_plus(self, px(21), cy, px(4.5), col)
        self.create_text(px(34), cy, text="Add workspace", anchor="w",
                         fill=col, font=f(10))
        self.add_hit(px(8), y + px(2), w - px(8), y + h - px(2), key)

    # --------------------------------------------------------- interaction
    def activate(self, key, _event):
        kind = key[0]
        if kind == "ws":
            ws = key[1]
            ws.expanded = not ws.expanded
            self.active_ws = ws
            self.store.save()
            self.redraw()
            self.cb["select"](ws)
        elif kind == "open_ws":
            self.active_ws = key[1]
            self.cb["open_workspace"](key[1])
            self.redraw()
        elif kind == "folder":
            self.active_ws = key[1]
            self.cb["open_folder"](key[2], key[1])
            self.redraw()
        elif kind == "add_ws":
            self.cb["add_workspace"]()

    def _double(self, e):
        key = self.hit(e.x, e.y)
        if key and key[0] == "ws":
            self.cb["open_workspace"](key[1])

    def _context(self, e):
        key = self.hit(e.x, e.y)
        if not key:
            return
        if key[0] in ("ws", "open_ws"):
            self.cb["menu"](key[1], e.x_root, e.y_root)
        elif key[0] == "folder" and "folder_menu" in self.cb:
            self.cb["folder_menu"](key[1], key[2], e.x_root, e.y_root)

    def _wheel(self, e):
        h = self.winfo_height()
        content = self._content_h or h
        if content <= h:
            return "break"
        self.offset = max(0, min(content - h + 12,
                                 self.offset - (60 if e.delta > 0 else -60)))
        self.redraw()
        return "break"


# ------------------------------------------------------------------ top bar
class HeaderBar(_HitCanvas):
    """App mark and sidebar toggle on the left, the layout switch in the
    middle, shell picker / broadcast / new pane / new tab / menu on the right."""

    H = 50

    def __init__(self, master, app):
        super().__init__(master, height=self.H, bg=UI["chrome"])
        self.app = app
        self.subtitle = ""

    def redraw(self):
        self.delete("all")
        self._hits = []
        w = self.winfo_width() or 1200
        cy = self.H / 2
        self.create_rectangle(0, 0, w, self.H, fill=UI["chrome"], outline="")
        self.create_line(0, self.H - 1, w, self.H - 1, fill=UI["border_soft"])

        # ---- left: mark, name, sidebar toggle
        x = px(16)
        gfx.logo(self, x, cy - px(10), px(20))
        x += px(28)
        if w >= px(1000):
            self.create_text(x, cy, text="MultiTerm", anchor="w",
                             fill=UI["text"], font=f(11, True))
            x += measure("MultiTerm", 11, True) + px(10)
        x = self._ibtn(x + px(4), cy, ("sidebar", None), gfx.icon_sidebar, px(7))
        left_end = x + px(8)

        # ---- right cluster, laid out from the edge inwards
        rx = w - px(12)
        rx = self._ibtn_r(rx, cy, ("menu", None), gfx.icon_dots, px(5))
        rx = self._ibtn_r(rx - px(2), cy, ("new_tab", None), gfx.icon_tab, px(7))
        rx = self._ibtn_r(rx - px(2), cy, ("new_pane", None), gfx.icon_plus, px(5))
        self.create_line(rx - px(8), cy - px(9), rx - px(8), cy + px(9),
                         fill=UI["border"])
        rx -= px(16)

        on = self.app.broadcast.get()
        key = ("broadcast", None)
        st = self.state(key)
        wide = w >= px(900)
        label = "Broadcast"
        bw = (measure(label, 10, True) + px(44)) if wide else px(32)
        y0, y1 = cy - px(14), cy + px(14)
        bx = rx - bw
        if on:
            gfx.round_rect(self, bx, y0, rx, y1, px(8),
                           fill=mix(UI["chrome"], UI["accent"], 0.22),
                           outline=mix(UI["chrome"], UI["accent"], 0.5))
            col = UI["text"]
        else:
            gfx.round_rect(self, bx, y0, rx, y1, px(8),
                           fill=UI["raised"] if st != "idle" else "",
                           outline=UI["border"])
            col = UI["text"] if st != "idle" else UI["text_dim"]
        gfx.icon_broadcast(self, bx + (px(16) if wide else bw / 2), cy, px(7),
                           UI["accent"] if on else col)
        if wide:
            self.create_text(bx + px(28), cy, text=label, anchor="w",
                             fill=col, font=f(10, on))
        self.add_hit(bx, y0, rx, y1, key)
        rx = bx - px(8)

        label = self.app.shell_var.get()
        key = ("shell", None)
        st = self.state(key)
        pw = measure(label, 10) + px(40)
        sx = rx - pw
        gfx.round_rect(self, sx, y0, rx, y1, px(8),
                       fill=UI["raised"] if st != "idle" else UI["panel"],
                       outline=UI["border"])
        self.create_text(sx + px(12), cy, text=label, anchor="w",
                         fill=UI["text"] if st != "idle" else UI["text_dim"],
                         font=f(10))
        gfx.icon_chevron(self, rx - px(13), cy, px(3.5), UI["muted"], down=True)
        self.add_hit(sx, y0, rx, y1, key)
        right_start = sx - px(10)

        # ---- centre: layout switch, text if it fits, glyphs otherwise
        cur = self.app.layout_var.get()
        items = [(name, LAYOUT_LABELS.get(name, name)) for name, _g, _t in
                 self.app.LAYOUTS]
        text_ws = [measure(lbl, 10) + px(22) for _n, lbl in items]
        seg_text = sum(text_ws) + px(8)
        seg_icon = len(items) * px(32) + px(8)
        room = right_start - left_end
        if seg_text <= room:
            widths, seg_w, glyphs = text_ws, seg_text, False
        elif seg_icon <= room:
            widths, seg_w, glyphs = [px(32)] * len(items), seg_icon, True
        else:
            return
        sx0 = (w - seg_w) / 2
        if sx0 < left_end or sx0 + seg_w > right_start:
            sx0 = left_end
        gfx.round_rect(self, sx0, y0, sx0 + seg_w, y1, px(8), fill=UI["panel"],
                       outline=UI["border_soft"])
        bx = sx0 + px(4)
        for (name, lbl), sw in zip(items, widths):
            key = ("layout", name)
            on = name == cur
            st = self.state(key)
            if on:
                gfx.round_rect(self, bx, y0 + px(3), bx + sw, y1 - px(3), px(6),
                               fill=UI["raised"], outline="")
            elif st != "idle":
                gfx.round_rect(self, bx, y0 + px(3), bx + sw, y1 - px(3), px(6),
                               fill=mix(UI["panel"], UI["raised"], 0.5), outline="")
            col = UI["text"] if (on or st != "idle") else UI["muted"]
            if glyphs:
                gfx.icon_layout(self, bx + sw / 2 - px(7), cy - px(7), px(14),
                                col, name)
            else:
                self.create_text(bx + sw / 2, cy, text=lbl, fill=col,
                                 font=f(10, on))
            self.add_hit(bx, y0, bx + sw, y1, key)
            bx += sw

    def activate(self, key, event):
        kind = key[0]
        if kind == "new_pane":
            self.app.new_pane()
        elif kind == "new_tab":
            self.app.new_tab(1)
        elif kind == "layout":
            self.app.set_layout(key[1])
        elif kind == "broadcast":
            self.app.toggle_broadcast()
        elif kind == "shell":
            self.app.post_shell_menu(event.x_root, event.y_root)
        elif kind == "menu":
            self.app.post_main_menu(event.x_root, event.y_root)
        elif kind == "sidebar":
            self.app.toggle_sidebar()


# ---------------------------------------------------------------- tab strip
class TabStrip(_HitCanvas):
    H = 40

    def __init__(self, master, app):
        super().__init__(master, height=self.H, bg=UI["bg"])
        self.app = app
        self.tabs = []
        self.active = None
        self.bind("<Double-Button-1>", self._double)

    def set_tabs(self, tabs, active, animate=True):
        self.tabs, self.active = list(tabs), active
        self.redraw()

    def _tab_w(self, label):
        text = label if len(label) <= 22 else label[:21] + "…"
        return max(px(110), min(px(240), measure(text, 10) + px(66)))

    def redraw(self, skip_anim=False):
        self.delete("all")
        self._hits = []
        w = self.winfo_width() or 1000
        cy = self.H / 2
        self.create_rectangle(0, 0, w, self.H, fill=UI["bg"], outline="")

        x = px(10)
        for key, label in self.tabs:
            active = key == self.active
            st = self.state(("tab", key))
            hover = st != "idle" or self.state(("close", key)) != "idle"
            tw = self._tab_w(label)
            text = label if len(label) <= 22 else label[:21] + "…"
            y0, y1 = px(6), self.H - px(6)
            if active:
                gfx.round_rect(self, x, y0, x + tw, y1, px(8), fill=UI["panel"],
                               outline=UI["border_soft"])
            elif hover:
                gfx.round_rect(self, x, y0, x + tw, y1, px(8),
                               fill=mix(UI["bg"], UI["panel"], 0.6), outline="")
            gfx.icon_terminal(self, x + px(12), cy - px(6), px(12),
                              UI["text_dim"] if active else UI["muted"])
            self.create_text(x + px(30), cy, text=text, anchor="w",
                             fill=UI["text"] if active else UI["muted"],
                             font=f(10))
            self.add_hit(x, 0, x + tw - px(24), self.H, ("tab", key))
            if active or hover:
                ck = ("close", key)
                cst = self.state(ck)
                cx = x + tw - px(15)
                if cst != "idle":
                    gfx.round_rect(self, cx - px(9), cy - px(9), cx + px(9),
                                   cy + px(9), px(5), fill=UI["raised"], outline="")
                gfx.icon_close(self, cx, cy, px(3.5),
                               UI["text"] if cst != "idle" else UI["muted"])
                self.add_hit(cx - px(10), 0, cx + px(10), self.H, ck)
            x += tw + px(6)

        self._ibtn(x, cy, ("new", None), gfx.icon_plus, px(4.5), w=px(26))

    def activate(self, key, event):
        kind = key[0]
        if kind == "tab":
            self.app.select_key(key[1])
        elif kind == "close":
            self.app.close_key(key[1])
        elif kind == "new":
            self.app.new_tab(1)

    def _double(self, e):
        key = self.hit(e.x, e.y)
        if key and key[0] == "tab":
            self.app.rename_key(key[1])


# -------------------------------------------------------------- pane header
class _CardEdge(_HitCanvas):
    """Shared by the pane header and footer: the canvas background is the
    card's border colour and the card surface is painted on top with two
    rounded corners, so the whole pane reads as one rounded card."""

    RADIUS = 10

    def __init__(self, master, pane, height):
        super().__init__(master, height=height, bg=master["bg"])
        self.pane = pane

    def card_color(self):
        return self.pane.view.bg

    def _paint_surface(self, w, h, top):
        r = px(self.RADIUS)
        if top:
            gfx.round_rect(self, 0, 0, w, h + r, r, fill=self.card_color(),
                           outline="")
        else:
            gfx.round_rect(self, 0, -r, w, h, r, fill=self.card_color(),
                           outline="")


class PaneHeader(_CardEdge):
    H = 36

    def __init__(self, master, pane):
        super().__init__(master, pane, self.H)
        self.active = False
        self.title = pane.session.label
        self.sub = ""
        self.alive = True
        self.bind("<Button-1>", self._focus_first, add="+")

    def _focus_first(self, e):
        key = self.hit(e.x, e.y)
        if key is None or key[0] == "reveal":
            self.pane.focus_pane()

    def update_state(self, title, alive, active, sub=""):
        if (title, alive, active, sub) == (self.title, self.alive, self.active,
                                           self.sub):
            return
        self.title, self.alive, self.active, self.sub = title, alive, active, sub
        self.redraw()

    def redraw(self):
        self.delete("all")
        self._hits = []
        w = self.winfo_width() or 300
        cy = self.H / 2
        self._paint_surface(w, self.H, top=True)
        self.add_hit(0, 0, w, self.H, ("reveal", None))

        # actions, right to left: close, split, maximise, menu
        bx = w - px(8)
        for key, draw, size in (("close", gfx.icon_close, px(3.8)),
                                ("split", gfx.icon_plus, px(4.5)),
                                ("max", gfx.icon_expand, px(4.5)),
                                ("menu", gfx.icon_dots, px(4.5))):
            bx = self._ibtn_r(bx, cy, (key, None), draw, size, w=px(24)) - px(2)
        actions_x = bx - px(4)

        # status dot, shell glyph, title
        r = px(3)
        dot = UI["ok"] if self.alive else UI["err"]
        self.create_oval(px(14) - r, cy - r, px(14) + r, cy + r, fill=dot,
                         outline="")
        gfx.icon_terminal(self, px(25), cy - px(6), px(12),
                          UI["text_dim"] if self.active else UI["muted"])
        tx = px(44)
        avail = actions_x - tx
        title = fit(self.title, 10, avail, self.active)
        self.create_text(tx, cy, text=title, anchor="w",
                         fill=UI["text"] if self.active else UI["text_dim"],
                         font=f(10, self.active))
        sub = self.sub if self.alive else "exited"
        if sub and sub != self.title:
            sx = tx + measure(title, 10, self.active) + px(8)
            sub = fit("·  " + sub, 9, actions_x - sx)
            if sub:
                self.create_text(sx, cy, text=sub, anchor="w",
                                 fill=UI["warn"] if not self.alive else UI["muted"],
                                 font=f(9))

    def activate(self, key, event):
        kind = key[0]
        if kind == "reveal":
            self.pane.focus_pane()
        elif kind == "close":
            self.pane.close()
        elif kind == "max":
            self.pane.toggle_max()
        elif kind == "split":
            self.pane.split()
        elif kind == "menu":
            self.pane.menu(event.x_root, event.y_root)


class PaneFooter(_CardEdge):
    """One line under the terminal: shell and folder on the left, and on the
    right the folder's startup command as a runnable action, or the grid
    size when there is none. An exited shell offers Restart instead."""

    H = 28

    def __init__(self, master, pane):
        super().__init__(master, pane, self.H)
        self._sig = None

    def refresh(self):
        s = self.pane.session
        sig = (s.label, s.cwd, s.cols, s.rows, s.is_alive(), s.exit_code,
               self.pane.startup_command(), self.pane.active,
               self._hover, self._pressed, self.winfo_width())
        if sig != self._sig:
            self._sig = sig
            self.redraw()

    def redraw(self):
        self.delete("all")
        self._hits = []
        w = self.winfo_width() or 300
        cy = self.H / 2 - px(1)
        self._paint_surface(w, self.H, top=False)
        s = self.pane.session
        alive = s.is_alive()
        cmd = self.pane.startup_command()

        if alive and cmd:
            action, key = "Run " + fit(cmd, 9, px(110), True), ("run", None)
        elif not alive:
            action, key = "Restart", ("restart", None)
        else:
            action, key = "%d×%d" % (s.cols, s.rows), None
        aw = measure(action, 9, key is not None)
        ax1 = w - px(14)
        if key:
            st = self.state(key)
            col = mix(UI["warm"], "#FFFFFF", 0.25) if st != "idle" else UI["warm"]
            self.create_text(ax1, cy, text=action, anchor="e", fill=col,
                             font=f(9, True))
            self.add_hit(ax1 - aw - px(8), 0, w, self.H, key)
        else:
            self.create_text(ax1, cy, text=action, anchor="e", fill=UI["muted"],
                             font=f(9))

        avail = ax1 - aw - px(14) - px(24)
        if alive:
            path = short_path(s.cwd)
            left = "%s  ·  %s" % (s.label, path)
            if measure(left, 9) > avail:
                left = path
            col = UI["muted"]
        else:
            code = s.exit_code
            left = "exited" if code in (None, 0) else "exited  ·  code %s" % code
            col = UI["warn"]
        self.create_text(px(14), cy, anchor="w", fill=col, font=f(9),
                         text=fit(left, 9, avail))

    def activate(self, key, _event):
        if key[0] == "run":
            self.pane.run_startup()
        elif key[0] == "restart":
            self.pane.restart()


# ------------------------------------------------------------- command bar
class CommandBar(_HitCanvas):
    """One field. Type a line, pick who gets it, press Enter or Run."""

    H = 58

    def __init__(self, master, app):
        super().__init__(master, height=self.H, bg=UI["chrome"])
        self.app = app
        self.entry = tk.Entry(self, bg=UI["panel"], fg=UI["text"],
                              insertbackground=UI["text"], relief="flat", bd=0,
                              highlightthickness=0,
                              font=(theme.mono_family(), 10))
        self.entry_win = self.create_window(0, 0, window=self.entry, anchor="w",
                                            width=10, height=22)
        self.focused = False
        self._ph_on = False
        self.entry.bind("<FocusIn>", self._focus)
        self.entry.bind("<FocusOut>", self._blur)
        self.entry.bind("<KeyRelease>", lambda _e: self.redraw())
        self._show_placeholder()

    # ------------------------------------------------------------ the text
    @property
    def PLACEHOLDER(self):
        target = self.app.target_var.get()
        return {"Focused pane": "Run a command in the focused pane",
                "All panes in tab": "Run a command in every pane of this tab",
                }.get(target, "Run a command in every pane, every tab")

    def _show_placeholder(self):
        if self._ph_on or self.entry.get():
            return
        self._ph_on = True
        self.entry.insert(0, self.PLACEHOLDER)
        self.entry.config(fg=UI["muted"])

    def _hide_placeholder(self):
        if not self._ph_on:
            return
        self._ph_on = False
        self.entry.delete(0, "end")
        self.entry.config(fg=UI["text"])

    @property
    def text(self):
        return "" if self._ph_on else self.entry.get()

    def set_text(self, value):
        self._ph_on = False
        self.entry.config(fg=UI["text"])
        self.entry.delete(0, "end")
        if value:
            self.entry.insert(0, value)
        else:
            self._show_placeholder()
        self.redraw()

    def _focus(self, _e=None):
        self.focused = True
        self._hide_placeholder()
        self.redraw()

    def _blur(self, _e=None):
        self.focused = False
        self._show_placeholder()
        self.redraw()

    def redraw(self):
        self.delete("field")
        self._hits = []
        w = self.winfo_width() or 900
        cy = self.H / 2
        self.create_rectangle(0, 0, w, self.H, fill=UI["chrome"], outline="",
                              tags="field")
        self.create_line(0, 0, w, 0, fill=UI["border_soft"], tags="field")
        if self._ph_on and self.entry.get() != self.PLACEHOLDER:
            self.entry.delete(0, "end")
            self.entry.insert(0, self.PLACEHOLDER)

        fx0, fx1 = px(12), w - px(12)
        y0, y1 = cy - px(18), cy + px(18)
        gfx.round_rect(self, fx0, y0, fx1, y1, px(10), fill=UI["panel"],
                       outline=UI["border_hi"] if self.focused else UI["border"],
                       tags="field")

        # prompt glyph
        gx = fx0 + px(16)
        col = UI["text_dim"] if self.focused else UI["muted"]
        self.create_line(gx - px(4), cy, gx + px(4), cy, fill=col, width=1.4,
                         capstyle="round", tags="field")
        self.create_line(gx + px(1), cy - px(3), gx + px(4), cy, gx + px(1),
                         cy + px(3), fill=col, width=1.4, capstyle="round",
                         joinstyle="round", tags="field")

        # run action (right), then target picker to its left
        run = "Run"
        rw = measure(run, 10, True)
        rx1 = fx1 - px(16)
        st = self.state(("send", None))
        self.create_text(rx1, cy, text=run, anchor="e",
                         fill=mix(UI["warm"], "#FFFFFF", 0.25) if st != "idle"
                         else UI["warm"], font=f(10, True), tags="field")
        self.add_hit(rx1 - rw - px(10), y0, fx1, y1, ("send", None))

        target = self.app.target_var.get()
        tw = measure(target, 9) + px(22)
        tx1 = rx1 - rw - px(18)
        tx0 = tx1 - tw
        tst = self.state(("target", None))
        if tst != "idle":
            gfx.round_rect(self, tx0, cy - px(11), tx1, cy + px(11), px(6),
                           fill=UI["raised"], outline="", tags="field")
        self.create_text(tx0 + px(8), cy, text=target, anchor="w",
                         fill=UI["text_dim"] if tst != "idle" else UI["muted"],
                         font=f(9), tags="field")
        gfx.icon_chevron(self, tx1 - px(9), cy, px(3), UI["muted"], down=True,
                         tags="field")
        self.add_hit(tx0, y0, tx1, y1, ("target", None))
        self.create_line(tx0 - px(10), cy - px(9), tx0 - px(10), cy + px(9),
                         fill=UI["border"], tags="field")

        ex0 = fx0 + px(34)
        self.coords(self.entry_win, ex0, cy)
        self.itemconfigure(self.entry_win, width=max(20, tx0 - px(20) - ex0))

    def activate(self, key, event):
        if key[0] == "send":
            self.app.send_command()
        elif key[0] == "target":
            self.app.post_target_menu(event.x_root, event.y_root)


# --------------------------------------------------------------- status bar
class StatusBar(_HitCanvas):
    """Quiet line of facts. A coloured dot in front of each one."""

    H = 28

    def __init__(self, master, app):
        super().__init__(master, height=self.H, bg=UI["bg"])
        self.app = app
        self.text = ""
        self.tone = "ok"
        self.right = ""
        self.chips = []          # [(label, colour), ...]

    def set(self, text, tone="ok", right=""):
        """Kept for callers that just want a line of text."""
        self.set_chips([(text, {"ok": UI["ok"], "warn": UI["warn"],
                                "err": UI["err"],
                                "info": UI["accent"]}.get(tone, UI["ok"]))],
                       right, tone)

    def set_chips(self, chips, right="", tone="ok"):
        text = "   ".join(label for label, _c in chips)
        if (text, right, tone) == (self.text, self.right, self.tone):
            return
        self.chips, self.text, self.right, self.tone = chips, text, right, tone
        self.redraw()

    def redraw(self):
        self.delete("all")
        w = self.winfo_width() or 800
        cy = self.H / 2
        self.create_rectangle(0, 0, w, self.H, fill=UI["bg"], outline="")
        right_w = measure(self.right, 9) + px(20) if self.right else 0
        x = px(16)
        for label, colour in self.chips:
            avail = w - right_w - x - px(10)
            if avail < px(30):
                break
            label = fit(label, 9, avail - px(14))
            r = px(2.5)
            self.create_oval(x - r, cy - r, x + r, cy + r, fill=colour, outline="")
            self.create_text(x + px(10), cy, text=label, anchor="w",
                             fill=UI["text_dim"], font=f(9))
            x += measure(label, 9) + px(30)
        if self.right:
            self.create_text(w - px(14), cy, text=self.right, anchor="e",
                             fill=UI["muted"], font=f(9))
