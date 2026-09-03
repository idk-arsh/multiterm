"""Canvas-drawn application chrome: sidebar, header, tab strip, command bar,
status bar and pane headers. Every surface is painted by hand so the whole
window shares one visual language."""
import os
import tkinter as tk
import tkinter.font as tkfont

from . import gfx, theme, ui
from .theme import UI, mix
from .ui import px

UIF = theme.ui_family()


def f(size, bold=False):
    """Font tuple at the current display scale (size stays in design pt)."""
    return gfx.font(size, bold, UIF)


def apply_scale():
    """Re-derive every structural size for the current display scale."""
    Sidebar.WIDTH = px(252)
    Sidebar.ROW_WS = px(36)
    Sidebar.ROW_FOLDER = px(31)
    HeaderBar.H = px(60)
    TabStrip.H = px(44)
    PaneHeader.H = px(32)
    CommandBar.H = px(62)
    StatusBar.H = px(30)


measure = gfx.measure


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


# --------------------------------------------------------------------- side
class Sidebar(_HitCanvas):
    """Workspaces and the folders inside them."""

    WIDTH = 252
    ROW_WS = 36
    ROW_FOLDER = 31

    def __init__(self, master, store, callbacks):
        super().__init__(master, width=self.WIDTH, bg=UI["sidebar_top"])
        self.store = store
        self.cb = callbacks
        self.offset = 0
        self.active_ws = None
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-3>", self._context)
        self.bind("<Double-Button-1>", self._double)

    # ------------------------------------------------------------ geometry
    def rows(self):
        out = [("title", None, None)]
        for ws in self.store.items:
            out.append(("ws", ws, None))
            if ws.expanded:
                entries = ws.entries()
                for p in entries[:24]:
                    out.append(("folder", ws, p))
                if not entries:
                    out.append(("empty", ws, None))
        out.append(("add", None, None))
        return out

    def _row_h(self, kind):
        return {"title": 42, "ws": self.ROW_WS, "folder": self.ROW_FOLDER,
                "empty": 26, "add": 48}[kind]

    # ------------------------------------------------------------- drawing
    def redraw(self):
        self.delete("all")
        self._hits = []
        w = self.winfo_width() or self.WIDTH
        h = self.winfo_height() or 600
        gfx.vgrad(self, 0, 0, w, h, UI["sidebar_top"], UI["sidebar_bot"], 30)
        # depth: the content sits "above" the sidebar
        for i in range(6):
            self.create_rectangle(w - 6 + i, 0, w - 5 + i, h, outline="",
                                  fill=mix(UI["sidebar_bot"], "#000000",
                                           0.22 * (i + 1) / 6))
        self.create_line(w - 1, 0, w - 1, h, fill=UI["border"])

        y = -self.offset
        for kind, ws, path in self.rows():
            rh = self._row_h(kind)
            if y + rh > 0 and y < h:
                getattr(self, "_draw_" + kind)(w, y, rh, ws, path)
            y += rh
        self._content_h = y + self.offset

        # top fade so scrolled rows slide under the title
        gfx.vgrad(self, 0, 0, w, 38, UI["sidebar_top"], UI["sidebar_top"], 2)
        self._draw_title(w, 0, 38, None, None)

    def _draw_title(self, w, y, h, _ws, _p):
        self.create_text(px(16), y + h / 2, text="WORKSPACES", anchor="w",
                         fill=UI["muted"], font=f(8, True))
        key = ("add_ws", None)
        st = self.state(key)
        cx, cy = w - px(20), y + h / 2
        if st != "idle":
            self.create_oval(cx - 11, cy - 11, cx + 11, cy + 11,
                             fill=UI["raised"], outline="")
        gfx.icon_plus(self, cx, cy, 5,
                      UI["text"] if st != "idle" else UI["muted"])
        self.add_hit(cx - 12, cy - 12, cx + 12, cy + 12, key)

    def _draw_ws(self, w, y, h, ws, _p):
        key = ("ws", ws)
        st = self.state(key)
        active = ws is self.active_ws
        if active:
            gfx.round_rect(self, 6, y + 1, w - 10, y + h - 1, 10,
                           fill=UI["raised"], outline="")
            gfx.round_rect(self, 6, y + 7, 9, y + h - 7, 2,
                           fill=UI["accent"], outline="")
        elif st != "idle":
            gfx.round_rect(self, 6, y + 1, w - 10, y + h - 1, 10,
                           fill=mix(UI["sidebar_top"], UI["raised"], 0.75),
                           outline="")
        cy = y + h / 2
        gfx.icon_chevron(self, px(22), cy, px(4), UI["muted"], down=ws.expanded)
        gfx.icon_folder(self, px(33), cy - px(7), px(14),
                        UI["accent"] if active else UI["text_dim"],
                        open_=ws.expanded)
        missing = not ws.exists()
        self.create_text(px(55), cy, text=ws.name, anchor="w",
                         fill=UI["err"] if missing else
                         (UI["text"] if (active or st != "idle") else UI["text_dim"]),
                         font=f(10, active))
        self.add_hit(6, y, w - 34, y + h, key)

        okey = ("open_ws", ws)
        ost = self.state(okey)
        if st == "idle" and ost == "idle" and not active:
            try:
                n = len(ws.entries())
            except Exception:                          # noqa: BLE001
                n = 0
            if n:
                self.create_text(w - 22, cy, text=str(n), anchor="e",
                                 fill=UI["muted"], font=f(9))
        if st != "idle" or ost != "idle" or active:
            bx = w - 26
            if ost != "idle":
                self.create_oval(bx - 11, cy - 11, bx + 11, cy + 11,
                                 fill=UI["accent_dim"], outline="")
            col = UI["text"] if ost != "idle" else UI["muted"]
            self.create_polygon(bx - 4, cy - 5, bx + 5, cy, bx - 4, cy + 5,
                                fill=col, outline="")
            self.add_hit(bx - 12, cy - 12, bx + 12, cy + 12, okey)

    def _draw_folder(self, w, y, h, ws, path):
        key = ("folder", ws, path)
        st = self.state(key)
        if st != "idle":
            gfx.round_rect(self, 14, y + 1, w - 10, y + h - 1, 7,
                           fill=mix(UI["sidebar_top"], UI["raised"], 0.85),
                           outline="")
        cy = y + h / 2
        gfx.icon_folder(self, px(40), cy - px(6), px(12),
                        UI["text_dim"] if st != "idle" else UI["muted"])
        name = os.path.basename(path.rstrip("\\/")) or path
        if len(name) > 18:
            name = name[:17] + "…"
        self.create_text(px(58), cy, text=name, anchor="w",
                         fill=UI["text"] if st != "idle" else UI["text_dim"],
                         font=f(10))
        runs = ws.command_for(path) if hasattr(ws, "command_for") else ""
        if st != "idle":
            gfx.icon_plus(self, w - px(24), cy, px(5), UI["accent"])
        elif runs:
            # this folder starts something on its own, so show what
            label = runs if len(runs) <= 16 else runs[:15] + "…"
            tw = measure(label, 8) + px(14)
            gfx.round_rect(self, w - px(16) - tw, cy - px(9),
                           w - px(16), cy + px(9), px(6),
                           fill=mix(UI["sidebar_top"], UI["accent"], 0.18),
                           outline="")
            self.create_text(w - px(16) - tw / 2, cy, text=label,
                             fill=UI["accent"], font=f(8))
        self.add_hit(14, y, w - 10, y + h, key)

    def _draw_empty(self, w, y, h, _ws, _p):
        self.create_text(px(58), y + h / 2, text="no sub-folders", anchor="w",
                         fill=UI["muted"], font=f(9))

    def _draw_add(self, w, y, h, _ws, _p):
        key = ("add_ws", None)
        st = self.state(key)
        gfx.round_rect(self, 12, y + 6, w - 16, y + h - 8, 9,
                       fill=UI["raised"] if st != "idle" else "",
                       outline=UI["border"], width=1)
        cy = y + (h - 2) / 2
        gfx.icon_plus(self, px(32), cy, px(5), UI["accent"])
        self.create_text(px(46), cy, text="Add workspace", anchor="w",
                         fill=UI["text"] if st != "idle" else UI["text_dim"],
                         font=f(10))
        self.add_hit(12, y + 4, w - 16, y + h - 6, key)

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
        content = getattr(self, "_content_h", h)
        if content <= h:
            return "break"
        self.offset = max(0, min(content - h + 12,
                                 self.offset - (60 if e.delta > 0 else -60)))
        self.redraw()
        return "break"


