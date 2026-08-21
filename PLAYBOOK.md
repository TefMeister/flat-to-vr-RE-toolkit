# The Unattempted-Engine VR Playbook

A reusable, point-by-point method for taking a game whose engine **nobody has
ever brought into VR** and getting it there. It is written for the hard case:
no prior art, no existing profile, no one to ask. It has been distilled from
real conversions and is meant to be copied into each project's
`<project>-vr-engine-research` repo and followed at a self-directed pace.

> This document is engine-agnostic. Everything specific to a particular game
> lives beside it in that project's `ENGINE-DOSSIER.md`, filled in from
> `templates/per-engine-research-template.md`.

---

## The North Star (read this before anything else)

**The one milestone that decides everything: the game renders in a headset and
the view tracks the player's head.** Stereo per-eye rendering plus head-tracked
orientation. Nothing else in a VR mod matters until this exists — motion
controllers, full body, weapon interaction, roomscale, comfort options are all
built *on top of* it and are worthless without it.

Therefore the critical path is: **foothold → engine model → own the camera →
stereo → VR + head tracking.** Breadth comes only after that path is walked.
Every phase below is ordered to reach the North Star as directly as correctness
allows. If a phase reveals the North Star is unreachable by our method, we stop
and reassess the whole approach rather than build further on sand.

Two rules that make the difference between this and a doomed attempt:

1. **The keystone is feasibility, not features.** Prove we can own the world's
   camera transform (Phase 4) as early as possible. That single proof is the
   go/no-go for the entire conversion. Do not invest in breadth before it.
2. **Model before you plan; instrument before you assume.** These engines
   repeatedly punish assumptions. Every time a plan has been demolished
   mid-task, the cause was a thin engine model. Map first, let captured data
   correct the model, then plan.

---

## Standing doctrine (applies to every phase, always)

- **Fail-safe or nothing.** Any hook, patch, or override must fall through to
  the stock game on any error and never crash it. Verbose logging, abort-on-
  fail, stock passthrough. A mod that crashes the game is worse than no mod.
- **Instrument → capture → analyse → conclude.** Never conclude from a guess
  when an instrument can measure it. Build the diagnostic, capture real data,
  analyse offline, and let the data overturn assumptions. Expect to be wrong;
  the method is designed to catch it cheaply.
- **Document promptly, not at the end.** After every notable success *or*
  failure, update the project's dev-archive, modding-notes, and this repo's
  dossier. A finding not written down is a finding you will re-derive.
- **No game assets in version control, ever.** Only files we create. Interface
  metadata we generate (export dumps, `.def` files, shader-reflection dumps of
  *names/offsets*, not game shader source) is fine; game content is not.
  `.gitignore` blocks binaries/assets/dumps as a safety net, never as the only
  line of defence.
- **Judge by correctness, not by the dev machine's framerate.** Stereo and
  double-render are inherently heavy and the dev PC is weak. Low FPS on the dev
  box is expected and non-diagnostic; real performance is judged on the target
  hardware. Never "fix" a feature because it is slow on the dev machine.
- **Legal footing.** Non-commercial fan work, requires owning a legitimate
  copy, redistributes no original assets. The RE techniques (DLL proxying,
  hooking, injection, memory patching) resemble malware only in tooling; the
  context is personal modding of games we own.
- **Credit everyone; honour rights-holder removal requests.** Tools, prior
  research, community knowledge, individuals — even inspiration. Maintain a
  "get credited, or ask us to stop" policy and honour requests from actual
  owners/creators.
- **Save a clean resume point whenever a session may end.** Commit, push,
  update the ledger and project memory, so nothing is lost and the next session
  knows exactly where it stands.

---

## Phase 0 — Ground truth and setup

Goal: a legitimate, well-scaffolded starting point and a first read of what we
are dealing with.

- [ ] **0.1 Confirm legitimacy.** We own the game. Record the platform, build,
      and version. Note if it is an unofficial port (e.g. an Xbox→PC port);
      those carry extra fragility and their own legal/attribution nuances.
- [ ] **0.2 Scaffold the repos.** Per the standing 5-repo convention:
      `-mod` (public, release-gated), `-dev-archive` (public), `-modding-notes`
      (public), `-staging` (private, free WIP), and `-vr-engine-research`
      (public — this repo). Local backup clones in the github-backups folder.
