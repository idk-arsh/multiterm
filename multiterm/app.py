"""MultiTerm - a multi-pane terminal workspace for Windows."""
import collections
import json
import math
import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from . import chrome, gfx, log as mlog, ui
from . import widget as widget_mod
from . import layout as mlayout
from . import theme
from .chrome import (CommandBar, HeaderBar, PaneFooter, PaneHeader, Sidebar,
                     StatusBar, TabStrip)
from .session import Session, discover_shells
from .theme import UI
from .widget import TerminalView
from .workspace import WorkspaceStore

APP_NAME = "MultiTerm"
FRAME_MS = 16
SLOW_FRAME_MS = 45            # anything past this is a visible stutter
BLINK_MS = 530
HEADER_MS = 220

SETTINGS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                            "MultiTerm")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULTS = {
    "theme": theme.DEFAULT_THEME,
    "font_family": "",
    "font_size": 12,
    "scrollback": 8000,
    "default_shell": "",
    "start_dir": "",
    "startup_panes": 2,
    "sidebar": True,
}


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8-sig") as fh:
            s.update(json.load(fh))
    except Exception:                                  # noqa: BLE001
        pass
    if s.get("theme") not in theme.THEMES:
        s["theme"] = theme.DEFAULT_THEME
    return s


def save_settings(s):
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(s, fh, indent=2)
    except Exception:                                  # noqa: BLE001
        pass


# --------------------------------------------------------------------- pane
class Pane(tk.Frame):
    """A terminal card: 1px border that brightens on focus, a drawn header,
    the terminal view, and a footer with the folder's startup command."""

    def __init__(self, master, app, session):
        super().__init__(master, bg=UI["border"], bd=0, highlightthickness=0)
        self.app = app
        self.session = session
        self.index = 0
        self.active = False
        self._title = ""

        self.view = TerminalView(self, session, app.settings,
                                 on_focus=app.on_pane_focus)
        self.view.router = app.route_input
        self.header = PaneHeader(self, self)
        self.header.pack(fill="x", side="top", padx=1, pady=(1, 0))
        self.footer = PaneFooter(self, self)
        self.footer.pack(fill="x", side="bottom", padx=1, pady=(0, 1))
        self.view.pack(fill="both", expand=True, padx=1)

    def focus_pane(self):
        self.view.focus_terminal()

    def startup_command(self):
        page = self.master
        ws = getattr(page, "workspace", None)
        return ws.command_for(self.session.cwd) if ws else ""

    def run_startup(self):
        cmd = self.startup_command()
        if cmd and self.session.is_alive():
            self.session.write(cmd + "\r")
            self.view.scroll_to_bottom()
            self.focus_pane()

    def split(self):
        self.app.split_pane(self.master._best_direction(self), near=self)

    def menu(self, x, y):
        self.app.post_pane_menu(self, x, y)

    def restart(self):
        self.session.restart()
        self.view.view_offset = self.view.scroll_target = 0
        self.view._need_full = True
        self.view.render()
        self.focus_pane()

    def close(self):
        self.app.close_pane(self)

    def toggle_max(self):
        self.app.toggle_maximize(self)

    def set_active(self, active):
        if active == self.active:
            return
        self.active = active
        start = UI["border"] if active else UI["border_hi"]
        end = UI["border_hi"] if active else UI["border"]
        self.view.set_card_bg(end)
        self.app.anim.add(
            "pane-%d" % id(self), 160,
            lambda t: self._safe_border(theme.mix(start, end, t)))
        self.header.update_state(self._title, self.session.is_alive(), active)
        self.footer.refresh()

    def _safe_border(self, color):
        try:
            self.config(bg=color)
            self.header.config(bg=color)
            self.footer.config(bg=color)
            self.header.redraw()
            self.footer.redraw()
        except tk.TclError:
            pass

    def header_text(self):
        return "%d  %s%s" % (self.index + 1, self._title,
                             "" if self.session.is_alive() else "   ·  exited")

    def refresh_header(self):
        s = self.session
        self._title = s.folder or s.label
        running = s.display_title()
        sub = "" if running in (self._title, s.label) else running
        self.header.update_state(self._title, s.is_alive(), self.active, sub)
        self.footer.refresh()

    def set_theme(self, name):
        self.view.set_theme(name)
        self.header.redraw()
        self.footer.redraw()


