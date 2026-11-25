"""State-o-matiC: the judging side - is the game in a menu, a cutscene, gameplay, or loading?

No game announces its state, so this combines signs that work from outside almost any game:
  - LETTERBOX: black bars at the top and bottom             -> usually a cutscene
  - MOTION: how much of the picture changes between looks   -> gameplay and cutscenes move a lot, menus little
  - SPINNER: only one small patch moves                     -> a loading icon, or an idle menu
  - DISK: how fast the game reads from disk                 -> loading reads hard
  - POKE (optional, it presses a key): does the picture answer a key? -> gameplay answers, cutscenes don't
  - TAUGHT: screens the person showed during setup (checkpoints with a state name) -> the surest sign of all
  - HUNG: Windows says the window stopped answering            -> frozen
  - CPU: how many processor cores the game keeps busy         -> a picture that never changes, no disk reads and
    cores still burning is a game stuck in a loop (RE2 2026-11-02: frozen at its "NOW 10%" loading text for minutes,
    2.0 cores busy, 0 MB/s, every pixel still, and Windows still called it responding)
  - IN FRONT: is the window the foreground one               -> RE Engine games pause when it is not
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
FROZEN_BUSY_CORES = 1.5          # a picture where NOTHING changes, no disk, and at least this many cores busy = stuck
                                  # (RE2 2026-11-02 froze at 2.0; a still menu in front measured ~0.3-1 elsewhere)
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
    'gameplay', 'moving', 'menu or loading screen', 'still', 'frozen', 'paused'."""
    if signs.get("taught"):
        return signs["taught"], "matches a screen taught during setup"
    if signs.get("hung"):
        return "frozen", "Windows says the window has stopped answering"
    still_all = signs["motion_anywhere"] == 0.0
    cores, disk0 = signs.get("cpu_cores"), signs.get("disk_mb_s")
    if still_all and signs.get("in_front", True) and cores is not None and cores >= FROZEN_BUSY_CORES and (disk0 or 0) < 1.0:
        # 2026-11-04 (Village): a player standing still in gameplay, or a chapter card waiting for a key, looks exactly
        # like this (still picture, no disk, 3-4 cores drawing the same frame) and the window answers. Only a poke that
        # gets no answer, or Windows saying the window hangs (above), proves a freeze.
        if signs.get("poke_answer") is not None and signs["poke_answer"] <= 0.0:
            return "frozen", (f"nothing on screen changes, nothing is read from disk, a key press changed nothing, yet the game "
                              f"keeps {cores:.1f} cores busy: stuck in a loop (a script or mod call that never returns is the "
                              "usual cause)")
        return "still", (f"nothing on screen changes and nothing is read from disk while the game keeps {cores:.1f} cores busy "
                         "and the window answers: an idle player, or a screen waiting for a key; a frozen game looks the same "
                         "until a poke (--poke KEY) gets no answer")
    if still_all and signs.get("in_front") is False:
        return "paused", "the window is not in front, and many games (every RE Engine one) pause until it is"
    disk = signs.get("disk_mb_s")
    avg, ever = signs["motion"], signs["motion_anywhere"]
    # 0.119.0: a game that streams from disk all through play (Resident Evil 4, 170-180 MB/s walking in the village,
    # Developer PC 2026-11-19) was called "loading". A game's states.json may set its own `disk_loading_mb_s`, and a
    # picture that answers a key is gameplay whatever the disk does.
    disk_limit = signs.get("disk_loading_mb_s") or DISK_LOADING_MB_S
    poke = signs.get("poke_answer")
    if poke is not None and poke >= POKE_ANSWER:
        # a still picture that answers a key is gameplay too: a parked car, a character standing still
        # (Burnout, 2026-09-28: the parked view looked exactly like a menu until a key was tried)
        return "gameplay", "the picture answers a key"
    if disk is not None and disk >= disk_limit and avg < MOVING_SHARE:
        return "loading", f"reading the disk at {disk:.0f} MB/s while the picture is fairly still"
    if signs["letterbox"]:
        return "cutscene", "black bars at the top and bottom"
    if avg >= MOVING_SHARE:
        if poke is None:
            return "moving", "lots of the picture is moving (gameplay or a cutscene; poke a key to tell them apart)"
        return "cutscene", "the picture moves but does not answer a key"
    if ever <= SPINNER_MAX_SHARE and avg > 0:
        why = "only a small patch moves (a loading icon or a menu highlight)"
        if disk is not None and disk >= disk_limit:
            return "loading", why + f", and the disk reads at {disk:.0f} MB/s"
        return "menu or loading screen", why
    if avg < STILL_SHARE:
        return "still", "the picture is not changing (a menu, a paused game, or a frozen one)"
    return "menu or loading screen", "a little of the picture moves"


# ---- Why a frozen game is frozen (2026-11-23) ------------------------------------------------------------------------
# "frozen" alone left the session guessing whether its own change had hung the game. Some freezes have a signature in a
# file beside the game; each entry here is one that was seen, with what it means and what to do. Asked for by the
# maintainer after a black, hung window: "report this to state-o-matic to learn from".
LOADER_LOG = "re2_framework_log.txt"      # REFramework writes its log under this name for every RE Engine game
LOADER_LOG_QUIET_S = 20.0                 # the log has stood still this long
LOADER_READY_TEXT = "textures have been setup"


def frozen_cause(game_dir, now=None):
    """Why is the frozen game in this folder frozen, if a known signature says so? -> dict(cause, why, do) or None.

    Known so far: REFramework's own start-up deadlock (Village, 2026-11-23, about one start in ten): its log stops in a
    run of "Suspending <thread>" lines with fewer "Resuming" ones (62 against 17; a good start has them equal) and never
    reaches the line that says its textures are set up. Nothing of a mod has loaded by then."""
    import os
    import time
    path = os.path.join(game_dir or "", LOADER_LOG)
    try:
        age = (now if now is not None else time.time()) - os.path.getmtime(path)
        with open(path, "rb") as f:
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    paused, resumed = text.count("] Suspending "), text.count("] Resuming ")
    if age >= LOADER_LOG_QUIET_S and paused > resumed and LOADER_READY_TEXT not in text:
        return {"cause": "loader_startup_hang",
                "why": f"the loader (REFramework) stopped in its own start-up: it paused {paused} of the game's threads and "
                       f"let only {resumed} go again, {age:.0f} s ago; nothing of a mod had loaded yet",
                "do": "end the process (its own close cannot work) and start the game again"}
    return None
