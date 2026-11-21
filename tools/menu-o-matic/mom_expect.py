"""Menu-o-matiC: a cheap picture check BEFORE a key press (owed DEV 2026-11-12, Tefa: "please add a picture taken
before a menu press somehow to the menu-o-matic, but it has to be cost effective and not run every single run").

Why: a hand-made Silent Hill 2 key route (Enter, Down, Enter ...) lost its first Enter on the warning screen, every
later key landed one step off, and the game ran its Credits instead of New Game, twice, voiding two tests.

A key, click, wheel or hold step may carry an "expect": what the screen must show before the input is sent.
    {"key": "enter", "expect": {"region": [x, y, w, h], "test": "red", "min": 0.3}}
    {"key": "enter", "expect": [<test>, <test>], "always": true}
A list passes when ANY of its tests passes: one test per way the game draws the screen (Silent Hill 2 draws its menu
in the upper two thirds of the window under the VR injector, the whole window without it).
The tests are NUMBERS on one small part of one grab of the window; no model looks at anything unless a check fails:
    red          share of clearly red pixels (r > 45 and r > 1.5 g), 0..1        default min 0.3
    bright       mean brightness, 0..255                                          default min 50
    dark         mean brightness, 0..255                                          default max 40
    checkpoint   a saved checkpoint of the route matches ({"test": "checkpoint", "name": "<checkpoint>"})
Every number test takes "min" and/or "max".

WHEN THE CHECKS RUN (so a normal run costs nothing extra):
    the first run of a route, and after the route, the game's program or the window size changed;
    the run after a run that failed or was stopped (a run that never reached "done");
    every CHECK_EVERY-th run as a spot check;
    always on a step marked "always": true (New Game, overwrite save: anything that destroys or overwrites);
    `run --check` forces every check, `run --no-check` skips all of them (also the "always" ones; said in the output).
A failed check stops the route BEFORE the input is sent, keeps the picture, and says which step and what was expected.
No Windows calls here except through the capture function passed in, so all of it is tested without a game.
"""
import hashlib
import json
import os
import time

import mom_route as R

# ---- Settings ----------------------------------------------------------------
CHECK_EVERY = 10             # a spot check every this many runs when nothing else makes one due
SETTLE_S = 3.0               # a screen still fading in gets this long to pass before the check fails
SETTLE_POLL_S = 0.25
RED_MIN_R, RED_RATIO = 45, 1.5
DEFAULTS = {"red": {"min": 0.3}, "bright": {"min": 50}, "dark": {"max": 40}}
TESTS = ("red", "bright", "dark", "checkpoint")
MEASURE_SIZE = (64, 36)      # the part is shrunk to this many pixels (2,304) before it is counted: enough, and cheap
SUGGEST_RED_SHARE = 0.5      # `expect --image`: a red limit of half the red read on the right screen
SUGGEST_BRIGHT_SHARE = 0.6   # ... a brightness limit of 60 % of the right screen's
SUGGEST_DARK_MARGIN = 20     # ... a darkness limit 20 grey levels above the right screen's
STATE_FILE = os.path.join(os.environ.get("LANES_STATE_DIR") or os.path.join(
    os.path.expandvars("%LOCALAPPDATA%") if os.name == "nt" else os.path.expanduser("~/.cache"), "menu-o-matic"),
    "expect-state.json")


# ---- The number tests ------------------------------------------------------------
def measure(image, test):
    """The number one test reads from a full window capture."""
    kind = test["test"]
    if kind not in ("red", "bright", "dark"):
        raise ValueError(f"no number test {kind!r}")
    part = R.crop(image, test["region"]).convert("RGB").resize(MEASURE_SIZE)
    px = list(part.getdata())
    if kind == "red":
        return sum(1 for r, g, _ in px if r > RED_MIN_R and r > RED_RATIO * g) / max(1, len(px))
    return sum(r + g + b for r, g, b in px) / (3.0 * max(1, len(px)))


def suggest_limit(kind, read):
    """{"min": ..} or {"max": ..} set from a reading on a picture of the right screen."""
    if kind == "red":
        return {"min": round(read * SUGGEST_RED_SHARE, 3)}
    if kind == "bright":
        return {"min": round(read * SUGGEST_BRIGHT_SHARE, 1)}
    return {"max": round(read + SUGGEST_DARK_MARGIN, 1)}


def passes(route, image, test):
    """(passed, what was read) for one test."""
    if test["test"] == "checkpoint":
        d, ok = R.matches(route, test["name"], image)
        return ok, round(d, 2)
    value = measure(image, test)
    lim = dict(DEFAULTS.get(test["test"], {}))
    lim.update({k: test[k] for k in ("min", "max") if k in test})
    ok = ("min" not in lim or value >= lim["min"]) and ("max" not in lim or value <= lim["max"])
    return ok, round(value, 3)


def tests_of(step):
    e = step.get("expect")
    return [] if not e else (e if isinstance(e, list) else [e])


