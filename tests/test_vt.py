"""Unit tests for the VT parser / screen buffer. Run: python tests\\test_vt.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multiterm.vt import F_BOLD, F_REVERSE, Screen   # noqa: E402

FAILED = []


def check(name, got, want):
    if got != want:
        FAILED.append("%s\n   got:  %r\n   want: %r" % (name, got, want))
        print("FAIL  " + name)
    else:
        print("ok    " + name)


def line(s, y):
    return "".join(s.chars[y]).rstrip()


def t_basic():
    s = Screen(20, 4)
    s.feed("hello")
    check("plain text", line(s, 0), "hello")
    check("cursor x", s.x, 5)


def t_crlf():
    s = Screen(20, 4)
    s.feed("one\r\ntwo\r\n")
    check("crlf line 0", line(s, 0), "one")
    check("crlf line 1", line(s, 1), "two")
    check("crlf cursor", (s.x, s.y), (0, 2))


def t_wrap():
    s = Screen(5, 3)
    s.feed("abcdefgh")
    check("wrap row0", line(s, 0), "abcde")
    check("wrap row1", line(s, 1), "fgh")


def t_no_wrap_at_edge():
    s = Screen(5, 3)
    s.feed("abcde")
    check("deferred wrap keeps row", (line(s, 0), s.y), ("abcde", 0))


def t_cup_and_erase():
    s = Screen(10, 3)
    s.feed("xxxxxxxxxx\r\nyyyyyyyyyy")
    s.feed("\x1b[1;1H")
    check("CUP home", (s.x, s.y), (0, 0))
    s.feed("\x1b[2J")
    check("ED 2 clears", (line(s, 0), line(s, 1)), ("", ""))


def t_el():
    s = Screen(10, 2)
    s.feed("abcdefghij\x1b[1;4H\x1b[K")
    check("EL 0", line(s, 0), "abc")


def t_sgr():
    s = Screen(10, 2)
    s.feed("\x1b[1;31mR\x1b[0mn")
    fg, bg, flags = s.attrs[0][0]
    check("sgr fg", fg, 1)
    check("sgr bold", bool(flags & F_BOLD), True)
    check("sgr reset", s.attrs[0][1], (None, None, 0))


def t_sgr_256_and_rgb():
    s = Screen(10, 2)
    s.feed("\x1b[38;5;200mA\x1b[48;2;10;20;30mB")
    check("256 colour fg", s.attrs[0][0][0], 200)
    check("truecolor bg", s.attrs[0][1][1], (10, 20, 30))


def t_reverse():
    s = Screen(5, 2)
    s.feed("\x1b[7mZ")
    check("reverse flag", bool(s.attrs[0][0][2] & F_REVERSE), True)


def t_scroll_and_scrollback():
    s = Screen(6, 2)
    s.feed("a\r\nb\r\nc")
    check("scrolled view", (line(s, 0), line(s, 1)), ("b", "c"))
    check("scrollback kept", "".join(s.scrollback[0][0]).rstrip(), "a")


def t_scroll_region():
    s = Screen(6, 4)
    s.feed("1\r\n2\r\n3\r\n4")
    s.feed("\x1b[2;3r")           # region = rows 2..3
    s.feed("\x1b[3;1H\ny")        # index at bottom of region -> scroll region
    check("region scrolled", [line(s, i) for i in range(4)], ["1", "3", "y", "4"])


def t_insert_delete_line():
    s = Screen(6, 3)
    s.feed("a\r\nb\r\nc\x1b[1;1H\x1b[L")
    check("IL", [line(s, i) for i in range(3)], ["", "a", "b"])
    s.feed("\x1b[M")
    check("DL", [line(s, i) for i in range(3)], ["a", "b", ""])


def t_ich_dch():
    s = Screen(8, 2)
    s.feed("abcdef\x1b[1;2H\x1b[2@")
    check("ICH", line(s, 0), "a  bcdef")
    s.feed("\x1b[2P")
    check("DCH", line(s, 0), "abcdef")


def t_backspace_overwrite():
    s = Screen(8, 2)
    s.feed("abc\b\bX")
    check("backspace", line(s, 0), "aXc")


def t_tab():
    s = Screen(20, 2)
    s.feed("a\tb")
    check("tab stop", line(s, 0), "a       b")


def t_alt_screen():
    s = Screen(8, 2)
    s.feed("main\r\n")
    s.feed("\x1b[?1049h")
    s.feed("alt")
    check("alt content", line(s, 0), "alt")
    s.feed("\x1b[?1049l")
    check("main restored", line(s, 0), "main")


def t_title_osc():
    s = Screen(8, 2)
    s.feed("\x1b]0;My Title\x07rest")
    check("osc title", s.title, "My Title")
    check("osc consumed", line(s, 0), "rest")


def t_osc_st_terminator():
    s = Screen(8, 2)
    s.feed("\x1b]2;T2\x1b\\ok")
    check("osc ST title", s.title, "T2")
    check("osc ST rest", line(s, 0), "ok")


def t_split_escape_across_chunks():
    s = Screen(10, 2)
    s.feed("\x1b[3")
    s.feed("1mX")
    check("split CSI", s.attrs[0][0][0], 1)
    s.feed("\x1b")
    s.feed("[0mY")
    check("split ESC", s.attrs[0][1], (None, None, 0))


def t_dsr_response():
    s = Screen(10, 4)
    out = []
    s.respond = out.append
    s.feed("\x1b[2;3H\x1b[6n")
    check("DSR report", out, ["\x1b[2;3R"])
    s.feed("\x1b[c")
    check("DA report", out[-1], "\x1b[?1;2c")


def t_resize_keeps_text():
    s = Screen(20, 5)
    s.feed("keep me")
    s.resize(40, 10)
    check("resize keeps text", line(s, 0), "keep me")
    s.resize(10, 3)
    check("shrink keeps text", line(s, 0), "keep me")


def t_conpty_handshake():
    """The exact prologue Windows ConPTY emits must not print garbage."""
    s = Screen(40, 5)
    s.respond = lambda d: None
    s.feed("\x1b[1t\x1b[c\x1b[?1004h\x1b[?9001h\x1b[?7l\x1b[?7h"
           "\x1b]0;C:\\Windows\\system32\\cmd.exe\x1b\\Microsoft Windows")
    check("conpty prologue clean", line(s, 0), "Microsoft Windows")
    check("conpty title", s.title, "C:\\Windows\\system32\\cmd.exe")


def t_wide_output_perf():
    s = Screen(120, 40)
    payload = ("\x1b[32mline of output with colour\x1b[0m\r\n" * 4000)
    s.feed(payload)
    check("bulk feed last line", line(s, 38), "line of output with colour")


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            fn()
    print()
    if FAILED:
        print("%d FAILED:" % len(FAILED))
        for f in FAILED:
            print(" - " + f)
        return 1
    print("all VT tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
