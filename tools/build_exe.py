"""Build dist/MultiTerm.exe with PyInstaller.

pywinpty ships helper binaries next to its extension module: conpty.dll,
winpty.dll and, crucially, OpenConsole.exe (the pseudo-console host) plus
winpty-agent.exe. PyInstaller only picks up the DLLs, so a naive build
produces an app whose shells start and are then torn down with
STATUS_CONTROL_C_EXIT (0xC000013A). This script adds them explicitly.

    python tools/build_exe.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPERS = ("OpenConsole.exe", "winpty-agent.exe", "conpty.dll", "winpty.dll")


def winpty_dir():
    import winpty
    return os.path.dirname(os.path.abspath(winpty.__file__))


def main():
    wp = winpty_dir()
    missing = [h for h in HELPERS if not os.path.isfile(os.path.join(wp, h))]
    if missing:
        print("[!] pywinpty is missing %s, reinstall it" % ", ".join(missing))

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--onefile", "--windowed", "--name", "MultiTerm",
           "--icon", os.path.join(ROOT, "assets", "multiterm.ico"),
           "--add-data", "%s;assets" % os.path.join(ROOT, "assets",
                                                    "multiterm.ico"),
           "--hidden-import", "winpty"]
    for helper in HELPERS:
        path = os.path.join(wp, helper)
        if os.path.isfile(path):
            cmd += ["--add-binary", "%s;winpty" % path]
    cmd.append(os.path.join(ROOT, "main.py"))

    print("building...")
    rc = subprocess.call(cmd, cwd=ROOT)
    exe = os.path.join(ROOT, "dist", "MultiTerm.exe")
    if rc == 0 and os.path.isfile(exe):
        print("\nBuilt %s (%.1f MB)" % (exe, os.path.getsize(exe) / 1e6))
    else:
        print("\nbuild failed (exit %s)" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
