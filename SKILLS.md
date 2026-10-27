# Claude Code skills, plugins & MCP servers we depend on

These are the Claude Code extensions we actually use to do this work: the ones that, in practice, we would not want
to run a conversion without. Everything below is installed in our working environment; this file exists so a fresh
machine (or a new collaborator) can reproduce the setup and verify it, and so we have one honest record of *why*
each one earns its place.

> Principle: we only add skills/plugins we have used ourselves. New candidates get
> tested on a real task before they're listed here.

The quickest way to get most of them: install **Lanes** (section 4). Its `/lanes:setup` checks what this PC already
has and offers the rest, installing it or giving you the official link. Lanes' own
[`docs/TOOLS.md`](https://github.com/TefMeister/lanes-plugin/blob/main/plugins/lanes/docs/TOOLS.md) lists every
tool it can offer, with its maker; this page keeps to the ones proven on our projects.

| | Name | By | What it adds |
|---|---|---|---|
| 1 | Superpowers | obra | process skills: plan, debug, check |
| 2 | x64dbg-skills | dariushoule | ready-made debugger workflows |
| 3 | x64dbg MCP server | dariushoule | the live debugger, as tools |
| 4 | Lanes | TefMeister (ours) | the session lanes, the board and the VR testing tools |
| 5 | Ghidrust MCP | oofz | decompiling a game's .exe with nothing running |
| 6 | RE Engine MCP | praydog | inside a running RE Engine game |
| 7 | UEVR-MCP | elliotttate | inside a running Unreal game under UEVR |
| 8 | OpenXR Simulator MCP | webhead2oo9 | the pretend headset, driven by the session |
| 9 | Blender MCP | ahujasid | a live Blender |
| 10 | gimp-mcp | maorcc | a live GIMP |

---

## 1. Superpowers — Jesse Vincent (obra) & Prime Radiant

- **What:** A skills framework for Claude Code — a library of process skills
  (brainstorming, systematic-debugging, test-driven-development, writing-plans,
  executing-plans, requesting/receiving-code-review, using-git-worktrees, and more)
  plus the discipline to invoke them.
- **Why we depend on it:** The RE work lives or dies on method — *model before you
  plan, instrument before you assume*. Superpowers' brainstorming and
  systematic-debugging skills are how we keep from building on a thin engine model, and
  writing-plans / executing-plans structure the multi-session conversions. It's the
  process backbone the PLAYBOOK assumes. Lanes' Windows hook wrapper is adapted from it.
- **Repo:** https://github.com/obra/superpowers
- **Install (Claude Code plugin marketplace):**
  ```
  /plugin marketplace add obra/superpowers-marketplace
  /plugin install superpowers
  ```
  Lanes' setup also offers it, once.
- **Verify:** in a new session the `superpowers:using-superpowers` skill loads, and
  `/brainstorming` (and the other `superpowers:*` skills) are listed as available.

---

## 2. x64dbg-skills — dariushoule

- **What:** A set of reverse-engineering skill guides for Claude Code that drive x64dbg
  through the automation bridge — state snapshot/diff, decompile (angr), trace analysis
  (tracealyzer), YARA scanning, OEP finding for packed binaries, and a vuln-hunter.
- **Why we depend on it:** These turn the debugger into something the model can operate
  end-to-end during Phase 0 recon and Phase 3 model-building — snapshot the process
  state, diff before/after a camera move, decompile the function that fills the view
  constant buffer — instead of hand-driving every step.
- **Repo:** https://github.com/dariushoule/x64dbg-skills
- **Depends on:** x64dbg + **x64dbg-automate** installed and a session connected (see
  [`SETUP.md`](SETUP.md) and the MCP server below).
- **Verify:** the `x64dbg-skills:*` skills (e.g. `state-snapshot`, `decompile`,
  `tracealyzer`, `find-oep`) are listed as available.

---

## 3. x64dbg MCP server — dariushoule (part of x64dbg-automate)

- **What:** An MCP server that exposes x64dbg to Claude Code as tools — start/connect a
  session, set breakpoints, read/write memory, disassemble, assemble, step/trace,
  registers, memory map, and more.
- **Why we depend on it:** It's the live control channel between the model and a running
  debuggee. Combined with x64dbg-skills it's how we do unattended debugger work while
  building the engine model (Phase 3) and proving the camera override (Phase 4).
- **Source:** https://github.com/dariushoule/x64dbg-automate
- **Usage note:** `list_sessions` or `start_session` first, then `connect`, before other
  tools. Addresses are hex strings (e.g. `0x7FF6A0001000`). Use `read_memory_many` to
  batch scattered struct-field reads.
- **Verify:** `mcp__x64dbg__*` tools are available and `get_debugger_status` responds
  after a session is connected.

---

## 4. Lanes — TefMeister (ours)

- **What:** A growing collection of tools, skills and programs for Claude Code, primarily meant for flat-to-VR video
  game modding. Named session lanes (`/pd` with nothing running, `/lm` driving the game, `/ms` with you at the
  keyboard, `/gr` and `/sr` research), a shared work board that says what each job needs (no game, the game, the
  headset), the close-out box that says whether everything is on GitHub, Menu-o-matiC and Move-o-matiC for getting
  through a game's menus by themselves, VR Bench and the BeG0nE fault reports for testing VR with nobody in the
  headset, and installers for the other tools on this page. Every feature is optional.
- **Why we depend on it:** It is how all of our projects are run. Several sessions can work at once without treading
  on each other, nothing found in a session is lost, and the method in the PLAYBOOK is built into the commands.
- **Repo:** https://github.com/TefMeister/lanes-plugin
- **Install:**
  ```
  /plugin marketplace add TefMeister/lanes-plugin
  /plugin install lanes@lanes-plugin
  ```
  then `/lanes:setup` in a new session.
- **Verify:** the `lanes:*` commands (`/lanes:setup`, `/lanes:gates`, `/lanes:pd` and the rest) are listed, and a new
  session opens with the plugin's notes.

---

## 5. Ghidrust MCP server — oofz

- **What:** The MCP server built into Ghidrust, a Rust reverse-engineering toolkit inspired by Ghidra: load a PE,
  run auto-analysis, list strings, imports and cross-references, and decompile functions to pseudo-C, as tools.
- **Why we depend on it:** It reads the game's compiled code with nothing running, which is most `/pd` work on a new
  game and something x64dbg cannot do. On RE2 it showed that the support-hand joint is an anchor, not the
  weapon-to-hand attach, which turned a dead end into a design decision. See [`TOOLKIT.md`](TOOLKIT.md).
- **Repo:** https://github.com/oofz/Ghidrust (Apache-2.0)
- **Install:** build with Rust (`cargo build --release`), then
  `claude mcp add --scope user ghidrust -- <clone>/target/release/ghidrust.exe mcp`. Lanes' setup does it for you.
- **Verify:** `mcp__ghidrust__*` tools are available and `server_info` responds.

---

## 6. RE Engine MCP — praydog

- **What:** A C# plugin for REFramework inside any RE Engine game (Resident Evil 2/3/4/7/Village and more) that
  serves the game's live objects on this PC only, plus the MCP server that hands them to Claude: every type,
  singleton, field and method, read and written, any method called, small C# test plugins hot-reloaded with their
  compile errors read back.
- **Why we depend on it:** It replaces guessing what a value means with reading it in the running game. Used on
  RE2 for the Visceral work and on Village for BeG0nE's settings checks.
- **Repo:** https://github.com/praydog/re-engine-mcp (MIT). Needs a nightly REFramework and the .NET 10 SDK.
- **Install:** Lanes' `engine-mcp.py install re` (the PC side) and, from that game's own session only,
  `engine-mcp.py game re <game folder>` (the game side, removed again with `--remove`).
- **Verify:** the connector is listed in `claude mcp list` and answers while the game runs.

---

## 7. UEVR-MCP — elliotttate

- **What:** The same for Unreal Engine 4.22 to 5.5 games running UEVR: every UObject live, Lua run inside the game,
  the headset's and controllers' poses, screenshots from the graphics card, function hooks, a ProcessEvent listener,
  snapshots and diffs, and dumps of the game's class layout.
- **Why we depend on it:** Our Silent Hill 2 (remake) work is a native UEVR plugin; this is how a session reads the
  running game instead of guessing.
- **Repo:** https://github.com/elliotttate/uevr-mcp
- **Install:** Lanes' `engine-mcp.py install uevr`, and `engine-mcp.py game uevr <game .exe>` from that game's own
  session. Only one game with either connector runs at a time: they share a port.
- **Verify:** `mcp__uevr__*` tools are available and `uevr_get_status` responds while the game runs.

---

## 8. OpenXR Simulator MCP — webhead2oo9's fork

- **What:** The MCP server that ships in webhead2oo9's fork of elliotttate's OpenXR Simulator: per-eye screenshots, frame diagnostics, flicker detection, `set_head_pose`,
  `set_fov`, `set_ipd`, `set_headset_profile`, pose sweeps and `validate_stereo`.
- **Why we depend on it:** It is an agent-drivable stereo test rig. A session can move the pretend head, check that
  both eyes are really separate and catch a one-frame flicker without anyone wearing a headset; it is how the
  Condemned 2, Prototype and Metro head-tracking checks were run. See [`TOOLKIT.md`](TOOLKIT.md).
- **Repo:** https://github.com/webhead2oo9/OpenXR-Simulator (MIT)
- **Install:** Lanes' `openxr-sim.py install --fork`, then register its `mcp-server/` as its README says.
- **Verify:** `mcp__openxr-simulator__*` tools are available and `get_session_state` responds while a game runs on it.

---

## 9. Blender MCP — ahujasid

- **What:** Lets a session build and edit 3D scenes in a running Blender: run Python inside it, look at the result,
  import assets.
- **Why we depend on it:** All of our weapon and hand models (Brutal Doom, Ashes 2063, the CubeKit guns) are built in
  Blender with Tefa watching, one step at a time; this is the live link that makes that possible.
- **Repo:** https://github.com/ahujasid/mcp-for-blender (MIT; formerly `blender-mcp`)
- **Install:** its Blender add-on, then `claude mcp add --scope user blender -- uvx mcp-for-blender`. Run only one
  client connected to Blender at a time.
- **Verify:** `mcp__blender__*` tools are available and `get_scene_info` responds with Blender open.

---

## 10. gimp-mcp — maorcc

- **What:** The same live link for GIMP: open, crop, clean, colour-correct and export images while you watch.
- **Why we depend on it:** Cleaning up scanned drawings, textures and screenshots for the projects.
- **Repo:** https://github.com/maorcc/gimp-mcp (GPL-3.0)
- **Install:** clone it, copy its plug-in into GIMP's `plug-ins` folder, then
  `claude mcp add --scope user gimp -- uv run --directory <clone> gimp_mcp_server.py`. In GIMP: Tools → MCP → Start
  MCP Server.
- **Verify:** `gimp` in `claude mcp list`, and its tools respond with the server started in GIMP.

---

## Adding a new skill/plugin to this list

1. Use it on a real task in a real conversion.
2. If it proves it belongs, add it here with **what / why we depend on it / install /
   verify**, exactly like the entries above, and a row in the table at the top.
3. Credit its author in [`CREDITS.md`](CREDITS.md).

Un-tested candidates do not go in this file — the whole point of this toolkit is that
everything in it has been used in anger. Lanes offers more (frame-inspection connectors for PIX and Nsight Graphics, a Unity
connector and others); they move here once they have earned it.
