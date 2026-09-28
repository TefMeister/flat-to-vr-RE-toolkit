"""Menu-o-matiC - drive a game's menus by recorded routes, and record new routes cheaply.

For any person or AI that can run a command and (only when needed) look at a picture. Windows only.

    look   <window> OUT.png [--region x,y,w,h] [--scale 0.5]   save what the window shows (all or a patch)
    press  <window> KEY [--route FILE] [--changed OUT.png]     press a key; optionally record it, and save
                                                               a crop of only what the key changed
    mark   <window> FILE NAME --region x,y,w,h [--note ..]     save a checkpoint (and a step that waits for it)
    check  <window> FILE NAME                                  does the screen match that checkpoint now?
    new    FILE --game G --window W --route R                  start an empty route file
    add    FILE (--sleep S | --launch URL)                     add a plain step
    run    FILE [--from N] [--lost-dir DIR] [--timeout S]      replay a route; stops at the first
                                                               checkpoint that does not match

Regions are fractions of the window (x,y,width,height), so a route recorded in one window size replays in
another. Exit codes: 0 done, 2 lost (a checkpoint did not match in time), 1 anything else.

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


def lost(route, index, step, hwnd, lost_dir, distance):
    """Save what the screen showed (a full half-size picture and the checkpoint patch) and report."""
    import mom_window as W
    os.makedirs(lost_dir, exist_ok=True)
    img = W.capture(hwnd)
    full = os.path.join(lost_dir, "lost-full.png")
    patch = os.path.join(lost_dir, "lost-patch.png")
    img.resize((img.width // 2, img.height // 2)).save(full)
    R.crop(img, route["checkpoints"][step["wait"]]["region"]).save(patch)
    say(event="lost", step=index, checkpoint=step["wait"], distance=round(distance, 2),
        note=route["checkpoints"][step["wait"]].get("note", ""), full=full, patch=patch)
    sys.exit(2)


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
            hwnd = W.wait_window(route["window"], WINDOW_TIMEOUT_S)
            if not hwnd:
                say(event="error", step=i, error="the window never appeared")
                sys.exit(1)
            time.sleep(LAUNCH_SETTLE_S)
            say(event="launched", step=i)
        elif "sleep" in step:
            time.sleep(step["sleep"])
        elif "key" in step:
            if not hwnd:
                hwnd = W.wait_window(route["window"], WINDOW_TIMEOUT_S)
            W.tap(step["key"], hwnd)
            say(event="key", step=i, key=step["key"])
        elif "wait" in step:
            # "repress": N  = if the screen has not come after N seconds, press the previous key again.
            # Some screens ignore a key while they are still fading in (Burnout's title, 2026-09-28).
            end = time.time() + (step.get("timeout") or a.timeout)
            repress = step.get("repress")
            last_key = next((s["key"] for s in reversed(route["steps"][:i]) if "key" in s), None)
            next_press = time.time() + repress if repress and last_key else None
            d = 255.0
            while time.time() < end:
                d, ok = R.matches(route, step["wait"], W.capture(hwnd))
                if ok:
                    break
                if next_press and time.time() >= next_press:
                    W.tap(last_key, hwnd)
                    say(event="repress", step=i, key=last_key)
                    next_press = time.time() + repress
                time.sleep(POLL_S)
            else:
                lost(route, i, step, hwnd, a.lost_dir, d)
            say(event="reached", step=i, checkpoint=step["wait"], distance=round(d, 2))
    say(event="done", route=route["route"])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("look"); s.add_argument("window"); s.add_argument("out")
    s.add_argument("--region"); s.add_argument("--scale", type=float, default=1.0); s.set_defaults(f=cmd_look)
    s = sub.add_parser("press"); s.add_argument("window"); s.add_argument("key")
    s.add_argument("--route"); s.add_argument("--changed"); s.set_defaults(f=cmd_press)
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
