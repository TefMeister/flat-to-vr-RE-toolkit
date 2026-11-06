"""State-o-matiC - what is the game doing right now: main menu, cutscene, gameplay, or loading?

    watch <window> [--seconds 2] [--states FILE] [--game G] [--poke KEY]   look for a moment and give a verdict
                                                                with reasons; the game's taught screens are found
                                                                in the routes folder by themselves (lanes.conf routes)
    teach <window> FILE STATE --region x,y,w,h [--note ..]      store a screen the person names ("main_menu",
                                                                "gameplay"...) so watch can recognise it for sure

`watch` takes a few small looks over a couple of seconds (shrunk to 64x36, judged on this PC, no model involved)
and reads how fast the game is reading its disk. With `--poke KEY` it also presses a harmless key (the person names
one during setup, e.g. a camera key) to see whether the picture answers: gameplay does, a cutscene does not.
Screens taught with `teach` win over every other sign. Menu-o-matiC and Move-o-matiC add this verdict when they get
lost, so the report says "loading" or "cutscene" instead of only "wrong screen". One JSON line out.
"""
import argparse
import json
import os
import re
import sys
import threading
import time

import mom_route as R
import mom_state as S
from mom_run import say

# ---- Settings ----------------------------------------------------------------
LOOKS = 6                  # small captures per watch
POKE_LOOKS = 4             # captures after the poke key
FROZEN_RECHECK_S = 5.0     # a "frozen" verdict is only given if a second look this much later agrees
ROUTES_LOOK_UP = 4         # how many folders up the clone root is looked for (copies of the routes repo)
WATCH_SPARE_S = 15.0       # a watch that has not finished this long after its looks should have: the game is frozen
                           # (Run 5 D4, 2026-11-06: a suspended game made watch wait until it ran again)


def routes_folder():
    """`routes = <folder>` in lanes.conf (the per-game routes, with each game's states.json), or ''"""
    path = os.environ.get("LANES_CONFIG") or os.path.join(os.path.expanduser("~"), ".claude", "lanes.conf")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"^\s*routes\s*=\s*(.*?)\s*(?:\s#.*)?$", line.rstrip("\r\n"))
                if m:
                    return os.path.expanduser(m.group(1).strip().strip('"'))
    except OSError:
        pass
    return ""


def routes_copies(root):
    """the routes folder and every other copy of the same repo beside it in the PC's other clone roots
    (github-backups, github-backups-gu ...). Run 6 F18 (2026-11-06): lanes.conf named the /gu root's copy, which had
    not been pulled since the screens were taught, so watch found nothing; the live copy had them."""
    out = [root]
    here = os.path.normpath(root)
    for _level in range(ROUTES_LOOK_UP):           # the clone root may sit a few folders up (<root>/<repo>/routes)
        parent, lane = os.path.split(here)
        if not lane or not parent or parent == here:
            break
        rel = os.path.relpath(root, here)
        stem = lane.split("-")[0]
        try:
            others = sorted(os.listdir(parent))
        except OSError:
            others = []
        sib = [os.path.join(parent, o, rel) for o in others
               if o != lane and o.split("-")[0] == stem and os.path.isdir(os.path.join(parent, o, rel))]
        if sib:
            return out + sib
        here = parent
    return out


def find_states(window, game=None):
    """the states.json taught for this game: routes/<game>/states.json, or the one whose window matches (Run 5 D1:
    watch did not find a game's taught screens unless told with --states). Every copy of the routes folder on this PC
    is looked at, and the newest file wins."""
    root = routes_folder()
    if not root or not os.path.isdir(root):
        return None
    found = []
    want = (window or "").lower()
    for folder in routes_copies(root):
        names = [game] if game else sorted(os.listdir(folder))
        for name in names:
            p = os.path.join(folder, name, "states.json")
            if os.path.isfile(p) and (game or window_matches(p, want)):
                found.append((os.path.getmtime(p), p))
    return max(found)[1] if found else None


def window_matches(path, want):
    """does this states.json name a window that matches the one being watched?"""
    try:
        with open(path, encoding="utf-8") as f:
            w = (json.load(f).get("window") or "").lower()
    except (OSError, ValueError):
        return False
    return bool(w and (w in want or want in w))