def judge(route, image, step):
    """(passed, readings) for a step's whole expect: passes when ANY of its tests passes."""
    readings, ok = [], False
    for t in tests_of(step):
        good, value = passes(route, image, t)
        readings.append({"test": t["test"], "region": t.get("region"), "name": t.get("name"), "read": value,
                         "min": t.get("min", DEFAULTS.get(t["test"], {}).get("min")),
                         "max": t.get("max", DEFAULTS.get(t["test"], {}).get("max")), "passed": good})
        ok = ok or good
    return ok, readings


def check_step(route, step, capture, settle_s=SETTLE_S, poll_s=SETTLE_POLL_S, clock=time.time, sleep=time.sleep):
    """Grab and judge until it passes or settle_s runs out. Returns (passed, readings, last image)."""
    end = clock() + settle_s
    while True:
        img = capture()
        ok, readings = judge(route, img, step)
        if ok or clock() >= end:
            return ok, readings, img
        sleep(poll_s)


def validate(route, where="route"):
    """Raise ValueError for an expect that cannot be run (checked when the route loads, not mid-run)."""
    for i, step in enumerate(route["steps"]):
        for t in tests_of(step):
            if t.get("test") not in TESTS:
                raise ValueError(f"{where}: step {i}: expect test must be one of {', '.join(TESTS)}")
            if t["test"] == "checkpoint":
                if t.get("name") not in route["checkpoints"]:
                    raise ValueError(f"{where}: step {i}: expect names unknown checkpoint {t.get('name')!r}")
            elif not (isinstance(t.get("region"), list) and len(t["region"]) == 4):
                raise ValueError(f"{where}: step {i}: an expect needs a region [x, y, w, h] in fractions")


# ---- When the checks are due -----------------------------------------------------
def fingerprint(route):
    """Changes when the route's steps or checkpoints change."""
    text = json.dumps({"steps": route["steps"], "checkpoints": route["checkpoints"]}, sort_keys=True)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def exe_mark(path):
    """size + date of the game's program, or '' when it is not known (a new build of the game changes it)."""
    try:
        st = os.stat(path)
        return f"{st.st_size}:{int(st.st_mtime)}"
    except (OSError, TypeError):
        return ""


def load_state(path=None):
    try:
        with open(path or STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state, path=None):
    path = path or STATE_FILE
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1)
    except OSError:
        pass                     # a run never fails because its bookkeeping could not be written


def due(route, window_size, exe_path="", mode="auto", prev=None):
    """(checks due on this run, why). mode: auto | force (--check) | off (--no-check).
    prev: this route's bookkeeping as it was BEFORE this run began (run_began returns it)."""
    if mode == "force":
        return True, "--check"
    if mode == "off":
        return False, "--no-check"
    st = prev
    if not st or not st.get("fingerprint"):
        return True, "the first run of this route"
    if st.get("running"):
        return True, "the last run did not finish (failed or stopped)"
    if st.get("fingerprint") != fingerprint(route):
        return True, "the route changed"
    if exe_path and st.get("exe") != exe_mark(exe_path):
        return True, "the game's program changed (a new build)"
    if window_size and st.get("size") != list(window_size):
        return True, "the window size changed"
    if st.get("runs_since_check", 0) + 1 >= CHECK_EVERY:
        return True, f"the spot check every {CHECK_EVERY} runs"
    return False, f"none due ({st.get('runs_since_check', 0) + 1} of {CHECK_EVERY} runs since the last check)"


def run_began(route, path=None):
    """Written before the first step, so a run that never reaches run_finished leaves running = true behind.
    Returns this route's bookkeeping as it was before (for due)."""
    state = load_state(path)
    st = state.get(route["route"], {})
    prev = dict(st)
    st.update({"running": True, "checked_this_run": False, "started": time.strftime("%Y-%m-%d %H:%M:%S")})
    state[route["route"]] = st
    save_state(state, path)
    return prev


def checks_decided(route, window_size, exe_path, checked, path=None):
    """At the first step with an expect: only a CHECKED run vouches for a new route, game build or window size
    (after a --no-check run they stay due)."""
    state = load_state(path)
    st = state.get(route["route"], {})
    st["checked_this_run"] = bool(checked)
    if checked:
        st.update({"fingerprint": fingerprint(route), "exe": exe_mark(exe_path) if exe_path else "",
                   "size": list(window_size) if window_size else st.get("size")})
    state[route["route"]] = st
    save_state(state, path)


def run_finished(route, path=None):
    state = load_state(path)
    st = state.get(route["route"], {})
    st["running"] = False
    st["runs_since_check"] = 0 if st.get("checked_this_run") else st.get("runs_since_check", 0) + 1
    state[route["route"]] = st
    save_state(state, path)


def step_checked(step, checks_due, mode="auto"):
    """Is this step's expect looked at on this run?"""
    if not tests_of(step) or mode == "off":
        return False
    return checks_due or bool(step.get("always"))
