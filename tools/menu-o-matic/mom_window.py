"""Menu-o-matiC: the window side - find a game window, capture it, press keys.

Windows only. Plain ctypes + Pillow. Same primitives as `tools/game-harness.py`, which were verified live on
several games: BitBlt from the SCREEN (never PrintWindow, which serves stale frames while a game is paused or
loading) and keyboard SCANCODES with the extended flag on arrow keys (without it, Down is numpad-2 and the game
silently ignores it).
"""
import ctypes
import ctypes.wintypes as w
import time

u, g = ctypes.windll.user32, ctypes.windll.gdi32

# ---- Settings ----------------------------------------------------------------
FOCUS_SETTLE_S = 0.30   # after bringing the window to the front
KEY_HOLD_S = 0.15       # how long a tapped key stays down. 0.07 s was missed by Burnout Paradise running
                        # slowly with a logging proxy (2026-09-28): a game that reads keys once a frame
                        # can miss a press shorter than one frame
SRCCOPY = 0x00CC0020
SW_RESTORE = 9
ALT_SCAN = 0x38
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x0001, 0x0002, 0x0008

# Scancodes. The second value marks EXTENDED keys; get it wrong and the key silently does nothing.
KEYS = {
    "esc": (0x01, False), "enter": (0x1C, False), "space": (0x39, False), "tab": (0x0F, False),
    "backspace": (0x0E, False), "tilde": (0x29, False),
    "up": (0x48, True), "down": (0x50, True), "left": (0x4B, True), "right": (0x4D, True),
    "home": (0x47, True), "end": (0x4F, True), "pageup": (0x49, True), "pagedown": (0x51, True),
    "lshift": (0x2A, False), "lctrl": (0x1D, False), "lalt": (0x38, False),
    "numpad0": (0x52, False), "numpad1": (0x4F, False), "numpad2": (0x50, False),
    "numpad3": (0x51, False), "numpad4": (0x4B, False), "numpad5": (0x4C, False),
    "numpad6": (0x4D, False), "numpad7": (0x47, False), "numpad8": (0x48, False), "numpad9": (0x49, False),
    "f1": (0x3B, False), "f2": (0x3C, False), "f3": (0x3D, False), "f4": (0x3E, False),
    "f5": (0x3F, False), "f6": (0x40, False), "f7": (0x41, False), "f8": (0x42, False),
    "f9": (0x43, False), "f10": (0x44, False), "f11": (0x57, False), "f12": (0x58, False),
}
_LETTERS = "qwertyuiop asdfghjkl zxcvbnm"
_ROW_START = {0: 0x10, 1: 0x1E, 2: 0x2C}
for _row, _chars in enumerate(_LETTERS.split()):
    for _i, _ch in enumerate(_chars):
        KEYS.setdefault(_ch, (_ROW_START[_row] + _i, False))
for _i, _ch in enumerate("1234567890"):
    KEYS.setdefault(_ch, (0x02 + _i, False))


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _U)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
                ("biSizeImage", w.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", w.DWORD), ("biClrImportant", w.DWORD)]


def find_window(title_part):
    """First visible top-level window whose title contains `title_part` (case-insensitive), or None."""
    found = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                if title_part.lower() in buf.value.lower():
                    found.append(hwnd)
        return True

    u.EnumWindows(cb, 0)
    return found[0] if found else None


def wait_window(title_part, timeout_s):
    """Poll for the window; returns its handle or None after `timeout_s`."""
    end = time.time() + timeout_s
    while time.time() < end:
        hwnd = find_window(title_part)
        if hwnd:
            return hwnd
        time.sleep(1.0)
    return None


def focus(hwnd):
    """Bring the window to the front. Returns True only if it really IS in front afterwards.

    Synthetic keys go to whatever window is in front, so this must succeed before any key is sent. Windows
    refuses SetForegroundWindow from a background process in many cases (the "foreground lock"); on
    2026-09-28 a plain SetForegroundWindow failed and a key went to a browser instead. So: restore if
    minimised, attach to the current foreground thread's input, and as a last resort tap Alt (which lifts the
    lock) before asking again."""
    if u.GetForegroundWindow() == hwnd:
        u.SetActiveWindow(hwnd)   # some games only take keys when their window is also ACTIVE
        return True
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, SW_RESTORE)
    fg = u.GetForegroundWindow()
    me = ctypes.windll.kernel32.GetCurrentThreadId()
    other = u.GetWindowThreadProcessId(fg, None) if fg else 0
    if other and other != me:
        u.AttachThreadInput(me, other, True)
    u.BringWindowToTop(hwnd)
    u.SetForegroundWindow(hwnd)
    if other and other != me:
        u.AttachThreadInput(me, other, False)
    time.sleep(FOCUS_SETTLE_S)
    if u.GetForegroundWindow() != hwnd:
        _send(ALT_SCAN, False, False)
        _send(ALT_SCAN, False, True)
        u.SetForegroundWindow(hwnd)
        time.sleep(FOCUS_SETTLE_S)
    return u.GetForegroundWindow() == hwnd


