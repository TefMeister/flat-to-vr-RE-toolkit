# openxr-probe — does the VR plumbing hold, with no headset and no game?

One command. Exit code 0 means a runtime accepted a real stereo frame loop; exit 1 means it
did not, and the printout says where it stopped.

```powershell
python xr_probe.py --frames 30 --runtime "..\OpenXR-Simulator\openxr_simulator.json"
python xr_probe.py --frames 30 --json          # machine-readable, for CI or a log
python xr_probe.py --frames 30                 # against whatever runtime the machine has
```

`--runtime` sets `XR_RUNTIME_JSON` **for that process only**, so the machine-wide OpenXR
runtime (Virtual Desktop, SteamVR, Quest Link) is never touched. Prefer it. The simulator's
`activate_simulator.ps1` changes the machine default and needs undoing afterwards.

## What it checks, in order

1. **Extensions.** Which of the six we care about the runtime advertises, and which are missing.
   Missing ones are reported, not fatal — a probe that hides what it found is useless.
2. **Two stereo views**, with each eye's recommended and maximum render target size.
3. **A real session** on the OpenGL path (instance → system → GL context → session → per-eye
   swapchains in sRGB).
4. **Real frames.** `xrWaitFrame`/`xrBeginFrame`/`xrLocateViews`/`xrEndFrame` with a genuine
   projection layer, N times, reporting p50/p95 frame time.
5. **The numbers that matter for stereo**: per-eye FOV in radians, per-eye position, and the
   eye separation derived from them.

Each eye is cleared to a **different colour** (left purple, right green). A stereo capture
showing one colour in both panes means the eyes are not actually separate — that is the point
of the colours, so do not "tidy" them into one clear colour.

## Baseline: OpenXR Simulator 1.0.34 on the dev PC, 2026-09-18

```
stereo views     : 2
   eye 0 target  1280 x 1400 recommended
   eye 0 fov     L-0.9425 R+0.6981 U+0.7676 D-0.9472 rad
   eye 1 fov     L-0.6981 R+0.9425 U+0.7676 D-0.9472 rad
   eye separation 64.0 mm      (eye height 1.700 m, STAGE space)
swapchain format : 0x8c43 (sRGB)
frames           : 30/30 (p50 16.6 ms, p95 19.1 ms)
VERDICT          : PASS
```

Note the FOV is **asymmetric and mirrored** between the eyes — that is correct for a VR headset
and is exactly the shape a naive symmetric projection matrix gets wrong. If a future run comes
back symmetric, the runtime or our maths changed, not the headset.

## Requirements

`pip install pyopenxr` (pulls in glfw, PyOpenGL, numpy). Python 3.10+.

## Credit

The pass/fail-probe idea is **[webhead2oo9](https://github.com/webhead2oo9)**'s, from
`probe/xr_probe.cpp` in his fork of
[OpenXR-Simulator](https://github.com/webhead2oo9/OpenXR-Simulator), where it replays
BetterVR's exact OpenXR sequence and returns an exit code. This is the same idea rewritten in
Python for our own contract. The simulator itself is by
**[fholger](https://github.com/fholger/OpenXR-Simulator)**, extended by
**[elliotttate](https://github.com/elliotttate/OpenXR-Simulator)** and then by webhead2oo9
(Vulkan backend, ten measured headset profiles, real `xrEndFrame` timing, 32-bit runtime, and
the MCP server). MIT licence throughout.

If you should be credited here and are not, email <td3kxlvr@proton.me> and it will be fixed.
