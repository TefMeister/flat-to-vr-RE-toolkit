"""Menu-o-matiC: the route side - checkpoints, screen signatures and route files. No Windows calls here,
so all of it can be tested without a game.

A ROUTE is a recorded way through a game's menus: a list of steps, each one of
    {"key": "enter"}                       press a key
    {"wait": "<checkpoint name>"}          wait until a small patch of screen looks like the saved one
    {"sleep": 2.0}                         just wait
    {"launch": "steam://rungameid/..."}    start something (the game), then wait for its window
A CHECKPOINT is a small rectangle of the window (stored as fractions of its size, so it survives a different
window size) plus a SIGNATURE of what it looked like: the patch shrunk to 32x32 grey levels. Comparing two
signatures is about a thousand subtractions, so waiting for a screen costs nothing - no model looks at
anything until a checkpoint fails. No picture of the game is stored, only those 1,024 numbers.
A patch counts as matching when the AVERAGE difference is small AND no single spot differs a lot: the second
test is what tells "Col 2" from "Col 3", where one digit barely moves the average (2026-09-28).
"""
import json
import os

# ---- Settings ----------------------------------------------------------------
SIG_SIZE = 32            # signature = SIG_SIZE x SIG_SIZE grey levels (16 missed a one-digit change)
DEFAULT_TOLERANCE = 12   # mean grey-level difference (0..255) still counted as "the same screen"
DEFAULT_SPOT_TOLERANCE = 64  # ...and no single spot of the signature may differ by more than this
CHANGE_THRESHOLD = 30    # a pixel whose grey level moved more than this counts as changed
CHANGE_PADDING = 0.02    # grow the changed box by this fraction of the window on each side
GRID_W, GRID_H = 64, 36  # change detection works on cells of 1/64 x 1/36 of the window
CELL_MIN_SHARE = 0.02    # a cell counts as changed when this share of its pixels changed
SCHEMA = "menu-o-matic/1"


# ---- Regions -------------------------------------------------------------------
def parse_region(text):
    """'x,y,w,h' as fractions (0..1) of the window. Returns a list of four floats."""
    parts = [float(v) for v in text.split(",")]
    if len(parts) != 4 or any(v < 0 or v > 1 for v in parts) or parts[2] <= 0 or parts[3] <= 0:
        raise ValueError("a region is four fractions x,y,w,h between 0 and 1, e.g. 0.2,0.4,0.5,0.1")
    return parts


def region_pixels(region, size):
    """Fractions -> a pixel box (left, top, right, bottom) inside an image of `size` (w, h)."""
    width, height = size
    x, y, rw, rh = region
    left, top = int(round(x * width)), int(round(y * height))
    right, bottom = int(round((x + rw) * width)), int(round((y + rh) * height))
    return max(0, left), max(0, top), min(width, max(left + 1, right)), min(height, max(top + 1, bottom))


def crop(image, region):
    return image.crop(region_pixels(region, image.size))


# ---- Signatures ----------------------------------------------------------------
def signature(image):
    """SIG_SIZE x SIG_SIZE grey levels of the image, shrunk."""
    small = image.convert("L").resize((SIG_SIZE, SIG_SIZE))
    return list(small.tobytes())


def distance(sig_a, sig_b):
    """Mean absolute difference, 0 (identical) .. 255."""
    if len(sig_a) != len(sig_b):
        raise ValueError("signatures of different sizes")
    return sum(abs(a - b) for a, b in zip(sig_a, sig_b)) / len(sig_a)


def spot_distance(sig_a, sig_b):
    """The largest difference at any one spot of the signature, 0 .. 255."""
    return max(abs(a - b) for a, b in zip(sig_a, sig_b))


def _changed_cells(a, b):
    """Grid cells (GRID_W x GRID_H) where more than CELL_MIN_SHARE of the pixels changed between a and b."""
    from PIL import ImageChops
    diff = ImageChops.difference(a.convert("L"), b.convert("L"))
    mask = diff.point(lambda v: 255 if v > CHANGE_THRESHOLD else 0)
    # share of changed pixels per cell = the mask shrunk to the grid with area averaging
    grid = mask.resize((GRID_W, GRID_H), resample=3)  # BOX
    return {(x, y) for y in range(GRID_H) for x in range(GRID_W)
            if grid.getpixel((x, y)) > 255 * CELL_MIN_SHARE}


