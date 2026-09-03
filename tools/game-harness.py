"""
game-harness.py - drive a running game window: see it, key it, mouse it.

Built 2026-09-03 from primitives verified live against ENSLAVED (UE3/D3D9). The
per-game map of menus/routes/hazards belongs in `ai-game-control-profiles`; this
file is only the mechanism.

WHY BitBlt AND NOT PrintWindow  (the trap this file exists to avoid)
    PrintWindow(PW_RENDERFULLCONTENT) returns correct frames *while the game is
    rendering*, then silently keeps serving the last DWM-composited frame once the
    game stops presenting - paused, in a menu, mid-load - indefinitely and with no
    error. It is wrong exactly when the picture matters most. The tell is identical
    consecutive captures and a frame delta that repeats at a constant value.
    BitBlt from the screen DC reads what is actually on screen. It requires the
    window to be unoccluded, which is a real cost, but it never lies.
    `tools/capture-window.ps1` still uses PrintWindow; prefer this.

WHY SCANCODES, AND WHY ARROWS NEED -Extended
    Scancodes keep keyboard layout out of the path (doom-2016-vr lost a session to
    that). Arrow keys are EXTENDED keys: without KEYEVENTF_EXTENDEDKEY, scan 0x50 is
    numpad-2, the game ignores it, and NOTHING ERRORS - it reads as "this game
    ignores the keyboard". `tools/send-key.ps1` documents the same rule.

Usage:
    python game-harness.py <window-substring> shot out.png
    python game-harness.py <window-substring> key enter
    python game-harness.py <window-substring> key down --repeat 3
    python game-harness.py <window-substring> mouse 40 0 --repeat 120
    python game-harness.py <window-substring> watch 6 0.4      # is it rendering?
"""
import ctypes, ctypes.wintypes as w, time, sys, os

u, g = ctypes.windll.user32, ctypes.windll.gdi32
SRCCOPY = 0x00CC0020
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x0001, 0x0002, 0x0008
MOUSEEVENTF_MOVE = 0x0001

# Scancodes. `ext` marks the EXTENDED keys - get this wrong and the key silently does nothing.
KEYS = {
    "esc": (0x01, False), "enter": (0x1C, False), "space": (0x39, False), "tab": (0x0F, False),
    "tilde": (0x29, False), "backspace": (0x0E, False),
    "up": (0x48, True), "down": (0x50, True), "left": (0x4B, True), "right": (0x4D, True),
    "w": (0x11, False), "a": (0x1E, False), "s": (0x1F, False), "d": (0x20, False),
    "q": (0x10, False), "e": (0x12, False), "c": (0x2E, False), "f": (0x21, False),
    "lshift": (0x2A, False), "lalt": (0x38, False), "lctrl": (0x1D, False),
    "end": (0x4F, True), "pagedown": (0x51, True), "home": (0x47, True),
    "f1": (0x3B, False), "f2": (0x3C, False), "f3": (0x3D, False), "f4": (0x3E, False),
    "f5": (0x3F, False), "f6": (0x40, False), "f7": (0x41, False), "f8": (0x42, False),
    "f9": (0x43, False), "f10": (0x44, False), "f11": (0x57, False), "f12": (0x58, False),
    # NUMPAD keys - NON-extended, which is the whole point. The same scancode with
    # the extended flag is the navigation-cluster key instead (0x50 extended = Down
    # arrow, 0x50 plain = numpad-2). Probes that read GetAsyncKeyState often accept
    # EITHER the numpad VK or the navigation VK precisely so NumLock cannot break
    # them (mad-max-vr's cbfp does), in which case these work whatever NumLock is set to.
    "numpad0": (0x52, False), "numpad1": (0x4F, False), "numpad2": (0x50, False),
    "numpad3": (0x51, False), "numpad4": (0x4B, False), "numpad5": (0x4C, False),
    "numpad6": (0x4D, False), "numpad7": (0x47, False), "numpad8": (0x48, False),
    "numpad9": (0x49, False),
}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _I(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _I)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
                ("biSizeImage", w.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", w.DWORD), ("biClrImportant", w.DWORD)]


def find_window(substr):
    out = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, b, n + 1)
                if substr.lower() in b.value.lower():
                    out.append((hwnd, b.value))
        return True

    u.EnumWindows(cb, 0)
    if not out:
        raise SystemExit("no visible window matching %r" % substr)
    return out[0]


