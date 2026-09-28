"""State-o-matiC: the judging side - is the game in a menu, a cutscene, gameplay, or loading?

No game announces its state, so this combines signs that work from outside almost any game:
  - LETTERBOX: black bars at the top and bottom             -> usually a cutscene
  - MOTION: how much of the picture changes between looks   -> gameplay and cutscenes move a lot, menus little
  - SPINNER: only one small patch moves                     -> a loading icon, or an idle menu
  - DISK: how fast the game reads from disk                 -> loading reads hard
  - POKE (optional, it presses a key): does the picture answer a key? -> gameplay answers, cutscenes don't
  - TAUGHT: screens the person showed during setup (checkpoints with a state name) -> the surest sign of all
The signs are pure numbers here, so all of it can be tested with drawn pictures. Every threshold is a named
setting; they were first set from a live game (Burnout Paradise, 2026-09-28) and are meant to be tuned per game.
"""
from PIL import ImageChops, ImageStat

# ---- Settings ----------------------------------------------------------------
THUMB = (64, 36)                  # every look is shrunk to this before judging (cheap, and ignores fine noise)
BAR_SHARE = 0.10                  # the top and bottom bands looked at for letterbox bars
BAR_DARK = 12                     # a band this dark (0..255 mean)...
BAR_FLAT = 6                      # ...and this even (standard deviation) is a black bar
CELL_CHANGED = 12                 # a thumbnail pixel that moved more than this counts as changed
MOVING_SHARE = 0.15               # more than this share of the picture changing = "lots of motion"
STILL_SHARE = 0.01                # less than this = a still picture
SPINNER_MAX_SHARE = 0.06          # motion limited to this share of the picture = "only a small patch moves"
DISK_LOADING_MB_S = 8.0           # reading faster than this = loading (checked against the disk counter)
POKE_ANSWER = 0.05                # the picture must change this much more after a key than without it


def thumb(image):
    return image.convert("L").resize(THUMB)


def letterbox(image):
    """True when the top and bottom bands are flat black (cinema bars)."""
    t = thumb(image)
    w, h = t.size
    band = max(1, int(h * BAR_SHARE))
    for box in ((0, 0, w, band), (0, h - band, w, h)):
        stat = ImageStat.Stat(t.crop(box))
        if stat.mean[0] > BAR_DARK or stat.stddev[0] > BAR_FLAT:
            return False
    return True


def motion(images):
    """(share of the picture that changed between consecutive looks, averaged; share that changed at least once).

    The second number tells a spinner (a small patch that changes every time) from a busy scene."""
    thumbs = [thumb(i) for i in images]
    if len(thumbs) < 2:
        return 0.0, 0.0
    per_step, ever = [], None
    for a, b in zip(thumbs, thumbs[1:]):
        mask = ImageChops.difference(a, b).point(lambda v: 255 if v > CELL_CHANGED else 0)
        share = ImageStat.Stat(mask).mean[0] / 255
        per_step.append(share)
        ever = mask if ever is None else ImageChops.lighter(ever, mask)
    return sum(per_step) / len(per_step), ImageStat.Stat(ever).mean[0] / 255


def judge(signs):
    """Best guess from the signs. Returns (state, why). States: taught name, 'loading', 'cutscene',
    'gameplay', 'moving', 'menu or loading screen', 'still'."""
    if signs.get("taught"):
        return signs["taught"], "matches a screen taught during setup"
    disk = signs.get("disk_mb_s")
    avg, ever = signs["motion"], signs["motion_anywhere"]
    if disk is not None and disk >= DISK_LOADING_MB_S and avg < MOVING_SHARE:
        return "loading", f"reading the disk at {disk:.0f} MB/s while the picture is fairly still"
    if signs["letterbox"]:
        return "cutscene", "black bars at the top and bottom"
    poke = signs.get("poke_answer")
    if poke is not None and poke >= POKE_ANSWER:
        # a still picture that answers a key is gameplay too: a parked car, a character standing still
        # (Burnout, 2026-09-28: the parked view looked exactly like a menu until a key was tried)
        return "gameplay", "the picture answers a key"
    if avg >= MOVING_SHARE:
        if poke is None:
            return "moving", "lots of the picture is moving (gameplay or a cutscene; poke a key to tell them apart)"
        return "cutscene", "the picture moves but does not answer a key"
    if ever <= SPINNER_MAX_SHARE and avg > 0:
        why = "only a small patch moves (a loading icon or a menu highlight)"
        if disk is not None and disk >= DISK_LOADING_MB_S:
            return "loading", why + f", and the disk reads at {disk:.0f} MB/s"
        return "menu or loading screen", why
    if avg < STILL_SHARE:
        return "still", "the picture is not changing (a menu, a paused game, or a frozen one)"
    return "menu or loading screen", "a little of the picture moves"
