"""VT100 / xterm compatible screen buffer and escape sequence parser.

Pure logic, no GUI. The renderer reads `chars`/`attrs` and `dirty`.
"""
import re
from collections import deque

# --- attribute flags -------------------------------------------------------
F_BOLD = 1
F_DIM = 2
F_ITALIC = 4
F_UNDER = 8
F_BLINK = 16
F_REVERSE = 32
F_HIDDEN = 64
F_STRIKE = 128

# attr = (fg, bg, flags); fg/bg is None (default), int 0..255, or (r, g, b)
DEF_ATTR = (None, None, 0)

_TEXT_RE = re.compile(r"[^\x00-\x1f\x7f\x9b]+")

# parser states
_GROUND, _ESC, _CSI, _OSC, _STR, _CHARSET = range(6)


class Screen:
    def __init__(self, cols=80, rows=24, scrollback=5000):
        self.cols = max(2, cols)
        self.rows = max(1, rows)
        self.scrollback = deque(maxlen=scrollback)
        self.title = ""
        self.respond = None          # callback(str) -> send back to the pty
        self.on_bell = None
        self.dirty = set()
        self.full_dirty = True
        self._reset(hard=True)

    # ------------------------------------------------------------------ init
    def _blank_row(self):
        return ([" "] * self.cols, [DEF_ATTR] * self.cols)

    def _new_grid(self):
        chars, attrs = [], []
        for _ in range(self.rows):
            c, a = self._blank_row()
            chars.append(c)
            attrs.append(a)
        return chars, attrs

    def _reset(self, hard=False):
        self.chars, self.attrs = self._new_grid()
        self.alt_chars = None
        self.main_chars = self.main_attrs = None
        self.main_cursor = (0, 0)
        self.in_alt = False
        self.x = self.y = 0
        self.saved = None
        self.cur_attr = DEF_ATTR
        self.top, self.bottom = 0, self.rows - 1
        self.autowrap = True
        self.pending_wrap = False
        self.insert_mode = False
        self.origin_mode = False
        self.cursor_visible = True
        self.app_cursor_keys = False
        self.app_keypad = False
        self.bracketed_paste = False
        self.mouse_mode = 0
        self.tabstops = set(range(8, self.cols, 8))
        self.state = _GROUND
        self.params = ""
        self.intermediate = ""
        self.osc = ""
        if hard:
            self.scrollback.clear()
        self.full_dirty = True

    # --------------------------------------------------------------- resizing
    def resize(self, cols, rows):
        cols = max(2, cols)
        rows = max(1, rows)
        if cols == self.cols and rows == self.rows:
            return
        old_chars, old_attrs = self.chars, self.attrs
        old_rows = self.rows
        self.cols, self.rows = cols, rows

        # keep the bottom of the screen anchored (like a real terminal)
        first = 0
        if old_rows > rows:
            first = min(old_rows - rows, max(0, self.y - rows + 1))
            if not self.in_alt:
                for i in range(first):
                    self.scrollback.append((old_chars[i], old_attrs[i]))
        self.chars, self.attrs = self._new_grid()
        for i in range(min(rows, old_rows - first)):
            src_c, src_a = old_chars[first + i], old_attrs[first + i]
            n = min(cols, len(src_c))
            self.chars[i][:n] = src_c[:n]
            self.attrs[i][:n] = src_a[:n]
        if self.alt_chars is not None:
            self.alt_chars = None
            self.in_alt = False
        self.y = max(0, min(rows - 1, self.y - first))
        self.x = max(0, min(cols - 1, self.x))
        self.top, self.bottom = 0, rows - 1
        self.tabstops = set(range(8, cols, 8))
        self.pending_wrap = False
        self.full_dirty = True

    # --------------------------------------------------------------- feeding
    def feed(self, text):
        i = 0
        n = len(text)
        while i < n:
            st = self.state
            if st == _GROUND:
                m = _TEXT_RE.match(text, i)
                if m:
                    self._put(m.group())
                    i = m.end()
                    continue
                self._control(text[i])
                i += 1
            elif st == _ESC:
                i = self._feed_esc(text, i)
            elif st == _CSI:
                i = self._feed_csi(text, i)
            elif st in (_OSC, _STR):
                new_i = self._feed_string(text, i)
                if new_i == i:
                    break
                i = new_i
            elif st == _CHARSET:
                self.state = _GROUND
                i += 1

    # ------------------------------------------------------------ text output
    def _put(self, s):
        attr = self.cur_attr
        cols = self.cols
        dirty = self.dirty
        for ch in s:
            if self.pending_wrap:
                if self.autowrap:
                    self.x = 0
                    self._index()
                else:
                    self.x = cols - 1
                self.pending_wrap = False
            chars, attrs = self.chars, self.attrs
            if self.insert_mode:
                row_c, row_a = chars[self.y], attrs[self.y]
                row_c.insert(self.x, " ")
                row_a.insert(self.x, attr)
                del row_c[cols:]
                del row_a[cols:]
            chars[self.y][self.x] = ch
            attrs[self.y][self.x] = attr
            dirty.add(self.y)
            if self.x + 1 >= cols:
                self.pending_wrap = True
            else:
                self.x += 1

    def _control(self, ch):
        o = ord(ch)
        if ch == "\x1b":
            self.state = _ESC
            self.params = ""
            self.intermediate = ""
        elif ch == "\r":
            self.x = 0
            self.pending_wrap = False
            self.dirty.add(self.y)
        elif ch in ("\n", "\x0b", "\x0c"):
            self._index()
            self.pending_wrap = False
        elif ch == "\b":
            if self.pending_wrap:
                self.pending_wrap = False
            elif self.x > 0:
                self.x -= 1
            self.dirty.add(self.y)
        elif ch == "\t":
            self._tab(1)
        elif ch == "\x07":
            if self.on_bell:
                self.on_bell()
        elif o == 0x9B:  # 8-bit CSI
            self.state = _CSI
            self.params = ""
            self.intermediate = ""
        # everything else (NUL, SO, SI, ...) ignored

    # ------------------------------------------------------------- ESC / CSI
    def _feed_esc(self, text, i):
        ch = text[i]
        self.state = _GROUND
        if ch == "[":
            self.state = _CSI
            self.params = ""
            self.intermediate = ""
        elif ch == "]":
            self.state = _OSC
            self.osc = ""
        elif ch in "P^_X":          # DCS / PM / APC / SOS -> consume until ST
            self.state = _STR
            self.osc = ""
        elif ch in "()*+":
            self.state = _CHARSET
        elif ch == "7":
            self._save_cursor()
        elif ch == "8":
            self._restore_cursor()
        elif ch == "D":
            self._index()
        elif ch == "M":
            self._reverse_index()
        elif ch == "E":
            self.x = 0
            self._index()
        elif ch == "H":
            self.tabstops.add(self.x)
        elif ch == "c":
            self._reset(hard=True)
        elif ch == "=":
            self.app_keypad = True
        elif ch == ">":
            self.app_keypad = False
        return i + 1

    def _feed_csi(self, text, i):
        n = len(text)
        while i < n:
            ch = text[i]
            o = ord(ch)
            if 0x30 <= o <= 0x3F:          # parameter bytes
                self.params += ch
                i += 1
            elif 0x20 <= o <= 0x2F:        # intermediate bytes
                self.intermediate += ch
                i += 1
            elif 0x40 <= o <= 0x7E:        # final byte
                self.state = _GROUND
                self._csi(ch)
                return i + 1
            else:                          # embedded control char
                self._control(ch)
                if self.state != _CSI:
                    return i + 1
                i += 1
        return i

    def _feed_string(self, text, i):
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == "\x07":
                self._end_string()
                return i + 1
            if ch == "\x1b":
                if i + 1 < n:
                    if text[i + 1] == "\\":
                        self._end_string()
                        return i + 2
                    self._end_string()
                    return i          # re-parse the ESC in ground state
                return i              # incomplete: wait for more input
            self.osc += ch
            i += 1
        return i

    def _end_string(self):
        if self.state == _OSC:
            data = self.osc
            code, _, val = data.partition(";")
            if code in ("0", "2"):
                self.title = val
        self.state = _GROUND
        self.osc = ""

    # ------------------------------------------------------------- CSI verbs
    def _nums(self):
        raw = self.params
        priv = raw[:1] if raw[:1] in "?<>=" else ""
        if priv:
            raw = raw[1:]
        out = []
        for p in raw.split(";"):
            p = p.split(":")[0]
            try:
                out.append(int(p))
            except ValueError:
                out.append(0)
        return priv, out

    def _csi(self, cmd):
        priv, nums = self._nums()
        a0 = nums[0] if nums else 0

        if cmd == "@":
            self._ich(max(1, a0))
        elif cmd == "A":
            self.y = max(0, self.y - max(1, a0))
            self.pending_wrap = False
            self.full_dirty = True
        elif cmd in ("B", "e"):
            self.y = min(self.rows - 1, self.y + max(1, a0))
            self.pending_wrap = False
            self.full_dirty = True
        elif cmd in ("C", "a"):
            self.x = min(self.cols - 1, self.x + max(1, a0))
            self.pending_wrap = False
        elif cmd == "D":
            self.x = max(0, self.x - max(1, a0))
            self.pending_wrap = False
        elif cmd == "E":
            self.y = min(self.rows - 1, self.y + max(1, a0))
            self.x = 0
        elif cmd == "F":
            self.y = max(0, self.y - max(1, a0))
            self.x = 0
        elif cmd in ("G", "`"):
            self.x = min(self.cols - 1, max(1, a0) - 1)
            self.pending_wrap = False
        elif cmd in ("H", "f"):
            row = nums[0] if len(nums) > 0 and nums[0] else 1
            col = nums[1] if len(nums) > 1 and nums[1] else 1
            if self.origin_mode:
                row += self.top
            self.y = max(0, min(self.rows - 1, row - 1))
            self.x = max(0, min(self.cols - 1, col - 1))
            self.pending_wrap = False
        elif cmd == "I":
            self._tab(max(1, a0))
        elif cmd == "J":
            self._erase_display(a0)
        elif cmd == "K":
            self._erase_line(a0)
        elif cmd == "L":
            self._insert_lines(max(1, a0))
        elif cmd == "M":
            self._delete_lines(max(1, a0))
        elif cmd == "P":
            self._dch(max(1, a0))
        elif cmd == "S":
            self._scroll_up(max(1, a0))
        elif cmd == "T":
            self._scroll_down(max(1, a0))
        elif cmd == "X":
            self._ech(max(1, a0))
        elif cmd == "Z":
            self._tab(-max(1, a0))
        elif cmd == "d":
            self.y = max(0, min(self.rows - 1, max(1, a0) - 1))
            self.pending_wrap = False
        elif cmd == "h":
            self._mode(priv, nums, True)
        elif cmd == "l":
            self._mode(priv, nums, False)
        elif cmd == "m":
            self._sgr(nums)
        elif cmd == "n":
            if self.respond:
                if a0 == 6:
                    self.respond("\x1b[%d;%dR" % (self.y + 1, self.x + 1))
                elif a0 == 5:
                    self.respond("\x1b[0n")
        elif cmd == "r":
            top = (nums[0] if len(nums) > 0 and nums[0] else 1) - 1
            bot = (nums[1] if len(nums) > 1 and nums[1] else self.rows) - 1
            if 0 <= top < bot < self.rows:
                self.top, self.bottom = top, bot
            else:
                self.top, self.bottom = 0, self.rows - 1
            self.x = 0
            self.y = self.top if self.origin_mode else 0
            self.full_dirty = True
        elif cmd == "s":
            self._save_cursor()
        elif cmd == "u":
            self._restore_cursor()
        elif cmd == "c":
            if self.respond:
                self.respond("\x1b[?1;2c")
        elif cmd == "g":
            if a0 == 3:
                self.tabstops.clear()
            else:
                self.tabstops.discard(self.x)
        # 't' (window ops) and anything unknown are ignored

    def _mode(self, priv, nums, on):
        for m in nums:
            if priv == "?":
                if m == 1:
                    self.app_cursor_keys = on
                elif m == 6:
                    self.origin_mode = on
                    self.x = 0
                    self.y = self.top if on else 0
                elif m == 7:
                    self.autowrap = on
                    self.pending_wrap = False
                elif m == 25:
                    self.cursor_visible = on
                elif m in (1000, 1002, 1003, 1006, 1015):
                    self.mouse_mode = m if on else 0
                elif m == 2004:
                    self.bracketed_paste = on
                elif m in (47, 1047, 1049):
                    self._switch_alt(on, save=(m == 1049))
            else:
                if m == 4:
                    self.insert_mode = on

    def _switch_alt(self, on, save=False):
        if on and not self.in_alt:
            self.main_chars, self.main_attrs = self.chars, self.attrs
            self.main_cursor = (self.x, self.y)
            self.chars, self.attrs = self._new_grid()
            self.alt_chars = self.chars
            self.in_alt = True
            if save:
                self.x = self.y = 0
        elif not on and self.in_alt:
            self.chars, self.attrs = self.main_chars, self.main_attrs
            self.alt_chars = None
            self.in_alt = False
            if save:
                self.x, self.y = self.main_cursor
            self.x = min(self.x, self.cols - 1)
            self.y = min(self.y, self.rows - 1)
        self.top, self.bottom = 0, self.rows - 1
        self.pending_wrap = False
        self.full_dirty = True

    def _sgr(self, nums):
        if not nums:
            nums = [0]
        fg, bg, flags = self.cur_attr
        i = 0
        while i < len(nums):
            n = nums[i]
            if n == 0:
                fg, bg, flags = None, None, 0
            elif n == 1:
                flags |= F_BOLD
            elif n == 2:
                flags |= F_DIM
            elif n == 3:
                flags |= F_ITALIC
            elif n == 4:
                flags |= F_UNDER
            elif n in (5, 6):
                flags |= F_BLINK
            elif n == 7:
                flags |= F_REVERSE
            elif n == 8:
                flags |= F_HIDDEN
            elif n == 9:
                flags |= F_STRIKE
            elif n == 22:
                flags &= ~(F_BOLD | F_DIM)
            elif n == 23:
                flags &= ~F_ITALIC
            elif n == 24:
                flags &= ~F_UNDER
            elif n == 25:
                flags &= ~F_BLINK
            elif n == 27:
                flags &= ~F_REVERSE
            elif n == 28:
                flags &= ~F_HIDDEN
            elif n == 29:
                flags &= ~F_STRIKE
            elif 30 <= n <= 37:
                fg = n - 30
            elif n == 39:
                fg = None
            elif 40 <= n <= 47:
                bg = n - 40
            elif n == 49:
                bg = None
            elif 90 <= n <= 97:
                fg = n - 90 + 8
            elif 100 <= n <= 107:
                bg = n - 100 + 8
            elif n in (38, 48):
                kind = nums[i + 1] if i + 1 < len(nums) else -1
                col = None
                if kind == 5 and i + 2 < len(nums):
                    col = nums[i + 2] & 0xFF
                    i += 2
                elif kind == 2 and i + 4 < len(nums):
                    col = (nums[i + 2] & 0xFF, nums[i + 3] & 0xFF, nums[i + 4] & 0xFF)
                    i += 4
                else:
                    i += 1
                if n == 38:
                    fg = col
                else:
                    bg = col
            i += 1
        self.cur_attr = (fg, bg, flags)

    # ----------------------------------------------------------- line editing
    def _erase_cells(self, y, x0, x1):
        row_c, row_a = self.chars[y], self.attrs[y]
        blank_attr = (None, self.cur_attr[1], 0)
        for x in range(max(0, x0), min(self.cols, x1)):
            row_c[x] = " "
            row_a[x] = blank_attr
        self.dirty.add(y)

    def _erase_display(self, mode):
        if mode == 0:
            self._erase_cells(self.y, self.x, self.cols)
            for y in range(self.y + 1, self.rows):
                self._erase_cells(y, 0, self.cols)
        elif mode == 1:
            self._erase_cells(self.y, 0, self.x + 1)
            for y in range(0, self.y):
                self._erase_cells(y, 0, self.cols)
        else:
            if mode == 3 and not self.in_alt:
                self.scrollback.clear()
            for y in range(self.rows):
                self._erase_cells(y, 0, self.cols)
        self.pending_wrap = False
        self.full_dirty = True

    def _erase_line(self, mode):
        if mode == 0:
            self._erase_cells(self.y, self.x, self.cols)
        elif mode == 1:
            self._erase_cells(self.y, 0, self.x + 1)
        else:
            self._erase_cells(self.y, 0, self.cols)
        self.pending_wrap = False

    def _ich(self, n):
        row_c, row_a = self.chars[self.y], self.attrs[self.y]
        for _ in range(min(n, self.cols - self.x)):
            row_c.insert(self.x, " ")
            row_a.insert(self.x, DEF_ATTR)
        del row_c[self.cols:]
        del row_a[self.cols:]
        self.dirty.add(self.y)

    def _dch(self, n):
        row_c, row_a = self.chars[self.y], self.attrs[self.y]
        for _ in range(min(n, self.cols - self.x)):
            del row_c[self.x]
            del row_a[self.x]
            row_c.append(" ")
            row_a.append(DEF_ATTR)
        self.dirty.add(self.y)

    def _ech(self, n):
        self._erase_cells(self.y, self.x, self.x + n)

    def _insert_lines(self, n):
        if not (self.top <= self.y <= self.bottom):
            return
        for _ in range(min(n, self.bottom - self.y + 1)):
            self.chars.pop(self.bottom)
            self.attrs.pop(self.bottom)
            c, a = self._blank_row()
            self.chars.insert(self.y, c)
            self.attrs.insert(self.y, a)
        self.full_dirty = True

    def _delete_lines(self, n):
        if not (self.top <= self.y <= self.bottom):
            return
        for _ in range(min(n, self.bottom - self.y + 1)):
            self.chars.pop(self.y)
            self.attrs.pop(self.y)
            c, a = self._blank_row()
            self.chars.insert(self.bottom, c)
            self.attrs.insert(self.bottom, a)
        self.full_dirty = True

    # -------------------------------------------------------------- scrolling
    def _scroll_up(self, n=1):
        for _ in range(n):
            row = (self.chars.pop(self.top), self.attrs.pop(self.top))
            if self.top == 0 and not self.in_alt:
                self.scrollback.append(row)
            c, a = self._blank_row()
            self.chars.insert(self.bottom, c)
            self.attrs.insert(self.bottom, a)
        self.full_dirty = True

    def _scroll_down(self, n=1):
        for _ in range(n):
            self.chars.pop(self.bottom)
            self.attrs.pop(self.bottom)
            c, a = self._blank_row()
            self.chars.insert(self.top, c)
            self.attrs.insert(self.top, a)
        self.full_dirty = True

    def _index(self):
        if self.y == self.bottom:
            self._scroll_up(1)
        elif self.y < self.rows - 1:
            self.y += 1
        self.dirty.add(self.y)

    def _reverse_index(self):
        if self.y == self.top:
            self._scroll_down(1)
        elif self.y > 0:
            self.y -= 1

    def _tab(self, n):
        if n > 0:
            for _ in range(n):
                stops = [t for t in self.tabstops if t > self.x]
                self.x = min(stops) if stops else self.cols - 1
        else:
            for _ in range(-n):
                stops = [t for t in self.tabstops if t < self.x]
                self.x = max(stops) if stops else 0
        self.pending_wrap = False

    def _save_cursor(self):
        self.saved = (self.x, self.y, self.cur_attr, self.origin_mode, self.autowrap)

    def _restore_cursor(self):
        if self.saved:
            self.x, self.y, self.cur_attr, self.origin_mode, self.autowrap = self.saved
            self.x = min(self.x, self.cols - 1)
            self.y = min(self.y, self.rows - 1)
        self.pending_wrap = False

    # ---------------------------------------------------------------- reading
    def total_lines(self):
        return len(self.scrollback) + self.rows

    def line(self, idx):
        """Row `idx` counted from the top of the scrollback."""
        sb = len(self.scrollback)
        if idx < sb:
            return self.scrollback[idx]
        i = idx - sb
        if 0 <= i < self.rows:
            return self.chars[i], self.attrs[i]
        return self._blank_row()

    def text(self, strip=True):
        out = []
        for y in range(self.rows):
            s = "".join(self.chars[y])
            out.append(s.rstrip() if strip else s)
        return "\n".join(out)

    def all_text(self):
        return "\n".join("".join(self.line(i)[0]).rstrip()
                         for i in range(self.total_lines()))
