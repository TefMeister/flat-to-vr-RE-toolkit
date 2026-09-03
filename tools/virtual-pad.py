"""
virtual-pad.py - drive a game with a VIRTUAL XInput controller (ViGEmBus).

Why this exists: synthetic keyboard/mouse is easy to ignore. A game that imports
XInput directly (DOOM 2016 does) or that gates a feature behind a CONTROLLER
chord (ENSLAVED's debug free camera does) cannot tell a ViGEm pad from a real
one - the OS reports it through the same XInput API the game already calls, so
focus rules, DirectInput exclusive mode and keyboard layout all stop mattering.

Requirements, both one-time:
  1. ViGEmBus driver  - https://github.com/nefarius/ViGEmBus/releases
     Kernel driver, so it needs an admin install and a UAC click.
     Verify before installing: Get-AuthenticodeSignature should report Valid and
     the signer should be "CN=Nefarius Software Solutions e.U.".
  2. pip install vgamepad     (bundles ViGEmClient)

Verified end to end on the dev PC 2026-09-03: with no real controller attached,
creating a VX360Gamepad made XInput slot 0 appear; left_joystick_float(0.9)
read back as sThumbLX=29490 and XUSB_GAMEPAD_A read back as wButtons=0x1000.

NOTE: this machine also carries an "Oculus Virtual Gamepad Emulation Bus"
(Facebook's own ViGEmBus fork, oculus_vigembus.inf). It is a SEPARATE device and
did not conflict, but if pad creation ever fails on a machine with Oculus
software installed, that is the first thing to look at.

Usage:
    python virtual-pad.py check                 # is the driver there, does a pad appear
    python virtual-pad.py chord LS RS 0.5       # hold both thumbstick clicks (debug-cam chords)
    python virtual-pad.py stick left 0.8 0 1.5  # hold the left stick for N seconds
    python virtual-pad.py button A 0.1
"""
import ctypes, sys, time

BUTTONS = {}          # filled after vgamepad imports


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint32), ("wButtons", ctypes.c_uint16),
                ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]


def xinput():
    for dll in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
        try:
            return ctypes.WinDLL(dll), dll
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


def read(xin, slot):
    st = XINPUT_STATE()
    if xin.XInputGetState(slot, ctypes.byref(st)) != 0:
        return None
    return st


def make_pad():
    try:
        import vgamepad as vg
    except ImportError:
        raise SystemExit("pip install vgamepad")
    for name in dir(vg.XUSB_BUTTON):
        if name.startswith("XUSB_GAMEPAD_"):
            BUTTONS[name.replace("XUSB_GAMEPAD_", "")] = getattr(vg.XUSB_BUTTON, name)
    return vg, vg.VX360Gamepad()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    xin, dll = xinput()
    cmd = sys.argv[1]

    before = connected(xin)
    vg, pad = make_pad()
    time.sleep(1.0)
    after = connected(xin)
    new = [s for s in after if s not in before]
    if cmd == "check":
        print("XInput DLL          :", dll)
        print("slots before        :", before)
        print("slots after new pad :", after, "-> virtual pad on slot", new[0] if new else "NONE")
        if not new:
            raise SystemExit("pad did not appear - is ViGEmBus installed and running?")
        pad.left_joystick_float(x_value_float=0.9, y_value_float=0.0)
        pad.press_button(button=BUTTONS["A"]); pad.update(); time.sleep(0.35)
        st = read(xin, new[0])
        print("readback            : thumbLX=%d buttons=0x%04X (A=0x1000)" % (st.sThumbLX, st.wButtons))
        pad.reset(); pad.update()
        print("OK" if st and st.wButtons == 0x1000 else "UNEXPECTED READBACK")
    elif cmd == "chord":
        names = [a for a in sys.argv[2:] if not a.replace(".", "").isdigit()]
        secs = float(sys.argv[-1]) if sys.argv[-1].replace(".", "").isdigit() else 0.5
        keymap = {"LS": "LEFT_THUMB", "RS": "RIGHT_THUMB"}
        for n in names:
            pad.press_button(button=BUTTONS[keymap.get(n, n)])
        pad.update(); time.sleep(secs)
        pad.reset(); pad.update()
        print("held chord %s for %.2fs" % (names, secs))
    elif cmd == "stick":
        which, x, y, secs = sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
        (pad.left_joystick_float if which == "left" else pad.right_joystick_float)(
            x_value_float=x, y_value_float=y)
        pad.update(); time.sleep(secs)
        pad.reset(); pad.update()
        print("held %s stick (%.2f,%.2f) for %.2fs" % (which, x, y, secs))
    elif cmd == "button":
        name, secs = sys.argv[2], float(sys.argv[3])
        pad.press_button(button=BUTTONS[name]); pad.update(); time.sleep(secs)
        pad.reset(); pad.update()
        print("pressed", name)
    else:
        raise SystemExit("unknown command %r" % cmd)
