#!/usr/bin/env python3
"""test-xr-refused.py: xr-refused.py against three small logs shaped like UEVR's (2026-11-06, Silent Hill 2).
Exit 0 = all passed."""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "xr-refused.py")
ok = bad = 0


def check(name, cond):
    global ok, bad
    if cond:
        ok += 1
    else:
        bad += 1
        print("FAIL:", name)


def run(*args):
    r = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)
    return r.returncode, r.stdout


d = tempfile.mkdtemp()
black = os.path.join(d, "black.txt")      # the 00:55 run: Early sync on Virtual Desktop
with open(black, "w") as f:
    f.write("[2026-11-06 00:55:58.100] [info] [OpenXR] Detected Virtual Desktop, enabling Virtual Desktop fix.\n")
    for s in range(57, 60):
        for _ in range(3):
            f.write(f"[2026-11-06 00:55:{s:02d}.705] [error] [VR] xrEndFrame failed: XR_ERROR_SWAPCHAIN_RECT_INVALID\n")
            f.write(f"[2026-11-06 00:55:{s:02d}.716] [error] [VR] xrBeginFrame failed: XR_FRAME_DISCARDED\n")
clean = os.path.join(d, "clean.txt")      # the 00:59 run: Very Late, picture back
with open(clean, "w") as f:
    f.write("[2026-11-06 00:59:01.000] [info] [OpenXR] Did not detect Virtual Desktop, disabling Virtual Desktop fix.\n")
    f.write("[2026-11-06 00:59:02.000] [info] [VR] frame 100\n")
    f.write("[2026-11-06 00:59:03.000] [error] [VR] xrGetActionStatePose failed: XR_ERROR_PATH_UNSUPPORTED\n")
mixed = os.path.join(d, "mixed.txt")      # refusals only early on, then a clean measuring window
with open(mixed, "w") as f:
    for s in range(0, 30):
        f.write(f"[2026-11-06 01:00:{s:02d}.000] [error] [VR] xrEndFrame failed: XR_ERROR_LAYER_INVALID\n")
    f.write("[2026-11-06 01:05:00.000] [info] [VR] frame 9000\n")

rc, out = run(black)
check("a black run is REFUSED, exit 3", rc == 3 and out.startswith("REFUSED"))
check("it counts both calls", "9  xrEndFrame: XR_ERROR_SWAPCHAIN_RECT_INVALID" in out and "xrBeginFrame: XR_FRAME_DISCARDED" in out)
check("it says the frame times are not real", "NOT a speed result" in out)
check("it gives the first and last time", "first 00:55:57" in out and "last 00:55:59" in out)
check("it notices Virtual Desktop", "Virtual-Desktop-only layer was ON" in out)
rc, out = run(clean)
check("a clean run is CLEAN, exit 0", rc == 0 and out.startswith("CLEAN"))
check("a non-frame error is listed but does not fail the run", "xrGetActionStatePose: XR_ERROR_PATH_UNSUPPORTED" in out)
check("it notices no Virtual Desktop", "layer was OFF" in out)
rc, out = run(mixed, "--from", "01:01:00")
check("a window after the refusals is CLEAN", rc == 0 and "between 01:01:00" in out)
rc, out = run(mixed, "--to", "01:00:30")
check("a window holding them is REFUSED", rc == 3)
blip = os.path.join(d, "blip.txt")        # a working run's start: 4 refusals in one second (SH2 log, 2026-09-19)
with open(blip, "w") as f:
    for ms in (325, 373):
        f.write(f"[2026-09-19 15:04:28.{ms}] [UnrealVR] [error] [VR] xrEndFrame failed: XR_ERROR_TIME_INVALID\n")
        f.write(f"[2026-09-19 15:04:28.{ms}] [UnrealVR] [error] [VR] xrBeginFrame failed: XR_FRAME_DISCARDED\n")
    f.write("[2026-09-19 15:06:00.000] [UnrealVR] [info] [VR] frame 9000\n")
rc, out = run(blip)
check("a start-up blip is not a refused run, exit 4", rc == 4 and out.startswith("STARTUP BLIP"))
check("the UEVR AFW log shape ([UnrealVR] before the level) is read", "xrEndFrame: XR_ERROR_TIME_INVALID" in out)
rc, out = run(os.path.join(d, "missing.txt"))
check("a missing log exits 2", rc == 2)
print(f"test-xr-refused: {ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
