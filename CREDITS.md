# Credits & Attribution

This toolkit is a distillation of reverse-engineering and VR-modding work built on the
public research, tools, and creative work of many people who came before us. None of it
would be possible without them. We list every tool, framework, and prior work the kit
depends on or draws from below — by name or handle, as accurately as we could verify —
including those that helped only as inspiration.

If we've missed someone, the omission is a mistake, not a slight. See the "Get
credited, or ask us to stop" section at the bottom.

> No original game files or assets are included in this repository or any of ours. We
> mod games we legitimately own; all rights to those games belong to their owners.

## Tools, frameworks & prior research this toolkit builds on

| Source / Work | Creator(s) | Link |
|---|---|---|
| REFramework — mod loader, Lua/C++ scripting, and generic 6DOF VR for RE Engine games; the foothold for our RE Engine work | praydog | https://github.com/praydog/REFramework |
| The REFramework Book (Lua scripting API docs) | cursey and REFramework contributors | https://cursey.github.io/reframework-book/ |
| REFramework API / TDB / VM reference | praydog and contributors | https://refdocs.praydog.com/ |
| `RE8VR.cpp` / `FirstPerson.cpp` (reference implementations for per-pass render flags & RE2 first-person joint handling) | praydog | https://github.com/praydog/REFramework |
| UEVR — Unreal Engine (4.8–5.x) VR injector; reused as reference for the engine-agnostic runtime/compositor/math layers | praydog | https://github.com/praydog/UEVR |
| MinHook — function-hooking library | Tsuda Kageyu (TsudaKageyu) and contributors | https://github.com/TsudaKageyu/minhook |
| x64dbg — debugger | mrexodia, Sigma, tr4ceflow, Dreg, Nukem, Herz3h, torusrxxx, and the x64dbg contributor community | https://github.com/x64dbg/x64dbg |
| x64dbg-automate — remote-automation plugin + Python client (and the x64dbg MCP server) | dariushoule (Darius Houle) | https://github.com/dariushoule/x64dbg-automate |
| x64dbg-skills — reverse-engineering skill guides for Claude Code | dariushoule (Darius Houle) | https://github.com/dariushoule/x64dbg-skills |
| Superpowers — the Claude Code skills framework we work inside | Jesse Vincent (GitHub: obra) and contributors at Prime Radiant | https://github.com/obra/superpowers |
| EMV-Engine — REFramework Lua toolkit; a hook-timing technique from its bone-posing tool was studied and reused (as technique, not copied code). MIT licensed. | alphaZomega (alphazolam) | https://github.com/alphazolam/EMV-Engine |
| EMV-Engine-SILVER — actively-maintained fork of EMV-Engine | SilverEzredes | https://github.com/SilverEzredes/EMV-Engine-SILVER |
| OpenVR / SteamVR — VR runtime & compositor target | Valve | https://github.com/ValveSoftware/openvr |
| OpenXR — cross-vendor VR runtime standard | The Khronos Group and contributors | https://www.khronos.org/openxr/ |
| R.E.A.L. VR mods (alternate-eye D3D injection *concept* only — GTA V repo is source-available but unlicensed/all-rights-reserved, other titles are paid; no code, paywalled, or proprietary material used) | Luke Ross | https://github.com/LukeRoss00/gta5-real-mod · https://www.patreon.com/realvr |
| vorpX — commercial VR injection driver, referenced only as public prior art (closed source; no code inspected or reused) | Ralf Ostertag / Animation Labs | https://www.vorpx.com |
| AI development assistance | Claude (Anthropic) | https://www.anthropic.com |

Project lead and author: **TefMeister**.

Where a handle or attribution above is uncertain, we've said so or linked the source so
anyone can check it. If you can correct or confirm a detail, please open a GitHub issue
— we'd much rather fix it than leave it wrong.

## Get credited, or ask us to stop

**If you helped and are not credited:** if you contributed anything to this work — code,
research, tools, documentation, or even just an idea that inspired part of it — and you
don't see yourself credited above, that's an oversight on our part, not a judgement
about your contribution. Please open a GitHub issue on this repository and we'll correct
the credits as soon as possible.

**If you want your work removed or not used:** if you're the owner or creator of
something referenced or used here, and you'd rather your work not be referenced in this
project, or you want specific content removed, please tell us by opening a GitHub issue.
We'll honour that request promptly — no argument and no delay — and find another way to
do the job that doesn't rely on your material. This is your work; we're only grateful to
have learned from it.
