"""Record a short demo of MultiTerm actually being used.

Drives the real app (no mock-ups), grabs the window with PrintWindow at a
steady frame rate and writes an animated WebP plus a poster frame for the
website.

    python tools/record_demo.py [--out web/public] [--fps 10] [--width 1200]
"""
import argparse
import ctypes
import ctypes.wintypes as wintypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image                                  # noqa: E402

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def grab(hwnd):
    """The window's pixels as a PIL image, even when partly covered."""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None

    window_dc = user32.GetWindowDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, w, h)
    gdi32.SelectObject(mem_dc, bitmap)
    try:
        # 2 == PW_RENDERFULLCONTENT
        if not user32.PrintWindow(hwnd, mem_dc, 2):
            gdi32.BitBlt(mem_dc, 0, 0, w, h, window_dc, 0, 0, SRCCOPY)
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = w
        info.bmiHeader.biHeight = -h            # top-down
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem_dc, bitmap, 0, h, buf, ctypes.byref(info),
                        DIB_RGB_COLORS)
        return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, window_dc)


class Recorder:
    def __init__(self, app, hwnd, fps, width):
        self.app, self.hwnd, self.width = app, hwnd, width
        self.interval = 1.0 / fps
        self.frames = []
        self.size = None          # locked from the first frame
        self._next = time.perf_counter()

    def pump(self, seconds):
        """Run the app for a while, capturing at the target frame rate."""
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            self.app.update()
            now = time.perf_counter()
            if now >= self._next:
                self._next = now + self.interval
                frame = grab(self.hwnd)
                if frame:
                    if self.size is None:
                        h = round(frame.height * self.width / frame.width)
                        self.size = (self.width, h)
                    if frame.size != self.size:
                        frame = frame.resize(self.size, Image.LANCZOS)
                    self.frames.append(frame)
            time.sleep(0.004)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("web", "public"))
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--width", type=int, default=1200)
    args = ap.parse_args()

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                                  # noqa: BLE001
        pass
    os.environ["MULTITERM_TEST"] = "1"                 # do not touch settings
    # a bare ">" prompt: no machine name, no user name, no paths on screen
    os.environ["PROMPT"] = "$G"

    import tempfile
    from multiterm import workspace as ws_mod

    # a throwaway project so the recording shows neutral folder names, and a
    # throwaway store so the real workspace list is left alone
    sandbox = tempfile.mkdtemp(prefix="mt-demo-")
    ws_mod.STORE_DIR = sandbox
    ws_mod.STORE_FILE = os.path.join(sandbox, "workspaces.json")
    project = os.path.join(sandbox, "acme-platform")
    parts = ["api", "web", "worker", "tests"]
    for part in parts:
        os.makedirs(os.path.join(project, part), exist_ok=True)

    from multiterm.app import App

    app = App()
    app.geometry("1760x1040+40+30")
    for _ in range(120):
        app.update()
        time.sleep(0.005)

    hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
    user32.SetForegroundWindow(hwnd)
    rec = Recorder(app, hwnd, args.fps, args.width)

    # 1. two plain shells, the thing every terminal already gives you
    rec.pump(1.3)

    # 2. a workspace that knows what each folder should run.
    # Drop the auto-discovered defaults first: they list the real home folder
    # and would put personal directory names in the recording.
    app.store.items = []
    ws = app.store.add(project, "acme-platform")
    ws.set_command(os.path.join(project, "api"),
                   "echo [api] listening on http://localhost:8080")
    ws.set_command(os.path.join(project, "web"),
                   "echo [web] dev server ready in 412 ms")
    ws.set_command(os.path.join(project, "worker"),
                   "echo [worker] connected to the queue")
    ws.set_command(os.path.join(project, "tests"),
                   "echo [tests] 72 passed in 3.1s")
    app.sidebar.active_ws = ws
    app.sidebar.redraw()
    rec.pump(1.4)

    # 3. one click: four terminals, each in its folder, each already running
    page = app.open_workspace(ws)
    rec.pump(3.4)

    # 4. broadcast: type once, every pane runs it
    app.broadcast.set(True)
    app._broadcast_changed()
    rec.pump(0.7)
    if page.panes:
        page.panes[0].view.send("echo deploying to staging\r")
    rec.pump(1.8)
    app.broadcast.set(False)
    app._broadcast_changed()
    rec.pump(0.6)

    # 5. reshape: drag a divider, panes are not stuck in a grid
    page.layout = "Custom"
    app.layout_var.set("Custom")
    sashes = [s for s in page._sashes if s.winfo_ismapped()]
    if sashes:
        sash = sashes[0]

        class Ev:
            pass
        for step in (-26, -26, -22, -18, 16, 22, 26, 22):
            ev = Ev()
            ev.x, ev.y = step, step
            page._sash_drag(sash, ev)
            rec.pump(0.13)
    rec.pump(0.9)

    # 6. find inside a pane, every match highlighted
    if page.panes:
        view = page.panes[0].view
        view.toggle_find()
        for ch in "listening":
            view.find_query += ch
            view._run_find()
            view._need_full = True
            view._ovl_sig = None
            view.render()
            rec.pump(0.12)
        rec.pump(1.4)
        view.toggle_find()
    rec.pump(1.0)

    frames = rec.frames
    print("captured %d frames at %dx%d" % (len(frames), frames[0].width,
                                           frames[0].height))
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    webp = os.path.join(out_dir, "demo.webp")
    poster = os.path.join(out_dir, "screenshot.png")
    frames[0].save(webp, save_all=True, append_images=frames[1:],
                   duration=int(1000 / args.fps), loop=0, quality=72, method=4)
    # note: Pillow's reader under-reports frames once WebP merges identical
    # ones. Browsers play the full sequence; verified in Chrome.
    print("stored, reader reports %d frames" % Image.open(webp).n_frames)
    # a middle frame makes a better still than the opening one
    frames[len(frames) // 2].save(poster, optimize=True)
    print("wrote %s (%.1f MB)" % (webp, os.path.getsize(webp) / 1e6))
    print("wrote %s (%.0f kB)" % (poster, os.path.getsize(poster) / 1e3))

    app.on_close()


if __name__ == "__main__":
    main()
