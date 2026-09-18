# The Toolkit — tested tools, by job

Every tool below has been used on at least one of our real conversions. For each:
**what it is**, **why we reach for it**, the **[PLAYBOOK.md](PLAYBOOK.md) phase** it
serves, and **which of our games proved it**. If a tool isn't here, we haven't
personally relied on it yet — this list is deliberately "battle-tested only".

Full attribution and links are in [`CREDITS.md`](CREDITS.md).

---

## Turnkey VR frameworks (use these when the engine matches)

Always check for existing prior art *for the engine family* before doing manual work.
When one of these fits, it collapses Phases 1 and 5–6 into configuration.

### REFramework — praydog
- **Link:** https://github.com/praydog/REFramework · docs: https://cursey.github.io/reframework-book/ · https://refdocs.praydog.com/
- **What:** Mod loader, Lua/C++ scripting platform, and generic 6DOF VR for **all RE
  Engine games** (RE2/RE3/RE7/RE8/DMC5/MHR/…).
- **Why we use it:** For RE Engine titles it *is* the foothold — it already solves
  injection, the VR runtime, and per-eye rendering. Our RE2/RE3 work builds on top of
  it rather than reimplementing any of it. Its `RE8VR.cpp` / `FirstPerson.cpp` are the
  reference implementations for per-pass render flags and first-person joint handling.
- **Phase:** 1 (foothold), 5–6 (stereo + runtime), and the scripting API for polish.
- **Proven on:** RE2 / RE3 (arcade-controls-re2, RE3VRMODRELOADED work).
- **Docs:** the REFramework Book (Lua API) and refdocs.praydog.com (TDB/VM reference)
  — see `CREDITS.md`.

### UEVR — praydog
- **Link:** https://github.com/praydog/UEVR
- **What:** Unreal Engine VR injector, attaches to **UE 4.8 → 5.x** via Unreal's own
  reflection (RTTI/vtable scans for `FSceneView`, `GEngine`, the `UObject`/`FName`
  system).
- **Why we use it:** When the target *is* modern Unreal, it's turnkey. When it isn't
  (UE2/UE3 or non-Unreal), **it will not attach and cannot be made to** — but its
  **runtime + compositor + VR-math layers are the best open reference** for Phases 5–6
  (per-eye matrix construction, OpenXR/OpenVR submission, HMD pose, frame timing).
  Reuse that engine-agnostic half; ignore its Unreal-reflection camera plumbing.
- **Phase:** 5–6 as a reference implementation; direct use only on UE4.8+.
- **Proven on:** studied as reference for XIII (UE2) and Enslaved (UE3), where it
  cannot attach; see the PLAYBOOK appendix for the reuse/ignore split.

---

## Injection & hooking (Phase 1 foothold, Phase 3–4 overrides)

### Proxy-DLL injection (winmm.dll / dinput8.dll / version.dll)
- **What:** Our default zero-injector foothold — replace a system DLL the game loads,
  forward **every** export, run our code from `DllMain`/first export.
- **Why we use it:** Simplest reliable way to get our code in-process, and it loads
  *after* DRM unwrap so it targets the already-decrypted game. Pick a DLL with
  only-named exports that's trivially forwardable.
- **Phase:** 1. **Proven on:** the manual-engine projects (id Tech 5, Dunia, UE2/UE3
  targets).

### MinHook — TsudaKageyu & contributors
- **Link:** https://github.com/TsudaKageyu/minhook
- **What:** Minimalist x86/x64 function-hooking library (inline trampolines).
- **Why we use it:** The workhorse for hooking the graphics-API boundary
  (Present/swapchain, `OMSetRenderTargets`, device/context calls) and engine functions
  once we're in-process. Small, dependable, easy to vendor into the mod DLL.
- **Phase:** 1–4. **Proven on:** The Evil Within (id Tech 5) and the other manual
  targets.

---

## Debugger & automation (Phase 0 recon, Phase 3 model-building)

### x64dbg — mrexodia, Sigma, torusrxxx & the x64dbg community
- **Link:** https://github.com/x64dbg/x64dbg
- **What:** Open-source x64/x86 debugger for Windows.
- **Why we use it:** First read of the binary (renderer API, strings, console/cvar
  system), DRM/anti-debug recon, and stepping through camera/projection code to find
  where the world transform reaches the GPU.
