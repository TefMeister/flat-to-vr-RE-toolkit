"""Menu-o-matiC - drive a game's menus by recorded routes, and record new routes cheaply.

For any person or AI that can run a command and (only when needed) look at a picture. Windows only.

    look   <window> OUT.png [--region x,y,w,h] [--scale 0.5]   save what the window shows (all or a patch)
    press  <window> KEY [--route FILE] [--changed OUT.png]     press a key; optionally record it, and save
                                                               a crop of only what the key changed
    click  <window> x,y [--route FILE]                         left-click a point (fractions of the window);
                                                               optionally record it
    mark   <window> FILE NAME --region x,y,w,h [--note ..]     save a checkpoint (and a step that waits for it)
    check  <window> FILE NAME                                  does the screen match that checkpoint now?
    new    FILE --game G --window W --route R                  start an empty route file
    add    FILE (--sleep S | --launch URL)                     add a plain step
    run    FILE [--from N] [--lost-dir DIR] [--timeout S]      replay a route; stops at the first
                                                               checkpoint that does not match

Regions are fractions of the window (x,y,width,height), so a route recorded in one window size replays in
another. Exit codes: 0 done; 2 lost (the checkpoint never matched: the JSON says whether the picture was
frozen or just different); 3 the game window closed, crashed or never opened; 4 Windows reported the game
'Not Responding' for a minute; 1 anything else. A wait keeps trying for its whole time limit (default 90 s,
`--timeout`, or `"timeout"` on the step), so a slow loading screen is fine.

HOW TO SPEND LITTLE (the point of the tool; see README.md):
  1. `look --scale 0.5` ONCE to see the screen (a half-size picture costs a quarter of a full one).
  2. `press <window> down --changed crop.png`: the tool itself finds what changed - normally the menu lines -
     and saves only that patch. Read the small crop, not the screen.
  3. Keep reading crops of that region. Take a full picture again only when a crop stops making sense.
  4. `mark` each screen as you reach it. Next time, `run` replays everything with no pictures at all.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import mom_route as R

# ---- Settings ----------------------------------------------------------------
POLL_S = 0.5                 # how often `run` re-checks a checkpoint
DEFAULT_WAIT_TIMEOUT_S = 90  # loading screens can be long
KEY_SETTLE_S = 0.8           # after a key, before a "what changed" capture
NOISE_GAP_S = 0.8            # between the two no-key captures that find self-moving parts
WINDOW_TIMEOUT_S = 240       # after a launch step
LAUNCH_SETTLE_S = 2.0        # after the window appears, before the first key
HUNG_GIVE_UP_S = 60          # 'Not Responding' this long in a row = give up (games do hang briefly while loading)
FROZEN_S = 30                # a timeout with the picture unchanged this long is reported as "frozen"
EXIT_LOST, EXIT_GONE, EXIT_HUNG = 2, 3, 4


def say(**fields):
    """One JSON line per event, so another program (or an AI) can read the result reliably."""
    print(json.dumps(fields, ensure_ascii=False), flush=True)


def need_window(title):
    import mom_window as W
    hwnd = W.find_window(title)
    if not hwnd:
        say(event="error", error=f"no visible window whose title contains {title!r}")
        sys.exit(1)
    if not W.focus(hwnd):
        say(event="error", error="the window could not be brought to the front; nothing was sent")
        sys.exit(1)
    return hwnd


def cmd_look(a):
    import mom_window as W
    img = W.capture(need_window(a.window))
    if a.region:
        img = R.crop(img, R.parse_region(a.region))
    if a.scale != 1.0:
        img = img.resize((max(1, int(img.width * a.scale)), max(1, int(img.height * a.scale))))
    img.save(a.out)
    say(event="look", out=a.out, size=list(img.size))


def cmd_press(a):
    import mom_window as W
    hwnd = need_window(a.window)
    noise = before = None
    if a.changed:
        noise = W.capture(hwnd)          # two captures with no key between them: whatever differs
        time.sleep(NOISE_GAP_S)          # moves by itself and is left out of "what changed"
        before = W.capture(hwnd)
    try:
        W.tap(a.key, hwnd)
    except KeyError:
        say(event="error", error=f"unknown key {a.key!r}", known=sorted(W.KEYS))
        sys.exit(1)
    if a.route:
        route = R.load(a.route)
        route["steps"].append({"key": a.key.lower()})
        R.save(route, a.route)
    result = {"event": "press", "key": a.key}
    if a.changed:
        time.sleep(KEY_SETTLE_S)
        after = W.capture(hwnd)
        regions = R.changed_regions(before, after, noise)
        if regions:
            R.crop(after, regions[0]).save(a.changed)
            result.update(changed_region=",".join(str(v) for v in regions[0]), crop=a.changed,
                          other_regions=[",".join(str(v) for v in r) for r in regions[1:4]])
        else:
            result.update(changed_region=None, note="nothing on screen changed")
    say(**result)


def cmd_click(a):
    import mom_window as W
    hwnd = need_window(a.window)
    point = R.parse_point(a.point)
    W.click(hwnd, *point)
    if a.route:
        route = R.load(a.route)
        route["steps"].append({"click": point})
        R.save(route, a.route)
    say(event="click", at=point)


def cmd_mark(a):
    import mom_window as W
    img = W.capture(need_window(a.window))
    region = R.parse_region(a.region)
    route = R.load(a.route)
    if a.name in route["checkpoints"]:
        say(event="error", error=f"checkpoint {a.name!r} already exists in {a.route}")
        sys.exit(1)
    R.add_checkpoint(route, a.name, region, R.signature(R.crop(img, region)), a.note, a.tol)
    R.save(route, a.route)
    say(event="mark", checkpoint=a.name, region=a.region)


def cmd_check(a):
    import mom_window as W
    img = W.capture(need_window(a.window))
    d, ok = R.matches(R.load(a.route), a.name, img)
    say(event="check", checkpoint=a.name, distance=round(d, 2), match=ok)


def cmd_new(a):
    if os.path.exists(a.route):
        say(event="error", error=f"{a.route} already exists")
        sys.exit(1)
    R.save(R.new_route(a.game, a.window, a.name), a.route)
    say(event="new", route=a.route)


def cmd_add(a):
    route = R.load(a.route)
    route["steps"].append({"sleep": a.sleep} if a.sleep is not None else {"launch": a.launch})
    R.save(route, a.route)
    say(event="add", step=route["steps"][-1])


def lost(route, index, step, hwnd, lost_dir, distance, reason):
    """Save what the screen showed (a full half-size picture and the checkpoint patch) and report."""
    import mom_window as W
    os.makedirs(lost_dir, exist_ok=True)
    img = W.capture(hwnd)
    full = os.path.join(lost_dir, "lost-full.png")
    patch = os.path.join(lost_dir, "lost-patch.png")
    img.resize((img.width // 2, img.height // 2)).save(full)
    R.crop(img, route["checkpoints"][step["wait"]]["region"]).save(patch)
    say(event="lost", step=index, checkpoint=step["wait"], reason=reason, distance=round(distance, 2),
        note=route["checkpoints"][step["wait"]].get("note", ""), full=full, patch=patch)
    sys.exit(EXIT_LOST)


def gone(index, what):
    """The game's window is gone (closed or crashed), or never came."""
    say(event="gone", step=index, reason=what)
    sys.exit(EXIT_GONE)