- [ ] **0.3 Toolchain.** A working compiler for the mod DLL (verify which is
      actually installed — do not assume MSVC; a mingw/clang toolchain with
      D3D/DX headers is a reliable fallback). A debugger (x64dbg or similar)
      with a scripting/automation bridge. A hex/vt tool. Python for offline
      capture analysis.
- [ ] **0.4 First read of the binary.** Identify: 32- vs 64-bit, size, the
      **renderer API** (scan imports/strings for `d3d11`, `dxgi`, `d3d12`,
      `opengl32`, `vulkan`), companion runtimes (CUDA, audio middleware,
      animation middleware), and whether the engine has a **developer console /
      cvar system** (often the single biggest lever — FOV, camera, HUD, debug).
- [ ] **0.5 Identify the engine lineage.** Strings, build tags, symbol naming,
      middleware, file formats. Knowing the family (id Tech, Unreal, Unity,
      RenderWare, a bespoke console engine, etc.) imports a wealth of prior
      structural knowledge even when no VR work exists for this specific title.
- [ ] **0.6 DRM and anti-debug reconnaissance.** Determine the launch/DRM story
      (Steam CEG, Denuvo, GOG, none). Many DRMs refuse to unwrap under a
      launch-time debugger — the standard workaround is to launch normally, let
      the DRM decrypt in memory, then attach. This also dictates the injection
      strategy: the mod must target the already-unwrapped running process.

**Exit criterion:** we can state the engine family, the render API, the DRM
constraint, and the console/cvar situation, with evidence, in the dossier.

---

## Phase 1 — Foothold: our code running inside the process

Goal: get our own code executing inside the target every frame, safely, with
logging and config.

- [ ] **1.1 Choose an injection vector.** Preferred for zero-injector
      simplicity: a **proxy DLL** — replace a system DLL the game loads (pick
      one with only-named exports that is trivially forwardable and loads
      *after* DRM unwrap; `winmm.dll`, `dinput8.dll`, `version.dll` are common
      choices). Forward **every** export (other loaded modules may import the
      same DLL). Alternatives: a launcher/injector, or an existing framework
      (e.g. a REFramework-class loader) if one fits the API.
- [ ] **1.2 Logging + config + fail-safe scaffold.** A logger to a known path,
      env-var/file-driven config, and the discipline that every future hook
      logs-and-continues. Build this now; everything leans on it.
- [ ] **1.3 Confirm liveness.** Verify our code loads, the game reaches its
      title/menu, and our banner appears in the log. Verify no game files are
      tracked by git and the push-gate on the `-mod` repo is respected.

**Exit criterion:** our DLL is loaded into the running, DRM-unwrapped game and
logs every launch, with the game fully functional.

---

## Phase 2 — The autonomous test harness (the self-driving enabler)

Goal: **remove the human from the measurement loop.** We must be able, entirely
on our own, to launch the game, reach a deterministic in-game scene, move the
camera, and *see* the result by capturing frames — so RE experiments run at our
own pace without anyone describing the screen in real time. Build this early; it
multiplies the speed of every later phase.

- [ ] **2.1 Deterministic launch to a known state.** Script the launch (through
      the store or the raw exe with the right app-id file). Reach a repeatable
      scene without menus where possible: the engine's own console/dev commands
      are the lever — a chapter/level jump command, a "load save" command, a
      free-camera or no-clip cvar, a pause/time-stop cvar. Enumerate these from
      the binary and the community; wire them into the harness.
- [ ] **2.2 Drive input from *inside* the process — not from outside.** External
      synthetic input (SendInput/SendKeys/SetForegroundWindow) is commonly
      rejected by these engines, and they often pause when unfocused. Because we
      are already injected (Phase 1), drive input from within: hook the engine's
      input polling (XInput/DirectInput) and feed synthetic controller/keyboard
      state, or drive the camera directly through the engine's console/cvars or
      its camera-update function. This is the reliable path and it sidesteps the
      focus/pause problem.
- [ ] **2.3 Frame capture to disk.** Copy the back-buffer (or a chosen render
      target) to an image file on demand and on a timer, so we can *read the
      pixels* to judge an experiment instead of asking a person. Include a
      timestamp/label and the current camera/parameters in the filename or a
      sidecar.
- [ ] **2.4 A scripted probe routine + automated comparison.** A canned
      "orbit/walk/look" sequence with deterministic camera poses, plus an
      offline image-diff so a change's visual effect is measured, not eyeballed.
      Where a probe must be witnessed by a human (a headset-only judgement),
      make that explicit and rare.

