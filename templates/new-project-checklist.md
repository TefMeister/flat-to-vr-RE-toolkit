# New VR-RE project — bootstrap checklist

Copy this into a new game's `-modding-notes` (or wherever you keep the ledger) and work
top to bottom. It gets a fresh conversion from nothing to "ready to start PLAYBOOK
Phase 0". Replace `<project>` with the game's slug (e.g. `far-cry-2-vr`).

## Legitimacy & scope
- [ ] Confirm we own the game. Record platform, store, build, version.
- [ ] Note if it's an unofficial port (extra fragility + legal/attribution nuance).

## Repos (the standing five, unified naming)
- [ ] `<project>-mod` — **public**, releases only. *Ask before pushing here.*
- [ ] `<project>-dev-archive` — **public**, messy in-progress history.
- [ ] `<project>-modding-notes` — **public**, field notes / progress ledger.
- [ ] `<project>-staging` — **PRIVATE**, all unverified WIP, pushed freely without asking.
- [ ] `<project>-vr-engine-research` — **public**, the distilled engine knowledge.
- [ ] Local backup clones of all five in `D:\claude video game stuff\github-backups\`.

## Seed the research repo
- [ ] Copy `PLAYBOOK.md` from this toolkit into `<project>-vr-engine-research/`.
- [ ] Start `ENGINE-DOSSIER.md` from `templates/per-engine-research-template.md`.
- [ ] Copy `templates/` in as well (per-engine template travels with the repo).
- [ ] Start `CREDITS.md` — the original game's creators + every tool you'll use.
- [ ] Add `.gitignore` from this toolkit (blocks game assets/binaries/dumps).
- [ ] If the engine has strong prior art (e.g. RE Engine → REFramework), add an
      `EXTERNAL-RESOURCES.md` pointing at the authoritative upstream docs.

## Toolchain (see SETUP.md)
- [ ] Debugger (x64dbg) + x64dbg-automate bridge working.
- [ ] Mod-DLL compiler with DX headers verified (build a trivial exporting DLL).
- [ ] Python 3 on PATH for capture analysis.
- [ ] Pick/confirm the injection vector (proxy DLL name) once the binary is read.
- [ ] Claude Code skills installed & verified (see SKILLS.md).

## Ethics & hygiene (never skip)
- [ ] `.gitignore` in place before the first commit — **no game files, ever**.
- [ ] Credit everyone from the start; add the "get credited / ask us to stop" note.
- [ ] Push-gate respected on `-mod` (ask first); `-staging` is free.

## Ready?
When the repos exist, the playbook + dossier are seeded, and the toolchain smoke test
in `SETUP.md` passes, begin **PLAYBOOK Phase 0 — Ground truth and setup**.