def wait_for(route, i, step, hwnd, a):
    """Poll one checkpoint. Keeps trying until it matches or the step's time runs out, and on every poll checks
    that the game is still there and still answering. Returns the last distance."""
    import mom_window as W
    now = time.time()
    end = now + (step.get("timeout") or a.timeout)
    repress = step.get("repress")
    last_key = next((s["key"] for s in reversed(route["steps"][:i]) if "key" in s), None)
    next_press = now + repress if repress and last_key else None
    still, hung_since, d, unchanged = R.StillWatch(), None, 255.0, 0.0
    while time.time() < end:
        if not W.is_open(hwnd):
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
        d, ok = R.matches(route, step["wait"], img)
        if ok:
            return d
        unchanged = still.update(img, time.time())
        if next_press and time.time() >= next_press:
            W.tap(last_key, hwnd)
            say(event="repress", step=i, key=last_key)
            next_press = time.time() + repress
        time.sleep(POLL_S)
    if unchanged >= FROZEN_S:
        reason = f"frozen: the whole picture has not changed for {int(unchanged)} s"
    else:
        reason = "a different screen than expected (the picture is still moving)"
    lost(route, i, step, hwnd, a.lost_dir, d, reason)


def cmd_run(a):
    import mom_window as W
    route = R.load(a.route)
    hwnd = W.find_window(route["window"])
    for i, step in enumerate(route["steps"]):
        if i < a.start:
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
        elif "sleep" in step:
            time.sleep(step["sleep"])
        elif "key" in step or "click" in step:
            if not hwnd:
                hwnd = W.wait_window(route["window"], WINDOW_TIMEOUT_S)
            if not hwnd or not W.is_open(hwnd):
                gone(i, "the game window is not there")
            if "key" in step:
                W.tap(step["key"], hwnd)
                say(event="key", step=i, key=step["key"])
            else:
                W.click(hwnd, *step["click"])
                say(event="click", step=i, at=step["click"])
        elif "wait" in step:
            d = wait_for(route, i, step, hwnd, a)
            say(event="reached", step=i, checkpoint=step["wait"], distance=round(d, 2))
    say(event="done", route=route["route"])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("look"); s.add_argument("window"); s.add_argument("out")
    s.add_argument("--region"); s.add_argument("--scale", type=float, default=1.0); s.set_defaults(f=cmd_look)
    s = sub.add_parser("press"); s.add_argument("window"); s.add_argument("key")
    s.add_argument("--route"); s.add_argument("--changed"); s.set_defaults(f=cmd_press)
    s = sub.add_parser("click"); s.add_argument("window"); s.add_argument("point")
    s.add_argument("--route"); s.set_defaults(f=cmd_click)
    s = sub.add_parser("mark"); s.add_argument("window"); s.add_argument("route"); s.add_argument("name")
    s.add_argument("--region", required=True); s.add_argument("--note", default="")
    s.add_argument("--tol", type=float, default=R.DEFAULT_TOLERANCE); s.set_defaults(f=cmd_mark)
    s = sub.add_parser("check"); s.add_argument("window"); s.add_argument("route"); s.add_argument("name")
    s.set_defaults(f=cmd_check)
    s = sub.add_parser("new"); s.add_argument("route"); s.add_argument("--game", required=True)
    s.add_argument("--window", required=True); s.add_argument("--route", dest="name", required=True)
    s.set_defaults(f=cmd_new)
    s = sub.add_parser("add"); s.add_argument("route"); g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--sleep", type=float); g.add_argument("--launch"); s.set_defaults(f=cmd_add)
    s = sub.add_parser("run"); s.add_argument("route"); s.add_argument("--from", dest="start", type=int, default=0)
    s.add_argument("--lost-dir", default="menu-o-matic-lost")
    s.add_argument("--timeout", type=float, default=DEFAULT_WAIT_TIMEOUT_S); s.set_defaults(f=cmd_run)
    a = p.parse_args()
    import mom_window as W
    try:
        a.f(a)
    except W.NotInFront as e:
        say(event="error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
