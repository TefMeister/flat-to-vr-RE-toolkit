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
MOUSEEVENTF_MOVE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0001, 0x0002, 0x0004
TURN_STEP_COUNTS = 10   # a camera turn is sent as moves of at most this many counts...
TURN_STEP_S = 0.012     # ...this far apart, so the game sees a smooth turn
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
    "numpadplus": (0x4E, False), "numpadminus": (0x4A, False), "numpadstar": (0x37, False),
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
    """First visible top-level window whose title contains `title_part` (case-insensitive), or None.
    A title starting with '=' must match exactly (case-insensitive): '=MANHUNT' is the game, not 'Manhunt launcher'."""
    exact = title_part.startswith("=")
    if exact:
        title_part = title_part[1:]
    found = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                t = buf.value.lower()
                if (t == title_part.lower()) if exact else (title_part.lower() in t):
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
    global _target
    _target = hwnd
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
        _sendinput(ALT_SCAN, False, False)
        _sendinput(ALT_SCAN, False, True)
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


# How keys reach the game. Most games read the keyboard as SendInput delivers it; some only read window
# messages, and SendInput never reaches them (Manhunt, 2026-09-11: W by SendInput did nothing straight after a
# posted W had walked). A route says which with "key_input": "sendinput" (default), "post" or "both".
KEY_MODE = "sendinput"
_target = None                     # the game window, set by focus(); posted keys go here
WM_KEYDOWN, WM_KEYUP, MAPVK_VSC_TO_VK_EX = 0x0100, 0x0101, 3


def _sendinput(scan, extended, up):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0) | (KEYEVENTF_KEYUP if up else 0)
    event = INPUT(type=INPUT_KEYBOARD, u=_U(ki=KEYBDINPUT(0, scan, flags, 0, None)))
    u.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))


def _post(scan, extended, up):
    if not _target:
        return
    vk = u.MapVirtualKeyW(scan | (0xE000 if extended else 0), MAPVK_VSC_TO_VK_EX) or u.MapVirtualKeyW(scan, 1)
    lparam = 1 | (scan << 16) | ((1 << 24) if extended else 0) | ((0xC0000000) if up else 0)
    u.PostMessageW(_target, WM_KEYUP if up else WM_KEYDOWN, vk, ctypes.c_long(lparam & 0xFFFFFFFF if lparam < 2**31 else lparam - 2**32))


def _send(scan, extended, up):
    if KEY_MODE in ("sendinput", "both"):
        _sendinput(scan, extended, up)
    if KEY_MODE in ("post", "both"):
        _post(scan, extended, up)


def click_button(dialog_title, button_text):
    """Press a button in an ordinary Windows dialog (a game's launcher 'Play' button) with BM_CLICK: no mouse,
    no focus needed. Returns True if the button was found."""
    dlg = find_window(dialog_title)
    if not dlg:
        return False
    found = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def cb(child, _):
        # ANSI dialogs (Manhunt's launcher) answer GetWindowTextW with only the first letter ('P' for Play),
        # so read both ways and accept either
        wbuf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(child, wbuf, 256)
        abuf = ctypes.create_string_buffer(256)
        u.GetWindowTextA(child, abuf, 256)
        names = {wbuf.value, abuf.value.decode("mbcs", "replace")}
        if any(n.replace("&", "").strip().lower() == button_text.lower() for n in names):
            found.append(child)
        return True

    u.EnumChildWindows(dlg, cb, 0)
    if not found:
        return False
    u.SendMessageW(found[0], 0x00F5, 0, 0)          # BM_CLICK
    return True


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


def hold(names, seconds, hwnd):
    """Hold several keys down together for `seconds` (walk forward, drive and steer), then let go of all of
    them. Keys are released even if something goes wrong, so a key is never left stuck down."""
    codes = [KEYS[n.lower()] for n in names]
    if not focus(hwnd):
        raise NotInFront("the window is not in front; no key was held")
    try:
        for scan, extended in codes:
            _send(scan, extended, False)
            time.sleep(0.02)
        time.sleep(seconds)
    finally:
        for scan, extended in reversed(codes):
            _send(scan, extended, True)


def turn(hwnd, dx, dy):
    """Move the mouse by (dx, dy) counts, spread over small steps so the game sees a smooth turn rather than
    one jump. How far a count turns the camera depends on the game and its sensitivity setting."""
    if not focus(hwnd):
        raise NotInFront("the window is not in front; the mouse was not moved")
    steps = max(1, int(max(abs(dx), abs(dy)) / TURN_STEP_COUNTS))
    done_x = done_y = 0
    for k in range(1, steps + 1):
        tx, ty = round(dx * k / steps), round(dy * k / steps)
        event = INPUT(type=INPUT_MOUSE, u=_U(mi=MOUSEINPUT(tx - done_x, ty - done_y, 0, MOUSEEVENTF_MOVE, 0, None)))
        u.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        done_x, done_y = tx, ty
        time.sleep(TURN_STEP_S)


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount",
                                                  "OtherOperationCount", "ReadTransferCount",
                                                  "WriteTransferCount", "OtherTransferCount")]


def bytes_read(hwnd):
    """Total bytes the window's process has read so far (disk and other I/O), or None if Windows won't say.
    Two readings a few seconds apart give a read rate; loading screens read hard."""
    kernel32 = ctypes.windll.kernel32
    pid = w.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    kernel32.OpenProcess.restype = w.HANDLE
    handle = kernel32.OpenProcess(0x1000, False, pid.value)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        counters = IO_COUNTERS()
        ok = kernel32.GetProcessIoCounters(handle, ctypes.byref(counters))
        return counters.ReadTransferCount if ok else None
    finally:
        kernel32.CloseHandle(handle)


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