- **Phase:** 0, 3–4. **Proven on:** all manual-engine projects.

### x64dbg-automate — dariushoule
- **Link:** https://github.com/dariushoule/x64dbg-automate · skills: https://github.com/dariushoule/x64dbg-skills
- **What:** Remote-automation plugin for x64dbg plus a Python client — script the
  debugger instead of clicking.
- **Why we use it:** Lets the *model* drive the debugger: set breakpoints, read memory,
  disassemble, dump state — repeatably and unattended. This is what makes the debugger
  part of the autonomous loop rather than a manual chore.
- **Phase:** 0, 3–4. **Proven on:** the manual-engine RE work.
- **Paired with:** the **x64dbg MCP server** and **x64dbg-skills** — see
  [`SKILLS.md`](SKILLS.md).

### Ghidrust — oofz
- **Link:** https://github.com/oofz/Ghidrust (Apache-2.0)
- **What:** A Rust reverse-engineering toolkit inspired by Ghidra (not a fork): loads PE/ELF,
  runs auto-analysis, lists strings/imports/cross-references, and **decompiles functions to
  pseudo-C**, from a CLI or an **MCP server** a session can call directly.
- **Why we use it:** It reads the game's *compiled* code with nothing running, which x64dbg cannot.
  On `re2.exe` it decompiled the aim-joint setup and joint-constraint functions, and showed that the
  support-hand joint is an *anchor* rather than the weapon-to-hand attach. That turned a dead end
  into a design decision. It was also used in the RE Village sky hunt.
- **Phase:** 0, 3. **Proven on:** RE2 (2026-09-05), RE Village.
- **Setup:** build from source with Rust (`cargo build --release`), then
  `claude mcp add --scope user ghidrust -- <path>/target/release/ghidrust.exe mcp`. See
  [`SETUP.md`](SETUP.md).

---

## VR runtimes (Phase 6 — the North Star)

### OpenVR / SteamVR — Valve
- **Link:** https://github.com/ValveSoftware/openvr
- **What:** VR runtime + compositor. A Quest over a streaming link speaks SteamVR.
- **Why we use it:** The submission target for per-eye textures and the source of HMD
  pose. When we drive the compositor ourselves (non-REFramework engines), this is the
  runtime layer.
- **Phase:** 6. **Proven on:** the RE Engine path (via REFramework) and the target for
  manual conversions.

### OpenXR — The Khronos Group
- **Link:** https://www.khronos.org/openxr/ · SDK: https://github.com/KhronosGroup/OpenXR-SDK
- **What:** Cross-vendor VR runtime standard.
- **Why we use it:** The portable alternative to OpenVR for the runtime layer; UEVR's
  OpenXR path is our reference for how to do per-eye swapchain submission and pose
  sampling cleanly.
- **Phase:** 6. **Decision 2026-09-18:** OpenXR is now our **default output path** for new
  VR work. Reasons: the tooling around it is deeper, Virtual Desktop + Quest 3 is the
  household's actual setup, and OpenXR is what the desktop simulator below can stand in for.

### OpenXR-Simulator — fholger, extended by elliotttate and webhead2oo9
- **Link:** https://github.com/webhead2oo9/OpenXR-Simulator (the fork we use) ·
  original: https://github.com/fholger/OpenXR-Simulator
- **What:** A desktop OpenXR *runtime*. Any OpenXR application launched against it renders
  into a normal resizable window as a side-by-side stereo pair, with mouse/keyboard head
  control. MIT.
- **Why we use it:** It takes the headset out of the inner loop. The fork reproduces the
  measured per-eye FOV, panel resolution and IPD of ten headsets (Quest 2/3/Pro, Index,
  Vive Pro 2, Reverb G2, PS VR2, PICO 4, Bigscreen Beyond), so a projection error that only
  shows at one headset's FOV becomes reproducible at a desk. Frame timing is measured from
  real stereo `xrEndFrame` submissions, not window repaints, and `F3` gives rolling p50/p95.
  It ships a 32-bit runtime too, which several of our targets need.
