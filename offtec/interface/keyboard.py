"""Byte-safe terminal key reader for CSI/SS3 arrows used by Termux and xterm."""
import os
import select
import sys
import time


ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}


def decode_escape(sequence):
    """Decode one complete ANSI escape sequence without assuming its length."""
    if sequence == b"\x1b":
        return "esc"
    if len(sequence) < 3 or sequence[0] != 0x1B:
        return None
    introducer = sequence[1:2]
    final = chr(sequence[-1])
    if introducer in (b"[", b"O"):
        if final == "Z" and introducer == b"[":
            return "shift_tab"
        return ARROWS.get(final)
    return None


def _read_byte(fd, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
        return b""
    try:
        return os.read(fd, 1)
    except OSError:
        return b""


def read_key(fd, escape_timeout=0.18):
    """Read a key from a raw TTY descriptor; never use buffered ``sys.stdin``."""
    first = os.read(fd, 1)
    if not first:
        return ""
    if first != b"\x1b":
        return {
            b"\x03": "ctrlc", b"\r": "enter", b"\n": "enter",
            b"\t": "tab", b"\x7f": "backspace", b"\x08": "backspace",
        }.get(first, first.decode("utf-8", errors="ignore"))

    deadline = time.monotonic() + escape_timeout
    second = _read_byte(fd, deadline)
    if not second:
        return "esc"
    if second == b"[":
        sequence = bytearray(b"\x1b[")
        while time.monotonic() < deadline:
            byte = _read_byte(fd, deadline)
            if not byte:
                break
            sequence.extend(byte)
            # ECMA-48 final bytes are in 0x40..0x7e; parameters may vary in length.
            if 0x40 <= byte[0] <= 0x7E:
                return decode_escape(bytes(sequence)) or "unknown"
        return "unknown"
    if second == b"O":
        third = _read_byte(fd, deadline)
        if not third:
            return "unknown"
        return decode_escape(b"\x1bO" + third) or "unknown"
    return "esc"


def keypress():
    """Read one terminal key and restore terminal attributes on every path."""
    if not sys.stdin.isatty():
        return "\n"
    import termios
    import tty

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return read_key(fd)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