**Exit criterion:** unattended, we can launch → reach a known scene → move the
camera → capture frames → compare, and thereby answer a rendering question
without a human in the loop. *This is the phase that lets the project proceed at
the model's own pace.*

> Reality note: some judgements (final headset comfort, subtle stereo
> correctness) will always need human eyes. The harness exists to make those the
> exception, not the rule — the vast majority of RE iterations should be
> self-driven and pixel-verified.

---

## Phase 3 — Build the engine model

Goal: a written, evidence-backed model of how one frame is constructed and,
above all, **where the camera and projection maths live**. This is the map the
whole plan is drawn on; do not shortcut it.

- [ ] **3.1 Hook the graphics API boundary.** Present/swapchain, device,
      immediate context. Capture the real device/context/back-buffer/format.
      Determine the threading model: single immediate context, or **deferred
      contexts recording command lists replayed by the immediate context** (a
      common, plan-reshaping structure — the world may be recorded on worker
      threads and replayed, which changes where any override must be applied).
- [ ] **3.2 Inventory the passes by render target.** Log `OMSetRenderTargets` /
      viewport sizes and formats. Separate: main scene (full-res colour+depth),
      shadow passes (depth-only, various square sizes), post/AA (downscaled
      chains; SMAA/TAA), and UI/HUD. Knowing which pass is which is essential —
      each may need different per-eye treatment, and the HUD must stay separate.
- [ ] **3.3 Find how the camera transform reaches the GPU.** The central
      question. Possibilities, from easiest to hardest:
      (a) a shared view/projection constant buffer bound once — easy: override
      it; (b) **per-draw MVP** matrices in each draw's constant buffer
      (id Tech-style renderprog parameters) — no single buffer to override, but
      a uniform escape hatch exists (see 3.4); (c) matrices baked into other
      structures. Use **shader reflection** to read the *names* of constant-
      buffer parameters (compiled shaders carry them) and disassemble the
      world-geometry vertex shader to see exactly which constants produce
      `SV_Position`. Do not trust content-heuristics alone (an orthonormal,
      varying matrix can be a per-object model matrix, not the camera).
- [ ] **3.4 Establish the per-eye override maths.** Whatever the delivery, work
      out the constant transform that converts a stock frame into an eye view.
      For per-draw MVP where every draw ends in `M = P·V·Mmodel`, the whole
      per-object problem collapses: left-multiply every MVP by **one constant
      per-eye matrix** `K_eye = P_eye · T_eye(±IPD/2) · P⁻¹`, identical for all
      draws — no per-object knowledge needed. Identify where the projection `P`
      and FOV come from (a cvar, a reflected `projection` parameter, or
      recoverable from a matched MVP/model pair).
