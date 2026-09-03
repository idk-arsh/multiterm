"""End-to-end test: real shells over ConPTY feeding real Screen buffers.

Runs several sessions concurrently - the same thing the GUI does, minus Tk.
Run: python tests\\test_live.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multiterm.session import Session, discover_shells   # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    if ok:
        print("ok    " + name)
    else:
        FAILED.append("%s %s" % (name, detail))
        print("FAIL  %s %s" % (name, detail))


def pump(sessions, seconds):
    end = time.time() + seconds
    while time.time() < end:
        for s in sessions:
            s.drain()
        time.sleep(0.02)
    for s in sessions:
        s.drain()


def wait_for(sessions, pred, seconds):
    end = time.time() + seconds
    while time.time() < end:
        for s in sessions:
            s.drain()
        if pred():
            return True
        time.sleep(0.05)
    for s in sessions:
        s.drain()
    return pred()


def main():
    shells = discover_shells()
    print("shells found: " + ", ".join(s[0] for s in shells))

    # --- 1. several sessions at once, each getting its own command ----------
    sessions = []
    for label, argv in shells[:3]:
        s = Session(argv, cwd=os.path.expanduser("~"), cols=100, rows=30, title=label)
        check("spawn %s" % label, s.start(), s.error or "")
        sessions.append(s)
    if not sessions:
        print("no shells to test")
        return 1

    pump(sessions, 2.0)
    for s in sessions:
        check("%s produced a prompt" % s.label, len(s.screen.all_text().strip()) > 0)

    # --- 2. broadcast the same command to every session ---------------------
    for s in sessions:
        s.write("echo BROADCAST_MARKER\r")
    ok = wait_for(sessions,
                  lambda: all("BROADCAST_MARKER" in s.screen.all_text()
                              for s in sessions), 12)
    check("broadcast reached every pane", ok,
          "" if ok else [s.label for s in sessions
                         if "BROADCAST_MARKER" not in s.screen.all_text()])

    # --- 3. colour output is parsed into attributes -------------------------
    first = sessions[0]
    first.write("echo \x1b[31mREDTEXT\x1b[0m\r")
    ok = wait_for([first], lambda: "REDTEXT" in first.screen.all_text(), 8)
    check("colour output rendered", ok)
    if ok:
        found = False
        for y in range(first.screen.rows):
            row = "".join(first.screen.chars[y])
            col = row.find("REDTEXT")
            if col >= 0 and first.screen.attrs[y][col][0] == 1:
                found = True
        check("red attribute recorded", found)

    # --- 4. resize propagates to the child ----------------------------------
    first.resize(60, 20)
    check("resize applied", (first.screen.cols, first.screen.rows) == (60, 20))
    time.sleep(0.3)
    check("still alive after resize", first.is_alive())

    # --- 5. heavy output does not lose data ---------------------------------
    heavy = sessions[0]
    heavy.resize(100, 30)
    heavy.write("for /L %i in (1,1,200) do @echo LINE_%i\r"
                if heavy.label.startswith("Command") else
                "1..200 | ForEach-Object { \"LINE_$_\" }\r")
    ok = wait_for([heavy], lambda: "LINE_200" in heavy.screen.all_text(), 20)
    check("bulk output captured (200 lines)", ok)
    check("scrollback retained lines", len(heavy.screen.scrollback) > 50,
          "scrollback=%d" % len(heavy.screen.scrollback))

    # --- 6. exit is detected ------------------------------------------------
    last = sessions[-1]
    last.write("exit\r")
    ok = wait_for([last], lambda: not last.is_alive(), 10)
    check("exit detected", ok)

    # --- 7. restart works ---------------------------------------------------
    check("restart", last.restart())
    ok = wait_for([last], lambda: len(last.screen.all_text().strip()) > 0, 8)
    check("restarted shell prints again", ok)

    for s in sessions:
        s.close()
    time.sleep(0.3)
    check("all closed", all(not s.is_alive() for s in sessions))

    print()
    if FAILED:
        print("%d FAILED: %s" % (len(FAILED), FAILED))
        return 1
    print("all live ConPTY tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
