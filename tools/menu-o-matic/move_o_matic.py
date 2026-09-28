"""Move-o-matiC - move a game character (or a car) along a recorded route, from a save that always starts in
the same place. Record the moves once; after that every test run replays them with no pictures at all.

Same route files, checkpoints and replay engine as Menu-o-matiC (menu_o_matic.py), plus two movement steps:

    hold   <window> KEYS SECONDS [--route FILE] [--look OUT.png]   hold keys together, e.g. w or w,a
           [--mark NAME --region x,y,w,h [--note ..]]              ...and take a checkpoint THE MOMENT the keys
                                                                    are released (on-screen maps and speedometers
                                                                    often fade a second after you stop)
    turn   <window> DX,DY [--route FILE] [--look OUT.png]          move the mouse (turn the camera)
    ...and every Menu-o-matiC command: look, press, click, mark, check, new, add, run

`--look OUT.png` saves a QUARTER-size picture after the move, so you can see where the character ended up for
about 75 tokens instead of 1,200. Mark a landmark (a sign, a door, a doorway edge) at the end of each stretch;
on replay, that checkpoint proves the character really got there, and if a later test needs more movement, only
the new stretch is recorded and looked at.

A typical test day:  run menus.json walk_to_the_door.json   (menus, then movement, 0 pictures)

Movement is replayed by TIME, so it is only as repeatable as the game: a steady walk replays well, physics and
frame-rate swings less so. That is what the checkpoints are for: a drifted replay stops with "lost" and two
small pictures instead of carrying on somewhere wrong. Exit codes as Menu-o-matiC.
"""
import time

import menu_o_matic as M
import mom_route as R
from mom_run import say

# ---- Settings ----------------------------------------------------------------
LOOK_SCALE = 0.25        # the after-move picture: a quarter of the width and height
MOVE_SETTLE_S = 0.5      # let the camera settle after a move before the picture


def _after(a, hwnd, step):
    import mom_window as W
    marked = None
    if getattr(a, "mark", None):
        if not (a.route and a.region):
            say(event="error", error="--mark needs --route and --region")
            raise SystemExit(1)
        region = R.parse_region(a.region)
        marked = R.signature(R.crop(W.capture(hwnd), region))   # first, before anything fades
    if a.route:
        route = R.load(a.route)
        route["steps"].append(step)
        if marked is not None:
            R.add_checkpoint(route, a.mark, region, marked, a.note, a.tol, a.spot_tol)
        R.save(route, a.route)
    result = dict(event="move", step=step, marked=a.mark if marked is not None else None)
    if a.look:
        time.sleep(MOVE_SETTLE_S)
        img = W.capture(hwnd)
        img.resize((max(1, int(img.width * LOOK_SCALE)), max(1, int(img.height * LOOK_SCALE)))).save(a.look)
        result.update(look=a.look)
    say(**result)


def cmd_hold(a):
    import mom_window as W
    hwnd = M.need_window(a.window)
    keys = [k.strip().lower() for k in a.keys.split(",") if k.strip()]
    unknown = [k for k in keys if k not in W.KEYS]
    if unknown:
        say(event="error", error=f"unknown key(s) {unknown}", known=sorted(W.KEYS))
        raise SystemExit(1)
    W.hold(keys, a.seconds, hwnd)
    _after(a, hwnd, {"hold": keys, "seconds": a.seconds})


def cmd_turn(a):
    import mom_window as W
    hwnd = M.need_window(a.window)
    dx, dy = (int(v) for v in a.by.split(","))
    W.turn(hwnd, dx, dy)
    _after(a, hwnd, {"turn": [dx, dy]})


def register_moves(sub):
    s = sub.add_parser("hold"); s.add_argument("window"); s.add_argument("keys"); s.add_argument("seconds", type=float)
    s.add_argument("--route"); s.add_argument("--look"); s.add_argument("--mark"); s.add_argument("--region")
    s.add_argument("--note", default=""); s.add_argument("--tol", type=float, default=R.DEFAULT_TOLERANCE)
    s.add_argument("--spot-tol", type=float, default=R.DEFAULT_SPOT_TOLERANCE); s.set_defaults(f=cmd_hold)
    s = sub.add_parser("turn"); s.add_argument("window"); s.add_argument("by")
    s.add_argument("--route"); s.add_argument("--look"); s.set_defaults(f=cmd_turn)


if __name__ == "__main__":
    M.main(__doc__, register_moves)
