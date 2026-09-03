"""Colour palettes, UI chrome colours and font selection."""
import tkinter.font as tkfont

# ---------------------------------------------------------------- terminal
ANSI_CAMPBELL = [
    "#0C0C0C", "#C50F1F", "#13A10E", "#C19C00",
    "#0037DA", "#881798", "#3A96DD", "#CCCCCC",
    "#767676", "#E74856", "#16C60C", "#F9F1A5",
    "#3B78FF", "#B4009E", "#61D6D6", "#F2F2F2",
]

THEMES = {
    "Graphite": {
        "bg": "#0E0E12", "fg": "#E3E3E8", "cursor": "#0A84FF",
        "sel": "#2C4A6E",
        "ansi": ["#16161A", "#FF6961", "#30D158", "#FFD60A",
                 "#0A84FF", "#BF5AF2", "#5AC8FA", "#D5D5DB",
                 "#5A5A61", "#FF8A80", "#5BE07A", "#FFE066",
                 "#64A9FF", "#D08BFF", "#8AE0FF", "#F5F5F7"],
    },
    "Campbell": {
        "bg": "#0C0C0C", "fg": "#CCCCCC", "cursor": "#CCCCCC",
        "sel": "#264F78", "ansi": ANSI_CAMPBELL,
    },
    "One Dark": {
        "bg": "#22262E", "fg": "#ABB2BF", "cursor": "#61AFEF",
        "sel": "#3E4451",
        "ansi": ["#282C34", "#E06C75", "#98C379", "#E5C07B",
                 "#61AFEF", "#C678DD", "#56B6C2", "#ABB2BF",
                 "#5C6370", "#E06C75", "#98C379", "#E5C07B",
                 "#61AFEF", "#C678DD", "#56B6C2", "#FFFFFF"],
    },
    "Solarized Dark": {
        "bg": "#002B36", "fg": "#93A1A1", "cursor": "#93A1A1",
        "sel": "#073642",
        "ansi": ["#073642", "#DC322F", "#859900", "#B58900",
                 "#268BD2", "#D33682", "#2AA198", "#EEE8D5",
                 "#586E75", "#CB4B16", "#93A1A1", "#657B83",
                 "#839496", "#6C71C4", "#B7C7C7", "#FDF6E3"],
    },
    "Paper (light)": {
        "bg": "#FBFBFD", "fg": "#25262B", "cursor": "#3B6FE0",
        "sel": "#CFE0FF",
        "ansi": ["#25262B", "#C5283D", "#0E7A3C", "#8A6400",
                 "#2B5FD9", "#8B2FA8", "#0F6C8C", "#5A5D68",
                 "#7C8091", "#E0455E", "#12A054", "#B08600",
                 "#4C82F0", "#B04BD0", "#1E93B8", "#111217"],
    },
}
DEFAULT_THEME = "Graphite"

# ------------------------------------------------------------------- chrome
UI = {
    "bg": "#131316",          # backdrop behind the panes
    "sidebar_top": "#1C1D22",
    "sidebar_bot": "#17181C",
    "chrome": "#1E1F25",      # title / tool bar
    "chrome_lo": "#191A1F",
    "panel": "#26272E",       # cards, tabs
    "raised": "#31323A",      # hover / elevated
    "sunken": "#131316",
    "border": "#3A3C45",
    "border_soft": "#26272E",
    "accent": "#0A84FF",      # macOS system blue
    "accent2": "#5E5CE6",     # macOS indigo
    "accent_dim": "#1D3A5C",
    "accent_glow": "#2A5A8C",
    "text": "#F2F2F7",
    "text_dim": "#D4D7DF",
    "muted": "#9AA1AE",
    "ok": "#30D158",
    "warn": "#FFD60A",
    "err": "#FF453A",
}

BADGES = {
    "Command Prompt": ("CMD", "#0A84FF"),
    "Windows PowerShell": ("PS", "#5AC8FA"),
    "PowerShell 7": ("PS7", "#5AC8FA"),
    "Git Bash": ("BASH", "#FFD60A"),
    "WSL": ("WSL", "#BF5AF2"),
    "Python REPL": ("PY", "#30D158"),
}


def badge_for(label):
    return BADGES.get(label, (label[:4].upper(), UI["muted"]))


def build_palette(theme_name=DEFAULT_THEME):
    """256-entry hex colour table for a theme."""
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    pal = list(t["ansi"])
    levels = (0, 95, 135, 175, 215, 255)
    for r in levels:
        for g in levels:
            for b in levels:
                pal.append("#%02X%02X%02X" % (r, g, b))
    for i in range(24):
        v = 8 + i * 10
        pal.append("#%02X%02X%02X" % (v, v, v))
    return pal


def get(theme_name):
    return THEMES.get(theme_name, THEMES[DEFAULT_THEME])


# -------------------------------------------------------------------- fonts
_MONO = ("Cascadia Mono", "Consolas", "Lucida Console", "Courier New")
_UI = ("Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI",
       "Tahoma")
_cache = {}


def _pick(candidates, fallback):
    key = candidates
    if key in _cache:
        return _cache[key]
    try:
        fams = set(tkfont.families())
    except Exception:                                  # noqa: BLE001
        fams = set()
    choice = next((c for c in candidates if c in fams), fallback)
    _cache[key] = choice
    return choice


def mono_family():
    return _pick(_MONO, "Consolas")


def ui_family():
    return _pick(_UI, "Segoe UI")


def mix(c1, c2, t):
    """Blend two #rrggbb colours; t=0 -> c1, t=1 -> c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(
        max(0, min(255, round(a[i] + (b[i] - a[i]) * t))) for i in range(3))
