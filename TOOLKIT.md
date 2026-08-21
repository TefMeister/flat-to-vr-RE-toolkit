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
- **Phase:** 6.

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
  source-**available** but **unlicensed** — i.e. all rights reserved by default: viewable,
  **not** reusable) · https://www.patreon.com/realvr (the other titles are **paid builds**
  distributed via Patreon).
- **What:** Alternate-eye (AER) D3D-injection VR mods for AAA games.
- **Why noted:** The *publicly-known concept* of alternate-eye injection is the
  inspiration. Because the GTA V repo carries **no license**, we treat its code as
  look-don't-touch and copy nothing from it; we likewise do not access, unpack, or reuse
  any paid build or patron-only material. Only the idea, which is common knowledge, is
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
