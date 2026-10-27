# New VR-RE project — bootstrap checklist

Copy this into a new game's `modding-notes/` folder (or wherever you keep the ledger) and work
top to bottom. It gets a fresh conversion from nothing to "ready to start PLAYBOOK
Phase 0". Replace `<project>` with the game's slug (e.g. `far-cry-2-vr`). With the
[Lanes](https://github.com/TefMeister/lanes-plugin) plugin, `estate.py project <project>` makes the
repo and its folders for you.

## Legitimacy & scope
- [ ] Confirm we own the game. Record platform, store, build, version.
- [ ] Note if it's an unofficial port (extra fragility + legal/attribution nuance).

## The repo (one per game since 2026-08-30; the folders are added as each is earned)
- [ ] `<project>` — one repo, holding:
  - [ ] `dev-archive/` — the live mod source and its messy history.
  - [ ] `engine-research/` — the distilled engine knowledge (the dossier).
  - [ ] `modding-notes/` — field notes / progress ledger.
  - [ ] `mod/` — release packaging and player-facing docs. *Ask before releasing.*
  - [ ] `external-research/` — public-research leads (written only by research sessions).
- [ ] `staging/<project>/` in the one **PRIVATE** `staging` repo — unverified work and
      hand-over between PCs, pushed freely.
- [ ] A local clone in your backup folder (ours: `D:\claude video game stuff\github-backups\`).

## Seed the research folder
- [ ] Add the standard `PLAYBOOK.md` pointer file to `engine-research/`
      (copy it from any existing project's `engine-research/`; it links back to this
      toolkit's canonical `PLAYBOOK.md` — do not paste the full text).
- [ ] Start `ENGINE-DOSSIER.md` from `templates/per-engine-research-template.md`.
- [ ] Copy `templates/` in as well (per-engine template travels with the repo).
- [ ] Start `CREDITS.md` — the original game's creators + every tool you'll use.
- [ ] Add `.gitignore` from this toolkit (blocks game assets/binaries/dumps).
- [ ] If the engine has strong prior art (e.g. RE Engine → REFramework), add an
      `EXTERNAL-RESOURCES.md` pointing at the authoritative upstream docs.
- [ ] Add an `inbox/` folder with the standard one-paragraph `inbox/README.md`
      (copy it from any existing project's `engine-research/` — it explains the
      hand-off convention between concurrent research and modding sessions).

## Toolchain (see SETUP.md)
- [ ] Debugger (x64dbg) + x64dbg-automate bridge working.
- [ ] Mod-DLL compiler with DX headers verified (build a trivial exporting DLL).
- [ ] Python 3 on PATH for capture analysis.
- [ ] Pick/confirm the injection vector (proxy DLL name) once the binary is read.
- [ ] Claude Code skills installed & verified (see SKILLS.md).

## Ethics & hygiene (never skip)
- [ ] `.gitignore` in place before the first commit — **no game files, ever**.
- [ ] Credit everyone from the start; add the "get credited / ask us to stop" note.
- [ ] Releases from `mod/` only when asked; `staging` is free.

## Ready?
When the repo exists, the playbook + dossier are seeded, and the toolchain smoke test
in `SETUP.md` passes, begin **PLAYBOOK Phase 0 — Ground truth and setup**.
