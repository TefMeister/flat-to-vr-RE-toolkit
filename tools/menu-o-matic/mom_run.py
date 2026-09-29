"""Menu-o-matiC / Move-o-matiC: the replay engine both tools share.

Runs a route's steps in order:
    {"launch": "..."}                      start the game, then wait for its window
    {"sleep": 2.0}                         wait
    {"key": "enter"}                       tap a key
    {"click": [x, y]}                      left-click at a point (fractions of the window)
    {"hold": ["w", "a"], "seconds": 1.5}   hold keys together (walk, drive, steer)          (Move-o-matiC)
    {"turn": [dx, dy]}                     move the mouse by dx, dy (turn the camera)        (Move-o-matiC)
    {"play": [[dt, key, 1|0], ...]}        replay what a person played, with its exact timing (setup mode)
    {"wait": "<checkpoint>"}               wait until a small patch of the window looks like the saved one
While waiting it checks that the game is still open and answering, so a crash or a hang is told apart from a
slow screen. Output: one JSON line per event.
"""
import json
import os
import subprocess
import sys
import time

import mom_route as R

# ---- Settings ----------------------------------------------------------------
POLL_S = 0.5                 # how often a wait re-checks its checkpoint
DEFAULT_WAIT_TIMEOUT_S = 90  # loading screens can be long
WINDOW_TIMEOUT_S = 240       # after a launch step
LAUNCH_SETTLE_S = 2.0        # after the window appears, before the first key
HUNG_GIVE_UP_S = 60          # 'Not Responding' this long in a row = give up (games do hang briefly while loading)
FROZEN_S = 30                # a timeout with the picture unchanged this long is reported as "frozen"
EXIT_LOST, EXIT_GONE, EXIT_HUNG = 2, 3, 4


def say(**fields):
    """One JSON line per event, so another program (or an AI) can read the result reliably."""
    print(json.dumps(fields, ensure_ascii=False), flush=True)