# ------------------------------------------------------------------- header
class HeaderBar(_HitCanvas):
    H = 60

    def __init__(self, master, app):
        super().__init__(master, height=self.H, bg=UI["chrome"])
        self.app = app
        self.subtitle = ""

    def redraw(self):
        self.delete("all")
        self._hits = []
        w = self.winfo_width() or 1200
        gfx.vgrad(self, 0, 0, w, self.H, UI["chrome"], UI["chrome_lo"], 16)

        self.create_line(0, self.H - 1, w, self.H - 1, fill=UI["border_soft"])
        x = px(18)
        gfx.logo(self, x, self.H / 2 - px(12), px(24))
        x += px(34)
        # the wordmark and workspace name only appear when there is room
        show_word = w >= px(1010)
        show_sub = w >= px(1180) and bool(self.subtitle)
        if show_word:
            name_w = measure("MultiTerm", 12, True)
            if show_sub:
                sub = self.subtitle
                self.create_text(x, self.H / 2 - px(6), text="MultiTerm",
                                 anchor="w", fill=UI["text"], font=f(12, True))
                self.create_text(x, self.H / 2 + px(8), text=sub, anchor="w",
                                 fill=UI["muted"], font=f(9))
                x += max(name_w, measure(sub, 9)) + px(22)
            else:
                self.create_text(x, self.H / 2, text="MultiTerm", anchor="w",
                                 fill=UI["text"], font=f(12, True))
                x += name_w + px(22)

        x = self._divider(x)
        x = self._pill(x, ("new_pane", None), "Pane", primary=True,
                       plus=True) + px(8)
        x = self._pill(x, ("new_tab", None), "Tab", plus=True) + 10
        x = self._divider(x)

        # layout segmented control
        seg_w = 4 * px(30) + px(8)
        gfx.round_rect(self, x, self.H / 2 - 15, x + seg_w, self.H / 2 + 15, 9,
                       fill=UI["sunken"], outline=UI["border_soft"])
        cur = self.app.layout_var.get()
        for i, (name, _g, _t) in enumerate(self.app.LAYOUTS):
            bx = x + px(4) + i * px(30)
            key = ("layout", name)
            on = name == cur
            st = self.state(key)
            if on:
                gfx.round_rect(self, bx, self.H / 2 - 11, bx + 30, self.H / 2 + 11,
                               7, fill=UI["accent_dim"], outline="")
            elif st != "idle":
                gfx.round_rect(self, bx, self.H / 2 - 11, bx + 30, self.H / 2 + 11,
                               7, fill=UI["raised"], outline="")
            gfx.icon_layout(self, bx + px(8), self.H / 2 - px(7), px(14),
                            UI["text"] if on or st != "idle" else UI["muted"], name)
            self.add_hit(bx, self.H / 2 - 13, bx + 30, self.H / 2 + 13, key)
        x += seg_w + 10

        # broadcast toggle
        on = self.app.broadcast.get()
        key = ("broadcast", None)
        st = self.state(key)
        wide = w >= px(900)
        bw = (measure("Broadcast", 10, True) + px(52)) if wide else px(40)
        y0, y1 = self.H / 2 - px(15), self.H / 2 + px(15)
        if on:
            gfx.round_vgrad(self, x, y0, x + bw, y1, 12,
                            mix(UI["accent"], "#FFFFFF", 0.10), UI["accent2"])
        else:
            gfx.round_rect(self, x, y0, x + bw, y1, 12,
                           fill=UI["raised"] if st != "idle" else "",
                           outline=UI["border"])
        col = "#FFFFFF" if on else (UI["text"] if st != "idle" else UI["text_dim"])
        gfx.icon_broadcast(self, x + (px(20) if wide else bw / 2),
                           self.H / 2, px(8), col)
        if wide:
            self.create_text(x + px(36), self.H / 2, text="Broadcast", anchor="w",
                             fill=col, font=f(10, on))
        self.add_hit(x, y0, x + bw, y1, key)

        # shell picker (right)
        label = self.app.shell_var.get()
        key = ("shell", None)
        st = self.state(key)
        pw = measure(label, 10) + px(44)
        sx = w - pw - px(14)
        gfx.round_rect(self, sx, y0, sx + pw, y1, px(12),
                       fill=UI["raised"] if st != "idle" else UI["panel"],
                       outline=UI["border"])
        self.create_text(sx + px(12), self.H / 2, text=label, anchor="w",
                         fill=UI["text_dim"] if st == "idle" else UI["text"],
                         font=f(10))
        gfx.icon_chevron(self, sx + pw - px(13), self.H / 2, px(4), UI["muted"],
                         down=True)
        self.add_hit(sx, y0, sx + pw, y1, key)
        self._icon_btn(sx - px(42), ("menu", None), gfx.icon_menu, px(7))
        if w >= px(1320):
            self.create_text(sx - px(52), self.H / 2, text="new panes use",
                             anchor="e", fill=UI["muted"], font=f(9))

    def _divider(self, x):
        self.create_line(x + 6, 14, x + 6, self.H - 14, fill=UI["border"])
        return x + 14

    def _icon_btn(self, x, key, draw, size):
        st = self.state(key)
        cy = self.H / 2
        if st != "idle":
            gfx.round_rect(self, x, cy - 15, x + 32, cy + 15, 9,
                           fill=UI["raised"], outline="")
        draw(self, x + 16, cy, size,
             UI["text"] if st != "idle" else UI["text_dim"])
        self.add_hit(x, cy - 15, x + 32, cy + 15, key)
        return x + 32

    def _pill(self, x, key, label, primary=False, plus=False):
        st = self.state(key)
        w = measure(label, 10, primary) + px(28) + (px(14) if plus else 0)
        y0, y1 = self.H / 2 - px(15), self.H / 2 + px(15)
        if primary:
            lift = 0.14 if st == "hover" else 0.0
            dark = 0.18 if st == "press" else 0.0
            top = mix(mix(UI["accent"], "#FFFFFF", 0.16 + lift), "#000000", dark)
            bot = mix(mix(UI["accent2"], "#FFFFFF", lift), "#000000", dark)
            gfx.round_rect(self, x, y0 + 2, x + w, y1 + 2, 10,
                           fill=mix(UI["chrome"], UI["accent"], 0.22), outline="")
            gfx.round_vgrad(self, x, y0, x + w, y1, 12, top, bot)
            fg = "#FFFFFF"
        else:
            gfx.round_rect(self, x, y0, x + w, y1, 12,
                           fill=UI["raised"] if st != "idle" else "",
                           outline=UI["border"])
            fg = UI["text"] if st != "idle" else UI["text_dim"]
        tx = x + 14
        if plus:
            gfx.icon_plus(self, tx, self.H / 2, 5, fg)
            tx += 12
        self.create_text(tx, self.H / 2, text=label, anchor="w", fill=fg,
                         font=f(10, primary))
        self.add_hit(x, y0, x + w, y1, key)
        return x + w

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