- **How to use it without disturbing your headset setup:** set `XR_RUNTIME_JSON` for the one
  process, **not** the machine-wide runtime — `activate_simulator.ps1` changes the system
  default and has to be undone afterwards. Per-process leaves Virtual Desktop, SteamVR and
  Quest Link untouched.
- **It also ships an MCP server** (`mcp-server/`): per-eye screenshots, frame diagnostics,
  quad-layer flicker detection, `set_head_pose` / `set_fov` / `set_ipd` /
  `set_headset_profile`, `enable_pose_sweep`, `enable_anaglyph_preview` and `validate_stereo`.
  That is an agent-drivable stereo test rig — it answers the questions a session normally has
  to spend a human's eyes on.
- **The limit:** it is an OpenXR runtime. It does nothing for a mod that renders stereo itself
  into the game's own swapchain. It is a reason to choose OpenXR as the output path, not a
  free win for an existing custom-stereo mod.
- **Phase:** 6. **Proven on:** dev PC, 2026-09-18 — `tools/openxr-probe/` PASS, 30/30 frames,
  two stereo views, asymmetric mirrored FOV, 64.0 mm eye separation, p50 16.6 ms
  `[verified-live 2026-09-18, n=1]`.

---

## Engine-specific Lua toolkits (RE Engine polish, Phase 7)

### EMV-Engine — alphaZomega (alphazolam) · fork: EMV-Engine-SILVER (SilverEzredes)
- **Link:** https://github.com/alphazolam/EMV-Engine · fork: https://github.com/SilverEzredes/EMV-Engine-SILVER
- **What:** A large collection of REFramework Lua scripts (Enhanced Model Viewer,
  console, gravity gun, enemy spawner) and a shared utility library.
- **Why we use it:** A **technique reference** — e.g. a hook-timing technique from its
  live bone-posing tool was studied and reused (as technique, not copied code) for
  posture correction on the RE2 work. The SILVER fork is handy when upstream lags a
  game update.
- **Phase:** 7 (interaction/body polish on RE Engine). **Proven on:** RE2.

---

## Prior VR routes we mined as reference (not dependencies)

These are **closed-source, proprietary/commercial** products. They are not part of any
shipped mod and are listed only as *reference/inspiration* — we note that they exist and
what approach they take, drawn from **publicly available, non-paywalled** information.

> **Safety boundary (applies to everything in this section):** we use **none of their
> code**, decompile nothing, and reproduce **no paywalled or proprietary content** (paid
> builds, patron-only posts, internal docs). What we take is the publicly-known *concept*
> (e.g. "alternate-eye injection exists"), never their implementation. If any owner would
> rather not be referenced at all, we'll remove the mention — see [`CREDITS.md`](CREDITS.md).

### vorpX — Ralf Ostertag / Animation Labs
- **Link:** https://www.vorpx.com · forums: https://www.vorpx.com/forums/ (commercial
  product; **closed source, no public repository**)
- **What:** Commercial VR injection driver with per-game profiles.
- **Why noted:** For some of our targets (e.g. The Evil Within via a Z3D profile) it was
  the *only prior VR route in existence* — useful only to know "some VR path is possible"
  before doing it properly ourselves. We inspect none of its binaries and copy nothing.

