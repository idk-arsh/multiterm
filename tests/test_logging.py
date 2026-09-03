"""Checks for the logging / diagnostics layer.

Run: python tests\\test_logging.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multiterm import log as mlog                      # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    if ok:
        print("ok    " + name)
    else:
        FAILED.append("%s %s" % (name, detail))
        print("FAIL  %s %s" % (name, detail))


def main():
    mlog.setup()
    log = mlog.get("selftest")
    marker = "selftest-marker-%d" % time.time()
    log.info(marker)
    for h in mlog.get().handlers:
        h.flush()

    check("log file created", os.path.isfile(mlog.LOG_FILE), mlog.LOG_FILE)
    check("message reaches the file", marker in mlog.tail(50))
    check("tail survives a missing file", isinstance(mlog.tail(5), str))

    # a second setup() must not double up handlers (duplicate lines)
    before = len(mlog.get().handlers)
    mlog.setup()
    check("setup is idempotent", len(mlog.get().handlers) == before,
          (before, len(mlog.get().handlers)))

    # exceptions must be captured rather than lost
    old_hook = sys.excepthook
    mlog.install_excepthook()
    try:
        raise ValueError("captured-by-hook")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    for h in mlog.get().handlers:
        h.flush()
    check("uncaught exceptions are logged", "captured-by-hook" in mlog.tail(60))
    sys.excepthook = old_hook

    text = mlog.diagnostics()
    check("diagnostics without an app", "MultiTerm diagnostics" in text
          and "log file:" in text)

    # banner writes a session separator
    mlog.banner({"scenario": "selftest"})
    for h in mlog.get().handlers:
        h.flush()
    tail = mlog.tail(30)
    check("banner records the run", "MultiTerm starting" in tail
          and "scenario: selftest" in tail)

    print()
    if FAILED:
        print("%d FAILED: %s" % (len(FAILED), FAILED))
        return 1
    print("all logging tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
