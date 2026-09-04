"""Workspaces: a named project root plus the folders you work in inside it.

Opening a workspace spins up one terminal per folder; clicking a single folder
opens just that one. Everything is persisted to %APPDATA%\\MultiTerm.
"""
import json
import os

STORE_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                         "MultiTerm")
STORE_FILE = os.path.join(STORE_DIR, "workspaces.json")

SKIP_DIRS = {".git", ".svn", "node_modules", "__pycache__", ".venv", "venv",
             ".idea", ".vscode", "dist", "build", ".mypy_cache", ".pytest_cache",
             "obj", "bin", ".next", ".cache"}


class Workspace:
    def __init__(self, name, root, folders=None, expanded=True, shell=None,
                 layout="Auto", commands=None, pinned=False):
        self.name = name
        self.pinned = bool(pinned)
        self.root = os.path.abspath(root) if root else ""
        self.folders = list(folders) if folders else []
        self.expanded = expanded
        self.shell = shell
        self.layout = layout
        # folder path -> command to run when the workspace opens. This is the
        # difference between a pile of shells and a project that starts itself.
        self.commands = dict(commands or {})

    @staticmethod
    def _key(path):
        return os.path.normcase(os.path.abspath(path))

    def command_for(self, path):
        return self.commands.get(self._key(path), "")

    def set_command(self, path, command):
        key = self._key(path)
        if command and command.strip():
            self.commands[key] = command.strip()
        else:
            self.commands.pop(key, None)

    # ------------------------------------------------------------- contents
    def scan(self, limit=40):
        """Immediate sub-directories of the root, minus the usual noise."""
        found = []
        try:
            with os.scandir(self.root) as it:
                for e in it:
                    if len(found) >= limit:
                        break
                    if not e.is_dir() or e.name.startswith(".")                             or e.name in SKIP_DIRS:
                        continue
                    try:
                        attrs = e.stat(follow_symlinks=False).st_file_attributes
                    except (OSError, AttributeError):
                        attrs = 0
                    if attrs & 0x6:            # FILE_ATTRIBUTE_HIDDEN | SYSTEM
                        continue
                    found.append(e.path)
        except OSError:
            return []
        return sorted(found, key=lambda p: os.path.basename(p).lower())

    def entries(self):
        """Pinned folders first, then discovered ones (deduplicated)."""
        seen = set()
        out = []
        for p in self.folders + self.scan():
            key = os.path.normcase(os.path.abspath(p))
            if key in seen or not os.path.isdir(p):
                continue
            seen.add(key)
            out.append(p)
        return out

    def exists(self):
        return bool(self.root) and os.path.isdir(self.root)

    def to_dict(self):
        return {"name": self.name, "root": self.root, "folders": self.folders,
                "expanded": self.expanded, "shell": self.shell,
                "layout": self.layout, "commands": self.commands,
                "pinned": self.pinned}

    @staticmethod
    def from_dict(d):
        return Workspace(d.get("name") or os.path.basename(d.get("root", "")),
                         d.get("root", ""), d.get("folders"),
                         d.get("expanded", True), d.get("shell"),
                         d.get("layout", "Auto"), d.get("commands"),
                         d.get("pinned", False))


class WorkspaceStore:
    def __init__(self):
        self.items = []
        self.load()

    def load(self):
        try:
            with open(STORE_FILE, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh)
            self.items = [Workspace.from_dict(d) for d in data.get("workspaces", [])]
        except Exception:                              # noqa: BLE001
            self.items = []
        if not self.items:
            self.items = self._defaults()
        return self.items

    def save(self):
        try:
            os.makedirs(STORE_DIR, exist_ok=True)
            with open(STORE_FILE, "w", encoding="utf-8") as fh:
                json.dump({"workspaces": [w.to_dict() for w in self.items]},
                          fh, indent=2)
        except Exception:                              # noqa: BLE001
            pass

    def _defaults(self):
        home = os.path.expanduser("~")
        out = [Workspace("Home", home)]
        for name in ("source", "Projects", "repos", "dev", "code"):
            p = os.path.join(home, name)
            if os.path.isdir(p):
                out.append(Workspace(name, p))
        return out

    # ------------------------------------------------------------ mutation
    def add(self, root, name=None):
        root = os.path.abspath(root)
        for w in self.items:
            if os.path.normcase(w.root) == os.path.normcase(root):
                return w
        ws = Workspace(name or os.path.basename(root.rstrip("\\/")) or root, root)
        self.items.append(ws)
        self.save()
        return ws

    def remove(self, ws):
        if ws in self.items:
            self.items.remove(ws)
            self.save()

    def rename(self, ws, name):
        ws.name = name
        self.save()

    def set_pinned(self, ws, pinned):
        ws.pinned = bool(pinned)
        self.save()

    def pin_folder(self, ws, path):
        path = os.path.abspath(path)
        if path not in ws.folders:
            ws.folders.append(path)
            self.save()
