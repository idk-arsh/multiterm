"""MultiTerm launcher."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _fail(msg):
    try:
        import tkinter.messagebox as mb
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        mb.showerror("MultiTerm", msg)
        r.destroy()
    except Exception:                                  # noqa: BLE001
        pass
    print(msg, file=sys.stderr)
    sys.exit(1)


def main():
    if os.name != "nt":
        _fail("MultiTerm needs Windows (it uses the ConPTY API).")
    try:
        import winpty                                   # noqa: F401
    except ImportError:
        _fail("The 'pywinpty' package is missing.\n\n"
              "Install it with:\n    pip install pywinpty")
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)         # crisp text on HiDPI
    except Exception:                                   # noqa: BLE001
        pass
    from multiterm import log as mlog
    mlog.setup(debug=bool(os.environ.get("MULTITERM_DEBUG")))
    mlog.install_excepthook()
    try:
        from multiterm.app import main as run
        run()
    except Exception:                                   # noqa: BLE001
        mlog.get().exception("fatal error while running the app")
        _fail("MultiTerm hit a fatal error.\n\nDetails were written to:\n"
              + mlog.LOG_FILE)


if __name__ == "__main__":
    main()