def focus(hwnd, settle=0.40):
    """Synthetic input follows FOCUS, and many of these games stop ticking unfocused."""
    u.SetForegroundWindow(hwnd)
    u.SetActiveWindow(hwnd)
    time.sleep(settle)
    return u.GetForegroundWindow() == hwnd


def grab(hwnd):
    """BitBlt the window's CLIENT area from the screen. Returns a PIL Image."""
    from PIL import Image
    r = RECT()
    u.GetClientRect(hwnd, ctypes.byref(r))
    width, height = r.right - r.left, r.bottom - r.top
    if width <= 0 or height <= 0:
        raise SystemExit("window has no client area (minimised?)")
    pt = w.POINT(0, 0)
    u.ClientToScreen(hwnd, ctypes.byref(pt))          # client origin, so the title bar is excluded
    hdc = u.GetDC(0)
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, width, height)
    g.SelectObject(mdc, bmp)
    g.BitBlt(mdc, 0, 0, width, height, hdc, pt.x, pt.y, SRCCOPY)
    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight = width, -height           # negative height = top-down
    bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
    buf = ctypes.create_string_buffer(width * height * 4)
    g.GetDIBits(mdc, bmp, 0, height, buf, ctypes.byref(bi), 0)
    g.DeleteObject(bmp); g.DeleteDC(mdc); u.ReleaseDC(0, hdc)
    return Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB")


def _key(scan, ext, up):
    f = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if ext else 0) | (KEYEVENTF_KEYUP if up else 0)
    i = INPUT(type=INPUT_KEYBOARD, u=_I(ki=KEYBDINPUT(0, scan, f, 0, None)))
    u.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def tap(name, hold=0.07, settle=0.9):
    if name not in KEYS:
        raise SystemExit("unknown key %r; known: %s" % (name, ", ".join(sorted(KEYS))))
    scan, ext = KEYS[name]
    _key(scan, ext, False); time.sleep(hold); _key(scan, ext, True); time.sleep(settle)


def hold(name, seconds):
    scan, ext = KEYS[name]
    _key(scan, ext, False); time.sleep(seconds); _key(scan, ext, True); time.sleep(0.25)


def mouse(dx, dy, repeat=1, gap=0.012):
    for _ in range(repeat):
        i = INPUT(type=INPUT_MOUSE, u=_I(mi=MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, None)))
        u.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))
        time.sleep(gap)


def delta(a, b):
    from PIL import ImageChops, ImageStat
    return ImageStat.Stat(ImageChops.difference(a.convert("L"), b.convert("L"))).mean[0]


def watch(hwnd, n=6, gap=0.4):
    """Is the game actually presenting? A flat 0.00 means paused / not rendering."""
    a = grab(hwnd); ds = []
    for _ in range(n):
        time.sleep(gap); b = grab(hwnd); ds.append(delta(a, b)); a = b
    return ds


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    hwnd, title = find_window(sys.argv[1])
    cmd, rest = sys.argv[2], sys.argv[3:]
    focus(hwnd)
    if cmd == "shot":
        out = rest[0] if rest else "shot.png"
        grab(hwnd).save(out); print("saved", out)
    elif cmd == "key":
        rep = int(rest[rest.index("--repeat") + 1]) if "--repeat" in rest else 1
        for _ in range(rep):
            tap(rest[0])
        print("tapped %s x%d" % (rest[0], rep))
    elif cmd == "hold":
        hold(rest[0], float(rest[1])); print("held %s for %ss" % (rest[0], rest[1]))
    elif cmd == "mouse":
        rep = int(rest[rest.index("--repeat") + 1]) if "--repeat" in rest else 1
        mouse(int(rest[0]), int(rest[1]), rep); print("moved mouse %sx" % rep)
    elif cmd == "watch":
        n = int(rest[0]) if rest else 6
        gap = float(rest[1]) if len(rest) > 1 else 0.4
        ds = watch(hwnd, n, gap)
        print("deltas:", ["%.2f" % x for x in ds],
              "->", "RENDERING" if max(ds) > 1.0 else "STATIC / PAUSED / NOT PRESENTING")
    else:
        raise SystemExit("unknown command %r" % cmd)