# ---------------------------------------------------------------- tab strip
class TabStrip(_HitCanvas):
    H = 44

    def __init__(self, master, app):
        super().__init__(master, height=self.H, bg=UI["bg"])
        self.app = app
        self.tabs = []
        self.active = None
        self._underline = None          # animated x span
        self.bind("<Double-Button-1>", self._double)

    def set_tabs(self, tabs, active, animate=True):
        moved = active != self.active
        self.tabs, self.active = list(tabs), active
        self.redraw()
        if moved and animate:
            self.app.anim.add("tab-underline", 180, self._tween_underline)

    def _tab_span(self, key):
        x = 10
        for k, label in self.tabs:
            w = self._tab_w(label)
            if k == key:
                return x + 14, x + w - 14
            x += w + 5
        return None

    def _tab_w(self, label):
        text = label if len(label) <= 20 else label[:19] + "…"
        return max(px(118), min(px(250), measure(text, 10, True) + px(78)))

    def _tween_underline(self, t):
        target = self._tab_span(self.active)
        if not target:
            return
        if self._underline is None:
            self._underline = target
        a, b = self._underline
        self._underline = (a + (target[0] - a) * t, b + (target[1] - b) * t)
        self.redraw(skip_anim=True)
        if t >= 1.0:
            self._underline = target

    def redraw(self, skip_anim=False):
        self.delete("all")
        self._hits = []
        w = self.winfo_width() or 1000
        self.create_rectangle(0, 0, w, self.H, fill=UI["bg"], outline="")

        x = px(10)
        for key, label in self.tabs:
            active = key == self.active
            st = self.state(("tab", key))
            hover = st != "idle" or self.state(("close", key)) != "idle"
            tw = self._tab_w(label)
            text = label if len(label) <= 20 else label[:19] + "…"
            y0, y1 = px(5), self.H - px(3)
            if active:
                gfx.round_rect(self, x, y0, x + tw, y1 + 6, 12,
                               fill=UI["panel"], outline="")
                gfx.round_rect(self, x, y0, x + tw, y0 + 18, 10,
                               fill=mix(UI["panel"], UI["raised"], 0.5),
                               outline="")
                self.create_rectangle(x, y0 + 10, x + tw, y1 + 6,
                                      fill=UI["panel"], outline="")
            elif hover:
                gfx.round_rect(self, x, y0 + 2, x + tw, y1, 9,
                               fill=mix(UI["bg"], UI["panel"], 0.7), outline="")
            gfx.icon_terminal(self, x + px(13), self.H / 2 - px(7), px(13),
                              UI["accent"] if active else UI["muted"])
            self.create_text(x + px(34), self.H / 2, text=text, anchor="w",
                             fill=UI["text"] if active else UI["text_dim"],
                             font=f(10, active))
            self.add_hit(x, 0, x + tw - 22, self.H, ("tab", key))
            if active or hover:
                ck = ("close", key)
                cst = self.state(ck)
                cx, cy = x + tw - 16, self.H / 2
                if cst != "idle":
                    self.create_oval(cx - 9, cy - 9, cx + 9, cy + 9,
                                     fill=UI["raised"], outline="")
                gfx.icon_close(self, cx, cy, 4,
                               UI["text"] if cst != "idle" else UI["muted"])
                self.add_hit(cx - 10, cy - 10, cx + 10, cy + 10, ck)
            x += tw + px(5)

        nk = ("new", None)
        st = self.state(nk)
        if st != "idle":
            gfx.round_rect(self, x, 8, x + 30, self.H - 6, 8, fill=UI["panel"],
                           outline="")
        gfx.icon_plus(self, x + 15, self.H / 2, 5,
                      UI["text"] if st != "idle" else UI["muted"])
        self.add_hit(x, 4, x + 30, self.H - 2, nk)

        span = self._underline if (self._underline and not skip_anim is None) \
            else self._tab_span(self.active)
        span = self._underline or self._tab_span(self.active)
        if span:
            gfx.hgrad(self, span[0], self.H - 3, span[1], self.H - 1,
                      UI["accent"], UI["accent2"], 24)

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
class PaneHeader(_HitCanvas):
    H = 32

    def __init__(self, master, pane):
        super().__init__(master, height=self.H, bg=UI["panel"])
        self.pane = pane
        self.active = False
        self.title = pane.session.label
        self.alive = True
        self.bind("<Button-1>", self._focus_first, add="+")

    def _focus_first(self, e):
        if not self.hit(e.x, e.y):
            self.pane.focus_pane()

    def update_state(self, title, alive, active):
        if (title, alive, active) == (self.title, self.alive, self.active):
            return
        self.title, self.alive, self.active = title, alive, active
        self.redraw()


    def redraw(self):
        self.delete("all")
        self._hits = []
        w = self.winfo_width() or 300
        top = UI["raised"] if self.active else UI["panel"]
        gfx.vgrad(self, 0, 0, w, self.H, top,
                  mix(top, UI["sunken"], 0.55), 10)
        self.create_line(0, self.H - 1, w, self.H - 1, fill=UI["border_soft"])
        if self.active:
            gfx.hgrad(self, 0, 0, w, 2, UI["accent"], UI["accent2"], 40)

        # the badge carries the shell *and* its state, so no separate dot
        label, color = theme.badge_for(self.pane.session.label)
        if not self.alive:
            color = UI["err"]
        bw, _bh = gfx.chip(self, px(10), (self.H - px(20)) / 2, label, color,
                           mix(color, UI["sunken"], 0.82), font=f(8, True),
                           padx=7, pady=3)
        x = px(10) + bw + px(10)
        text = self.title if self.alive else self.title + "   ·  exited"
        self.create_text(x, self.H / 2, text=text, anchor="w",
                         fill=UI["text"] if self.active else UI["text_dim"],
                         font=f(10, self.active))

        # actions stay out of the way until the pane is focused or hovered
        if not (self.active or self._hover or self._pressed):
            self.create_text(w - px(14), self.H / 2,
                             text="%d" % (self.pane.index + 1),
                             anchor="e", fill=UI["muted"], font=f(9))
            self.add_hit(w - 90, 0, w, self.H, ("reveal", None))
            return
        self.add_hit(w - 100, 0, w, self.H, ("reveal", None))
        bx = w - px(18)
        for key, draw in (("close", gfx.icon_close),
                          ("max", gfx.icon_maximize),
                          ("restart", gfx.icon_restart)):
            st = self.state((key, None))
            if st != "idle":
                self.create_oval(bx - 12, self.H / 2 - 12, bx + 12,
                                 self.H / 2 + 12,
                                 fill=UI["err"] if key == "close"
                                 else UI["border"], outline="")
            col = UI["text"] if st != "idle" else UI["muted"]
            draw(self, bx, self.H / 2, 4 if key == "close" else 5, col)
            self.add_hit(bx - 12, 0, bx + 12, self.H, (key, None))
            bx -= px(27)

    def activate(self, key, _event):
        if key[0] == "reveal":
            self.pane.focus_pane()
            return
        {"close": self.pane.close, "max": self.pane.toggle_max,
         "restart": self.pane.restart}[key[0]]()


