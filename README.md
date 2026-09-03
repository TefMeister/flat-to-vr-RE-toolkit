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
| **[tools/](tools/)** | Small scripts written for one game and kept because they generalised — see the table below. |
| **[templates/](templates/)** | `per-engine-research-template.md` (the dossier skeleton) and `new-project-checklist.md` (bootstrap a fresh VR-RE project). |
| **[CREDITS.md](CREDITS.md)** | Everyone whose tools and research this builds on, and how to ask for a correction or removal. |

### `tools/` — our own scripts

Each was written for a specific game, then kept because it turned out to apply generally. All are
PowerShell, no install, no dependencies.

| Script | What it does | Proven on |
|---|---|---|
| [`pe-inspect.ps1`](tools/pe-inspect.ps1) | Check whether a module really exports given symbols; dump bytes at a VA or symbol. Reads the file on disk — no process, no debugger. | XIII, Psychonauts |
| [`list-exports.ps1`](tools/list-exports.ps1) | Enumerate a PE's exports, regex-filtered. Parses the export directory rather than scanning strings, so it can *prove* a symbol is exported. | XIII |
| [`static-disasm.py`](tools/static-disasm.py) | Disassemble a function, follow its calls, or find every reference to an address - straight off the PE on disk. No debugger, no running process, x86 and x64. `func` / `xrefs` / `at` / `info`. **`--raw` reads a memory image dumped from a live process instead**, which is the only way in when the on-disk `.text` is packed. | Psychonauts, Manhunt, XIII |
| [`dxbc-reflect.py`](tools/dxbc-reflect.py) | Read D3D10/11 shader reflection (RDEF) out of any file - shader bundles, pack files, loose `.cso`. Gives constant-buffer names, variable names, byte offsets and sizes, so "which cbuffer holds the view-projection" is answerable off disk. **Works even when the executable is protected**, because shaders are separate data. `list` / `find` / `summary`, plus `bind` (2026-09-03) which reports the register (`b#`) each cbuffer binds to -- the missing half of "which cbuffer, and where do I patch it". `bind` cross-checks every binding name against a real cbuffer in the same shader and says so, because a misread record layout would produce a plausible-looking wrong register. | Mad Max |
| [`dxbc-usage.py`](tools/dxbc-usage.py) | The step after reflection: which shader **stages** declare a cbuffer, and which of its 16-byte slots the code actually **reads** — every DXBC blob split by stage from its RDEF header, disassembled with `fxc -dumpbin`, `cb<N>[slot]` references tallied for the register that cbuffer binds to, sample instructions per slot, and for vertex shaders the cbuffer slots on the register chain feeding `SV_Position`. Added 2026-09-03 after a 4×4-*shaped* run of frame-constant slots turned out to be an offset+scale pair that two slots' worth of shaders never read, while the real clip transform sat at slots 0..3 and varied per pass. Reflection names layouts; this names what the slots *do*. Needs `fxc`. | Mad Max |
| [`d3d9-ctab.py`](tools/d3d9-ctab.py) | The D3D9 counterpart: reads shader constant tables (`CTAB`) - constant names and their **register indices** - off disk. Answers "which constant register holds the view-projection" without a debugger or a capture. `list` / `find` / `summary`. | Alice: Madness Returns |
| [`capture-window.ps1`](tools/capture-window.ps1) | Screenshot one window by process name, including when it is not foreground. | XIII, Psychonauts |
| [`analyze-capture.ps1`](tools/analyze-capture.ps1) | Measure a frame: near-black percentage with **row and column** profiles, or stereo disparity of a side-by-side capture. | Psychonauts |
| [`send-key.ps1`](tools/send-key.ps1) | Synthetic keyboard input by DIK scancode. Usually works where mouse injection does not. | XIII, Psychonauts |
| [`send-mouse.ps1`](tools/send-mouse.ps1) | Relative mouse motion. **Kept mainly as a fast negative** — it cannot beat DirectInput exclusive mode, and one run tells you so. | XIII (failed), Psychonauts (failed) |
| [`unreal-nav.ps1`](tools/unreal-nav.ps1) | Closed-loop navigation from pose telemetry: turn to a heading, walk a measured distance. Lands a heading within ~1°. | XIII |

**A warning worth repeating from inside two of these:** a rotator read from telemetry may already
be *unwrapped*. Applying a shortest-arc wrap to it makes a real −199° turn read as +161°, which
looks exactly like an input reversing direction. Confirm before you wrap.

### `lib/` — reusable C for the proxies themselves

`tools/` is for analysis you run at a terminal. `lib/` is C you compile **into** a proxy DLL.

| file | what it does |
| --- | --- |
| `d3d9ctab.{h,c}` | read a D3D9 shader's constant table (`CTAB`) at `CreateShader` time, and keep a pointer-keyed map of what each shader wants |

**Why it exists.** Every D3D9-era conversion asks the same question at the same moment: *which
register does THIS shader put the camera matrix in?* It cannot be assumed fixed — a skinning palette
displaces it (`alan-wake-vr` c0/c192, `prince-of-persia-2008-vr` c0/c128) and samplers vary too
(`alice-madness-returns-vr` s1/s3/s0/s2). A fixed register corrupts the other half of the corpus
silently, in a way that still renders.

**How it is validated.** It has no test of its own, deliberately — it is exercised by the two
project suites that use it, against **55,803 real shipped shaders** between them, each compared with
an independent Python implementation that finds tables a different way:

- `staging/alan-wake-vr/proxy-d3d9` — 9,971 shaders (`bash build-selftest.sh`)
- `staging/alice-madness-returns-vr/proxy-d3d9` — 45,832 shaders, plus hand-built synthetic
  shaders that exercise the register-set guard (`bash build-stereo-test.sh`)

Both were run before and after the factoring and produce identical numbers in every bucket. If you
change `d3d9ctab.c`, run both.

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
