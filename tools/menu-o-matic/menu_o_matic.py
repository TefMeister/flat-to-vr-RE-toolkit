"""Menu-o-matiC - drive a game's menus by recorded routes, and record new routes cheaply.

For any person or AI that can run a command and (only when needed) look at a picture. Windows only.

    look   <window> OUT.png [--region x,y,w,h] [--scale 0.5]   save what the window shows (all or a patch)
    windowcheck <window> [--route FILE] [--confirmed]          windowed or fullscreen? Measures the window AND
                                                               the screen; ASK the person ONCE per game, then
                                                               --confirmed stores their yes in the route
    press  <window> KEY [--route FILE] [--changed OUT.png]     press a key; optionally record it, and save
                                                               a crop of only what the key changed
    click  <window> x,y [--route FILE]                         left-click a point (fractions of the window);
                                                               optionally record it
    mark   <window> FILE NAME --region x,y,w,h [--note ..]     save a checkpoint (and a step that waits for it)
    check  <window> FILE NAME                                  does the screen match that checkpoint now?
    new    FILE --game G --window W --route R [--from S --to S]   start an empty route file; --from/--to name
                                                               where it starts and ends (closed, gameplay,
                                                               keybindings...), so a game's routes form a MAP
    add    FILE (--sleep S | --launch URL | --picture NAME)    add a plain step; --picture saves what the
                                                               screen shows (a key bindings page) at that point
    routes FOLDER                                              the map: every route of a game, start -> end
    SETUP, done once per game WITH the person (see README.md, "Setting a game up"):
    record <window> FILE [--frames DIR]                        the person plays; keys + timing recorded;
                                                               Page Up = key needed here, Page Down = just
                                                               wait here, Home = undo last mark, End = stop
    mark-image FILE N NAME --region x,y,w,h [--image PNG]      marker N (or any saved picture) -> checkpoint
    probe  <window> KEYS [--seconds S] [--region ..] [--watch-file LOG]   does this key reach the game?
    note   FILE "TEXT"                                         keep what the person said (controls, save slot)
    brief  FILE [--why ..] [--start ..] [--move .. (repeat)] [--screen ..] [--avoid ..] [--end ..]
                                                               what the TEST needs to see happen on screen;
                                                               with no options, prints it. `record` prints it
                                                               first, so the person knows exactly what to play
    run    FILE [FILE ..] [--from N] [--lost-dir DIR] [--timeout S]  replay one or more routes in a row;
                                                               stops at the first checkpoint that does not match

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
import os
import sys
import time

import mom_route as R
from mom_run import DEFAULT_WAIT_TIMEOUT_S, cmd_run, say

# ---- Settings ----------------------------------------------------------------
KEY_SETTLE_S = 0.8           # after a key, before a "what changed" capture
NOISE_GAP_S = 0.8            # between the two no-key captures that find self-moving parts


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


def window_verdict(hwnd):
    """Is the game in a real window, or fullscreen? Measures the window AND the screen: a game told only a
    size can switch the whole display to that size (Prototype, 2026-09-29), so the window alone lies."""
    import ctypes
    import ctypes.wintypes as wt
    u = ctypes.windll.user32
    r = wt.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    win = (r.right - r.left, r.bottom - r.top)
    screen = (u.GetSystemMetrics(0), u.GetSystemMetrics(1))
    covers = r.left <= 0 and r.top <= 0 and win[0] >= screen[0] and win[1] >= screen[1]
    return dict(window=list(win), client=list(__import__("mom_window").client_size(hwnd)), screen=list(screen),
                verdict="FULLSCREEN (the window covers the whole screen)" if covers else "windowed",
                ask_the_person="Is the game in a window of the right size, and can you still see the session "
                               "beside it? Their answer settles it.")


def cmd_windowcheck(a):
    """Windowed or fullscreen? The person confirms ONCE per game (--confirmed stores it in the route); after
    that the check only measures, and asks again only if the window no longer matches what was confirmed."""
    import datetime
    import mom_window as W
    hwnd = W.find_window(a.window)
    if not hwnd:
        say(event="error", error=f"no visible window whose title contains {a.window!r}")
        sys.exit(1)
    v = window_verdict(hwnd)
    route = R.load(a.route) if a.route else None
    ok = route.get("window_confirmed") if route else None
    if a.confirmed:
        if not route:
            say(event="error", error="--confirmed needs --route (the confirmation is kept in the route file)")
            sys.exit(1)
        route["window_confirmed"] = {"date": datetime.date.today().isoformat(), "window": v["window"]}
        R.save(route, a.route)
        v.pop("ask_the_person")
        v["confirmed"] = "stored: this game will not ask again while the window stays this size"
    elif ok and v["verdict"] == "windowed" and ok.get("window") == v["window"]:
        v.pop("ask_the_person")
        v["confirmed"] = f"the person confirmed this window on {ok['date']}; no need to ask"
    say(event="windowcheck", **v)


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
    R.add_checkpoint(route, a.name, region, R.signature(R.crop(img, region)), a.note, a.tol, a.spot_tol)
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
    route = R.new_route(a.game, a.window, a.name)
    route["from"], route["to"] = a.start_state, a.end_state      # a MAP of the game: routes join end to start
    R.save(route, a.route)
    say(event="new", route=a.route, start=a.start_state, end=a.end_state)


def cmd_add(a):
    route = R.load(a.route)
    if a.sleep is not None:
        route["steps"].append({"sleep": a.sleep})
    elif a.picture:
        route["steps"].append({"picture": a.picture})       # the route's result is a picture (a settings page)
    else:
        route["steps"].append({"launch": a.launch})
    R.save(route, a.route)
    say(event="add", step=route["steps"][-1])


def cmd_record(a):
    """Setup mode: the person plays; every key and its timing is recorded, Page Up / Page Down mark a moment."""
    import mom_record as C
    hwnd = need_window(a.window)
    route = R.load(a.route)
    frames_dir = a.frames or os.path.splitext(a.route)[0] + "-frames"
    print_brief(route)                      # what the person should play, before they start
    if not route.get("window_confirmed"):
        say(event="window", **window_verdict(hwnd))  # confirm with the person before recording
    if not any("play" in st or "key" in st for st in route["steps"]):
        say(event="first_recording", note="first recording of this route: has the person rehearsed it? They launch the game once themselves, play the route with nothing recording and note every button each screen needs; then record, with no mistaken presses and no guessing")
    say(event="recording", keys="play normally", key_screen="Page Up = a key is needed on this screen",
        wait_screen="Page Down = this screen just needs waiting for", undo="Home = undo the last mark",
        stop="End = stop", pictures=frames_dir)
    events, frames = C.record(hwnd, frames_dir)
    steps = C.build_steps(events, frames)
    route["steps"].extend(steps)
    R.save(route, a.route)
    say(event="recorded", steps=len(steps), key_events=sum(len(s.get("play", [])) for s in steps),
        markers=len(frames), note="pictures stay on this PC; never commit them")


def cmd_mark_image(a):
    """Turn marker N (a saved picture) into a checkpoint: a region of that picture."""
    from PIL import Image
    route = R.load(a.route)
    todos = [i for i, s in enumerate(route["steps"]) if "todo" in s]
    if a.n >= len(todos):
        say(event="error", error=f"there are only {len(todos)} unfinished markers")
        sys.exit(1)
    i = todos[a.n]
    region = R.parse_region(a.region)
    img = Image.open(a.image or route["steps"][i]["todo"])
    route["checkpoints"][a.name] = {"region": region, "sig": R.signature(R.crop(img, region)), "tol": a.tol,
                                    "spot_tol": a.spot_tol, "note": a.note}
    kind = route["steps"][i].get("kind", "key")
    route["checkpoints"][a.name]["state"] = "menu" if kind == "key" else "loading"   # State-o-matiC can use it
    route["steps"][i] = {"wait": a.name}
    R.save(route, a.route)
    say(event="mark", checkpoint=a.name, from_marker=a.n)


def cmd_probe(a):
    """Does this key reach the game? Holds it and reports what changed in a region, and in a log file."""
    import mom_window as W
    hwnd = need_window(a.window)
    region = R.parse_region(a.region) if a.region else [0.0, 0.0, 1.0, 1.0]
    size = os.path.getsize(a.watch_file) if a.watch_file and os.path.exists(a.watch_file) else None
    before = R.crop(W.capture(hwnd), region)
    W.hold([k.strip() for k in a.keys.split(",")], a.seconds, hwnd)
    after = R.crop(W.capture(hwnd), region)
    d = R.distance(R.signature(before), R.signature(after))
    result = dict(event="probe", keys=a.keys, region_changed=d > R.STILL_DIFFERENCE, difference=round(d, 2))
    if size is not None:
        with open(a.watch_file, "rb") as f:
            f.seek(size)
            new = f.read().decode("utf-8", "replace").splitlines()
        result.update(new_log_lines=len(new), last_log_lines=new[-3:])
    if a.out:
        after.save(a.out)
        result.update(picture=a.out)
    say(**result)


BRIEF_FIELDS = (                 # the order a brief is printed in, and what each line is called
    ("why", "What the test is for"),
    ("start", "Start from"),
    ("move", "Then do this"),
    ("screen", "Keep this on screen"),
    ("avoid", "Avoid"),
    ("end", "End like this"),
)


def print_brief(route):
    """The person-readable sheet: exactly what has to happen on screen for the test to gather its data."""
    brief = route.get("brief")
    if not brief:
        return False
    print(f"=== TEST BRIEF: {route.get('route', '')} ===", flush=True)
    for key, label in BRIEF_FIELDS:
        value = brief.get(key)
        if not value:
            continue
        if isinstance(value, list):
            print(f"{label}:", flush=True)
            for n, line in enumerate(value, 1):
                print(f"  {n}. {line}", flush=True)
        else:
            print(f"{label}: {value}", flush=True)
    print("=" * 40, flush=True)
    return True


def cmd_brief(a):
    """Write (or, with no options, print) what the test needs to see happen on screen."""
    route = R.load(a.route)
    brief = route.setdefault("brief", {})
    changed = False
    for key, _ in BRIEF_FIELDS:
        value = getattr(a, key)
        if value:
            brief[key] = value
            changed = True
    if changed:
        R.save(route, a.route)
    if not print_brief(route):
        say(event="error", error="this route has no brief yet: add one with --why, --start, --move ...")
        sys.exit(1)
    say(event="brief", route=a.route, saved=changed)


def cmd_routes(a):
    """The map of one game: every route in its folder, where it starts and where it ends, so routes can be
    chained (closed -> gameplay, then gameplay -> key bindings)."""
    import glob
    rows = []
    for path in sorted(glob.glob(os.path.join(a.folder, "*.json"))):
        try:
            r = R.load(path)
        except Exception:
            continue
        rows.append(dict(route=os.path.basename(path), start=r.get("from", "?"), end=r.get("to", "?"),
                         steps=len(r.get("steps", [])), checkpoints=len(r.get("checkpoints", {})),
                         what=(r.get("brief") or {}).get("why", ""),
                         window_confirmed=(r.get("window_confirmed") or {}).get("date")))
    say(event="routes", folder=a.folder, routes=rows)


def cmd_note(a):
    route = R.load(a.route)
    route.setdefault("setup_notes", []).append(a.text)
    R.save(route, a.route)
    say(event="note", notes=len(route["setup_notes"]))


def register_common(sub):
    """The commands both Menu-o-matiC and Move-o-matiC have."""
    s = sub.add_parser("look"); s.add_argument("window"); s.add_argument("out")
    s.add_argument("--region"); s.add_argument("--scale", type=float, default=1.0); s.set_defaults(f=cmd_look)
    s = sub.add_parser("press"); s.add_argument("window"); s.add_argument("key")
    s.add_argument("--route"); s.add_argument("--changed"); s.set_defaults(f=cmd_press)
    s = sub.add_parser("click"); s.add_argument("window"); s.add_argument("point")
    s.add_argument("--route"); s.set_defaults(f=cmd_click)
    s = sub.add_parser("mark"); s.add_argument("window"); s.add_argument("route"); s.add_argument("name")
    s.add_argument("--region", required=True); s.add_argument("--note", default="")
    s.add_argument("--tol", type=float, default=R.DEFAULT_TOLERANCE)
    s.add_argument("--spot-tol", type=float, default=R.DEFAULT_SPOT_TOLERANCE); s.set_defaults(f=cmd_mark)
    s = sub.add_parser("check"); s.add_argument("window"); s.add_argument("route"); s.add_argument("name")
    s.set_defaults(f=cmd_check)
    s = sub.add_parser("new"); s.add_argument("route"); s.add_argument("--game", required=True)
    s.add_argument("--window", required=True); s.add_argument("--route", dest="name", required=True)
    s.add_argument("--from", dest="start_state", default="closed", help="where it starts, e.g. closed, gameplay")
    s.add_argument("--to", dest="end_state", default="gameplay", help="where it ends, e.g. gameplay, keybindings")
    s.set_defaults(f=cmd_new)
    s = sub.add_parser("add"); s.add_argument("route"); g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--sleep", type=float); g.add_argument("--launch"); g.add_argument("--picture")
    s.set_defaults(f=cmd_add)
    s = sub.add_parser("routes"); s.add_argument("folder"); s.set_defaults(f=cmd_routes)
    s = sub.add_parser("record"); s.add_argument("window"); s.add_argument("route"); s.add_argument("--frames")
    s.set_defaults(f=cmd_record)
    s = sub.add_parser("mark-image"); s.add_argument("route"); s.add_argument("n", type=int); s.add_argument("name")
    s.add_argument("--region", required=True); s.add_argument("--image"); s.add_argument("--note", default="")
    s.add_argument("--tol", type=float, default=R.DEFAULT_TOLERANCE)
    s.add_argument("--spot-tol", type=float, default=R.DEFAULT_SPOT_TOLERANCE); s.set_defaults(f=cmd_mark_image)
    s = sub.add_parser("probe"); s.add_argument("window"); s.add_argument("keys")
    s.add_argument("--seconds", type=float, default=1.0); s.add_argument("--region"); s.add_argument("--watch-file")
    s.add_argument("--out"); s.set_defaults(f=cmd_probe)
    s = sub.add_parser("note"); s.add_argument("route"); s.add_argument("text"); s.set_defaults(f=cmd_note)
    s = sub.add_parser("windowcheck"); s.add_argument("window"); s.add_argument("--route")
    s.add_argument("--confirmed", action="store_true"); s.set_defaults(f=cmd_windowcheck)
    s = sub.add_parser("brief"); s.add_argument("route")
    s.add_argument("--why"); s.add_argument("--start"); s.add_argument("--move", action="append")
    s.add_argument("--screen"); s.add_argument("--avoid"); s.add_argument("--end"); s.set_defaults(f=cmd_brief)
    s = sub.add_parser("run"); s.add_argument("routes", nargs="+")
    s.add_argument("--from", dest="start", type=int, default=0)
    s.add_argument("--lost-dir", default="menu-o-matic-lost")
    s.add_argument("--timeout", type=float, default=DEFAULT_WAIT_TIMEOUT_S); s.set_defaults(f=cmd_run)


def main(doc=__doc__, extra=None):
    p = argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    register_common(sub)
    if extra:
        extra(sub)
    a = p.parse_args()
    import mom_window as W
    try:
        a.f(a)
    except W.NotInFront as e:
        say(event="error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
