"""Offline tests for Menu-o-matiC's picture check before a key press (mom_expect.py): no window, no game.
The "done when" of the owed job (2026-11-12): a route with expect steps stops by itself on a planted wrong screen,
runs clean on the right one, and a normal run with no check due takes no longer than before (no picture is taken).
Run: python test_mom_expect.py"""
import os
import sys
import tempfile
import types

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mom_expect as E  # noqa: E402
import mom_route as R  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def screen(kind, size=(1280, 720)):
    """warning: a white square in the middle; menu: a red bar on the second line; credits: grey text only."""
    img = Image.new("RGB", size, (8, 8, 10))
    d = ImageDraw.Draw(img)
    w, h = size
    if kind == "warning":
        d.rectangle([int(0.45 * w), int(0.63 * h), int(0.55 * w), int(0.81 * h)], fill=(240, 240, 240))
    if kind == "menu":
        d.rectangle([int(0.02 * w), int(0.24 * h), int(0.12 * w), int(0.27 * h)], fill=(170, 20, 20))
    if kind == "menu-vr":                     # the same menu drawn in the upper two thirds (under the VR injector)
        d.rectangle([int(0.02 * w), int(0.16 * h), int(0.12 * w), int(0.18 * h)], fill=(170, 20, 20))
    for i in range(6):
        d.rectangle([int(0.3 * w), 80 + 60 * i, int(0.7 * w), 100 + 60 * i], fill=(110, 110, 110))
    return img


RED_LINE = {"region": [0.02, 0.24, 0.10, 0.03], "test": "red", "min": 0.3}
RED_LINE_VR = {"region": [0.02, 0.16, 0.10, 0.02], "test": "red", "min": 0.3}
WHITE_SQUARE = {"region": [0.44, 0.62, 0.12, 0.20], "test": "bright", "min": 50}


def route_with(steps):
    return {"schema": R.SCHEMA, "game": "test", "window": "TestGame", "route": "to-new-game", "steps": steps,
            "checkpoints": {}}


# ---- the number tests ------------------------------------------------------------
menu, warn, credits = screen("menu"), screen("warning"), screen("credits")
check("red: the highlighted line reads red", E.measure(menu, RED_LINE) > 0.9)
check("red: the credits screen reads no red there", E.measure(credits, RED_LINE) < 0.05)
check("bright: the warning's white square is bright", E.measure(warn, WHITE_SQUARE) > 150)
check("bright: the menu has no white square there", E.measure(menu, WHITE_SQUARE) < 50)
r = route_with([{"key": "enter", "expect": RED_LINE}])
check("judge passes the right screen", E.judge(r, menu, r["steps"][0])[0])
check("judge fails the wrong screen", not E.judge(r, credits, r["steps"][0])[0])
both = {"key": "enter", "expect": [RED_LINE, RED_LINE_VR]}
check("a list passes when any way passes (flat)", E.judge(r, menu, both)[0])
check("a list passes when any way passes (VR layout)", E.judge(r, screen("menu-vr"), both)[0])
check("a list fails when no way passes", not E.judge(r, credits, both)[0])
check("dark: an empty corner is dark", E.passes(r, credits, {"test": "dark", "region": [0, 0.9, 0.1, 0.1]})[0])
cp = route_with([{"key": "enter", "expect": {"test": "checkpoint", "name": "menu"}}])
cp["checkpoints"]["menu"] = {"region": RED_LINE["region"], "sig": R.signature(R.crop(menu, RED_LINE["region"])),
                             "tol": R.DEFAULT_TOLERANCE, "spot_tol": R.DEFAULT_SPOT_TOLERANCE}
check("checkpoint test: a saved checkpoint is used", E.judge(cp, menu, cp["steps"][0])[0]
      and not E.judge(cp, credits, cp["steps"][0])[0])
for bad in ({"key": "a", "expect": {"test": "blue", "region": [0, 0, 1, 1]}},
            {"key": "a", "expect": {"test": "red"}},
            {"key": "a", "expect": {"test": "checkpoint", "name": "nowhere"}}):
    try:
        E.validate(route_with([bad]))
        check(f"validate refuses {bad['expect']}", False)
    except ValueError:
        check(f"validate refuses {bad['expect']}", True)

# a screen still fading in gets SETTLE_S to come right
frames = iter([credits, credits, menu])
clock = [0.0]
ok, _, _ = E.check_step(r, r["steps"][0], lambda: next(frames), settle_s=3, poll_s=1,
                        clock=lambda: clock[0], sleep=lambda s: clock.__setitem__(0, clock[0] + s))
check("a screen that comes right within the settle time passes", ok)

# ---- when the checks are due -------------------------------------------------------
tmp = tempfile.mkdtemp(prefix="mom-expect-")
E.STATE_FILE = os.path.join(tmp, "expect-state.json")
exe = os.path.join(tmp, "game.exe")
open(exe, "wb").write(b"x" * 10)
size = (1280, 720)


