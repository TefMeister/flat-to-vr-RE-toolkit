"""What a game has taught us: one KNOWN.md beside its routes, read before every launch, added to as we learn.

The routes say WHAT to press; KNOWN.md says what was learned getting there: each menu screen and the button that
gets past it, the controls that work (held or tapped, how long), the save spot, the hazards (walls, intro videos,
"keep these settings?" countdowns) and what failed. A session reads it before the game starts, so it already knows
how to reach gameplay, and adds every new thing the same session it learns it, so each run leaves the game easier
to drive than it found it.

    known FOLDER                       print KNOWN.md (made from the template if missing) and the route map

FOLDER is the game's routes folder, or just its name ("tale-of-two-wastelands"): a bare name is looked up in the
routes folder (LANES_ROUTES, else `routes =` in lanes.conf), never made in the current folder (2026-11-10: a bare
name put a stray game folder on the Desktop). With no routes folder known, a bare name that is not already a route
folder here is refused.
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


def routes_root():
    """The routes folder: LANES_ROUTES, else `routes =` in lanes.conf (LANES_CONFIG, ~/.claude, ~/.config/lanes)."""
    if os.environ.get("LANES_ROUTES"):
        return os.environ["LANES_ROUTES"]
    home = os.path.expanduser("~")
    confs = [os.environ["LANES_CONFIG"]] if os.environ.get("LANES_CONFIG") else \
        [os.path.join(home, ".claude", "lanes.conf"), os.path.join(home, ".config", "lanes", "lanes.conf")]
    for path in confs:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    key, sep, value = line.partition("=")
                    if sep and key.strip() == "routes" and not line.lstrip().startswith("#"):
                        return value.split(" #")[0].strip().strip('"').strip("'")
        except OSError:
            pass
    return ""


def resolve(folder):
    """The folder KNOWN.md belongs in. A path (with a slash, absolute, or starting with '.') is used as given. A bare
    name goes under the routes folder; with none known, it is used only if it is already a route folder here (has
    KNOWN.md or a route file), else ValueError: a typo or a stray name never makes a new folder in the current one."""
    if os.path.isabs(folder) or "/" in folder or "\\" in folder or folder.startswith("."):
        return folder
    root = routes_root()
    if root:
        return os.path.join(root, folder)
    if os.path.isdir(folder) and any(n == FILE_NAME or n.endswith(".json") for n in os.listdir(folder)):
        return folder
    raise ValueError(f"{folder!r} is a bare game name and no routes folder is known: give the game's routes folder "
                     "itself, or set `routes =` in lanes.conf (LANES_ROUTES for one command)")


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
