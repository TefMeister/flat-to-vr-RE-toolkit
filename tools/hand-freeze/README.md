# Hand Freeze — hold both VR controllers still, in any OpenXR game

<img src="app/hand_freeze_preview.png" width="64" align="right">

A desktop app with one switch, a seconds box and two buttons. Press **Freeze controllers**, hold the
controllers where you want the in-game hands, and when the countdown runs out (a beep each second, a
long beep at the end) both hands stay exactly there, fixed in the room, while the game keeps running
and the headset keeps tracking. Put the controllers down, lean in, look at the hands from any side,
move sliders with the mouse. **Unfreeze** lets them follow again. Closing the app always unfreezes.

Made for tuning hand and finger poses in our VR mods (2026-10-13), where holding two controllers in
one hand while dragging sliders on the monitor was the only way before.

## Use

1. Double-click **Hand Freeze** on the desktop and switch it **ON**.
2. Start the game (a game that was already running needs a restart: OpenXR add-ons load at start).
3. The app says *Connected to <game>.exe* once the game asks for a controller pose.
4. Pick the seconds, press **Freeze controllers**, hold still. **Unfreeze** when done.

Switch it **OFF** when you do not need it. While it is on but not frozen it only passes the game's
calls through; while it is off it is not loaded at all.

## Build and install

```
build.bat                                             (VS 2022 Build Tools + Windows' own C# compiler)
powershell -ExecutionPolicy Bypass -File install.ps1  (to %LOCALAPPDATA%\Programs\HandFreeze + desktop icon)
```

`install.ps1 -From <folder>` installs from a folder of built files instead of `dist\`.

## How it works

- `layer/hand_freeze_layer.cpp` is an **OpenXR API layer**: the OpenXR loader puts it between the
  game and the headset's runtime (Virtual Desktop, SteamVR, Quest Link, …). Every space the game
  makes with `xrCreateActionSpace` is a controller pose; the head and room spaces are never touched.
  At the first pose call after a freeze begins it takes each controller's pose in a room-fixed LOCAL
  space of its own. While frozen, every "controller relative to X" answer is computed from that kept
  pose and where X is right now, so a game that asks relative to the head sees the hands stay in the
  room as the head moves (not glued to the face). Velocities are zeroed so nothing reads a swing.
  Covers `xrLocateSpace`, `xrLocateSpaces` and `xrLocateSpacesKHR`.
- `app/HandFreeze.cs` is the WinForms app. **ON** writes the layer's manifest next to the DLL and
  registers it under `HKCU\Software\Khronos\OpenXR\1\ApiLayers\Implicit` (this Windows user only, no
  admin); **OFF** removes that entry. Freeze/unfreeze go through a 168-byte shared-memory block
  (`shared.h`), which the layer also uses to report which game is connected.
- `test/freeze_test.py` proves it end to end with no headset: a small OpenXR app on the
  [OpenXR Simulator](https://github.com/webhead2oo9/OpenXR-Simulator) runs free / frozen / free again
  while the simulated head is moved (MCP `set_head_pose`), and checks the hands move in the room when
  free, do not move at all when frozen, and do move relative to the head when frozen. `--implicit`
  tests the layer as the app registers it.

## Tested

`[verified-numerically 2026-10-13, n=3]` on the dev PC with OpenXR Simulator 1.0.34: free phases
0.30–0.58 m of hand movement in the room, frozen phase 0.000000 m while the head moved 0.38–0.58 m
relative to the hands; the third run through the app's own ON switch (implicit layer). The app's
countdown, freeze and unfreeze were checked by reading the shared block. **Not yet tried in a real
headset or a real game.**

## Limits

- **OpenXR games only.** A game that talks to SteamVR's own OpenVR API (many older VR games, and
  REFramework when set to OpenVR) does not go through OpenXR layers. Our own mods can freeze their
  hands themselves (Visceral RE2 has a tick box for it since b169).
- **64-bit games only** for now; a 32-bit OpenXR game would need a 32-bit build of the layer.
- Hand tracking (finger tracking without controllers) is not held, only controller poses.

## Credit

OpenXR headers in `third_party/openxr/` are from the Khronos Group's
[OpenXR-SDK](https://github.com/KhronosGroup/OpenXR-SDK) (release-1.1.43, Apache-2.0). The test uses
[pyopenxr](https://github.com/cmbruns/pyopenxr) and the OpenXR Simulator by fholger, extended by
elliotttate and webhead2oo9 (MIT).

If you should be credited here and are not, email <(an issue on this repository)> and it will be fixed.
