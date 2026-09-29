"""Menu-o-matiC / Move-o-matiC: record a person playing, so the machine can repeat it exactly.

While recording, every key the person presses in the game window is noted with its exact timing (down and up,
several keys at once, however long each is held). Two MARKER keys save a picture of the window at that moment, to
be turned into a checkpoint afterwards, and say what kind of screen it is (the player's own scheme, 2026-09-28;
moved off the numpad 2026-09-29, because our own mods put their hotkeys on the numpad):
    Page Up    "a key is needed here"   (a menu, a prompt: the next key the person presses gets past it)
    Page Down  "just wait here"         (a logo, a loading screen, a video: no key, it ends by itself)
    Home       undo the last marker     (pressed by mistake: its picture is dropped too)
    End        stop recording
Only the grey keys count (with NumLock off, the number pad sends the same keys; those are recorded as normal
keys). The four are kept away from the game while recording. Keys the tool itself sends are ignored, so a replay is never recorded by mistake.

The result goes into a route file as steps:
    {"play": [[0.0, "w", 1], [1.42, "w", 0], [0.10, "d", 1], ...]}   seconds since the previous event, key, 1 down / 0 up
    {"todo": "frames/03.png", "at": 12.8, "kind": "key"|"wait"}       a marker waiting to become a checkpoint
`mark-image` turns a todo into a real checkpoint (a region of that saved picture). Replays wait at checkpoints,
so a slow loading screen never throws the timing off: the clock starts again after every checkpoint.
Keyboard only for now; mouse movement is not recorded.
"""
import ctypes
import ctypes.wintypes as w
import os
import time

# ---- Settings ----------------------------------------------------------------
KEY_MARK_VK = 0x21   # Page Up    (VK_PRIOR)  "a key is needed here"
WAIT_MARK_VK = 0x22  # Page Down  (VK_NEXT)   "just wait here"
UNDO_VK = 0x24       # Home       (VK_HOME)   undo the last marker
STOP_VK = 0x23       # End        (VK_END)    stop recording
MARK_KIND = {KEY_MARK_VK: "key", WAIT_MARK_VK: "wait"}
CONTROL_VKS = (KEY_MARK_VK, WAIT_MARK_VK, UNDO_VK, STOP_VK)
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_QUIT, WM_APP = 0x0012, 0x8000
LLKHF_EXTENDED, LLKHF_INJECTED = 0x01, 0x10
# Testing only: also record keys sent by programs (normally ignored so a replay is never recorded)
INCLUDE_INJECTED = os.environ.get("MOM_RECORD_INJECTED") == "1"


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", w.DWORD), ("scanCode", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


def build_steps(events, frames):
    """Turn raw events into route steps. Pure logic, tested without a keyboard.

    events: list of (seconds, "key"|"marker", name, down) in time order; for a marker, name is its kind.
    frames: {marker index: picture path}.
    Keys still held at a marker are released there in the recording, so every chunk starts with nothing held."""
    steps, chunk, last_t, held, marker_no = [], [], None, set(), 0
    for t, kind, name, down in events:
        if kind == "key":
            if down and name in held or (not down and name not in held):
                continue                                  # auto-repeat, or an up without a down
            chunk.append([round(0.0 if last_t is None else t - last_t, 3), name, 1 if down else 0])
            (held.add if down else held.discard)(name)
            last_t = t
        else:
            for name_up in sorted(held):
                chunk.append([0.0, name_up, 0])
            held.clear()
            if chunk:
                steps.append({"play": chunk})
            steps.append({"todo": frames.get(marker_no, ""), "at": round(t, 2), "kind": name or "key"})
            # the next key keeps its real delay AFTER the marker: how long the person waited once the
            # screen was there (a replay starts that clock when the checkpoint matches)
            chunk, last_t, marker_no = [], t, marker_no + 1
    for name_up in sorted(held):
        chunk.append([0.0, name_up, 0])
    if chunk:
        steps.append({"play": chunk})
    return steps