- [ ] **3.5 Understand the constant-buffer *fill* mechanism.** How does per-draw
      data actually get written? Map/DISCARD ring buffers, `UpdateSubresource`,
      D3D11.1 offset binding, or **persistently-mapped buffers written by CPU
      memcpy** (invisible to Map hooks — a real trap; detect it by reading the
      bound buffer's bytes at draw time when no Map is ever seen). This decides
      *where and how* the override is applied, and whether the contents can be
      read cheaply (captured CPU pointer) or need a staging read-back.
- [ ] **3.6 Note the post/AA matrix consumers.** Shaders using
      inverse/previous-frame view-projection (SMAA, motion vectors, TAA) will
      eventually need consistent per-eye treatment. Catalogue them now; defer
      the fix.
- [ ] **3.7 Catalogue the useful cvars/console commands.** FOV, first-person /
      third-person camera, HUD toggle, player-shadow, view nodal offsets,
      view-pitch clamps, debug draws, time-stop. These are the "easy tier" of
      later features and free levers for the harness.

**Exit criterion:** the dossier contains a frame walkthrough, the pass
inventory, the exact camera/projection delivery mechanism with shader evidence,
the fill mechanism, and the per-eye override maths — enough to design the
override without further discovery.

---

## Phase 4 — Keystone proof: own the camera (go/no-go)

Goal: prove, mono and on the flat monitor, that we can take control of the
world's transform. **This is the single feasibility gate for the entire VR
conversion.**

- [ ] **4.1 Apply one constant transform to every world draw.** At the override
      point identified in Phase 3, substitute/patch each world draw's MVP with
      `K · M` for a single constant `K` — start with a **clip-space roll or
      tilt** (needs no projection knowledge; isolates "do we own the matrix"
      from "is our projection right").
- [ ] **4.2 Prove it visibly.** With the override on, the *whole world* visibly
      transforms and returns to normal when off — verified via the Phase 2
      harness (captured frames) or a human glance if unavoidable. Confirm it
      reaches the geometry that actually matters (if the world is recorded on
      deferred contexts, the override must reach those recorded draws, not just
      what the immediate context draws directly).
- [ ] **4.3 Fail-safe under load.** The override runs for thousands of draws per
      frame without crashing, corrupting, or leaking; any miss falls through to
      stock.

**Exit criterion:** the world moves on our command, stably. If this cannot be
achieved, **stop and reassess the injection strategy** before building anything
further — everything downstream depends on this capability.

---

## Phase 5 — Stereo on a flat monitor

Goal: a correct per-eye image pair, validated on the monitor before any headset
is involved (isolates the stereo maths from runtime/compositor concerns).

- [ ] **5.1 Double-render mechanism.** Produce the second eye. Options, chosen
      by what Phase 3 found: re-invoke the engine's scene render with a second
      camera; **re-execute the recorded command lists once per eye**; or replay
      the draw calls with the second eye's matrices bound. Pick per evidence,
      document why.
- [ ] **5.2 Per-eye matrices.** Build real `K_eye` per eye from the engine's FOV
      and aspect; render each eye into its half of the back-buffer (side-by-
      side). Same matrix both eyes first to isolate the double-render mechanics,
      then introduce the IPD offset.
- [ ] **5.3 Validate correctness by eye, not FPS.** A correct SBS pair: matching
      verticals, correct horizontal parallax, no per-object breakage, HUD/post
      handled sanely.

**Exit criterion:** a correct side-by-side stereo pair on the flat monitor.

---

## Phase 6 — VR runtime and head tracking (NUMERO UNO)

Goal: **the game in the headset, tracking the head.** The milestone the whole
project exists to reach.

- [ ] **6.1 Choose the runtime.** OpenVR/SteamVR or OpenXR, matched to the
      target hardware (e.g. a Quest via a streaming link speaks SteamVR).
- [ ] **6.2 Submit per-eye textures to the compositor.** Render each eye into a
      texture the runtime owns/accepts and submit both per frame. Let the
      runtime handle distortion, chromatic correction, and reprojection timing.
- [ ] **6.3 Drive the view from the head pose.** Read the HMD pose each frame.
      **Orientation first** — feeding head yaw/pitch/roll into the per-eye view
      is *head tracking* and is the milestone. Then positional (the translation
      part) for full 6DOF.
- [ ] **6.4 Frame timing and pose sync.** Query pose at the right point, submit
      on the runtime's cadence, avoid judder. This is where comfort is won or
      lost.

**Exit criterion — THE North Star:** the game renders in the headset and the
view tracks the player's head, stably enough to stand in. Reaching this proves
the conversion is real. **If, after honest effort, this is unreachable, the
project's core premise has failed and must be rethought — better to learn it
here than after building features on top.**

---

## Phase 7+ — Everything built on top of VR

Only after Phase 6 works. Each is its own sub-project with its own spec → plan →
build cycle, and each rests entirely on the North Star being real.

- **First-person & view polish:** collapse third-person camera, view height,
  nodal offsets, hide first-person artefacts, comfort options (snap/smooth turn,
  vignette), decouple HUD to a comfortable depth or a world panel.
- **Motion controllers:** map controllers to aim/move; weapon in hand.
- **Interaction & gestures:** two-handing, holsters, manual reload/rack/pump,
  physical melee, item pickup, collision-based door pushing, physical crouch.
- **Body & roomscale:** full body + shadow, roomscale locomotion.
- **3D UI:** ammo counters and readouts placed in the world.

Order these by dependency and by risk; ship the cheap engine-cvar wins early,
save the deep interaction work for last.

---

## Cross-cutting: what goes in the dossier as you learn

Fill `ENGINE-DOSSIER.md` (from the template) continuously, not at the end. The
high-value facts that stop future ambushes:

- Engine family/lineage and render API; module base and ASLR behaviour.
- DRM/anti-debug story and the injection foothold that works.
- Threading model (immediate vs deferred contexts; command lists).
- **Camera/projection delivery mechanism, with shader evidence** — the single
  most important fact.
- Constant-buffer fill mechanism (and any persistent-map trap).
- Pass inventory (scene / shadow / post / UI) with render-target signatures.
- The cvar/console cheat sheet.
- The autonomous-harness recipe that worked for this game.
- Every dead end and false lead, with why it was wrong (these save the most
  time later).
- A blunt **VR-readiness verdict** and the remaining risks.

---

## How to work through this (pacing)

- Walk the critical path (0→6) before breadth. Within a phase, prefer the
  cheapest experiment that answers the question correctly.
- Re-map before re-planning. When a capture contradicts the model, fix the
  model and the dossier first, then adjust the plan — do not push code against a
  known-wrong model.
- Keep a running ledger and a clean resume point at all times.
- Pull a human in only for what genuinely needs eyes (headset judgements, rare
  visual confirmations). Everything else is self-driven via the Phase 2 harness.

---

## Appendix: UEVR and cross-engine VR mods as reference implementations

The playbook above assumes no prior art. Often there is none *for your engine* — but there is
mature, open prior art for the **engine-agnostic half** of the problem, and it is worth mining
as a reference even when it cannot touch your game directly.

**UEVR** (Praydog's Unreal Engine VR injector) is the prime example. It attaches only to
**Unreal Engine 4.8 → 5.x**, using Unreal's own reflection (RTTI/vtable scans for `FSceneView`,
`GEngine`, the `UObject`/`FName` system). If the target is an older Unreal (UE2/UE3) or a
non-Unreal engine, **the injector will not attach and cannot be made to — do not try.** What
transfers is the *architecture and the reusable layers*, as reference, not as code you drop in.

### What in UEVR (and its kin) is reusable — mapped onto the phases

- **Phase 1 (foothold):** the loader/injector pattern and the fail-safe per-frame hook. Generic.
- **Phase 5 (stereo):** the stereo compositor loop — render the frame, capture the
  view-projection, build a per-eye `K_eye`, produce the second eye, submit side-by-side. UEVR's
  per-eye matrix construction and its handling of post/AA history matrices are a worked example
  of Phase 5.
- **Phase 6 (runtime — the North Star):** UEVR's **OpenXR/OpenVR runtime layer is the most
  reusable part of all** — device init, per-eye swapchain/texture submission, HMD pose sampling,
  frame timing and reprojection. This is exactly Phase 6.1–6.4, already solved in the open,
  independent of which engine drew the frame.
- **Cross-cutting VR math:** projection-matrix decomposition, per-eye FOV/IPD, world-scale,
  decoupled-yaw / roomscale, HUD-to-depth. Pure math; lift the approach freely.

### What is UE-locked — do NOT try to reuse it on a non-UE4/5 engine

- How UEVR *finds* the camera: RTTI/vtable scanning for `FSceneView`, `StereoRenderingDevice`,
  `GEngine`, and the `UObject`/`FName` reflection system. Your engine has none of this — Phase 3
  must find the camera its own way.
- Its native stereo path that flips Unreal's built-in `bIsStereoEnabled`.
- The `UObject`/Blueprint plugin and Lua scripting API.
- Motion-controller injection into Unreal's input pipeline.

The rule: **reuse UEVR's runtime + compositor + math (the engine-agnostic half); ignore its
Unreal-reflection camera plumbing (the engine-locked half).** The "own the camera" keystone
(Phase 4) is always your own work in your engine.

### Pick the right reference for the engine family

- **RE Engine (RE2 / RE3 / etc.):** the correct analog is **REFramework's own VR mod**, not
  UEVR — a purpose-built, turnkey VR path already exists for this family. Prefer it.
- **UE3 (e.g. Enslaved):** no UEVR-for-UE3 exists; UE3 is UE4's direct ancestor, so UEVR is
  useful as *conceptual* reference (view-matrix location, `TArray`/`FName` conventions) but not
  as runnable code.
- **UE2 (e.g. XIII), Dunia (Far Cry 2), id Tech 5 (The Evil Within), bespoke engines
  (Psychonauts):** no turnkey tool; treat Phase 3–4 as a fully manual camera-matrix hunt and
  borrow only UEVR's runtime/compositor/math layers for Phases 5–6.

> Bottom line: a mature cross-engine VR mod is a **reference for the half of the work that is
> the same everywhere**. It never removes the keystone task of owning *your* engine's camera.