def observe(hwnd, seconds, states=None, poke=None, _second=False):
    """Collect the signs and return (state, why, signs). Used by `watch` and by the replay engine."""
    import ctypes
    import mom_window as W
    if os.name == "nt" and ctypes.windll.user32.IsIconic(hwnd):
        # Run 5 D2: a minimised window has no picture to look at, and watch stopped with an error
        return "minimised", "the window is minimised, so there is nothing on screen to judge (not in front)", {"minimised": True}
    if W.hung(hwnd):   # before any capture: capturing a window that does not answer can wait forever (RE3 2026-11-02)
        return "frozen", "the window does not answer Windows (checked before looking at it)", {"hung": True}
    gap = seconds / max(1, LOOKS - 1)
    read0, cpu0, t0 = W.bytes_read(hwnd), W.cpu_seconds(hwnd), time.time()
    images = []
    for k in range(LOOKS):
        images.append(W.capture(hwnd))
        if k < LOOKS - 1:
            time.sleep(gap)
    read1, cpu1, t1 = W.bytes_read(hwnd), W.cpu_seconds(hwnd), time.time()
    avg, ever = S.motion(images)
    signs = {"letterbox": S.letterbox(images[-1]), "motion": round(avg, 3), "motion_anywhere": round(ever, 3)}
    if read0 is not None and read1 is not None and t1 > t0:
        signs["disk_mb_s"] = round((read1 - read0) / (t1 - t0) / 1e6, 1)
    if cpu0 is not None and cpu1 is not None and t1 > t0:
        signs["cpu_cores"] = round((cpu1 - cpu0) / (t1 - t0), 2)
    signs["hung"] = W.hung(hwnd)
    signs["in_front"] = W.in_front(hwnd)
    if states:
        for name, cp in states["checkpoints"].items():
            if R.matches(states, name, images[-1])[1]:
                signs["taught"] = cp.get("state", name)
                break
    if poke and "taught" not in signs:
        W.tap(poke, hwnd)
        after = [images[-1]]
        for _ in range(POKE_LOOKS):
            time.sleep(gap)
            after.append(W.capture(hwnd))
        signs["poke_answer"] = round(S.motion(after)[0] - avg, 3)
    state, why = S.judge(signs)
    if state == "frozen" and not signs.get("hung") and not _second:
        # a load can sit still for a moment with the processor busy and no disk (RE2 2026-11-02 said "frozen" right at
        # the end of a load): look again a few seconds later and only call it frozen if nothing changed in between
        time.sleep(FROZEN_RECHECK_S)
        again = W.capture(hwnd)
        changed = S.motion([images[-1], again])[0]
        state2, why2, signs2 = observe(hwnd, seconds, states, None, _second=True)
        signs["recheck"] = {"changed_since": round(changed, 3), "state": state2}
        if changed > 0 or state2 != "frozen":
            return "busy (not frozen)", "it looked stuck, but the picture or the signs moved on within a few seconds (loading or thinking)", signs
        why += f"; still the same {FROZEN_RECHECK_S:.0f} s later"
    return state, why, signs


def cmd_watch(a):
    import menu_o_matic as M
    states_file = a.states or find_states(a.window, a.game)
    states = R.load(states_file) if states_file else None
    done = {}

    def work():
        try:
            # Found WITHOUT bringing it to the front (Run 6 F19, 2026-11-06): focusing restored a minimised game before
            # the minimised check could see it, and pulled the game in front of whatever the person was doing. Only a
            # poke (a key sent to the game) needs it in front.
            import mom_window as W
            hwnd = W.find_window(a.window) if not a.poke else M.need_window(a.window)
            if not hwnd:
                say(event="error", error=f"no visible window whose title contains {a.window!r}")
                sys.exit(1)
            done["v"] = observe(hwnd, a.seconds, states, a.poke)
        except RuntimeError as e:   # e.g. "the window has no client area (minimised?)"
            done["v"] = ("minimised" if "client area" in str(e) else "unknown", str(e), {})
        except BaseException as e:  # noqa: BLE001 - reported below, never a crash
            done["e"] = e

    t = threading.Thread(target=work, daemon=True)
    t.start()
    limit = a.seconds * 2 + FROZEN_RECHECK_S + WATCH_SPARE_S
    t.join(limit)
    if t.is_alive():
        say(event="state", state="frozen", why=f"looking at the window did not finish within {limit:.0f} s: the game "
                                               f"is not answering at all (stopped or frozen)", signs={"timed_out": True},
            states=states_file or "")
        sys.stdout.flush()
        os._exit(0)
    if "e" in done:
        raise done["e"]
    state, why, signs = done["v"]
    say(event="state", state=state, why=why, signs=signs, states=states_file or "")


def cmd_teach(a):
    import menu_o_matic as M
    import mom_window as W
    hwnd = M.need_window(a.window)
    try:
        states = R.load(a.file)
    except FileNotFoundError:
        states = R.new_route(a.game or "", a.window, "states")
    region = R.parse_region(a.region)
    sig = R.signature(R.crop(W.capture(hwnd), region))
    name = f"{a.state}_{len(states['checkpoints'])}"
    states["checkpoints"][name] = {"region": region, "sig": sig, "tol": R.DEFAULT_TOLERANCE,
                                   "spot_tol": R.DEFAULT_SPOT_TOLERANCE, "note": a.note, "state": a.state}
    R.save(states, a.file)
    say(event="taught", state=a.state, as_checkpoint=name, file=a.file)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("watch"); s.add_argument("window"); s.add_argument("--seconds", type=float, default=2.0)
    s.add_argument("--states"); s.add_argument("--poke"); s.add_argument("--game")
    s.set_defaults(f=cmd_watch)
    s = sub.add_parser("teach"); s.add_argument("window"); s.add_argument("file"); s.add_argument("state")
    s.add_argument("--region", required=True); s.add_argument("--note", default=""); s.add_argument("--game")
    s.set_defaults(f=cmd_teach)
    a = p.parse_args()
    import mom_window as W
    try:
        a.f(a)
    except W.NotInFront as e:
        say(event="error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