# ----------------------------------------------------------------- tab page
class TabPage(tk.Frame):
    """Holds the pane split-tree and lays panes out with draggable dividers."""

    def __init__(self, master, app, name):
        super().__init__(master, bg=UI["bg"])
        self.app = app
        self.name = name
        self.panes = []
        self.tree = None
        self.layout = "Auto"
        self.maximized = None
        self.workspace = None
        self._sashes = []
        self._drag = None
        self._last_size = (0, 0)
        self.bind("<Configure>", self._on_configure)

    # -------------------------------------------------------------- panes
    def add_pane(self, session, near=None, direction=None):
        pane = Pane(self, self.app, session)
        self.panes.append(pane)
        if self.tree is None:
            self.tree = pane
        elif self.layout == "Custom" or direction:
            target = near or self.app.active_pane
            if target not in self.panes or target is pane:
                target = self.panes[-2]
            self.tree = mlayout.split_leaf(
                self.tree, target, pane, direction or self._best_direction(target))
        else:
            self.rebuild_tree()
        self.maximized = None
        self.relayout()
        return pane

    def _best_direction(self, target):
        """Split across the longer axis, like a tiling terminal does."""
        try:
            w, h = target.winfo_width(), target.winfo_height()
        except tk.TclError:
            return "h"
        return "h" if w >= h * 1.15 else "v"

    def remove_pane(self, pane):
        if pane in self.panes:
            self.panes.remove(pane)
        self.tree = mlayout.remove_leaf(self.tree, pane)
        if self.maximized is pane:
            self.maximized = None
        pane.session.close()
        pane.destroy()
        self.relayout()

    def grid_shape(self, n):
        if n <= 1:
            return 1, 1
        if self.layout == "Columns":
            return 1, n
        if self.layout == "Rows":
            return n, 1
        if self.layout == "2 x 2":
            return 2, 2
        if self.layout == "2 x 3":
            return 2, 3
        if self.layout == "3 x 3":
            return 3, 3
        table = {2: (1, 2), 3: (1, 3), 4: (2, 2), 5: (2, 3), 6: (2, 3),
                 7: (2, 4), 8: (2, 4), 9: (3, 3), 10: (3, 4), 11: (3, 4),
                 12: (3, 4)}
        if n in table:
            return table[n]
        cols = math.ceil(math.sqrt(n))
        return math.ceil(n / cols), cols

    def rebuild_tree(self):
        """Re-arrange every pane into the current preset layout."""
        n = len(self.panes)
        if not n:
            self.tree = None
            return
        rows, cols = self.grid_shape(n)
        rows = max(rows, math.ceil(n / cols))
        self.tree = mlayout.build_grid(self.panes, rows, cols)

    # ------------------------------------------------------------- layout
    def _on_configure(self, _e=None):
        size = (self.winfo_width(), self.winfo_height())
        if size != self._last_size:
            self._last_size = size
            self.relayout()

    def relayout(self):
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        pad = ui.px(4)
        rects, sashes = [], []
        if self.maximized in self.panes and self.maximized is not None:
            rects = [(self.maximized, pad, pad, w - 2 * pad, h - 2 * pad)]
            for p in self.panes:
                if p is not self.maximized:
                    p.place_forget()
        elif self.tree is not None:
            mlayout.place(self.tree, pad, pad, w - 2 * pad, h - 2 * pad,
                          rects, sashes)
        for pane, x, y, pw, ph in rects:
            pane.place(x=x, y=y, width=pw, height=ph)
        self._place_sashes(sashes)
        for i, p in enumerate(self.panes):
            p.index = i
            p.refresh_header()
        self.app.refresh_status()
        sidebar = getattr(self.app, "sidebar", None)
        if sidebar is not None:
            sidebar.mark_dirty()

    def _place_sashes(self, sashes):
        while len(self._sashes) < len(sashes):
            f = tk.Frame(self, bg=UI["bg"], bd=0, highlightthickness=0)
            f.bind("<Enter>", lambda e, s=f: self._sash_hover(s, True))
            f.bind("<Leave>", lambda e, s=f: self._sash_hover(s, False))
            f.bind("<Button-1>", lambda e, s=f: self._sash_press(s, e))
            f.bind("<B1-Motion>", lambda e, s=f: self._sash_drag(s, e))
            f.bind("<ButtonRelease-1>", lambda e, s=f: self._sash_hover(s, False))
            f.bind("<Double-Button-1>", lambda e, s=f: self._sash_reset(s))
            self._sashes.append(f)
        for f in self._sashes[len(sashes):]:
            f.place_forget()
        for f, (node, x, y, sw, sh, direction, rect) in zip(self._sashes, sashes):
            f.node, f.rect = node, rect
            f.config(cursor="sb_h_double_arrow" if direction == "h"
                     else "sb_v_double_arrow")
            f.place(x=x, y=y, width=sw, height=sh)
            f.lift()

    def _sash_hover(self, sash, on):
        sash.config(bg=UI["border_hi"] if on else UI["bg"])

    def _sash_press(self, sash, _e):
        self._sash_hover(sash, True)

    def _sash_drag(self, sash, e):
        node = getattr(sash, "node", None)
        if node is None:
            return
        px = sash.winfo_x() + e.x
        py = sash.winfo_y() + e.y
        node.ratio = mlayout.ratio_from_drag(node, sash.rect, px, py)
        self.layout = "Custom"
        self.app.layout_var.set("Custom")
        self.relayout()

    def _sash_reset(self, sash):
        node = getattr(sash, "node", None)
        if node is not None:
            node.ratio = 0.5
            self.relayout()

    def close_all(self):
        for p in list(self.panes):
            p.session.close()
            p.destroy()
        self.panes.clear()
        self.tree = None


