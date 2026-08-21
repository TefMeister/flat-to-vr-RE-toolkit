# Claude Code skills, plugins & MCP servers we depend on

These are the Claude Code extensions we actually use to do this work — the ones that,
in practice, we would not want to run a conversion without. All three below are already
installed in our working environment; this file exists so a fresh machine (or a new
collaborator) can reproduce the setup and verify it, and so we have one honest record
of *why* each one earns its place.

> Principle: we only add skills/plugins we have used ourselves. New candidates get
> tested on a real task before they're listed here.

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
  process backbone the PLAYBOOK assumes.
- **Repo:** https://github.com/obra/superpowers
- **Install (Claude Code plugin marketplace):**
  ```
  /plugin marketplace add obra/superpowers-marketplace
  /plugin install superpowers
  ```
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

## Adding a new skill/plugin to this list

1. Use it on a real task in a real conversion.
2. If it proves it belongs, add it here with **what / why we depend on it / install /
   verify**, exactly like the entries above.
3. Credit its author in [`CREDITS.md`](CREDITS.md).

Un-tested candidates do not go in this file — the whole point of this toolkit is that
everything in it has been used in anger.
