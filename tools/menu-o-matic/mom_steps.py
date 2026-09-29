"""Menu-o-matiC: the step recorder (the player's scheme, 2026-09-29).

Three keys, and only the keys the person means are recorded:
    Home       start recording (may be pressed BEFORE the game starts, so skippable logos are caught)
    Page Down  "the next key I press is a step": a picture of the game window is taken NOW, and the very next key
               pressed is recorded as the key that gets past this screen
    End        stop (a last picture is taken if the window is still there: where the route ended)
Every other key is ignored, so stray presses never end up in a route. If something goes wrong, start again.

Each step becomes, in the route file:
    {"todo": "<picture>", "kind": "key"}  then  {"play": [[0.3, KEY, 1], [HELD, KEY, 0]]}
and the picture is turned into a checkpoint afterwards (mark-image), so a replay waits for each screen and then
presses its key. The grey keys only (the number pad with NumLock off sends the same codes and is ignored).
"""
import ctypes
import ctypes.wintypes as w
import os
import time

# ---- Settings ----------------------------------------------------------------
START_VK, STEP_VK, STOP_VK = 0x24, 0x22, 0x23      # Home, Page Down, End
PRESS_DELAY_S = 0.3                                 # replay waits this long after a checkpoint before the key
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_QUIT, WM_APP = 0x0012, 0x8000
LLKHF_EXTENDED, LLKHF_INJECTED = 0x01, 0x10
INCLUDE_INJECTED = os.environ.get("MOM_RECORD_INJECTED") == "1"   # testing only


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", w.DWORD), ("scanCode", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


def say(**fields):
    import json
    print(json.dumps(fields, ensure_ascii=False), flush=True)


def record_steps(window_title, frames_dir):
    """Run until End. Returns (steps, final_picture_or_None)."""
    import mom_window as W
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    names = {v: k for k, v in W.KEYS.items()}            # (scan, extended) -> key name
    thread = kernel32.GetCurrentThreadId()
    state = {"started": False, "armed": False, "pending": [], "key": None, "down_t": 0.0}
    steps = []
    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, w.WPARAM, w.LPARAM)
    user32.CallNextHookEx.argtypes = [w.HHOOK, ctypes.c_int, w.WPARAM, w.LPARAM]
    user32.CallNextHookEx.restype = LRESULT
    kernel32.GetModuleHandleW.argtypes = [w.LPCWSTR]
    kernel32.GetModuleHandleW.restype = w.HMODULE
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, w.HINSTANCE, w.DWORD]
    user32.SetWindowsHookExW.restype = w.HHOOK
    user32.UnhookWindowsHookEx.argtypes = [w.HHOOK]

    def post(what):
        state["pending"].append((time.time(), what))
        user32.PostThreadMessageW(thread, WM_APP, 0, 0)

    def proc(code, wparam, lparam):
        if code == 0:
            k = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
            grey = bool(k.flags & LLKHF_EXTENDED)
            if grey and k.vkCode in (START_VK, STEP_VK, STOP_VK):
                if down:
                    post({START_VK: "start", STEP_VK: "step", STOP_VK: "stop"}[k.vkCode])
                return 1                                   # the three control keys never reach the game
            if state["started"] and (INCLUDE_INJECTED or not (k.flags & LLKHF_INJECTED)):
                name = names.get((k.scanCode, grey))
                if name and down and state["armed"] and state["key"] is None:
                    state["key"], state["down_t"] = name, time.time()
                elif name and not down and name == state["key"]:
                    post(("key", name, round(time.time() - state["down_t"], 3)))
        return user32.CallNextHookEx(None, code, wparam, lparam)

    callback = HOOKPROC(proc)
    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, callback, kernel32.GetModuleHandleW(None), 0)
    if not hook:
        raise RuntimeError("could not install the keyboard hook")
    os.makedirs(frames_dir, exist_ok=True)
    say(event="waiting", note="Home = start recording (before or after the game starts)")
    final = None
    msg = w.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            while state["pending"]:
                t, what = state["pending"].pop(0)
                if what == "start" and not state["started"]:
                    state["started"] = True
                    say(event="started", note="Page Down, then the key that gets past the screen; End to stop")
                elif what == "step" and state["started"] and state["key"] is None:
                    hwnd = W.find_window(window_title)
                    path = os.path.join(frames_dir, f"{len(steps):02d}.png")
                    if hwnd:
                        W.capture(hwnd).save(path)
                    state["armed"], state["picture"] = True, path if hwnd else ""
                    say(event="armed", step=len(steps), picture=bool(hwnd),
                        note="now press the key for this screen")
                elif isinstance(what, tuple) and what[0] == "key":
                    steps.append({"picture": state.get("picture", ""), "key": what[1], "held": max(what[2], 0.05)})
                    state["armed"], state["key"] = False, None
                    say(event="step", n=len(steps) - 1, key=what[1])
                elif what == "stop":
                    hwnd = W.find_window(window_title)
                    if hwnd and W.is_open(hwnd):
                        final = os.path.join(frames_dir, "end.png")
                        W.capture(hwnd).save(final)
                    user32.PostThreadMessageW(thread, WM_QUIT, 0, 0)
    finally:
        user32.UnhookWindowsHookEx(hook)
    return steps, final


def to_route_steps(steps, final):
    """Recorded steps -> route steps: wait for each screen (a marker to turn into a checkpoint), then its key."""
    out = []
    for s in steps:
        if s["picture"]:
            out.append({"todo": s["picture"], "kind": "key"})
        out.append({"play": [[PRESS_DELAY_S, s["key"], 1], [s["held"], s["key"], 0]]})
    if final:
        out.append({"todo": final, "kind": "wait"})
    return out
