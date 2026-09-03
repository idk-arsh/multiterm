"""Display scaling.

Tk enlarges point-sized fonts on a high-DPI display but knows nothing about
the pixel constants the chrome is laid out with, so at 150 % the text grew
while the bars did not and labels were clipped.

We take control instead: Tk's own font scaling is pinned to the 96 dpi
baseline, and one factor - SCALE - is applied to *both* fonts and layout, so
the whole interface grows together and nothing is cut off.

    px(n)      layout pixels, scaled
    font_px(p) font size for tkinter (negative = pixels, so Tk leaves it alone)

Set MULTITERM_UI_SCALE to force a factor (used by the tests to reproduce a
high-DPI display on a normal one).
"""
import os

BASE_SCALING = 1.3333333      # Tk's pixels-per-point at 96 dpi
PT_TO_PX = 1.3333333          # a "point" at that baseline

SCALE = 1.0


def init(root):
    """Work out the display scale and stop Tk from double-applying it."""
    global SCALE
    override = os.environ.get("MULTITERM_UI_SCALE")
    if override:
        try:
            SCALE = max(0.75, min(4.0, float(override)))
        except ValueError:
            SCALE = 1.0
    else:
        try:
            reported = float(root.tk.call("tk", "scaling"))
        except Exception:                              # noqa: BLE001
            reported = BASE_SCALING
        SCALE = max(1.0, min(4.0, reported / BASE_SCALING))
    try:
        # fonts are sized in pixels from here on, so keep Tk out of it
        root.tk.call("tk", "scaling", BASE_SCALING)
    except Exception:                                  # noqa: BLE001
        pass
    return SCALE


def px(n):
    """A design pixel, scaled for this display."""
    return int(round(n * SCALE))


def fpx(n):
    """Same, but keeps the fraction - for canvas coordinates."""
    return n * SCALE


def font_px(points):
    """Font size in pixels (negative), scaled. Tk never touches these."""
    return -max(6, int(round(points * PT_TO_PX * SCALE)))
