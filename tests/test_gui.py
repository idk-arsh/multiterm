"""Drives the real Tk application: opens the window, types into panes, checks
output, exercises layout / broadcast / tabs, then closes.

Run: python tests\\test_gui.py
"""
import os
import sys
import time

os.environ["MULTITERM_TEST"] = "1"       # never persist settings from tests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multiterm import ui as _ui                        # noqa: E402
from multiterm.app import App                          # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    if ok:
        print("ok    " + name)
    else:
        FAILED.append("%s %s" % (name, detail))
        print("FAIL  %s %s" % (name, detail))


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.01)


def wait(app, pred, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        if pred():
            return True
        time.sleep(0.02)
    return pred()


def text_of(pane):
    return pane.session.screen.all_text()


def main():
    app = App()
    app.geometry("1200x760")
    pump(app, 1.5)

    page = app.current_page()
    check("window opened with a tab", page is not None)
    check("two panes at startup", len(page.panes) == 2, len(page.panes))
    check("both shells running", all(p.session.is_alive() for p in page.panes))

    for i, p in enumerate(page.panes):
        cols, rows = p.view.grid_size_px()
        check("pane %d has a real grid (%dx%d)" % (i + 1, cols, rows),
              cols > 20 and rows > 5)
        check("pane %d screen matches widget" % (i + 1),
              (p.session.screen.cols, p.session.screen.rows) == (cols, rows),
              (p.session.screen.cols, p.session.screen.rows, cols, rows))

    check("prompt drawn in pane 1", wait(app, lambda: text_of(page.panes[0]).strip(), 8))

    # typing into one pane only
    page.panes[0].view.send("echo GUI_PANE_ONE\r")
    ok = wait(app, lambda: "GUI_PANE_ONE" in text_of(page.panes[0]), 10)
    check("typed command ran in pane 1", ok)
    check("pane 2 unaffected", "GUI_PANE_ONE" not in text_of(page.panes[1]))

    # broadcast
    app.broadcast.set(True)
    page.panes[0].view.send("echo GUI_BROADCAST\r")
    ok = wait(app, lambda: all("GUI_BROADCAST" in text_of(p) for p in page.panes), 12)
    check("broadcast typing hit every pane", ok)
    app.broadcast.set(False)

    # command bar -> all panes in tab
    app.target_var.set("All panes in tab")
    app.cmdbar.set_text("echo GUI_CMDBAR")
    check("command bar reads back its text", app.cmdbar.text == "echo GUI_CMDBAR",
          app.cmdbar.text)
    app.send_command()
    check("command bar clears after sending", app.cmdbar.text == "",
          app.cmdbar.text)
    ok = wait(app, lambda: all("GUI_CMDBAR" in text_of(p) for p in page.panes), 12)
    check("command bar reached every pane", ok)

    # add panes and check the grid re-flows
    app.new_pane()
    app.new_pane()
    pump(app, 1.0)
    check("four panes now", len(page.panes) == 4, len(page.panes))
    mx = page.winfo_width() / 2
    my = page.winfo_height() / 2
    quads = {(p.winfo_x() + p.winfo_width() / 2 > mx,
              p.winfo_y() + p.winfo_height() / 2 > my) for p in page.panes}
    check("2x2 auto layout fills four quadrants", len(quads) == 4, quads)
    check("new panes running", all(p.session.is_alive() for p in page.panes))

    app.layout_var.set("Columns")
    app.apply_layout()
    pump(app, 0.8)
    ys = {p.winfo_y() for p in page.panes}
    xs = sorted(p.winfo_x() for p in page.panes)
    check("columns layout puts panes in one row", len(ys) == 1 and len(set(xs)) == 4,
          (ys, xs))
    app.layout_var.set("Auto")
    app.apply_layout()
    pump(app, 0.6)

    # freeform reshaping: split, drag a divider, even out
    before_n = len(page.panes)
    app.split_pane("h")
    pump(app, 1.2)
    check("split right adds a pane", len(page.panes) == before_n + 1,
          len(page.panes))
    check("splitting switches to custom layout", page.layout == "Custom",
          page.layout)
    check("dividers exist", any(g.winfo_ismapped() for g in page._sashes),
          len(page._sashes))
    sash = next(g for g in page._sashes if g.winfo_ismapped())
    node = sash.node
    old_ratio = node.ratio
    widths_before = [p.winfo_width() for p in page.panes]

    class _E:
        pass
    ev = _E()
    ev.x, ev.y = -70, 0
    page._sash_drag(sash, ev)
    pump(app, 0.5)
    check("dragging a divider reshapes panes", node.ratio != old_ratio,
          (old_ratio, node.ratio))
    check("pane widths actually changed",
          [p.winfo_width() for p in page.panes] != widths_before)
    app.even_panes()
    pump(app, 0.4)
    check("even out resets the divider", abs(node.ratio - 0.5) < 1e-6, node.ratio)
    app.close_pane(page.panes[-1])
    pump(app, 0.5)
    check("closing a split pane keeps the rest",
          len(page.panes) == before_n and all(p.winfo_ismapped()
                                             for p in page.panes),
          len(page.panes))
    page.layout = "Auto"
    app.layout_var.set("Auto")
    app.apply_layout()
    pump(app, 0.5)

    # standard Windows window: native frame, native maximise
    check("window uses the native frame (snap, taskbar, Aero all work)",
          not app.overrideredirect(), app.overrideredirect())
    geo_before = (app.winfo_width(), app.winfo_height())
    app.toggle_zoom()
    pump(app, 0.8)
    check("maximise fills the screen", app.winfo_width() > geo_before[0],
          (geo_before, app.winfo_width()))
    check("window manager reports zoomed", app.state() == "zoomed", app.state())
    app.toggle_zoom()
    pump(app, 0.8)
    check("restore returns to the old size",
          abs(app.winfo_width() - geo_before[0]) <= 4,
          (geo_before[0], app.winfo_width()))
    # the header must not collide with itself at any width
    def overlaps(hits):
        bad = []
        for i in range(len(hits)):
            ax0, ay0, ax1, ay1, ak = hits[i]
            for j in range(i + 1, len(hits)):
                bx0, by0, bx1, by1, bk = hits[j]
                if ax0 < bx1 - 1 and bx0 < ax1 - 1 and ay0 < by1 - 1 and by0 < ay1 - 1:
                    bad.append((ak, bk))
        return bad

    collisions = []
    for width in (880, 1000, 1100, 1280, 1500):
        app.geometry("%dx780" % width)
        pump(app, 0.35)
        app.header.redraw()
        collisions += overlaps(app.header._hits)
    check("header controls never overlap at any width", not collisions,
          collisions[:3])
    app.geometry("1200x760")
    pump(app, 0.4)

    # labels must fit their pills - a clipped "Command Prompt" shipped once
    from multiterm import gfx as _gfx
    fits = []
    for x0, _y0, x1, _y1, key in app.header._hits:
        if key[0] == "shell":
            fits.append((key[0], x1 - x0, _gfx.measure(app.shell_var.get(), 10)))
        elif key[0] == "broadcast" and app.winfo_width() >= 900:
            fits.append((key[0], x1 - x0, _gfx.measure("Broadcast", 10, True)))
    check("header labels fit inside their pills",
          all(width >= text + 24 for _k, width, text in fits) and fits, fits)

    # labels must not run underneath the buttons either
    def label_collisions(canvas):
        hits = [(x0, y0, x1, y1, k) for x0, y0, x1, y1, k in canvas._hits]
        clashes = []
        for item in canvas.find_all():
            if canvas.type(item) != "text":
                continue
            box = canvas.bbox(item)
            label = canvas.itemcget(item, "text")
            if not box or not label.strip():
                continue
            tx0, ty0, tx1, ty1 = box
            for hx0, hy0, hx1, hy1, key in hits:
                inside = tx0 >= hx0 - 2 and tx1 <= hx1 + 2
                if inside:
                    continue          # the button's own caption
                if tx0 < hx1 - 3 and hx0 < tx1 - 3 and ty0 < hy1 and hy0 < ty1:
                    clashes.append((label[:16], key))
        return clashes

    clash = []
    for width in (1000, 1200, 1500):
        app.geometry("%dx780" % width)
        pump(app, 0.3)
        app.header.redraw()
        clash += label_collisions(app.header)
    check("header text never runs under a control", not clash, clash[:3])
    app.geometry("1200x760")
    pump(app, 0.3)

    check("header carries the real controls, no window buttons",
          not any(k[0] == "win" for *_r, k in app.header._hits)
          and {"new_pane", "new_tab", "broadcast", "shell", "menu"}.issubset(
              {k[0] for *_r, k in app.header._hits}),
          sorted({k[0] for *_r, k in app.header._hits}))

    # maximize / restore
    app.toggle_maximize(page.panes[2])
    pump(app, 0.3)
    placed = [bool(p.place_info()) for p in page.panes]
    check("maximized pane is the only one laid out",
          page.maximized is page.panes[2] and placed == [False, False, True, False],
          (placed, page.maximized is page.panes[2]))
    app.toggle_maximize(page.panes[2])
    pump(app, 0.3)
    check("restored: every pane laid out again",
          page.maximized is None
          and all(p.place_info() for p in page.panes),
          [bool(p.place_info()) for p in page.panes])

    # each pane keeps its own independent state
    for i, p in enumerate(page.panes):
        p.view.send("echo ID_%d\r" % i)
    ok = wait(app, lambda: all("ID_%d" % i in text_of(p)
                               for i, p in enumerate(page.panes)), 12)
    check("panes are independent", ok)
    cross = any("ID_3" in text_of(page.panes[0]) for _ in (0,))
    check("no cross-talk between panes", not cross)

    # scrollback + selection + copy
    big = page.panes[0]
    big.view.send("dir /b C:\\Windows\\System32\r"
                  if big.session.label.startswith("Command")
                  else "Get-ChildItem C:\\Windows\\System32 | Select-Object -First 200\r")
    pump(app, 3.0)
    check("scrollback filled", len(big.session.screen.scrollback) > 10,
          len(big.session.screen.scrollback))
    before = big.view.view_offset
    big.view.scroll(10)
    check("smooth wheel scrollback reaches target",
          wait(app, lambda: big.view.view_offset == big.view.scroll_target
               and big.view.view_offset > before, 3),
          (big.view.view_offset, big.view.scroll_target))
    big.view.scroll_to_bottom()
    check("scroll back to bottom", big.view.view_offset == 0)

    big.view.sel_anchor = (big.session.screen.total_lines() - 3, 0)
    big.view.sel_head = (big.session.screen.total_lines() - 3, 20)
    check("selection returns text", isinstance(big.view.selected_text(), str))
    big.view.clear_selection()

    # font zoom + theme switch must not raise and must re-grid the shells
    old = big.session.screen.cols
    app.zoom(4)
    pump(app, 0.8)
    check("zoom changed the grid", big.session.screen.cols != old,
          (old, big.session.screen.cols))
    app.zoom(-4)
    pump(app, 0.6)
    app.theme_var.set("One Dark")
    app.apply_theme()
    pump(app, 0.6)
    check("theme switch survived", all(p.session.is_alive() for p in page.panes))
    app.theme_var.set("Graphite")
    app.apply_theme()

    # close one pane
    victim = page.panes[3]
    app.close_pane(victim)
    pump(app, 0.6)
    check("pane closed", len(page.panes) == 3, len(page.panes))
    check("closed session terminated", not victim.session.is_alive())

    # second tab, independent sessions
    page2 = app.new_tab(2)
    pump(app, 1.5)
    check("second tab has 2 panes", len(page2.panes) == 2, len(page2.panes))
    check("total sessions across tabs",
          sum(len(p.panes) for p in app.pages()) == 5,
          sum(len(p.panes) for p in app.pages()))
    page2.panes[0].view.send("echo TAB_TWO\r")
    ok = wait(app, lambda: "TAB_TWO" in text_of(page2.panes[0]), 10)
    check("tab 2 pane works", ok)
    check("background tab kept running",
          all(p.session.is_alive() for p in page.panes))

    # background tab still receives output while hidden
    page.panes[0].session.write("echo BACKGROUND_TAB\r")
    ok = wait(app, lambda: "BACKGROUND_TAB" in text_of(page.panes[0]), 10)
    check("hidden tab still drains output", ok)

    # restart a dead shell
    p0 = page2.panes[0]
    p0.session.write("exit\r")
    ok = wait(app, lambda: not p0.session.is_alive(), 10)
    check("shell exit noticed", ok)
    pump(app, 0.5)
    check("header shows exited", "exited" in p0.header_text(), p0.header_text())
    p0.restart()
    ok = wait(app, lambda: p0.session.is_alive(), 8)
    check("pane restarted", ok)

    # in-pane find: highlight matches and step through them
    fv = page.panes[0].view
    fv.toggle_find()
    check("find bar opens", fv.find_open)
    fv.find_query = "Windows"
    fv._run_find()
    pump(app, 0.4)
    check("find located matches", len(fv.match_list) > 0, len(fv.match_list))
    check("matches map to lines", bool(fv.matches))
    pos = fv.match_pos
    fv.find_step(1)
    check("find steps between matches",
          fv.match_pos != pos or len(fv.match_list) == 1,
          (pos, fv.match_pos))
    fv.toggle_find()
    check("find bar closes and clears", not fv.find_open and not fv.matches)

    # overlay furniture: scrollbar dragging + jump-to-bottom
    fv.scroll(200)
    pump(app, 0.5)
    check("overlay scrollbar hit area registered",
          any(k == "scrollbar" for *_r, k in fv._ovl_hits), fv._ovl_hits)
    check("jump-to-latest chip appears when scrolled",
          any(k == "jump" for *_r, k in fv._ovl_hits))
    fv._scroll_from_mouse(fv.canvas.winfo_height() - 20)
    pump(app, 0.3)
    check("dragging the scrollbar moves the view", fv.view_offset == 0,
          fv.view_offset)

    # workspaces: sidebar model + opening folders as terminals
    import tempfile
    tmp = tempfile.mkdtemp(prefix="mt_ws_")
    for sub in ("alpha", "beta", "gamma"):
        os.makedirs(os.path.join(tmp, sub), exist_ok=True)
    ws = app.store.add(tmp, "TestWS")
    check("workspace added", ws in app.store.items)
    check("workspace finds its folders", len(ws.entries()) == 3,
          [os.path.basename(p) for p in ws.entries()])
    wpage = app.open_workspace(ws)
    pump(app, 2.0)
    check("workspace opened a tab with one pane per folder",
          wpage is not None and len(wpage.panes) == 3,
          len(wpage.panes) if wpage else None)
    check("workspace panes started in their folders",
          all(os.path.basename(p.session.cwd) in ("alpha", "beta", "gamma")
              for p in wpage.panes),
          [p.session.cwd for p in wpage.panes])
    check("workspace tab is named after the workspace", wpage.name == "TestWS",
          wpage.name)
    before = len(wpage.panes)
    app.open_folder(os.path.join(tmp, "alpha"), ws)
    pump(app, 1.2)
    check("clicking a folder adds a terminal", len(wpage.panes) == before + 1,
          len(wpage.panes))
    check("sidebar rows render", len(app.sidebar.rows()) > 3,
          len(app.sidebar.rows()))
    app.sidebar.redraw()
    app.header.redraw()
    app.tabstrip.redraw()
    app.cmdbar.redraw()
    check("chrome redraw is clean", True)
    # the differentiator: a workspace starts its own project
    ws.set_command(os.path.join(tmp, "alpha"), "echo ALPHA_AUTOSTART")
    ws.set_command(os.path.join(tmp, "beta"), "echo BETA_AUTOSTART")
    check("startup commands persist per folder",
          ws.command_for(os.path.join(tmp, "alpha")) == "echo ALPHA_AUTOSTART"
          and ws.command_for(os.path.join(tmp, "gamma")) == "",
          ws.commands)
    auto = app.open_workspace(ws)
    ok = wait(app, lambda: any("ALPHA_AUTOSTART" in text_of(p) for p in auto.panes)
              and any("BETA_AUTOSTART" in text_of(p) for p in auto.panes), 20)
    check("opening the workspace runs each folder's command", ok,
          [text_of(p)[-60:] for p in auto.panes])
    check("folders without a command stay idle",
          not any("AUTOSTART" in text_of(p) for p in auto.panes
                  if os.path.basename(p.session.cwd) == "gamma"))
    app.set_folder_command(ws, os.path.join(tmp, "alpha"), "")
    check("a startup command can be cleared",
          ws.command_for(os.path.join(tmp, "alpha")) == "")

    app.remove_workspace(ws)
    check("workspace removed", ws not in app.store.items)

    # nothing may be drawn outside its own surface at any display scale
    def clipped(canvas, check_y=True, margin=2):
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        out = []
        for item in canvas.find_all():
            if canvas.type(item) != "text":
                continue
            box = canvas.bbox(item)
            if not box:
                continue
            x0, y0, x1, y1 = box
            if x0 < -margin or x1 > cw + margin or (
                    check_y and (y0 < -margin or y1 > ch + margin)):
                out.append((canvas.itemcget(item, "text")[:18], box, (cw, ch)))
        return out

    surfaces = [("header", app.header, True), ("tabs", app.tabstrip, True),
                ("command bar", app.cmdbar, True),
                ("status bar", app.statusbar, True),
                ("sidebar", app.sidebar, False)]
    surfaces += [("pane %d header" % (p.index + 1), p.header, True)
                 for p in app.current_page().panes]
    bad = []
    for name, canvas, check_y in surfaces:
        for item in clipped(canvas, check_y):
            bad.append((name,) + item)
    check("no text is clipped by its surface (scale %.2f)" % _ui.SCALE,
          not bad, bad[:3])

    check("no render errors", "render error" not in app.status_text,
          app.status_text)

    app.on_close()
    time.sleep(0.5)
    print()
    if FAILED:
        print("%d FAILED: %s" % (len(FAILED), FAILED))
        return 1
    print("all GUI tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
