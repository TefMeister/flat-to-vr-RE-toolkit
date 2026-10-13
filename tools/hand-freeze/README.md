# Hand Freeze — hold both VR controllers still, in any OpenXR game

<img src="app/screenshot_off.png" width="300"> <img src="app/screenshot_on.png" width="300">

A pixel-art desktop app: a round switch (red OFF, fading to green ON), a seconds picker, and three rows,
**LEFT**, **RIGHT** and **BOTH**, each with a snowflake **FREEZE** button and a flame **UNFREEZE** button.
Press FREEZE, hold the controllers where you want the in-game hands, and when the countdown runs out (it
shows in the snowflake, with a beep each second and a long beep at the end) those hands stay exactly
there, fixed in the room, while the game keeps running and the headset keeps tracking. Put the
controllers down, lean in, look at the hands from any side, move sliders with the mouse. UNFREEZE lets
them follow again. Closing the window always unfreezes. A summer scene plays behind it while it is off,
a frozen winter while it is on.

Made for tuning hand and finger poses in our VR mods (2026-10-13), where holding two controllers in
one hand while dragging sliders on the monitor was the only way before.

## Use

1. Double-click **Hand Freeze** on the desktop and press the round switch: **ON**. Leave it on.
2. Start the game. The switch must be on **before** the game starts (OpenXR add-ons load at start); a
   game that was already running needs one restart. The window itself can be opened and closed any time.
3. The bottom line says *Connected: <game>.exe (LR)* once the game asks for a controller pose; L and R
   show which hands it has told apart.
4. Pick the seconds, press a row's snowflake, hold still. The flame lets that row's hands go. **TOP**
   keeps the window above the game.

Switch it **OFF** when you do not need it. While it is on but nothing is frozen it only passes the
game's calls through; while it is off it is not loaded at all.

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
- `app/HandFreeze.cs` starts the app and holds the switch logic; `app/FreezeUi.cs` draws the window by
  hand onto a 210 x 300 canvas and scales it up with hard pixel edges. The backgrounds come from
  `app/make_backgrounds.py` (two looping GIFs); the font is Marcellus, an Optima-like face. All three are
  embedded in the exe. **ON** writes the layer's manifest next to the DLL and
  registers it under `HKCU\Software\Khronos\OpenXR\1\ApiLayers\Implicit` (this Windows user only, no
  admin); **OFF** removes that entry. Freeze/unfreeze go through a 180-byte shared-memory block
  (`shared.h`): a left/right bit mask and a counter per hand, so a newly frozen hand takes a fresh pose
  while one already frozen keeps its own. The layer also reports which game is connected.
- **Which hand is which:** each controller space is sorted once, by the subaction path it was made with
  (`/user/hand/left` or `/right`), else by where its action is bound (`xrEnumerateBoundSourcesForAction`).
  A space whose hand cannot be told is held only by **BOTH**.
- `test/freeze_test.py` proves it end to end with no headset: a small OpenXR app on the
  [OpenXR Simulator](https://github.com/webhead2oo9/OpenXR-Simulator) runs free / frozen / free again
  while the simulated head is moved (MCP `set_head_pose`), and checks the hands move in the room when
  free, do not move at all when held (left only, then both), and do move relative to the head when held.
  `--implicit` tests the layer as the app registers it.

## Tested

`[verified-numerically 2026-10-13, n=3]` on the dev PC with OpenXR Simulator 1.0.34: free phases
0.30–0.58 m of hand movement in the room, frozen phase 0.000000 m while the head moved 0.38–0.58 m
relative to the hands; the third run through the app's own ON switch (implicit layer). v2 (the
pixel window, LEFT/RIGHT/BOTH) `[verified-numerically 2026-10-13, n=1]`: left only held the left hand
at 0.0000 m while the right moved 0.43 m; both held both; the layer told the two hands apart (left 1,
right 1). The window's countdown, freeze and unfreeze were checked by reading the shared block. **Not yet tried in a real
headset or a real game.**

## Limits

- **OpenXR games only.** A game that talks to SteamVR's own OpenVR API (many older VR games, and
  REFramework when set to OpenVR) does not go through OpenXR layers. Our own mods can freeze their
  hands themselves (Visceral RE2 has a tick box for it since b169).
- **64-bit games only** for now; a 32-bit OpenXR game would need a 32-bit build of the layer.
- Hand tracking (finger tracking without controllers) is not held, only controller poses.

## Credit

The font is [Marcellus](https://fonts.google.com/specimen/Marcellus) by Brian J. Bonislawsky
(Astigmatic), SIL Open Font License 1.1 (`app/Marcellus-OFL.txt`).
OpenXR headers in `third_party/openxr/` are from the Khronos Group's
[OpenXR-SDK](https://github.com/KhronosGroup/OpenXR-SDK) (release-1.1.43, Apache-2.0). The test uses
[pyopenxr](https://github.com/cmbruns/pyopenxr) and the OpenXR Simulator by fholger, extended by
elliotttate and webhead2oo9 (MIT).

If you should be credited here and are not, email <td3kxlvr@proton.me> and it will be fixed.
