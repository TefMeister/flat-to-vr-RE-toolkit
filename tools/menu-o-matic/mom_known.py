"""What a game has taught us: one KNOWN.md beside its routes, read before every launch, added to as we learn.

The routes say WHAT to press; KNOWN.md says what was learned getting there: each menu screen and the button that
gets past it, the controls that work (held or tapped, how long), the save spot, the hazards (walls, intro videos,
"keep these settings?" countdowns) and what failed. A session reads it before the game starts, so it already knows
how to reach gameplay, and adds every new thing the same session it learns it, so each run leaves the game easier
to drive than it found it.

    known FOLDER                       print KNOWN.md (made from the template if missing) and the route map
    known FOLDER --add SECTION "TEXT"  add one dated line under a section (Menus, Controls, Save spot, Hazards,
                                       What failed, Tool ideas)

Only game facts belong here: route folders are often shared publicly.
"""
import datetime
import os

SECTIONS = ["Menus", "Controls", "Save spot", "Hazards", "What failed", "Tool ideas"]
FILE_NAME = "KNOWN.md"


def template(game):
    lines = [f"# {game}: what we know about driving it", "",
             "Read before every launch. Add what you learn the same session (`known FOLDER --add ...`).",
             "Only game facts: no paths, machine names or people.", ""]
    for s in SECTIONS:
        lines += [f"## {s}", ""]
    return "\n".join(lines)


def path_of(folder):
    return os.path.join(folder, FILE_NAME)


def ensure(folder):
    """Return KNOWN.md's text, creating it from the template the first time."""
    p = path_of(folder)
    if not os.path.exists(p):
        os.makedirs(folder, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(template(os.path.basename(os.path.normpath(folder))))
    with open(p, encoding="utf-8") as f:
        return f.read()


def match_section(name):
    for s in SECTIONS:
        if s.lower() == name.strip().lower():
            return s
    raise ValueError(f"unknown section {name!r}; use one of: {', '.join(SECTIONS)}")


def add(folder, section, text, today=None):
    """Add '- YYYY-MM-DD: text' at the end of a section. Returns the new file text."""
    section = match_section(section)
    body = ensure(folder)
    stamp = (today or datetime.date.today()).isoformat()
    entry = f"- {stamp}: {text.strip()}"
    lines = body.split("\n")
    head = f"## {section}"
    if head not in lines:
        lines += ["", head, ""]
    i = lines.index(head) + 1
    end = i
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    last = end
    while last > i and lines[last - 1].strip() == "":
        last -= 1
    lines[last:last] = [entry] if last > i else ["", entry]
    out = "\n".join(lines)
    with open(path_of(folder), "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    return out