def lost(route, index, step, hwnd, lost_dir, distance, reason):
    """Save what the screen showed (a full half-size picture and the checkpoint patch) and report."""
    import mom_window as W
    os.makedirs(lost_dir, exist_ok=True)
    img = W.capture(hwnd)
    full = os.path.join(lost_dir, "lost-full.png")
    patch = os.path.join(lost_dir, "lost-patch.png")
    img.resize((img.width // 2, img.height // 2)).save(full)
    R.crop(img, route["checkpoints"][step["wait"]]["region"]).save(patch)
    import state_o_matic                           # what does the game seem to be doing instead?
    guess, why, _ = state_o_matic.observe(hwnd, 1.5)
    say(event="lost", route=route["route"], step=index, checkpoint=step["wait"], reason=reason,
        distance=round(distance, 2), note=route["checkpoints"][step["wait"]].get("note", ""),
        state_guess=guess, state_why=why, full=full, patch=patch)
    sys.exit(EXIT_LOST)


def gone(index, what):
    """The game's window is gone (closed or crashed), or never came."""
    say(event="gone", step=index, reason=what)
    sys.exit(EXIT_GONE)


def wait_for(route, i, step, hwnd, timeout, lost_dir):
    """Poll one checkpoint until it matches or the step's time runs out, checking on every poll that the game
    is still there and still answering. Returns the last distance."""
    import mom_window as W
    now = time.time()
    end = now + (step.get("timeout") or timeout)
    # "repress": N = if the screen has not come after N seconds, repeat the last key tap OR key hold. A tap is
    # too short for some things: Burnout only shows its map once the car actually moves (2026-09-28).
    repress = step.get("repress")
    last_action = next((s for s in reversed(route["steps"][:i]) if "key" in s or "hold" in s or "play" in s),
                       None)
    next_press = now + repress if repress and last_action else None
    still, hung_since, d, unchanged = R.StillWatch(), None, 255.0, 0.0
    while time.time() < end:
        if not W.is_open(hwnd):
            hwnd = W.find_window(route["window"])     # some games swap their start-up window for the real one
            if not hwnd:
                gone(i, f"the game window closed while waiting for '{step['wait']}' (crashed or quit)")
        if W.is_hung(hwnd):
            hung_since = hung_since or time.time()
            if time.time() - hung_since >= HUNG_GIVE_UP_S:
                say(event="not_responding", step=i, seconds=int(time.time() - hung_since),
                    reason="Windows reports the game as Not Responding")
                sys.exit(EXIT_HUNG)
            time.sleep(POLL_S)
            continue
        hung_since = None
        try:
            img = W.capture(hwnd)
        except W.NotInFront:
            if not W.is_open(hwnd):
                gone(i, "the game window closed")
            raise
        except RuntimeError:                       # no picture yet: a window still starting up, or minimised
            time.sleep(POLL_S)                     # for a moment (Alice, 2026-09-29); keep waiting
            continue
        d, ok = R.matches(route, step["wait"], img)
        if ok:
            return d, hwnd
        unchanged = still.update(img, time.time())
        if next_press and time.time() >= next_press:
            if "key" in last_action:
                W.tap(last_action["key"], hwnd)
            elif "play" in last_action:
                import mom_record as C
                C.play(last_action["play"], hwnd)
            else:
                W.hold(last_action["hold"], last_action["seconds"], hwnd)
            say(event="repress", step=i, action=last_action)
            next_press = time.time() + repress
        time.sleep(POLL_S)
    if unchanged >= FROZEN_S:
        reason = f"frozen: the whole picture has not changed for {int(unchanged)} s"
    else:
        reason = "a different screen than expected (the picture is still moving)"
    lost(route, i, step, hwnd, lost_dir, d, reason)


def run_route(route, start, timeout, lost_dir):
    import mom_window as W
    hwnd = W.find_window(route["window"])
    for i, step in enumerate(route["steps"]):
        if i < start:
            continue
        if "launch" in step:
            if hwnd:
                say(event="skip", step=i, why="window already open")
                continue
            os.startfile(step["launch"]) if hasattr(os, "startfile") else subprocess.Popen([step["launch"]])
            hwnd = W.wait_window(route["window"], step.get("timeout") or WINDOW_TIMEOUT_S)
            if not hwnd:
                gone(i, f"no game window within {step.get('timeout') or WINDOW_TIMEOUT_S} s: it did not start, "
                        "or it crashed while starting")
            time.sleep(LAUNCH_SETTLE_S)
            say(event="launched", step=i)
            continue
        if "sleep" in step:
            time.sleep(step["sleep"])
            continue
        if not hwnd:
            hwnd = W.wait_window(route["window"], WINDOW_TIMEOUT_S)
        if not hwnd or not W.is_open(hwnd):
            gone(i, "the game window is not there")
        if "key" in step:
            W.tap(step["key"], hwnd)
            say(event="key", step=i, key=step["key"])
        elif "click" in step:
            W.click(hwnd, *step["click"])
            say(event="click", step=i, at=step["click"])
        elif "hold" in step:
            W.hold(step["hold"], step["seconds"], hwnd)
            say(event="hold", step=i, keys=step["hold"], seconds=step["seconds"])
        elif "turn" in step:
            W.turn(hwnd, *step["turn"])
            say(event="turn", step=i, by=step["turn"])
        elif "play" in step:
            import mom_record as C
            C.play(step["play"], hwnd)
            say(event="play", step=i, events=len(step["play"]))
        elif "todo" in step:
            say(event="skip", step=i, why="a marker that is not a checkpoint yet (mark-image turns it into one)")
        elif "wait" in step:
            d, hwnd = wait_for(route, i, step, hwnd, timeout, lost_dir)
            say(event="reached", step=i, checkpoint=step["wait"], distance=round(d, 2))
    say(event="done", route=route["route"])


def cmd_run(a):
    """Run one or more route files in a row (a menu route, then a movement route). --from applies to the first."""
    for n, path in enumerate(a.routes):
        run_route(R.load(path), a.start if n == 0 else 0, a.timeout, a.lost_dir)
