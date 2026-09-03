"""Set MultiTerm up: dependency check, icon, Desktop + Start Menu shortcuts."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON = os.path.join(ROOT, "assets", "multiterm.ico")
EXE = os.path.join(ROOT, "dist", "MultiTerm.exe")


def ensure_pywinpty():
    try:
        import winpty                                   # noqa: F401
        print("[ok] pywinpty is installed")
        return True
    except ImportError:
        print("[..] installing pywinpty ...")
        rc = subprocess.call([sys.executable, "-m", "pip", "install", "pywinpty"])
        if rc != 0:
            print("[!!] pip install pywinpty failed - run it manually")
            return False
        print("[ok] pywinpty installed")
        return True


def ensure_icon():
    if not os.path.isfile(ICON):
        subprocess.call([sys.executable, os.path.join(ROOT, "tools", "make_icon.py")])
    return os.path.isfile(ICON)


def pythonw():
    p = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return p if os.path.isfile(p) else sys.executable


def make_shortcut(path, target, args, workdir, icon):
    ps = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(%s);"
        "$s.TargetPath = %s;"
        "$s.Arguments = %s;"
        "$s.WorkingDirectory = %s;"
        "$s.IconLocation = %s;"
        "$s.Description = 'MultiTerm - multi-pane terminal workspace';"
        "$s.Save()"
    ) % tuple("'%s'" % v.replace("'", "''") for v in
              (path, target, args, workdir, icon))
    return subprocess.call(["powershell", "-NoProfile", "-NonInteractive",
                            "-Command", ps]) == 0


def main():
    print("MultiTerm setup")
    print("root: " + ROOT)
    ok = ensure_pywinpty()
    ensure_icon()

    if os.path.isfile(EXE):
        target, args = EXE, ""
    else:
        target, args = pythonw(), '"%s"' % os.path.join(ROOT, "main.py")

    desktop = subprocess.check_output(
        ["powershell", "-NoProfile", "-Command",
         "[Environment]::GetFolderPath('Desktop')"], text=True).strip()
    startmenu = os.path.join(os.environ.get("APPDATA", ""),
                             r"Microsoft\Windows\Start Menu\Programs")

    for folder in (desktop, startmenu):
        if not folder or not os.path.isdir(folder):
            continue
        lnk = os.path.join(folder, "MultiTerm.lnk")
        if make_shortcut(lnk, target, args, ROOT, ICON):
            print("[ok] shortcut: " + lnk)
        else:
            print("[!!] could not create " + lnk)

    print()
    print("Launch it with the Desktop shortcut, from the Start Menu,")
    print("or by double-clicking MultiTerm.bat in " + ROOT)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
