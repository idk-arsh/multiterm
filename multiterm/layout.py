"""Split-tree pane layout.

A tab holds a binary tree: leaves are panes, internal nodes are splits with a
direction and a ratio. Dragging a divider changes a ratio, so panes can be
reshaped freely instead of snapping to a fixed grid.
"""

from . import ui

SASH = 10           # design pixels; apply_scale() adjusts for the display
MIN_SIDE = 90       # smallest pane edge we allow while dragging


def apply_scale():
    global SASH, MIN_SIDE
    SASH = ui.px(10)
    MIN_SIDE = ui.px(90)


class Split:
    __slots__ = ("dir", "ratio", "a", "b")

    def __init__(self, direction, a, b, ratio=0.5):
        self.dir = direction          # "h": side by side, "v": stacked
        self.ratio = ratio
        self.a = a
        self.b = b


def leaves(node, out=None):
    out = [] if out is None else out
    if node is None:
        return out
    if isinstance(node, Split):
        leaves(node.a, out)
        leaves(node.b, out)
    else:
        out.append(node)
    return out


def find_parent(node, target):
    """Return (parent_split, 'a' | 'b') for target, or (None, None)."""
    if not isinstance(node, Split):
        return None, None
    if node.a is target:
        return node, "a"
    if node.b is target:
        return node, "b"
    for child in (node.a, node.b):
        p, side = find_parent(child, target)
        if p:
            return p, side
    return None, None


def split_leaf(root, target, new_leaf, direction, ratio=0.5):
    """Replace `target` with a split holding target and new_leaf."""
    node = Split(direction, target, new_leaf, ratio)
    if root is target:
        return node
    parent, side = find_parent(root, target)
    if parent is None:
        return root
    setattr(parent, side, node)
    return root


def remove_leaf(root, target):
    """Drop a leaf; its sibling takes the split's place."""
    if root is target:
        return None
    parent, side = find_parent(root, target)
    if parent is None:
        return root
    sibling = parent.b if side == "a" else parent.a
    if root is parent:
        return sibling
    gp, gside = find_parent(root, parent)
    if gp is None:
        return sibling
    setattr(gp, gside, sibling)
    return root


def build_grid(panes, rows, cols):
    """Balanced tree arranging panes into rows x cols, row-major."""
    panes = list(panes)
    if not panes:
        return None
    if len(panes) == 1:
        return panes[0]
    row_nodes = []
    i = 0
    for _r in range(rows):
        row = panes[i:i + cols]
        i += cols
        if not row:
            break
        row_nodes.append(_chain(row, "h"))
    return _chain(row_nodes, "v")


def _chain(items, direction):
    """Left-leaning chain so ratios stay meaningful as panes are added."""
    if not items:
        return None
    node = items[0]
    for k, item in enumerate(items[1:], start=2):
        node = Split(direction, node, item, (k - 1) / float(k))
    return node


def place(node, x, y, w, h, panes_out, sashes_out):
    """Walk the tree, collecting pixel rectangles for panes and dividers."""
    if node is None:
        return
    if not isinstance(node, Split):
        panes_out.append((node, int(x), int(y), max(1, int(w)), max(1, int(h))))
        return
    if node.dir == "h":
        avail = max(0, w - SASH)
        a = avail * node.ratio
        place(node.a, x, y, a, h, panes_out, sashes_out)
        sashes_out.append((node, int(x + a), int(y), SASH, max(1, int(h)),
                           "h", (x, y, w, h)))
        place(node.b, x + a + SASH, y, avail - a, h, panes_out, sashes_out)
    else:
        avail = max(0, h - SASH)
        a = avail * node.ratio
        place(node.a, x, y, w, a, panes_out, sashes_out)
        sashes_out.append((node, int(x), int(y + a), max(1, int(w)), SASH,
                           "v", (x, y, w, h)))
        place(node.b, x, y + a + SASH, w, avail - a, panes_out, sashes_out)


def ratio_from_drag(node, rect, px, py):
    """New ratio for a divider dragged to (px, py) inside its own rect."""
    x, y, w, h = rect
    if node.dir == "h":
        avail = max(1.0, w - SASH)
        r = (px - x) / avail
        lo = MIN_SIDE / avail
    else:
        avail = max(1.0, h - SASH)
        r = (py - y) / avail
        lo = MIN_SIDE / avail
    lo = min(0.45, lo)
    return max(lo, min(1.0 - lo, r))