# ---------------------------------------------------------------------- app
class App(tk.Tk):
    LAYOUTS = [("Auto", "auto", "Fit panes automatically"),
               ("Columns", "cols", "Side by side"),
               ("Rows", "rows", "Stacked"),
               ("2 x 2", "grid", "Two by two")]
    LAYOUT_NAMES = [n for n, _a, _b in LAYOUTS] + ["2 x 3", "3 x 3"]

    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.log = mlog.get("app")
        self.store = WorkspaceStore()
        self.anim = gfx.Animator()
        self._slow_frames = 0
        self._slow_logged_at = 0.0

        ui.init(self)             # display scale, before anything is built
        chrome.apply_scale()
        widget_mod.apply_scale()
        mlayout.apply_scale()
        self.title(APP_NAME)
        self._apply_initial_geometry()
        self.minsize(ui.px(900), ui.px(560))
        self.configure(bg=UI["bg"])
        self._set_icon()
        self._native_frame()

        self.shells = discover_shells()
        names = [s[0] for s in self.shells]
        if self.settings.get("default_shell") not in names:
            self.settings["default_shell"] = names[0]

        self.active_pane = None
        self.broadcast = tk.BooleanVar(value=False)
        self.shell_var = tk.StringVar(value=self.settings["default_shell"])
        self.layout_var = tk.StringVar(value="Auto")
        self.theme_var = tk.StringVar(value=self.settings["theme"])
        self.target_var = tk.StringVar(value="Focused pane")
        self._pages = []
        self._current = None
        self._hint = None
        self._blink_at = time.monotonic()
        self._blink_on = True
        self._header_at = 0.0
        self.frame_log = collections.deque(maxlen=6000)   # (start, work_ms)

        self._build_layout()
        self._build_menus()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        mlog.install_excepthook(self)
        mlog.banner({
            "shells": ", ".join(s[0] for s in self.shells),
            "theme": self.settings.get("theme"),
            "geometry": self.geometry(),
            "workspaces": len(self.store.items),
        })

        first = self.new_tab(panes=max(1, int(self.settings.get("startup_panes", 2))))
        if first.panes:
            self.after(120, first.panes[0].focus_pane)
        self.after(FRAME_MS, self._tick)

    # -------------------------------------------------------------- window
    def _apply_initial_geometry(self):
        """Open centred, at a sensible size for this display."""
        ax, ay, aw, ah = self.work_area()
        w = h = None
        saved = str(self.settings.get("window") or "")
        if "x" in saved:
            try:
                w, h = (int(v) for v in saved.split("+")[0].split("x"))
            except ValueError:
                w = h = None
        if not w or not h:
            w, h = int(aw * 0.82), int(ah * 0.84)
        w = max(900, min(w, aw))
        h = max(560, min(h, ah))
        self.geometry("%dx%d+%d+%d" % (w, h, ax + (aw - w) // 2,
                                       ay + (ah - h) // 2))

    def _set_icon(self):
        try:
            base = getattr(sys, "_MEIPASS", os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))
            self.iconbitmap(os.path.join(base, "assets", "multiterm.ico"))
        except Exception:                              # noqa: BLE001
            pass

    def _native_frame(self):
        """Standard Windows window - dark caption, snap, Aero, taskbar."""
        self._zoomed = False
        self._restore_geom = None
        self.update_idletasks()
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or                 self.winfo_id()
            self._hwnd = hwnd
            dark = ctypes.c_int(1)
            for attr in (20, 19):          # immersive dark mode, both spellings
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(dark), ctypes.sizeof(dark))
            corner = ctypes.c_int(2)       # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
        except Exception:                                  # noqa: BLE001
            self._hwnd = None

    # ---------------------------------------------------- window controls
    def minimize_window(self):
        self.iconify()

    def work_area(self):
        try:
            import ctypes

            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                            ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
            r = RECT()
            ctypes.windll.user32.SystemParametersInfoW(0x0030, 0,
                                                       ctypes.byref(r), 0)
            return r.left, r.top, r.right - r.left, r.bottom - r.top
        except Exception:                                    # noqa: BLE001
            return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def toggle_zoom(self):
        """Maximise / restore through the window manager."""
        try:
            self.state("normal" if self.state() == "zoomed" else "zoomed")
        except tk.TclError:
            pass
        return "break"

    def _build_layout(self):
        self.header = HeaderBar(self, self)
        self.header.pack(fill="x", side="top")

        self.statusbar = StatusBar(self, self)
        self.statusbar.pack(fill="x", side="bottom")
        self.cmdbar = CommandBar(self, self)
        self.cmdbar.pack(fill="x", side="bottom")
        self.cmd_entry = self.cmdbar.entry
        self.cmd_entry.bind("<Return>", lambda _e: self.send_command())
        self.cmd_entry.bind("<Up>", self._history_up)
        self.cmd_entry.bind("<Down>", self._history_down)
        self.cmd_entry.bind("<Escape>", lambda _e: self._focus_terminal())
        self.history = []
        self.hist_pos = 0

        body = tk.Frame(self, bg=UI["bg"])
        body.pack(fill="both", expand=True)
        self.body = body

        self.sidebar = Sidebar(body, self.store, {
            "select": self.on_workspace_select,
            "open_workspace": self.open_workspace,
            "open_folder": self.open_folder,
            "add_workspace": self.add_workspace,
            "menu": self.post_workspace_menu,
            "folder_menu": self.post_folder_menu,
            "open_paths": self.open_paths,
        })
        if self.settings.get("sidebar", True):
            self.sidebar.pack(side="left", fill="y")

        right = tk.Frame(body, bg=UI["bg"])
        right.pack(side="left", fill="both", expand=True)
        self.tabstrip = TabStrip(right, self)
        self.tabstrip.pack(fill="x", side="top")
        self.content = tk.Frame(right, bg=UI["bg"])
        self.content.pack(fill="both", expand=True, padx=ui.px(8),
                          pady=(0, ui.px(6)))
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

    # --------------------------------------------------------------- menus
    def _menu(self, parent=None):
        return tk.Menu(parent or self, tearoff=0, bg=UI["panel"], fg=UI["text"],
                       activebackground=UI["raised"], activeforeground=UI["text"],
                       bd=0, relief="flat", activeborderwidth=0)

    def _build_menus(self):
        m = self._menu()
        f = self._menu(m)
        f.add_command(label="New tab", accelerator="Ctrl+Shift+T",
                      command=lambda: self.new_tab(1))
        f.add_command(label="New pane", accelerator="Ctrl+Shift+N",
                      command=self.new_pane)
        f.add_command(label="Open folder as workspace…",
                      command=self.add_workspace)
        f.add_separator()
        f.add_command(label="Close pane", accelerator="Ctrl+Shift+W",
                      command=lambda: self.close_pane())
        f.add_command(label="Close tab", command=self.close_tab)
        f.add_separator()
        f.add_command(label="Exit", command=self.on_close)
        m.add_cascade(label="File", menu=f)

        t = self._menu(m)
        t.add_command(label="Restart shell in pane", command=self.restart_pane)
        t.add_command(label="Restart every pane in tab", command=self.restart_all)
        t.add_separator()
        t.add_command(label="Copy", accelerator="Ctrl+Shift+C", command=self.copy)
        t.add_command(label="Paste", accelerator="Ctrl+Shift+V", command=self.paste)
        t.add_command(label="Clear buffer", command=self.clear_pane)
        t.add_command(label="Find in pane", accelerator="Ctrl+F",
                      command=self.find_in_pane)
        t.add_separator()
        t.add_checkbutton(label="Broadcast typing", accelerator="Ctrl+Shift+B",
                          variable=self.broadcast, command=self._broadcast_changed)
        t.add_command(label="Run command in all panes…",
                      command=self.run_in_all_dialog)
        m.add_cascade(label="Terminal", menu=t)

        v = self._menu(m)
        lay = self._menu(v)
        for name in self.LAYOUT_NAMES:
            lay.add_radiobutton(label=name, value=name, variable=self.layout_var,
                                command=self.apply_layout)
        v.add_cascade(label="Layout", menu=lay)
        v.add_command(label="Split pane right", accelerator="Ctrl+Shift+D",
                      command=lambda: self.split_pane("h"))
        v.add_command(label="Split pane down", accelerator="Ctrl+Shift+S",
                      command=lambda: self.split_pane("v"))
        v.add_command(label="Even out panes", command=self.even_panes)
        v.add_command(label="Maximise / restore pane", accelerator="Ctrl+Shift+M",
                      command=lambda: self.toggle_maximize())
        v.add_command(label="Toggle sidebar", accelerator="Ctrl+Shift+E",
                      command=self.toggle_sidebar)
        v.add_separator()
        th = self._menu(v)
        for name in theme.THEMES:
            th.add_radiobutton(label=name, value=name, variable=self.theme_var,
                               command=self.apply_theme)
        v.add_cascade(label="Colour theme", menu=th)
        v.add_command(label="Bigger text", accelerator="Ctrl+Shift++",
                      command=lambda: self.zoom(1))
        v.add_command(label="Smaller text", accelerator="Ctrl+Shift+-",
                      command=lambda: self.zoom(-1))
        v.add_separator()
        v.add_command(label="Full screen", accelerator="F11",
                      command=self.toggle_fullscreen)
        m.add_cascade(label="View", menu=v)

        h = self._menu(m)
        h.add_command(label="Keyboard shortcuts", command=self.show_help)
        h.add_separator()
        h.add_command(label="Open log folder", command=self.open_logs)
        h.add_command(label="Copy diagnostics to clipboard",
                      command=self.copy_diagnostics)
        h.add_separator()
        h.add_command(label="About", command=self.show_about)
        m.add_cascade(label="Help", menu=h)
        self.main_menu = m

        self.shell_menu = self._menu()
        for label, _argv in self.shells:
            self.shell_menu.add_radiobutton(
                label=label, value=label, variable=self.shell_var,
                command=self._remember_shell)

        self.target_menu = self._menu()
        for opt in ("Focused pane", "All panes in tab", "All panes everywhere"):
            self.target_menu.add_radiobutton(
                label=opt, value=opt, variable=self.target_var,
                command=self.cmdbar.redraw)

    def _post(self, menu, x, y):
        try:
            menu.tk_popup(int(x), int(y))
        finally:
            menu.grab_release()

    def post_main_menu(self, x, y):
        self._post(self.main_menu, x, y)

    def post_shell_menu(self, x, y):
        self._post(self.shell_menu, x, y)

    def post_target_menu(self, x, y):
        self._post(self.target_menu, x, y)

    def post_workspace_menu(self, ws, x, y):
        m = self._menu()
        m.add_command(label="Open workspace in new tab",
                      command=lambda: self.open_workspace(ws))
        m.add_command(label="New terminal at root",
                      command=lambda: self.open_folder(ws.root, ws))
        m.add_separator()
        m.add_command(label="Unpin" if ws.pinned else "Pin to top",
                      command=lambda: self.toggle_pin(ws))
        m.add_command(label="Pin a folder…",
                      command=lambda: self.pin_folder(ws))
        m.add_command(label="Rename…", command=lambda: self.rename_workspace(ws))
        m.add_command(label="Remove from sidebar",
                      command=lambda: self.remove_workspace(ws))
        self._post(m, x, y)

    def post_folder_menu(self, ws, path, x, y):
        name = os.path.basename(path.rstrip("\\/")) or path
        current = ws.command_for(path)
        m = self._menu()
        m.add_command(label="Open a terminal in %s" % name,
                      command=lambda: self.open_folder(path, ws))
        m.add_separator()
        m.add_command(label=("Change what runs on open..." if current
                             else "Run a command when this opens..."),
                      command=lambda: self.set_folder_command(ws, path))
        if current:
            m.add_command(label="Clear \"%s\"" % current[:34],
                          command=lambda: self.set_folder_command(ws, path, ""))
        self._post(m, x, y)

    def post_pane_menu(self, pane, x, y):
        s = pane.session
        m = self._menu()
        cmd = pane.startup_command()
        if cmd:
            m.add_command(label="Run \"%s\"" % cmd[:34], command=pane.run_startup)
        m.add_command(label="Restart shell", command=pane.restart)
        m.add_command(label="Clear buffer", command=lambda: self._clear(pane))
        m.add_command(label="Find in pane", accelerator="Ctrl+F",
                      command=lambda: (pane.view.toggle_find(), pane.focus_pane()))
        m.add_separator()
        m.add_command(label="Split right", accelerator="Ctrl+Shift+D",
                      command=lambda: self.split_pane("h", near=pane))
        m.add_command(label="Split down", accelerator="Ctrl+Shift+S",
                      command=lambda: self.split_pane("v", near=pane))
        m.add_command(label="Restore pane" if pane.master.maximized is pane
                      else "Maximise pane", accelerator="Ctrl+Shift+M",
                      command=pane.toggle_max)
        m.add_separator()
        m.add_command(label="Copy folder path",
                      command=lambda: self._copy_text(s.cwd))
        page = pane.master
        if getattr(page, "workspace", None):
            m.add_command(label=("Change what runs on open…" if cmd
                                 else "Run a command when this opens…"),
                          command=lambda: self.set_folder_command(
                              page.workspace, s.cwd))
        m.add_separator()
        m.add_command(label="Close pane", accelerator="Ctrl+Shift+W",
                      command=pane.close)
        self._post(m, x, y)

    def _copy_text(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.hint("Copied " + text)

    def toggle_pin(self, ws):
        self.store.set_pinned(ws, not ws.pinned)
        self.sidebar.redraw()

    def open_paths(self):
        """Folders that currently have a terminal open, for the sidebar dots."""
        out = set()
        for page in self._pages:
            for p in page.panes:
                if p.session.is_alive():
                    out.add(os.path.normcase(os.path.abspath(p.session.cwd)))
        return out

    def set_folder_command(self, ws, path, value=None):
        """The command this folder should run every time the workspace opens."""
        name = os.path.basename(path.rstrip("\\/")) or path
        if value is None:
            value = simpledialog.askstring(
                APP_NAME,
                "Command to run in %s every time this workspace opens:" % name,
                initialvalue=ws.command_for(path), parent=self)
            if value is None:
                return
        ws.set_command(path, value)
        self.store.save()
        self.sidebar.redraw()
        for page in self._pages:
            for p in page.panes:
                p.footer.refresh()
        self.hint("%s will run \"%s\" on open" % (name, value.strip())
                  if value.strip() else "%s will not run anything on open" % name)

    # ---------------------------------------------------------- workspaces
    def on_workspace_select(self, ws):
        self.header.subtitle = ws.name
        self.header.redraw()

    def add_workspace(self):
        path = filedialog.askdirectory(title="Choose a project folder",
                                       parent=self)
        if not path:
            return
        ws = self.store.add(path)
        self.sidebar.active_ws = ws
        self.sidebar.redraw()
        self.open_workspace(ws)

    def pin_folder(self, ws):
        path = filedialog.askdirectory(title="Pin a folder to " + ws.name,
                                       initialdir=ws.root, parent=self)
        if path:
            self.store.pin_folder(ws, path)
            self.sidebar.redraw()

    def rename_workspace(self, ws):
        name = simpledialog.askstring(APP_NAME, "Workspace name:",
                                      initialvalue=ws.name, parent=self)
        if name:
            self.store.rename(ws, name)
            self.sidebar.redraw()
            if self.sidebar.active_ws is ws:
                self.on_workspace_select(ws)

    def remove_workspace(self, ws):
        self.store.remove(ws)
        if self.sidebar.active_ws is ws:
            self.sidebar.active_ws = None
        self.sidebar.redraw()

    def open_workspace(self, ws):
        """One tab for the workspace, one pane per folder inside it."""
        if not ws.exists():
            messagebox.showwarning(APP_NAME, "That folder no longer exists:\n"
                                   + ws.root)
            return
        folders = ws.entries()[:6] or [ws.root]
        page = self.new_tab(panes=0, name=ws.name)
        page.workspace = ws
        page.layout = ws.layout or "Auto"
        started = 0
        for folder in folders:
            pane = self.new_pane(page=page, cwd=folder, focus=False)
            command = ws.command_for(folder)
            if pane and command:
                # let the shell finish printing its banner before we type
                self.after(700, lambda p=pane, c=command: p.session.write(c + "\r"))
                started += 1
        self.layout_var.set(page.layout)
        page.relayout()
        self.sidebar.active_ws = ws
        self.sidebar.redraw()
        self.on_workspace_select(ws)
        if page.panes:
            self.after(80, page.panes[0].focus_pane)
        self.hint("Opened %s: %d terminal%s" % (ws.name, len(folders),
                                                 "" if len(folders) == 1 else "s"))
        return page

    def open_folder(self, path, ws=None):
        page = self.current_page()
        if page is None:
            page = self.new_tab(panes=0, name=ws.name if ws else "Tab")
        pane = self.new_pane(page=page, cwd=path)
        if ws:
            self.on_workspace_select(ws)
        if pane:
            self.hint("New terminal in " + os.path.basename(path.rstrip("\\/")))
        return pane

    def toggle_sidebar(self):
        if self.sidebar.winfo_ismapped():
            self.sidebar.pack_forget()
            self.settings["sidebar"] = False
        else:
            self.sidebar.pack(side="left", fill="y", before=self.body.winfo_children()[0]
                              if self.body.winfo_children() else None)
            self.settings["sidebar"] = True
        return "break"

    # ---------------------------------------------------------------- tabs
    def pages(self):
        return list(self._pages)

    def current_page(self):
        if self._current in self._pages:
            return self._current
        return self._pages[0] if self._pages else None

    def _sync_tabs(self, animate=True):
        self.tabstrip.set_tabs([(id(p), p.name) for p in self._pages],
                               id(self.current_page()) if self._pages else None,
                               animate=animate)

    def select_key(self, key):
        for p in self._pages:
            if id(p) == key:
                self.select_page(p)
                return

    def close_key(self, key):
        for p in self._pages:
            if id(p) == key:
                self.close_tab(p)
                return

    def rename_key(self, key):
        for p in self._pages:
            if id(p) == key:
                name = simpledialog.askstring(APP_NAME, "Tab name:",
                                              initialvalue=p.name, parent=self)
                if name:
                    p.name = name
                    self._sync_tabs(animate=False)
                return

    def select_page(self, page):
        self._current = page
        page.tkraise()
        self._sync_tabs()
        self.layout_var.set(page.layout)
        self.header.redraw()
        for p in page.panes:
            p.view._need_full = True
        if page.panes:
            self.after(20, page.panes[0].focus_pane)
        self.refresh_status()

    def new_tab(self, panes=1, name=None):
        page = TabPage(self.content, self, name or "Tab %d" % (len(self._pages) + 1))
        page.grid(row=0, column=0, sticky="nsew")
        self._pages.append(page)
        self._current = page
        for _ in range(max(0, panes)):
            self.new_pane(page=page, focus=False)
        self.select_page(page)
        if page.panes:
            page.panes[0].focus_pane()
        return page

    def close_tab(self, page=None):
        page = page or self.current_page()
        if page is None:
            return
        if len(self._pages) == 1:
            if not messagebox.askokcancel(APP_NAME, "Close the last tab and exit?"):
                return
            self.on_close()
            return
        idx = self._pages.index(page)
        page.close_all()
        self._pages.remove(page)
        page.destroy()
        self.select_page(self._pages[min(idx, len(self._pages) - 1)])

    # --------------------------------------------------------------- panes
    def _remember_shell(self):
        self.settings["default_shell"] = self.shell_var.get()
        self.header.redraw()

    def _shell_argv(self):
        name = self.shell_var.get()
        for label, argv in self.shells:
            if label == name:
                return label, argv
        return self.shells[0]

    def split_pane(self, direction, near=None):
        """Split the focused pane, keeping every other pane where it is."""
        page = self.current_page()
        if page is None:
            return None
        page.layout = "Custom"
        self.layout_var.set("Custom")
        pane = self.new_pane(page=page, direction=direction, near=near)
        self.header.redraw()
        return pane

    def new_pane(self, page=None, focus=True, cwd=None, direction=None,
                 near=None):
        page = page or self.current_page()
        if page is None:
            return None
        if len(page.panes) >= 12:
            messagebox.showinfo(APP_NAME, "12 panes per tab is the limit. "
                                          "open another tab for more.")
            return None
        label, argv = self._shell_argv()
        start = cwd or self.settings.get("start_dir") or os.path.expanduser("~")
        sess = Session(argv, cwd=start,
                       scrollback=int(self.settings.get("scrollback", 8000)),
                       title=label,
                       folder=os.path.basename(str(start).rstrip("\\/")) or None)
        if not sess.start():
            self.log.error("shell failed to start: %s (%s)", label, sess.error)
        page.maximized = None
        pane = page.add_pane(sess, near=near, direction=direction)
        if focus:
            self.after(60, pane.focus_pane)
        return pane

    def close_pane(self, pane=None):
        page = self.current_page()
        if page is None:
            return
        pane = pane or self.active_pane
        if pane is None or pane not in page.panes:
            return
        page.remove_pane(pane)
        if page.panes:
            page.panes[0].focus_pane()
        elif len(self._pages) > 1:
            self._pages.remove(page)
            page.destroy()
            self.select_page(self._pages[-1])
        else:
            self.new_pane(page=page)

    def restart_pane(self):
        if self.active_pane:
            self.active_pane.restart()

    def restart_all(self):
        page = self.current_page()
        for p in (page.panes if page else []):
            p.restart()

    def find_in_pane(self):
        if self.active_pane:
            self.active_pane.view.toggle_find()
            self.active_pane.focus_pane()

    def clear_pane(self):
        if self.active_pane:
            self._clear(self.active_pane)

    def _clear(self, pane):
        scr = pane.session.screen
        scr.scrollback.clear()
        scr._erase_display(2)
        scr.x = scr.y = 0
        v = pane.view
        v.view_offset = v.scroll_target = 0
        v._need_full = True
        v.render()

    def toggle_maximize(self, pane=None):
        page = self.current_page()
        if page is None:
            return
        pane = pane or self.active_pane
        if pane not in page.panes:
            return
        page.maximized = None if page.maximized is pane else pane
        page.relayout()
        pane.focus_pane()

    def focus_index(self, i):
        page = self.current_page()
        if page and 0 <= i < len(page.panes):
            page.panes[i].focus_pane()
        return "break"

    def cycle_pane(self, step=1):
        page = self.current_page()
        if not page or not page.panes:
            return "break"
        i = page.panes.index(self.active_pane) if self.active_pane in page.panes else -1
        page.panes[(i + step) % len(page.panes)].focus_pane()
        return "break"

    def on_pane_focus(self, view):
        for page in self._pages:
            for p in page.panes:
                active = p.view is view
                p.set_active(active)
                if active:
                    self.active_pane = p
        self.refresh_status()

    def _focus_terminal(self):
        if self.active_pane:
            self.active_pane.focus_pane()
        return "break"

    # ----------------------------------------------------------- broadcast
    def _broadcast_changed(self):
        self.header.redraw()
        self.refresh_status()

    def toggle_broadcast(self):
        self.broadcast.set(not self.broadcast.get())
        self._broadcast_changed()
        return "break"

    def route_input(self, view, data):
        if not self.broadcast.get():
            view.session.write(data)
            return
        page = self.current_page()
        panes = page.panes if page else []
        if not any(p.view is view for p in panes):
            view.session.write(data)
            return
        for p in panes:
            p.session.write(data)

    # ------------------------------------------------------------ commands
    def send_command(self, _e=None):
        text = self.cmdbar.text
        if not text.strip():
            return "break"
        self.history.append(text)
        self.hist_pos = len(self.history)
        target = self.target_var.get()
        payload = text + "\r"
        if target == "Focused pane":
            if self.active_pane:
                self.active_pane.session.write(payload)
                self.active_pane.view.scroll_to_bottom()
        elif target == "All panes in tab":
            page = self.current_page()
            for p in (page.panes if page else []):
                p.session.write(payload)
                p.view.scroll_to_bottom()
        else:
            for page in self._pages:
                for p in page.panes:
                    p.session.write(payload)
                    p.view.scroll_to_bottom()
        self.cmdbar.set_text("")
        return "break"

    _send_command = send_command          # kept for older callers

    def _history_up(self, _e=None):
        if self.history and self.hist_pos > 0:
            self.hist_pos -= 1
            self.cmdbar.set_text(self.history[self.hist_pos])
        return "break"

    def _history_down(self, _e=None):
        if self.hist_pos < len(self.history) - 1:
            self.hist_pos += 1
            self.cmdbar.set_text(self.history[self.hist_pos])
        else:
            self.hist_pos = len(self.history)
            self.cmdbar.set_text("")
        return "break"

    def run_in_all_dialog(self):
        cmd = simpledialog.askstring(APP_NAME, "Command to run in every pane "
                                               "of this tab:", parent=self)
        if not cmd:
            return
        page = self.current_page()
        for p in (page.panes if page else []):
            p.session.write(cmd + "\r")

    # ----------------------------------------------------------------- view
    def set_layout(self, name):
        self.layout_var.set(name)
        self.apply_layout()

    def apply_layout(self):
        page = self.current_page()
        if page:
            page.layout = self.layout_var.get()
            page.maximized = None
            if page.layout != "Custom":
                page.rebuild_tree()
            if page.workspace:
                page.workspace.layout = page.layout
                self.store.save()
            page.relayout()
        self.header.redraw()

    def even_panes(self):
        """Reset every divider back to the middle."""
        page = self.current_page()
        if page is None:
            return

        def walk(node):
            if isinstance(node, mlayout.Split):
                node.ratio = 0.5
                walk(node.a)
                walk(node.b)
        walk(page.tree)
        page.relayout()

    def apply_theme(self):
        name = self.theme_var.get()
        self.settings["theme"] = name
        for page in self._pages:
            for p in page.panes:
                p.set_theme(name)

    def zoom(self, delta):
        size = int(self.settings.get("font_size", 11)) + delta
        for page in self._pages:
            for p in page.panes:
                p.view.set_font_size(size)
        self.settings["font_size"] = max(6, min(40, size))
        self.refresh_status()
        return "break"

    def toggle_fullscreen(self):
        self.attributes("-fullscreen", not self.attributes("-fullscreen"))
        return "break"

    def copy(self):
        if self.active_pane and not self.active_pane.view.copy():
            self.hint("Nothing selected. Drag across the text you want first.")

    def paste(self):
        if self.active_pane:
            self.active_pane.view.paste()

    # --------------------------------------------------------------- status
    def hint(self, text):
        self._hint = text
        self._hint_at = time.monotonic()
        self.refresh_status()

    def refresh_status(self):
        page = self.current_page()
        panes = page.panes if page else []
        alive = sum(1 for p in panes if p.session.is_alive())
        right = self._right_status(panes, alive)
        if self._hint:
            self.statusbar.set_chips([(self._hint, UI["accent"])], right, "info")
            return
        chips = [("%d pane%s · %d running"
                  % (len(panes), "" if len(panes) == 1 else "s", alive),
                  UI["ok"] if panes and alive == len(panes) else UI["warn"])]
        if page and page.workspace:
            chips.append((page.workspace.name, UI["accent2"]))
        if page and page.layout == "Custom":
            chips.append(("custom layout", UI["muted"]))
        if self.broadcast.get():
            chips.append(("Broadcast on · keys go to every pane in this tab",
                          UI["accent"]))
        self.statusbar.set_chips(chips, right,
                                 "info" if self.broadcast.get() else "ok")

    def _right_status(self, panes, _alive):
        if self.active_pane and self.active_pane in panes:
            s = self.active_pane.session
            return "pane %d · %s · %d×%d" % (self.active_pane.index + 1,
                                             s.label, s.cols, s.rows)
        return ""

    # ---------------------------------------------------------------- keys
    def _bind_keys(self):
        b = self.bind_all
        b("<Control-Shift-KeyPress-T>", lambda e: self.new_tab(1))
        b("<Control-Shift-KeyPress-N>", lambda e: self.new_pane())
        b("<Control-Shift-KeyPress-W>", lambda e: self.close_pane())
        b("<Control-Shift-KeyPress-B>", lambda e: self.toggle_broadcast())
        b("<Control-Shift-KeyPress-M>", lambda e: self.toggle_maximize())
        b("<Control-Shift-KeyPress-D>", lambda e: self.split_pane("h"))
        b("<Control-Shift-KeyPress-S>", lambda e: self.split_pane("v"))
        b("<Control-Shift-KeyPress-E>", lambda e: self.toggle_sidebar())
        b("<Control-Shift-KeyPress-plus>", lambda e: self.zoom(1))
        b("<Control-Shift-KeyPress-underscore>", lambda e: self.zoom(-1))
        b("<Control-Shift-KeyPress-question>", lambda e: self.show_help())
        b("<Control-Tab>", lambda e: self.cycle_pane(1))
        b("<F11>", lambda e: self.toggle_fullscreen())
        for i in range(1, 10):
            b("<Alt-KeyPress-%d>" % i, lambda e, n=i: self.focus_index(n - 1))

    # ---------------------------------------------------------------- loops
    def _tick(self):
        t_start = time.perf_counter()
        try:
            now = time.monotonic()
            self.anim.step()
            if now - self._blink_at >= BLINK_MS / 1000.0:
                self._blink_at = now
                self._blink_on = not self._blink_on
            page = self.current_page()
            live = sum(len(pg.panes) for pg in self._pages) or 1
            slice_s = max(0.0012, 0.007 / live)
            for pg in self._pages:
                visible = pg is page
                for p in pg.panes:
                    changed = p.session.drain(slice_s)
                    if not visible:
                        continue
                    v = p.view
                    if not v.animate_scroll():
                        if changed or v._need_full or p.session.screen.dirty \
                                or p.session.screen.full_dirty:
                            v.render()
                    v.blink_tick(self._blink_on)
            if page and now - self._header_at > HEADER_MS / 1000.0:
                self._header_at = now
                for p in page.panes:
                    p.refresh_header()
                if self._hint and now - getattr(self, "_hint_at", 0) > 4:
                    self._hint = None
                    self.refresh_status()
        except Exception as exc:                       # noqa: BLE001
            self.statusbar.set("render error: %s" % exc, "err")
            self.log.exception("frame failed: %s", exc)
        work_ms = (time.perf_counter() - t_start) * 1000.0
        self.frame_log.append((t_start, work_ms))
        if work_ms > SLOW_FRAME_MS:
            self._note_slow_frame(work_ms, t_start)
        self.after(FRAME_MS, self._tick)

    def _note_slow_frame(self, work_ms, now):
        """Record stutters, but at most one log line every few seconds."""
        self._slow_frames += 1
        if now - self._slow_logged_at < 5.0:
            return
        self._slow_logged_at = now
        page = self.current_page()
        panes = page.panes if page else []
        self.log.warning(
            "slow frame %.1f ms (%d slow so far) - %d panes, backlog %s",
            work_ms, self._slow_frames, len(panes),
            [p.session.backlog() for p in panes])

    # ----------------------------------------------------------------- misc
    @property
    def status_text(self):
        return self.statusbar.text

    def show_help(self):
        messagebox.showinfo(
            APP_NAME + " keyboard shortcuts",
            "Ctrl+Shift+T    new tab\n"
            "Ctrl+Shift+N    new pane in this tab\n"
            "Ctrl+Shift+W    close focused pane\n"
            "Ctrl+Shift+M    maximise / restore focused pane\n"
            "Ctrl+Shift+E    show / hide the workspace sidebar\n"
            "Ctrl+Shift+B    broadcast typing to every pane\n"
            "Ctrl+Shift+C    copy selection\n"
            "Ctrl+Shift+V    paste\n"
            "Ctrl+Tab        next pane\n"
            "Alt+1 … Alt+9   focus pane by number\n"
            "Shift+PgUp/PgDn scroll history\n"
            "Ctrl+Shift++/-  text size\n"
            "F11             full screen\n\n"
            "Workspaces: click a folder in the sidebar to open a terminal "
            "there, or press ▶ on a workspace to open every folder at once "
            "in a new tab.\n\n"
            "Mouse: drag to select, double-click selects a word, right-click "
            "copies or pastes, wheel scrolls. Double-click a tab to rename it.")

    def open_logs(self):
        if mlog.open_folder():
            self.hint("Log folder opened: multiterm.log")
        else:
            self.hint("Could not open %s" % mlog.LOG_DIR)

    def copy_diagnostics(self):
        text = mlog.diagnostics(self)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.log.info("diagnostics copied to the clipboard")
        self.hint("Diagnostics copied. Paste them anywhere.")

    def show_about(self):
        messagebox.showinfo(
            "About " + APP_NAME,
            APP_NAME + "\n\nA multi-pane terminal workspace for Windows.\n\n"
            "Real shells over ConPTY: Command Prompt, PowerShell, pwsh, "
            "Git Bash, WSL and Python, side by side, with workspaces, "
            "broadcast typing and a command bar that drives every pane.\n\n"
            "Settings: " + SETTINGS_FILE)

    def on_close(self):
        self.log.info("shutting down - %d tabs, %d panes, %d slow frames",
                      len(self._pages),
                      sum(len(p.panes) for p in self._pages), self._slow_frames)
        try:
            if not os.environ.get("MULTITERM_TEST"):
                self.settings["window"] = "%dx%d" % (self.winfo_width(),
                                                     self.winfo_height())
                save_settings(self.settings)
                self.store.save()
        except Exception:                              # noqa: BLE001
            pass
        for page in self._pages:
            page.close_all()
        self.destroy()


def main():
    App().mainloop()
