"""State-o-matiC - what is the game doing right now: main menu, cutscene, gameplay, or loading?

    watch <window> [--seconds 2] [--states FILE] [--poke KEY]   look for a moment and give a verdict with reasons
    teach <window> FILE STATE --region x,y,w,h [--note ..]      store a screen the person names ("main_menu",
                                                                "gameplay"...) so watch can recognise it for sure

`watch` takes a few small looks over a couple of seconds (shrunk to 64x36, judged on this PC, no model involved)
and reads how fast the game is reading its disk. With `--poke KEY` it also presses a harmless key (the person names
one during setup, e.g. a camera key) to see whether the picture answers: gameplay does, a cutscene does not.
Screens taught with `teach` win over every other sign. Menu-o-matiC and Move-o-matiC add this verdict when they get
lost, so the report says "loading" or "cutscene" instead of only "wrong screen". One JSON line out.
"""
import argparse
import sys
import time

import mom_route as R
import mom_state as S
from mom_run import say

# ---- Settings ----------------------------------------------------------------
LOOKS = 6                  # small captures per watch
POKE_LOOKS = 4             # captures after the poke key


def observe(hwnd, seconds, states=None, poke=None):
    """Collect the signs and return (state, why, signs). Used by `watch` and by the replay engine."""
    import mom_window as W
    gap = seconds / max(1, LOOKS - 1)
    read0, t0 = W.bytes_read(hwnd), time.time()
    images = []
    for k in range(LOOKS):
        images.append(W.capture(hwnd))
        if k < LOOKS - 1:
            time.sleep(gap)
    read1, t1 = W.bytes_read(hwnd), time.time()
    avg, ever = S.motion(images)
    signs = {"letterbox": S.letterbox(images[-1]), "motion": round(avg, 3), "motion_anywhere": round(ever, 3)}
    if read0 is not None and read1 is not None and t1 > t0:
        signs["disk_mb_s"] = round((read1 - read0) / (t1 - t0) / 1e6, 1)
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
    return state, why, signs


def cmd_watch(a):
    import menu_o_matic as M
    hwnd = M.need_window(a.window)
    states = R.load(a.states) if a.states else None
    state, why, signs = observe(hwnd, a.seconds, states, a.poke)
    say(event="state", state=state, why=why, signs=signs)


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
    s.add_argument("--states"); s.add_argument("--poke"); s.set_defaults(f=cmd_watch)
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