def client_size(hwnd):
    r = RECT()
    u.GetClientRect(hwnd, ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


def capture(hwnd):
    """The window's client area as it is on screen (BitBlt). Returns a Pillow RGB image.

    BitBlt reads the SCREEN, so a covered window would give a picture of whatever covers it. The window is
    brought to the front first, and NotInFront is raised if that fails, rather than returning a wrong picture."""
    from PIL import Image
    if not focus(hwnd):
        raise NotInFront("the window is not in front; a capture would show another window")
    width, height = client_size(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("the window has no client area (minimised?)")
    pt = w.POINT(0, 0)
    u.ClientToScreen(hwnd, ctypes.byref(pt))
    hdc = u.GetDC(0)
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, width, height)
    g.SelectObject(mdc, bmp)
    g.BitBlt(mdc, 0, 0, width, height, hdc, pt.x, pt.y, SRCCOPY)
    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight = width, -height
    bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
    buf = ctypes.create_string_buffer(width * height * 4)
    g.GetDIBits(mdc, bmp, 0, height, buf, ctypes.byref(bi), 0)
    g.DeleteObject(bmp)
    g.DeleteDC(mdc)
    u.ReleaseDC(0, hdc)
    return Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB")


def _send(scan, extended, up):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0) | (KEYEVENTF_KEYUP if up else 0)
    event = INPUT(type=INPUT_KEYBOARD, u=_U(ki=KEYBDINPUT(0, scan, flags, 0, None)))
    u.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))


def is_open(hwnd):
    """False once the window is gone: the game closed or crashed."""
    return bool(u.IsWindow(hwnd)) and bool(u.IsWindowVisible(hwnd))


def is_hung(hwnd):
    """True while Windows considers the window 'Not Responding' (it has not handled messages for ~5 s)."""
    return bool(u.IsHungAppWindow(hwnd))


def click(hwnd, fx, fy, hold_s=KEY_HOLD_S):
    """Left-click at a point given as fractions of the window's client area. Only when the window is in front."""
    if not focus(hwnd):
        raise NotInFront("the window is not in front; no click was sent")
    width, height = client_size(hwnd)
    pt = w.POINT(int(fx * width), int(fy * height))
    u.ClientToScreen(hwnd, ctypes.byref(pt))
    u.SetCursorPos(pt.x, pt.y)
    time.sleep(0.05)
    for flag in (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP):
        event = INPUT(type=INPUT_MOUSE, u=_U(mi=MOUSEINPUT(0, 0, 0, flag, 0, None)))
        u.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        time.sleep(hold_s)


class NotInFront(RuntimeError):
    """The target window could not be brought to the front, so no key was sent."""


def tap(name, hwnd, hold_s=KEY_HOLD_S):
    """Press and release one named key in window `hwnd`. Never sends a key unless `hwnd` is in front.

    Raises KeyError for an unknown name, NotInFront if the window cannot be brought to the front."""
    scan, extended = KEYS[name.lower()]
    if not focus(hwnd):
        raise NotInFront("the window is not in front; no key was sent")
    _send(scan, extended, False)
    time.sleep(hold_s)
    _send(scan, extended, True)