def changed_regions(before, after, noise_before=None):
    """Separate patches (as fractions) that changed between two full captures, biggest first.

    This is the cheap "where are the choices?" step: pressing Down moves the highlight, and the pixels that
    change are exactly the menu lines involved. `noise_before` is a second capture taken a moment before
    `before` with no key pressed; whatever changed between those two is moving by itself (animated
    backgrounds, a blinking cursor) and is ignored. Computed locally; a model only looks at a small crop."""
    cells = _changed_cells(before, after)
    if noise_before is not None:
        noisy = _changed_cells(noise_before, before)
        # one cell of margin: a moving thing seldom fills the same cells twice
        cells -= {(x + dx, y + dy) for x, y in noisy for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    patches, seen = [], set()
    for start in sorted(cells):
        if start in seen:
            continue
        stack, group = [start], []
        seen.add(start)
        while stack:
            x, y = stack.pop()
            group.append((x, y))
            for nx in range(x - 1, x + 2):
                for ny in range(y - 1, y + 2):
                    if (nx, ny) in cells and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
        xs, ys = [c[0] for c in group], [c[1] for c in group]
        left = max(0.0, min(xs) / GRID_W - CHANGE_PADDING)
        top = max(0.0, min(ys) / GRID_H - CHANGE_PADDING)
        right = min(1.0, (max(xs) + 1) / GRID_W + CHANGE_PADDING)
        bottom = min(1.0, (max(ys) + 1) / GRID_H + CHANGE_PADDING)
        patches.append((len(group), [round(left, 4), round(top, 4),
                                     round(right - left, 4), round(bottom - top, 4)]))
    patches.sort(key=lambda p: -p[0])
    return [p[1] for p in patches]


def changed_region(before, after, noise_before=None):
    """The biggest changed patch, or None."""
    patches = changed_regions(before, after, noise_before)
    return patches[0] if patches else None


# ---- Is the picture moving at all? --------------------------------------------------
STILL_DIFFERENCE = 1.5   # whole-window fingerprints closer than this count as "the same picture"


class StillWatch:
    """Tracks how long the whole picture has stayed exactly the same.

    A loading screen with a spinner keeps changing; a frozen game does not. A static loading screen also does
    not, which is why this only EXPLAINS a timeout and never cuts a wait short."""

    def __init__(self):
        self.sig, self.since = None, None

    def update(self, image, now):
        sig = signature(image)
        if self.sig is None or distance(sig, self.sig) > STILL_DIFFERENCE:
            self.sig, self.since = sig, now
        return now - self.since


def parse_point(text):
    """'x,y' as fractions of the window, for a mouse click."""
    parts = [float(v) for v in text.split(",")]
    if len(parts) != 2 or any(v < 0 or v > 1 for v in parts):
        raise ValueError("a point is two fractions x,y between 0 and 1, e.g. 0.5,0.62")
    return parts


# ---- Route files ---------------------------------------------------------------
def new_route(game, window, name):
    return {"schema": SCHEMA, "game": game, "window": window, "route": name, "steps": [], "checkpoints": {}}


def load(path):
    with open(path, encoding="utf-8") as f:
        route = json.load(f)
    if route.get("schema") != SCHEMA:
        raise ValueError(f"{path}: not a {SCHEMA} route file")
    for step in route["steps"]:
        if "wait" in step and step["wait"] not in route["checkpoints"]:
            raise ValueError(f"{path}: step waits for unknown checkpoint {step['wait']!r}")
    return route


def save(route, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(route, f, indent=1)
        f.write("\n")


def add_checkpoint(route, name, region, sig, note="", tolerance=DEFAULT_TOLERANCE,
                   spot_tolerance=DEFAULT_SPOT_TOLERANCE):
    """Store a checkpoint and append a step that waits for it."""
    route["checkpoints"][name] = {"region": region, "sig": sig, "tol": tolerance,
                                  "spot_tol": spot_tolerance, "note": note}
    route["steps"].append({"wait": name})


def matches(route, name, image):
    """(distance, is_match) for checkpoint `name` against a full capture `image`."""
    cp = route["checkpoints"][name]
    now = signature(crop(image, cp["region"]))
    d = distance(now, cp["sig"])
    return d, d <= cp["tol"] and spot_distance(now, cp["sig"]) <= cp.get("spot_tol", DEFAULT_SPOT_TOLERANCE)
