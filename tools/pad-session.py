"""
pad-session.py - hold N virtual XInput pads and run a scripted sequence on ONE of
them, capturing the screen between steps.

WHY THIS EXISTS, on top of virtual-pad.py and hold-pads.py
    virtual-pad.py   creates a pad, does one thing, exits (pad dies with it).
    hold-pads.py     holds N pads but drives none of them.
    Neither can do the thing a "second controller" feature actually needs: keep
    BOTH pads present for the whole session while pressing buttons on the SECOND
    one and looking at the screen after each press.

    The case that prompted it: Mad Max's Video Mode exposes a shipped detached
    camera - Increase/Decrease Field Of View, Attach/Detach Camera To Max, Toggle
    Game Camera, Toggle Camera Tracking - all bound to a SECOND controller during
    live gameplay. Pressing them requires two pads to exist and one of them to be
    driven, which is exactly the gap between the two tools above.

METHOD NOTE - why a shot after every step
    A binding that does nothing and a binding that does something you cannot see
    are different findings, and only a frame tells them apart. Each `shot` is
    taken through game-harness.py, i.e. BitBlt, because PrintWindow serves stale
    DWM frames the moment a game stops presenting.

Script syntax (one step per line, '#' comments ignored):
    wait <secs>
    shot <path>
    key <name> <secs>                    keyboard tap via game-harness.py
    press <pad> <BUTTON> <secs>          e.g. press 1 A 0.30
    stick <pad> <left|right> <x> <y> <secs>
    trigger <pad> <left|right> <0..1> <secs>

Usage:
    python pad-session.py <n_pads> <window-substring> <script-file>
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HERE, "game-harness.py")


def main():
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    n = int(sys.argv[1])
    window = sys.argv[2]
    script = sys.argv[3]

    try:
        import vgamepad as vg
    except ImportError:
        raise SystemExit("pip install vgamepad (and install ViGEmBus)")

    buttons = {}
    for name in dir(vg.XUSB_BUTTON):
        if name.startswith("XUSB_GAMEPAD_"):
            buttons[name.replace("XUSB_GAMEPAD_", "")] = getattr(vg.XUSB_BUTTON, name)

    pads = []
    for _ in range(n):
        p = vg.VX360Gamepad()
        p.reset()
        p.update()
        pads.append(p)
        time.sleep(0.6)
    print("created %d pad(s); known buttons: %s" % (n, ",".join(sorted(buttons))))

    with open(script, encoding="utf-8") as fh:
        steps = [ln.strip() for ln in fh if ln.strip() and not ln.strip().startswith("#")]

    for ln in steps:
        parts = ln.split()
        op = parts[0]
        try:
            if op == "wait":
                time.sleep(float(parts[1]))
            elif op == "shot":
                subprocess.run([sys.executable, HARNESS, window, "shot", parts[1]],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("  shot -> %s" % parts[1])
            elif op == "key":
                # A KEYBOARD tap, through the same harness. Needed because the
                # decisive measurement is often not a pixel but a proxy dump
                # triggered by a hotkey - e.g. reading hfov out of the matrix
                # instead of guessing it from how wide the picture looks.
                subprocess.run([sys.executable, HARNESS, window, "hold", parts[1], parts[2]],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("  key %s held %ss" % (parts[1], parts[2]))
            elif op == "press":
                pad = pads[int(parts[1])]
                pad.press_button(button=buttons[parts[2].upper()])
                pad.update()
                time.sleep(float(parts[3]))
                pad.release_button(button=buttons[parts[2].upper()])
                pad.update()
                print("  pad %s: pressed %s for %ss" % (parts[1], parts[2], parts[3]))
            elif op == "stick":
                pad = pads[int(parts[1])]
                fn = pad.left_joystick_float if parts[2] == "left" else pad.right_joystick_float
                fn(x_value_float=float(parts[3]), y_value_float=float(parts[4]))
                pad.update()
                time.sleep(float(parts[5]))
                fn(x_value_float=0.0, y_value_float=0.0)
                pad.update()
                print("  pad %s: %s stick (%s,%s) for %ss"
                      % (parts[1], parts[2], parts[3], parts[4], parts[5]))
            elif op == "trigger":
                pad = pads[int(parts[1])]
                fn = pad.left_trigger_float if parts[2] == "left" else pad.right_trigger_float
                fn(value_float=float(parts[3]))
                pad.update()
                time.sleep(float(parts[4]))
                fn(value_float=0.0)
                pad.update()
                print("  pad %s: %s trigger %s for %ss"
                      % (parts[1], parts[2], parts[3], parts[4]))
            else:
                print("  ?? unknown step: %s" % ln)
        except Exception as exc:                                   # noqa: BLE001
            print("  !! step failed (%s): %s" % (ln, exc))

    for p in pads:
        p.reset()
        p.update()
    print("done; releasing pads")


main()
