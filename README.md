# flat-to-vr-RE-toolkit

The must-have tools, skills, and method for reverse-engineering **any** flat game's
engine and bringing it into VR — the reusable half of the work, distilled from real
conversions and containing **only things we have actually used and shipped with**.
Nothing speculative, nothing untested.

This is a cross-project **starter kit**. Each individual game gets its own five
repositories (`-mod`, `-dev-archive`, `-modding-notes`, `-staging`,
`-vr-engine-research`); this repo sits above all of them and holds what is the same
every time: the playbook, the tool list, the Claude Code skills we depend on, the
setup steps, and the templates to spin up a new project.

## What's here

| File | What it is |
|---|---|
| **[PLAYBOOK.md](PLAYBOOK.md)** | The engine-agnostic, phase-by-phase method. One North Star: *the game rendering in a headset with head tracking*, everything else built on top. This is the heart of the kit. |
| **[TOOLKIT.md](TOOLKIT.md)** | The tested tool list — for each tool: what it is, **why we use it**, which playbook phase it serves, and which of our games proved it. |
| **[SKILLS.md](SKILLS.md)** | The Claude Code skills / plugins / MCP servers we rely on, with install and verify steps. |
| **[SETUP.md](SETUP.md)** | Toolchain bootstrap — compiler, hooking library, Python, debugger + automation bridge, injection vectors. |
| **[templates/](templates/)** | `per-engine-research-template.md` (the dossier skeleton) and `new-project-checklist.md` (bootstrap a fresh VR-RE project). |
| **[CREDITS.md](CREDITS.md)** | Everyone whose tools and research this builds on, and how to ask for a correction or removal. |

## How to use it

1. **New game?** Open [`templates/new-project-checklist.md`](templates/new-project-checklist.md)
   and work top to bottom: scaffold the five repos, copy `PLAYBOOK.md` into the game's
   `-vr-engine-research` repo, start its dossier from the template.
2. **Setting up a machine?** Follow [`SETUP.md`](SETUP.md) and install the skills in
   [`SKILLS.md`](SKILLS.md).
3. **Working a conversion?** Follow the phases in [`PLAYBOOK.md`](PLAYBOOK.md); reach for
   tools by phase using [`TOOLKIT.md`](TOOLKIT.md).

## Games this kit has been proven on

RE2/RE3 (RE Engine), The Evil Within (id Tech 5 / STEM), XIII (Unreal Engine 2),
Psychonauts (bespoke), Far Cry 2 (Dunia), Enslaved (Unreal Engine 3). The tools listed
here earned their place on those projects — see each tool's "proven on" note in
[`TOOLKIT.md`](TOOLKIT.md).

## Scope, ethics, legality

- **Non-commercial fan work.** Requires owning a legitimate copy of any game worked on;
  **redistributes no original game assets** — only files we create. See
  [`.gitignore`](.gitignore).
- The techniques here (DLL proxying, hooking, injection, memory patching, shader
  reflection) resemble malware only in *tooling*; the context is personal modding of
  games we own.
- We **credit everyone** whose work this builds on and **honour correction/removal
  requests from actual rights holders** — see [`CREDITS.md`](CREDITS.md).
