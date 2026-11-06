#!/usr/bin/env python3
"""xr-refused.py: did the headset actually TAKE the frames?  Reads a VR mod's log and says whether the OpenXR
runtime refused frames, so a frame time measured in that run is never mistaken for a speed result.

Why it exists (2026-11-06, Silent Hill 2): UEVR's "Early" sync showed 11.2 ms a frame in the OpenXR Simulator and
9.7 ms on Virtual Desktop, but on Virtual Desktop every frame was refused (xrEndFrame failed:
XR_ERROR_SWAPCHAIN_RECT_INVALID, ~7,900 times) and the headset was black. A frame that never reaches the headset
costs less, so a refused run always looks FASTER. The frame-time line cannot tell; the runtime's answer can.

    python xr-refused.py --uevr SHProto-Win64-Shipping     # UEVR's own log for that game (%APPDATA%/UnrealVRMod)
    python xr-refused.py path/to/log.txt                   # any log that prints OpenXR result codes
    python xr-refused.py log.txt --from 00:59:00 --to 01:04:00   # only the window a frame time was read in

Exit 0 = no frame refused, 3 = frames refused (the frame times are not real), 4 = only the usual start-up blip (a few
frames inside two seconds; frame times after it are real), 2 = no log / nothing to read.
It reads the log only; it never touches the game.
"""
import argparse, collections, os, re, sys

# UEVR: "[VR] xrEndFrame failed: XR_ERROR_SWAPCHAIN_RECT_INVALID"; other mods print the bare result code.
CALL_FAIL = re.compile(r"\b(xr[A-Z]\w*)\b[^\n]*?\b(?:failed|error|returned)\b[^\n]*?\b(XR_(?:ERROR_\w+|FRAME_DISCARDED|SESSION_LOSS_PENDING))")
BARE = re.compile(r"\b(XR_ERROR_\w+|XR_FRAME_DISCARDED)\b")
STAMP = re.compile(r"(\d{4}-\d{2}-\d{2}[ T])?(\d{2}:\d{2}:\d{2})(\.\d+)?")
# calls whose failure means the frame did not reach the headset
FRAME_CALLS = {"xrWaitFrame", "xrBeginFrame", "xrEndFrame", "xrAcquireSwapchainImage", "xrWaitSwapchainImage",
               "xrReleaseSwapchainImage"}
VD_ON = "Detected Virtual Desktop"
STARTUP_MAX = 10        # at most this many refused calls ...
STARTUP_SPAN_S = 2      # ... inside this many seconds count as the start-up hiccup, not a refused run


def secs(hms):
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def uevr_log(game):
    base = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(base, "UnrealVRMod", game, "log.txt")


def stamp_of(line):
    m = STAMP.search(line[:40])
    return m.group(2) if m else None


def in_window(t, lo, hi):
    if t is None:
        return lo is None and hi is None
    return (lo is None or t >= lo) and (hi is None or t <= hi)


def scan(lines, lo=None, hi=None):
    refused = collections.Counter()          # (call, result) -> count, frame calls only
    other = collections.Counter()            # other OpenXR errors (not frame-losing by themselves)
    first = last = None
    vd = None
    for line in lines:
        if VD_ON in line:
            vd = True
        elif "Did not detect Virtual Desktop" in line:
            vd = False
        t = stamp_of(line)
        if (lo or hi) and not in_window(t, lo, hi):
            continue
        m = CALL_FAIL.search(line)
        if m:
            call, res = m.group(1), m.group(2)
            if call in FRAME_CALLS:
                refused[(call, res)] += 1
                first = first or t
                last = t or last
            else:
                other[(call, res)] += 1
            continue
        b = BARE.search(line)
        if b:
            other[("?", b.group(1))] += 1
    return refused, other, first, last, vd


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("log", nargs="?", help="the log file")
    ap.add_argument("--uevr", metavar="GAME", help="read UEVR's log for this game (its folder name in UnrealVRMod)")
    ap.add_argument("--from", dest="lo", metavar="HH:MM:SS", help="only lines from this time")
    ap.add_argument("--to", dest="hi", metavar="HH:MM:SS", help="only lines up to this time")
    a = ap.parse_args()
    path = uevr_log(a.uevr) if a.uevr else a.log
    if not path:
        ap.print_help()
        return 2
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"Cannot read the log: {e}")
        return 2
    refused, other, first, last, vd = scan(lines, a.lo, a.hi)
    where = f" between {a.lo or 'the start'} and {a.hi or 'the end'}" if (a.lo or a.hi) else ""
    total = sum(refused.values())
    # A few frames refused inside two seconds is the usual hiccup while a session starts (UEVR's first frames often get
    # XR_ERROR_TIME_INVALID, seen in a working Silent Hill 2 log of 2026-09-19): measure after it, the run is fine.
    burst = total and total <= STARTUP_MAX and first and last and secs(last) - secs(first) <= STARTUP_SPAN_S
    if burst:
        print(f"STARTUP BLIP: {total} frame call(s) refused in one burst at {first}{where}, the usual hiccup while the "
              f"headset session starts. Frame times read after {last} are real (to check: --from a time after it).")
        for (call, res), n in refused.most_common():
            print(f"  {n:>7,}  {call}: {res}")
    elif total:
        span = f" (first {first}, last {last})" if first else ""
        print(f"REFUSED: the headset runtime refused {total:,} frame call(s){where}{span}. Frames that never reach the "
              "headset cost less, so any frame time from this window is NOT a speed result.")
        for (call, res), n in refused.most_common():
            print(f"  {n:>7,}  {call}: {res}")
    else:
        print(f"CLEAN: no frame refused by the headset runtime{where} ({len(lines):,} log lines read).")
    if other:
        print("Other OpenXR errors (not frame-losing on their own):")
        for (call, res), n in other.most_common(8):
            print(f"  {n:>7,}  {call}: {res}")
    if vd is not None:
        print("UEVR saw Virtual Desktop running (its Virtual-Desktop-only layer was ON: the simulator never takes that path)."
              if vd else "UEVR did not see Virtual Desktop (its Virtual-Desktop-only layer was OFF).")
    return 4 if burst else 3 if total else 0


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
