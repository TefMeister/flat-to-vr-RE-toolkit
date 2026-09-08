"""
hold-pads.py - create N virtual XInput pads and HOLD them until killed.

WHY THIS EXISTS, separately from virtual-pad.py
    virtual-pad.py creates a pad, does one thing with it, and exits - and the pad
    disappears with the process. That is right for "press A", and useless for any
    feature a game gates on HOW MANY CONTROLLERS ARE CONNECTED, because the pads
    must still be there while the game runs.

    The case that prompted it: Mad Max's Video Mode is reported to be "enabled
    when two controllers are connected" (FRAMED screenshot-community guide), and
    Video Mode is the only route that carries a raised Capture Mode FOV back into
    gameplay. On a machine with zero physical pads - which the dev PC is,
    `slots before: []` - that reads as an untestable row. It is not: two virtual
    pads satisfy a count check just as well as two real ones, because the game
    asks XInput, and XInput cannot tell the difference.

    Generalises beyond Mad Max: any "requires a controller" / "requires two
    players" / local-co-op gate is worth trying against this before it is written
    down as needing hardware.

⚠️ WHAT IT DOES NOT PROVE
    That the gate is a COUNT check. If the game instead wants two pads that each
    report real capabilities, or a specific product ID, this will not satisfy it -
    and a negative result here is "two virtual pads did not open it", not
    "two controllers do not open it". Say it that way.

Usage:
    python hold-pads.py 2            # hold 2 pads until Ctrl-C / killed
    python hold-pads.py 2 --seconds 300
"""
import ctypes
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint32), ("wButtons", ctypes.c_uint16),
                ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]


def xinput():
    for dll in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
        try:
            return ctypes.windll.LoadLibrary(dll), dll
        except OSError:
            continue
    raise SystemExit("no XInput DLL found")


def connected(xin):
    out = []
    for i in range(4):
        st = XINPUT_STATE()
        if xin.XInputGetState(i, ctypes.byref(st)) == 0:
            out.append(i)
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    secs = None
    if "--seconds" in sys.argv:
        secs = float(sys.argv[sys.argv.index("--seconds") + 1])

    try:
        import vgamepad
    except ImportError:
        raise SystemExit("pip install vgamepad (and install ViGEmBus)")

    xin, dll = xinput()
    before = connected(xin)
    print("XInput DLL   :", dll)
    print("slots before :", before)

    pads = []
    for _ in range(n):
        p = vgamepad.VX360Gamepad()
        p.reset()
        p.update()
        pads.append(p)
        time.sleep(0.6)

    after = connected(xin)
    print("slots after  :", after)
    new = [s for s in after if s not in before]
    print("created      : %d pad(s) -> new slots %s" % (len(pads), new))
    if len(new) < n:
        print("WARNING: asked for %d, only %d new slot(s) appeared. XInput exposes at "
              "most 4; check for other virtual-pad software." % (n, len(new)))

    if secs:
        print("holding for %.0f s ..." % secs)
        time.sleep(secs)
    else:
        print("holding until killed (Ctrl-C) ...")
        try:
            while True:
                for p in pads:
                    p.update()       # keep the bus from idling the pads out
                time.sleep(2.0)
        except KeyboardInterrupt:
            pass
    print("releasing pads")


main()
