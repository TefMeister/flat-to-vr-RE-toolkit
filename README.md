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
   and work top to bottom: scaffold the repos, add the standard `PLAYBOOK.md` pointer file
   (linking back to this toolkit's canonical copy) to the game's `-vr-engine-research` repo,
   and start its dossier from the template.
2. **Setting up a machine?** Follow [`SETUP.md`](SETUP.md) and install the skills in
   [`SKILLS.md`](SKILLS.md).
3. **Working a conversion?** Follow the phases in [`PLAYBOOK.md`](PLAYBOOK.md); reach for
   tools by phase using [`TOOLKIT.md`](TOOLKIT.md).

## Games this kit has been proven on

RE2/RE3 (RE Engine), The Evil Within (id Tech 5 / STEM), XIII (Unreal Engine 2),
Psychonauts (bespoke), Far Cry 2 (Dunia), Enslaved (Unreal Engine 3). The tools listed
here earned their place on those projects — see each tool's "proven on" note in
[`TOOLKIT.md`](TOOLKIT.md).

## Related repositories

- **[flat-to-vr-cross-engine-research](https://github.com/TefMeister/flat-to-vr-cross-engine-research)**
  — the companion repo: a public, engine-agnostic **knowledge library** of publicly-available
  flat→VR info (the tool landscape, the per-engine adapter model + porting checklist, technique
  deep-dives, and worked case studies like RE Engine, Creation Engine 2, and Anvil). Where this
  toolkit is the *method and tooling*, that library is the *public knowledge* behind it. Use the
  two together.

## Scope, ethics, legality

- **Non-commercial fan work.** Requires owning a legitimate copy of any game worked on;
  **redistributes no original game assets** — only files we create. See
  [`.gitignore`](.gitignore).
- The techniques here (DLL proxying, hooking, injection, memory patching, shader
  reflection) resemble malware only in *tooling*; the context is personal modding of
  games we own.
- We **credit everyone** whose work this builds on and **honour correction/removal
  requests from actual rights holders** — see [`CREDITS.md`](CREDITS.md).

## License

The documentation, playbook, and templates in this repository are licensed
**[CC BY 4.0](LICENSE)** (Creative Commons Attribution 4.0) — share and adapt freely
with credit. The same goes for everything else we make (our tooling and our mods):
**free to use with credit.** This covers only the work we authored here; the third-party
tools and frameworks referenced (REFramework, UEVR, MinHook, x64dbg, Superpowers,
EMV-Engine, OpenVR, OpenXR, and the rest in [`CREDITS.md`](CREDITS.md)) remain under their
own licenses and are neither relicensed nor redistributed by this repo.

**How we treat others' work vs. our own:** we *study* everything public and **write every
line of our mods ourselves** by trial and error — we copy no one's source code or files,
regardless of license or price. Our own output, in turn, is yours to build on as long as
you credit us.

## Contributing & policy

See [CONTRIBUTING.md](CONTRIBUTING.md) — how we credit and link sources, our
**study-everything-public but write-our-own-code** rule (we copy no one else's
source code or files, any license or price), the terms for reusing our work
(free, with credit), and how to request a correction or removal.