def one_run(route, mode="auto", finish=True, win=size):
    prev = E.run_began(route)
    d, why = E.due(route, win, exe, mode, prev)
    E.checks_decided(route, win, exe, d)
    if finish:
        E.run_finished(route)
    return d, why


r = route_with([{"key": "enter", "expect": RED_LINE}])
check("the first run of a route is checked", one_run(r)[0])
check("the next run is not", not one_run(r)[0])
spots = [one_run(r)[0] for _ in range(E.CHECK_EVERY)]
check(f"a spot check comes within {E.CHECK_EVERY} runs, once", spots.count(True) == 1)
check("--check forces one", one_run(r, "force")[0])
check("--no-check skips", not one_run(r, "off")[0])
one_run(r, finish=False)                                # a run that failed or was stopped
d, why = one_run(r)
check("the run after an unfinished run is checked", d and "did not finish" in why)
check("a new window size is checked", one_run(r, win=(1920, 1080))[0])
open(exe, "wb").write(b"x" * 20)
check("a new build of the game is checked", one_run(r, win=(1920, 1080))[0])
r2 = route_with([{"key": "enter", "expect": RED_LINE}, {"key": "down"}])
check("--no-check after the route changed ...", not one_run(r2, "off", win=(1920, 1080))[0])
check("... leaves the check due on the next run", one_run(r2, win=(1920, 1080))[0])
check("an 'always' step is looked at with no check due", E.step_checked({"key": "a", "expect": RED_LINE,
                                                                       "always": True}, False))
check("--no-check skips even an 'always' step", not E.step_checked({"key": "a", "expect": RED_LINE,
                                                                    "always": True}, True, "off"))

# ---- end to end: the route player with a pretend game window -------------------------
fake = types.ModuleType("mom_window")
fake.KEY_MODE, fake.EXE = "sendinput", ""
fake.shown, fake.keys, fake.grabs = credits, [], 0


def _capture(h):
    fake.grabs += 1
    return fake.shown


fake.find_window = lambda *a, **k: 1
fake.wait_window = lambda *a, **k: 1
fake.is_open = lambda h: True
fake.is_hung = lambda h: False
fake.capture = _capture
fake.tap = lambda key, h: fake.keys.append(key)
fake.client_size = lambda h: size
fake.program_path = lambda h: exe
sys.modules["mom_window"] = fake
import mom_run as M  # noqa: E402

M.say = lambda **f: events.append(f)
E.SETTLE_S = 0.0
lost_dir = os.path.join(tmp, "lost")
plan = route_with([{"key": "enter", "expect": WHITE_SQUARE}, {"key": "down"},
                   {"key": "enter", "expect": [RED_LINE, RED_LINE_VR], "always": True}])
plan["route"] = "sh2-new-game"

events, fake.keys, fake.shown = [], [], menu            # PLANTED WRONG SCREEN: the menu where the warning should be
try:
    M.run_route(plan, 0, 1, lost_dir, "force")
    stopped = None
except SystemExit as e:
    stopped = e.code
check("a planted wrong screen stops the route", stopped == M.EXIT_LOST)
check("... before the key is sent", fake.keys == [])
check("... and keeps the picture", os.path.isfile(os.path.join(lost_dir, "unexpected-step0.png")))
check("... and says what it expected", any(ev.get("event") == "unexpected" and ev.get("readings") for ev in events))


class Screens:
    """the right screen for each step, as a game would show it"""
    def __init__(self):
        self.n = 0

    def __call__(self, h):
        fake.grabs += 1
        return warn if not fake.keys else menu


fake.capture = Screens()
events, fake.keys = [], []
M.run_route(plan, 0, 1, lost_dir, "force")
check("the right screens run clean", fake.keys == ["enter", "down", "enter"]
      and any(ev.get("event") == "done" for ev in events))

for _ in range(3):                                       # settle into "nothing due"
    events, fake.keys = [], []
    M.run_route(plan, 0, 1, lost_dir)
plain = route_with([{"key": "enter"}, {"key": "down"}, {"key": "enter"}])
plain["route"] = "sh2-new-game"
fake.grabs, events, fake.keys = 0, [], []
M.run_route(plain, 0, 1, lost_dir)
check("a route with no expect takes no picture at all", fake.grabs == 0 and fake.keys == ["enter", "down", "enter"])
fake.grabs, events, fake.keys = 0, [], []
M.run_route(plan, 0, 1, lost_dir)
due_line = next((ev for ev in events if ev.get("event") == "checks"), {})
check("with no check due only the 'always' step is looked at (one grab)", not due_line.get("due") and fake.grabs == 1)
fake.grabs, events, fake.keys = 0, [], []
M.run_route(plan, 0, 1, lost_dir, "off")
check("--no-check takes no picture", fake.grabs == 0 and fake.keys == ["enter", "down", "enter"])

print("\n" + ("all passed" if not FAILS else f"{len(FAILS)} FAILED: {FAILS}"))
sys.exit(1 if FAILS else 0)
