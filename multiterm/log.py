"""Logging and diagnostics.

A packaged windowed app has no stderr, so anything that goes wrong is
invisible unless it is written down. Everything lands in
%APPDATA%\\MultiTerm\\logs\\multiterm.log (rotated), including Tk callback
exceptions, shell spawns and exits, and frames that took too long.
"""
import logging
import logging.handlers
import os
import platform
import subprocess
import sys
import traceback

LOG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                       "MultiTerm", "logs")
LOG_FILE = os.path.join(LOG_DIR, "multiterm.log")

_log = logging.getLogger("multiterm")
_ready = False


def setup(debug=False):
    """Attach the rotating file handler once. Never raises."""
    global _ready
    if _ready:
        return _log
    _log.setLevel(logging.DEBUG if debug else logging.INFO)
    _log.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                            "%Y-%m-%d %H:%M:%S")
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(fmt)
        _log.addHandler(handler)
    except Exception:                                  # noqa: BLE001
        pass                                           # disk trouble: stay quiet
    # console output only on request: the file is the source of truth and
    # test output should stay readable
    if not getattr(sys, "frozen", False) and os.environ.get("MULTITERM_DEBUG"):
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        _log.addHandler(stream)
    _ready = True
    return _log


def get(name=None):
    setup()
    return _log.getChild(name) if name else _log


def banner(extra=None):
    """One line per run so log files are easy to split by session."""
    log = get()
    log.info("=" * 60)
    log.info("MultiTerm starting - python %s, %s %s, frozen=%s",
             platform.python_version(), platform.system(), platform.release(),
             getattr(sys, "frozen", False))
    if extra:
        for key, value in extra.items():
            log.info("  %s: %s", key, value)


def install_excepthook(app=None):
    """Route uncaught exceptions - including Tk callback errors - to the log."""
    log = get()

    def hook(exc_type, exc, tb):
        log.error("uncaught exception\n%s",
                  "".join(traceback.format_exception(exc_type, exc, tb)))
    sys.excepthook = hook

    if app is not None:
        def report(exc_type, exc, tb):
            log.error("Tk callback failed\n%s",
                      "".join(traceback.format_exception(exc_type, exc, tb)))
        app.report_callback_exception = report


def open_folder():
    """Show the log directory in Explorer."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        subprocess.Popen(["explorer", os.path.normpath(LOG_DIR)])
        return True
    except Exception:                                  # noqa: BLE001
        get().exception("could not open the log folder")
        return False


def tail(lines=200):
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readlines()[-lines:])
    except Exception:                                  # noqa: BLE001
        return "(no log file yet: %s)" % LOG_FILE


def diagnostics(app=None):
    """A paste-ready summary of the app's state plus the tail of the log."""
    out = ["MultiTerm diagnostics",
           "python %s | %s %s | frozen=%s"
           % (platform.python_version(), platform.system(), platform.release(),
              getattr(sys, "frozen", False)),
           "log file: %s" % LOG_FILE]
    if app is not None:
        try:
            panes = [p for pg in app.pages() for p in pg.panes]
            out.append("window %dx%d | tabs %d | panes %d (%d running)"
                       % (app.winfo_width(), app.winfo_height(),
                          len(app.pages()), len(panes),
                          sum(1 for p in panes if p.session.is_alive())))
            out.append("theme %s | font %s | shells: %s"
                       % (app.settings.get("theme"),
                          app.settings.get("font_size"),
                          ", ".join(s[0] for s in app.shells)))
            frames = [ms for _t, ms in app.frame_log]
            if frames:
                frames_sorted = sorted(frames)
                out.append("frame work: avg %.2f ms | p95 %.2f ms | worst %.2f ms"
                           % (sum(frames) / len(frames),
                              frames_sorted[int(len(frames) * 0.95) - 1],
                              frames_sorted[-1]))
            for p in panes:
                out.append("  pane %d %s alive=%s %dx%d backlog=%d"
                           % (p.index + 1, p.session.label,
                              p.session.is_alive(), p.session.cols,
                              p.session.rows, p.session.backlog()))
        except Exception as exc:                       # noqa: BLE001
            out.append("(state unavailable: %s)" % exc)
    out.append("")
    out.append("--- last log lines ---")
    out.append(tail(60))
    return "\n".join(out)