def record(hwnd, frames_dir):
    """Record until End is pressed. Returns (events, frames)."""
    import mom_window as W
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    names = {v: k for k, v in W.KEYS.items()}            # (scan, extended) -> key name
    events, frames, start = [], {}, time.time()
    thread = kernel32.GetCurrentThreadId()
    pending_markers = []
    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, w.WPARAM, w.LPARAM)
    user32.CallNextHookEx.argtypes = [w.HHOOK, ctypes.c_int, w.WPARAM, w.LPARAM]
    user32.CallNextHookEx.restype = LRESULT
    # 64-bit Python: without these, the module handle and the hook handle are cut to 32 bits and
    # SetWindowsHookEx fails (it did, 2026-09-28)
    kernel32.GetModuleHandleW.argtypes = [w.LPCWSTR]
    kernel32.GetModuleHandleW.restype = w.HMODULE
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, w.HINSTANCE, w.DWORD]
    user32.SetWindowsHookExW.restype = w.HHOOK
    user32.UnhookWindowsHookEx.argtypes = [w.HHOOK]

    def proc(code, wparam, lparam):
        if code == 0:
            k = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
            if k.vkCode in CONTROL_VKS and k.flags & LLKHF_EXTENDED:   # the grey keys, not the number pad
                if down and k.vkCode in MARK_KIND:
                    pending_markers.append((time.time() - start, MARK_KIND[k.vkCode]))
                    user32.PostThreadMessageW(thread, WM_APP, 0, 0)
                elif down and k.vkCode == UNDO_VK:
                    pending_markers.append((time.time() - start, None))
                    user32.PostThreadMessageW(thread, WM_APP, 0, 0)
                elif down:
                    user32.PostThreadMessageW(thread, WM_QUIT, 0, 0)
                return 1                                   # keep these keys away from the game
            if (INCLUDE_INJECTED or not (k.flags & LLKHF_INJECTED)) and user32.GetForegroundWindow() == hwnd:
                name = names.get((k.scanCode, bool(k.flags & LLKHF_EXTENDED)))
                if name:
                    events.append((time.time() - start, "key", name, down))
        return user32.CallNextHookEx(None, code, wparam, lparam)

    callback = HOOKPROC(proc)
    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, callback, kernel32.GetModuleHandleW(None), 0)
    if not hook:
        raise RuntimeError("could not install the keyboard hook")
    os.makedirs(frames_dir, exist_ok=True)
    msg = w.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            while pending_markers:                         # pictures are taken here, outside the hook
                t, kind = pending_markers.pop(0)
                if kind is None:                           # Home: undo the last marker and its picture
                    marks = [i for i, e in enumerate(events) if e[1] == "marker"]
                    if marks:
                        events.pop(marks[-1])
                        n = len(frames) - 1
                        path = frames.pop(n)
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                        print(f'{{"event": "undone", "n": {n}}}', flush=True)
                    else:
                        print('{"event": "undone", "n": null, "note": "no marker to undo"}', flush=True)
                    continue
                n = len(frames)
                path = os.path.join(frames_dir, f"{n:02d}.png")
                W.capture(hwnd).save(path)
                frames[n] = path
                events.append((t, "marker", kind, True))
                print(f'{{"event": "marker", "n": {n}, "kind": "{kind}", "at": {t:.2f}, "picture": "{path}"}}', flush=True)
    finally:
        user32.UnhookWindowsHookEx(hook)
    events.sort(key=lambda e: e[0])
    return events, frames


def play(chunk, hwnd):
    """Replay one recorded chunk with its original timing. Anything still held at the end is released."""
    import mom_window as W
    if not W.focus(hwnd):
        raise W.NotInFront("the window is not in front; nothing was played")
    held = set()
    try:
        for delay, name, down in chunk:
            if delay > 0:
                time.sleep(delay)
            scan, extended = W.KEYS[name]
            W._send(scan, extended, not down)
            (held.add if down else held.discard)(name)
    finally:
        for name in held:
            scan, extended = W.KEYS[name]
            W._send(scan, extended, True)
