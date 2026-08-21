# Machine setup — bootstrapping a VR-RE workstation

Everything needed to work a conversion end to end. Ordered roughly by the
[PLAYBOOK.md](PLAYBOOK.md) phase that first needs it. Install the Claude Code skills
separately from [`SKILLS.md`](SKILLS.md).

---

## 0. Recon & analysis

- **A debugger — x64dbg.** Grab a release from https://github.com/x64dbg/x64dbg. Used
  for the first read of the binary (renderer API, strings, console/cvar detection) and
  for DRM/anti-debug recon.
- **x64dbg-automate** — the remote-automation plugin + Python client:
  https://github.com/dariushoule/x64dbg-automate. Follow its README to drop the plugin
  into x64dbg's `plugins` folder and install the Python client. This is the bridge the
  `x64dbg-skills` and the x64dbg MCP server drive.
- **A hex / binary viewer** for quick structural reads and dump inspection.
- **Python 3** on `PATH` — offline capture analysis, frame-diffing, and driving
  x64dbg-automate.

## 1. Building the mod DLL

- **A C/C++ toolchain with Direct3D / DX headers.**
  - **Verify what's actually installed — do not assume MSVC.** A mingw/clang toolchain
    with DX headers is a reliable, proven fallback on our machines.
  - Confirm you can compile a trivial DLL that exports a function and links against the
    D3D/DXGI import libs before starting real work.
- **MinHook** — vendor the source into the mod DLL for function hooking:
  https://github.com/TsudaKageyu/minhook.
- **Injection foothold — proxy DLL.** No install; it's a technique. Build your mod as a
  replacement for a system DLL the game loads (`winmm.dll`, `dinput8.dll`,
  `version.dll` are common), forwarding **every** export. See PLAYBOOK Phase 1.

## 2. Turnkey frameworks (install per target engine)

- **RE Engine target →** REFramework: https://github.com/praydog/REFramework/releases.
  Install per the community VR-setup guide at https://reframework.dev/. Scripting docs:
  the REFramework Book (https://cursey.github.io/reframework-book/) and
  https://refdocs.praydog.com/.
- **UE 4.8–5.x target →** UEVR: https://github.com/praydog/UEVR (praydog). Turnkey for
  modern Unreal only; for older/other engines it's a *reference*, not an install (see
  TOOLKIT and the PLAYBOOK appendix).
- **RE Engine Lua technique reference →** EMV-Engine
  (https://github.com/alphazolam/EMV-Engine) or the SILVER fork.

## 3. VR runtime (Phase 6)

- **SteamVR / OpenVR** — https://github.com/ValveSoftware/openvr. Install SteamVR; a
  Quest over a streaming link (Link/Air Link/Virtual Desktop) presents as SteamVR.
- **OpenXR** — the portable alternative; https://www.khronos.org/openxr/. UEVR's OpenXR
  path is the reference for clean per-eye submission + pose sampling.

## 4. Repos & backups (standing convention)

- **Five repos per game:** `<project>-mod` (public, release-gated),
  `<project>-dev-archive` (public), `<project>-modding-notes` (public),
  `<project>-staging` (**private**, free WIP / cross-machine handoff),
  `<project>-vr-engine-research` (public). See
  [`templates/new-project-checklist.md`](templates/new-project-checklist.md).
- **Local backup clones** of every game-project repo live in
  `D:\claude video game stuff\github-backups\` (create the equivalent folder on a new
  machine). This toolkit repo is cloned there too.
- **GitHub CLI (`gh`)** authenticated for creating and pushing repos.

## 5. Claude Code skills

Install and verify Superpowers, x64dbg-skills, and the x64dbg MCP server per
[`SKILLS.md`](SKILLS.md).

---

## Smoke test

You're ready when you can, on a throwaway target you own:

1. Launch it under (or attach) x64dbg and drive a breakpoint from the Python client.
2. Build a proxy DLL that logs a banner and forwards all exports, drop it beside the
   game, and see the banner in your log with the game fully functional.
3. Bring up SteamVR/OpenXR and confirm the headset is tracked.

If those three work, the foothold + debugger + runtime legs of the PLAYBOOK are all
live and you can start Phase 0 on a real target.
