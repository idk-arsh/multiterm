"""A single shell session: ConPTY process + screen buffer + reader thread."""
import os
import queue
import sys
import threading
import time

from winpty import PtyProcess

from . import log as mlog
from .vt import Screen


def _exists(p):
    return p and os.path.isfile(p)


def discover_shells():
    """Return [(label, argv), ...] for the shells installed on this machine."""
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    sys32 = os.path.join(sysroot, "System32")
    shells = []

    cmd = os.path.join(sys32, "cmd.exe")
    if _exists(cmd):
        shells.append(("Command Prompt", [cmd]))

    ps = os.path.join(sys32, "WindowsPowerShell", "v1.0", "powershell.exe")
    if _exists(ps):
        shells.append(("Windows PowerShell", [ps, "-NoLogo"]))

    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("LOCALAPPDATA", "")):
        pwsh = os.path.join(base, "PowerShell", "7", "pwsh.exe")
        if _exists(pwsh):
            shells.append(("PowerShell 7", [pwsh, "-NoLogo"]))
            break

    for git in (r"C:\Program Files\Git\bin\bash.exe",
                r"C:\Program Files (x86)\Git\bin\bash.exe",
                os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\Git\bin\bash.exe")):
        if _exists(git):
            shells.append(("Git Bash", [git, "--login", "-i"]))
            break

    wsl = os.path.join(sys32, "wsl.exe")
    if _exists(wsl):
        shells.append(("WSL", [wsl]))

    py = os.path.join(sys32, "..", "py.exe")
    for cand in ("py.exe", "python.exe"):
        found = None
        for d in os.environ.get("PATH", "").split(os.pathsep):
            p = os.path.join(d, cand)
            if _exists(p):
                found = p
                break
        if found:
            shells.append(("Python REPL", [found, "-i", "-q"]))
            break
    del py

    if not shells:                       # last resort
        shells.append(("Command Prompt", ["cmd.exe"]))
    return shells


class Session:
    """Owns one child process. Reading happens on a worker thread; the screen
    is only ever touched from the UI thread via drain()."""

    def __init__(self, argv, cwd=None, cols=80, rows=24, scrollback=5000,
                 title=None, folder=None):
        self.argv = list(argv)
        self.cwd = cwd or os.path.expanduser("~")
        self.cols, self.rows = cols, rows
        self.screen = Screen(cols, rows, scrollback)
        self.screen.respond = self._respond
        self.label = title or os.path.basename(self.argv[0])
        self.folder = folder
        self.proc = None
        self.error = None
        self.exit_code = None
        self._q = queue.SimpleQueue()
        self._reader = None
        self._alive = False
        self._lock = threading.Lock()
        self.log = mlog.get("session")

    # ------------------------------------------------------------------ life
    @staticmethod
    def child_env():
        """Environment for a child shell.

        When we are running from a PyInstaller bundle the loader prepends its
        extraction directory to PATH and exports its own _PYI_* variables; a
        child shell must not inherit those or it will load our bundled DLLs
        instead of its own (Git Bash dies outright).
        """
        env = dict(os.environ)
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            keep = [p for p in env.get("PATH", "").split(os.pathsep)
                    if p and os.path.normcase(os.path.abspath(p))
                    != os.path.normcase(os.path.abspath(bundle))]
            env["PATH"] = os.pathsep.join(keep)
            for key in list(env):
                if key.startswith("_PYI") or key in ("_MEIPASS2", "_MEIPASS"):
                    env.pop(key, None)
        env["TERM"] = "xterm-256color"
        env.setdefault("COLORTERM", "truecolor")
        env["MULTITERM"] = "1"
        return env

    def start(self):
        env = self.child_env()
        try:
            self.proc = PtyProcess.spawn(
                self.argv, cwd=self.cwd, env=env,
                dimensions=(self.rows, self.cols))
        except Exception as exc:                       # noqa: BLE001
            self.error = str(exc)
            self._q.put("\r\n\x1b[31mFailed to start %s:\x1b[0m %s\r\n"
                        % (" ".join(self.argv), exc))
            return False
        self._alive = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        return True

    def _read_loop(self):
        proc = self.proc
        while True:
            try:
                data = proc.read(65536)
            except EOFError:
                break
            except Exception:                          # noqa: BLE001
                break
            if data:
                self._q.put(data)
            elif not proc.isalive():
                break
        self._alive = False
        try:
            self.exit_code = proc.exitstatus
        except Exception:                              # noqa: BLE001
            self.exit_code = None
        self._q.put("\r\n\x1b[90m[process exited"
                    + (" with code %s" % self.exit_code if self.exit_code is not None else "")
                    + " - press Enter to restart]\x1b[0m\r\n")

    def is_alive(self):
        return self._alive

    def close(self):
        self._alive = False
        p, self.proc = self.proc, None
        if p is None:
            return
        try:
            p.terminate(True)
        except Exception:                              # noqa: BLE001
            pass

    def restart(self):
        self.close()
        self.screen._reset(hard=True)
        self.exit_code = None
        self.error = None
        return self.start()

    # ------------------------------------------------------------------- io
    def write(self, data):
        if not data:
            return
        p = self.proc
        if p is None or not self._alive:
            return
        with self._lock:
            try:
                p.write(data)
            except Exception:                          # noqa: BLE001
                self._alive = False

    def _respond(self, data):
        self.write(data)

    def resize(self, cols, rows):
        cols, rows = max(2, int(cols)), max(1, int(rows))
        if (cols, rows) == (self.cols, self.rows):
            return
        self.cols, self.rows = cols, rows
        self.screen.resize(cols, rows)
        p = self.proc
        if p is not None and self._alive:
            try:
                p.setwinsize(rows, cols)
            except Exception:                          # noqa: BLE001
                pass

    def drain(self, time_budget=0.004):
        """Feed pending output into the screen. UI thread only.

        Bounded by wall-clock time rather than bytes: we consume as much as
        we can in our slice of the frame and leave the rest for the next one.
        A byte budget cannot do this - too small and the reader backs up
        until the UI starves, too large and one frame parses megabytes.
        Returns True if anything changed.
        """
        got = False
        deadline = time.perf_counter() + time_budget
        while True:
            try:
                chunk = self._q.get_nowait()
            except queue.Empty:
                break
            self.screen.feed(chunk)
            got = True
            if time.perf_counter() >= deadline:
                break
        return got

    def backlog(self):
        return self._q.qsize()

    # ---------------------------------------------------------------- titles
    def display_title(self):
        """Prefer what the shell is doing over the raw OSC title."""
        t = (self.screen.title or "").strip()
        if not t:
            return self.folder or self.label
        if " - " in t:                       # 'cmd.exe - ping example.com'
            running = t.split(" - ", 1)[1].strip()
            if running:
                return running[:44]
        if t.lower().endswith(".exe"):       # just the shell's own path
            return self.folder or self.label
        return t[:44]
