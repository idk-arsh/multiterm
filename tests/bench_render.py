"""Frame-time benchmark: four panes all streaming output at once.

Run: python tests\\bench_render.py
"""
import os
import sys
import time

os.environ["MULTITERM_TEST"] = "1"       # never persist settings from tests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multiterm.app import App                          # noqa: E402


def percentile(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(len(vals) * p))]


def measure(app, seconds, label):
    """Measure the app's own frame work.

    Timing app.update() is misleading: while there is always a ready timer
    callback, one update() call keeps running frames and never returns. What
    matters for responsiveness is how long each frame's work takes and how
    often frames run, which the app records itself in app.frame_log.
    """
    app.frame_log.clear()
    start = time.perf_counter()
    end = start + seconds
    while time.perf_counter() < end:
        app.update()
        time.sleep(0.001)
    frames = [ms for _t, ms in app.frame_log]
    starts = [t for t, _ms in app.frame_log]
    if not frames:
        print("%-34s no frames recorded" % label)
        return 0.0, 0.0
    gaps = [(starts[i] - starts[i - 1]) * 1000.0 for i in range(1, len(starts))]
    fps = len(frames) / seconds
    print("%-34s frames=%4d (%3.0f/s)  work avg=%5.2f ms  p95=%5.2f ms  "
          "worst=%6.2f ms  gap p95=%5.1f ms"
          % (label, len(frames), fps, sum(frames) / len(frames),
             percentile(frames, 0.95), max(frames),
             percentile(gaps, 0.95) if gaps else 0))
    return sum(frames) / len(frames), percentile(frames, 0.95)


def main():
    app = App()
    app.geometry("1500x900")
    for _ in range(2):
        app.new_pane()
    for _ in range(200):
        app.update()
        time.sleep(0.005)
    page = app.current_page()
    print("panes: %d   grid: %dx%d each\n"
          % (len(page.panes), page.panes[0].session.screen.cols,
             page.panes[0].session.screen.rows))

    idle = measure(app, 2.0, "idle (4 panes)")

    # every pane blasting output at the same time
    for p in page.panes:
        cmd = ("for /L %i in (1,1,4000) do @echo [%i] the quick brown fox "
               "jumps over the lazy dog\r"
               if p.session.label.startswith("Command")
               else "1..4000 | %{ \"[$_] the quick brown fox jumps over the "
                    "lazy dog\" }\r")
        p.session.write(cmd)
    time.sleep(0.4)
    busy = measure(app, 6.0, "4 panes streaming output")

    for p in page.panes:
        p.session.write("\x03")
    time.sleep(1.0)
    for _ in range(100):
        app.update()

    # scrolling while output is live
    page.panes[0].view.scroll(400)
    scroll = measure(app, 2.0, "smooth scrolling 400 lines")

    total = sum(len(p.session.screen.scrollback) for p in page.panes)
    print("\nscrollback lines captured across panes: %d" % total)
    app.on_close()

    ok = busy[1] < 33 and idle[1] < 8
    print("\n%s  (target: p95 under 33 ms => 30+ fps while streaming)"
          % ("PASS" if ok else "SLOW"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