### R.E.A.L. VR — Luke Ross
- **Links:** https://github.com/LukeRoss00/gta5-real-mod (the GTA V mod is
  source-**available** but **unlicensed** — all rights reserved by default: viewable, **not**
  reusable) · https://www.patreon.com/realvr. **Availability (verified Aug 2026):** the R.E.A.L.
  framework has been **free with optional donations since 15 March 2026** (formerly paid), after a
  CD Projekt DMCA over the paid Cyberpunk 2077 mod — **Cyberpunk 2077 is excluded** from the free
  release; the GTA V / RDR2 / Mafia mods were earlier pulled after a Take-Two complaint. See
  [Road to VR](https://roadtovr.com/luke-ross-vr-mods-free-cyberpunk-2077/).
- **What:** Alternate-eye (AER) D3D-injection VR mods for AAA games.
- **Why noted:** The *publicly-known concept* of alternate-eye injection is the
  inspiration. Because the GTA V repo carries **no license**, we treat its code as
  look-don't-touch and copy nothing from it; we likewise do not access, unpack, or reuse
  any donation-gated or previously-paid build. Only the idea, which is common knowledge, is
  ours to use.

---

## Utility layer (used throughout)

- **Python 3** — offline capture analysis, image-diffing the autonomous harness's
  frame grabs, and driving x64dbg-automate. **Phase:** 2–4.
- **A C/C++ toolchain with D3D/DX headers** — to build the mod DLL. **Verify what's
  actually installed; do not assume MSVC** — a mingw/clang toolchain with DX headers is
  a reliable fallback. See [`SETUP.md`](SETUP.md). **Phase:** 1 onward.
- **A hex / binary viewer** — quick structural reads of the binary and dumps.
  **Phase:** 0.
- **Blender + Blender MCP** — https://www.blender.org/download/ and
  https://github.com/ahujasid/mcp-for-blender (MIT, ahujasid). Lets a session build and edit 3D
  scenes in a running Blender: weapon remakes, reference props, mesh work with game-format add-ons.
  **Phase:** 7 (polish and assets).

---

## Quick chooser

| Situation | Reach for |
|---|---|
| Target is an **RE Engine** game | REFramework (turnkey), + EMV-Engine techniques for polish |
| Target is **UE 4.8–5.x** | UEVR (turnkey) |
| Target is **older/other engine** (UE2/UE3, id Tech 5, Dunia, bespoke) | Manual path: proxy DLL + MinHook + x64dbg(-automate); borrow UEVR's runtime/compositor/math for Phases 5–6 |
| Need to **find the camera matrix** | x64dbg + x64dbg-automate + shader reflection (Phase 3) |
| Need to **get our code in-process** | Proxy DLL (winmm/dinput8/version), forward all exports |
| Need to **submit to a headset** | OpenVR/SteamVR or OpenXR (Phase 6) |

## Tools we wrote (in `tools/`)

Small, dependency-free PowerShell utilities that earned their place by being used
in real sessions. Rule for this section is the same as the rest of the toolkit:
**only things actually shipped with, not things that seemed like a good idea.**

### `pe-inspect.ps1` — static PE inspection
List/check exports, dump bytes at a virtual address or at an exported symbol.
Reads the file **on disk** — no process, no debugger — so recon works without the
game running, which matters when only the user may launch it.
Use it to confirm a symbol really is exported (a raw string search cannot tell
you that) and to check a function prologue before building an inline hook.

### `capture-window.ps1` — capture a game window to PNG
`PrintWindow` with `PW_RENDERFULLCONTENT`, which works for most D3D windows
and does not need the window foreground. Falls back to a screen copy.
**Use it before every live test.** Inferring game state from a derived number
instead of looking at the frame is a documented way to lose a session.

### `analyze-capture.ps1` — measure a capture
`-Black` reports near-black percentage plus a column profile (measuring
unrendered regions); `-Stereo` reports the horizontal disparity between the two
eyes of a side-by-side capture (measuring the virtual depth of a HUD without a
headset). Its output is **evidence, not a state check** — see above.

### `openxr-probe/xr_probe.py` — will the VR plumbing hold, with no headset and no game?
The one tool here that is Python rather than PowerShell, and the one with dependencies
(`pip install pyopenxr`); it earns the exception because nothing else can answer this
question without a headset. It creates a real OpenXR session against whichever runtime you
point it at, submits N genuine projection-layer frames, and **exits 0 or 1**. The printout
gives the advertised extensions, both eyes' render-target sizes, per-eye FOV and position,
the derived eye separation, the swapchain format, and p50/p95 frame time.

`--runtime <path>` sets `XR_RUNTIME_JSON` **for that process only**, so the machine-wide
runtime is never touched — always prefer it over activating a runtime system-wide.

Each eye is cleared to a different colour on purpose (left purple, right green): a capture
showing one colour in both panes means the eyes are not actually separate. Don't "tidy" that
into a single clear colour.

Idea credit: webhead2oo9's `probe/xr_probe.cpp` — see `CREDITS.md`.