# ------------------------------------------------------------- command bar
class CommandBar(_HitCanvas):
    H = 62

    def __init__(self, master, app):
        super().__init__(master, height=self.H, bg=UI["chrome"])
        self.app = app
        self.entry = tk.Entry(self, bg=UI["sunken"], fg=UI["text"],
                              insertbackground=UI["accent"], relief="flat", bd=0,
                              highlightthickness=0,
                              font=(theme.mono_family(), 10))
        self.entry_win = self.create_window(0, 0, window=self.entry, anchor="w",
                                            width=10, height=22)
        self.focused = False
        self.PLACEHOLDER = "type a command, press Enter to run it"
        self._ph_on = False
        self.entry.bind("<FocusIn>", self._focus)
        self.entry.bind("<FocusOut>", self._blur)
        self.entry.bind("<KeyRelease>", lambda _e: self.redraw())
        self._show_placeholder()

    # ------------------------------------------------------------ the text
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
        self.delete("bg")
        gfx.vgrad(self, 0, 0, w, self.H, UI["chrome_lo"], UI["chrome"], 12)
        self.tag_lower("bg")
        self.create_line(0, 0, w, 0, fill=UI["border_soft"], tags="field")

        target = self.app.target_var.get()
        tw = measure(target, 10) + px(36)
        send_w = px(62)
        right = w - px(14)
        y0, y1 = self.H / 2 - px(17), self.H / 2 + px(17)

        # send button
        sx = right - send_w
        st = self.state(("send", None))
        lift = 0.14 if st == "hover" else 0.0
        gfx.round_vgrad(self, sx, y0, right, y1, 12,
                        mix(UI["accent"], "#FFFFFF", 0.16 + lift),
                        mix(UI["accent2"], "#FFFFFF", lift), tags="field")
        self.create_text((sx + right) / 2, self.H / 2, text="Send",
                         fill="#FFFFFF", font=f(10, True), tags="field")
        self.add_hit(sx, y0, right, y1, ("send", None))

        # target chip
        tx = sx - 8 - tw
        tst = self.state(("target", None))
        gfx.round_rect(self, tx, y0, tx + tw, y1, 12,
                       fill=UI["raised"] if tst != "idle" else UI["panel"],
                       outline=UI["border"], tags="field")
        self.create_text(tx + 12, self.H / 2, text=target, anchor="w",
                         fill=UI["text_dim"], font=f(10), tags="field")
        gfx.icon_chevron(self, tx + tw - 13, self.H / 2, 4, UI["muted"],
                         down=True, tags="field")
        self.add_hit(tx, y0, tx + tw, y1, ("target", None))

        # entry field
        fx0, fx1 = px(14), tx - px(10)
        gfx.round_rect(self, fx0, y0, fx1, y1, 13, fill=UI["sunken"],
                       outline=UI["accent"] if self.focused else UI["border"],
                       tags="field")
        gfx.icon_chevron(self, fx0 + px(17), self.H / 2, px(4), UI["accent"],
                         tags="field")
        cap_w = px(46)
        self.coords(self.entry_win, fx0 + 32, self.H / 2)
        self.itemconfigure(self.entry_win,
                           width=max(20, fx1 - fx0 - 48 - cap_w))
        gfx.round_rect(self, fx1 - cap_w - 10, self.H / 2 - 10,
                       fx1 - 10, self.H / 2 + 10, 6,
                       fill=mix(UI["sunken"], "#FFFFFF", 0.07),
                       outline=UI["border"], tags="field")
        self.create_text(fx1 - cap_w / 2 - 10, self.H / 2, text="Enter",
                         fill=UI["muted"], font=f(8), tags="field")

    def activate(self, key, event):
        if key[0] == "send":
            self.app.send_command()
        elif key[0] == "target":
            self.app.post_target_menu(event.x_root, event.y_root)


# --------------------------------------------------------------- status bar
class StatusBar(_HitCanvas):
    H = 30

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
        self.create_rectangle(0, 0, w, self.H, fill=UI["bg"], outline="")
        self.create_line(0, 0, w, 0, fill=UI["border_soft"])
        x = px(14)
        for label, colour in self.chips:
            cw, _ch = gfx.chip(self, x, (self.H - px(20)) / 2, label, colour,
                               mix(colour, UI["bg"], 0.86), font=f(9),
                               padx=9, pady=3, radius=9)
            x += cw + px(7)
        if self.right:
            self.create_text(w - px(14), self.H / 2, text=self.right, anchor="e",
                             fill=UI["muted"], font=f(9))
