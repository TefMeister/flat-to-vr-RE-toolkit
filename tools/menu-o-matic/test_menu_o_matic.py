"""Offline tests for Menu-o-matiC's route logic: no window, no game. Run: python test_menu_o_matic.py"""
import os
import sys
import tempfile

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mom_route as R  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def menu(highlight, size=(1280, 720)):
    """A fake menu: four text-like bars, one of them highlighted, on a noisy-ish background."""
    img = Image.new("RGB", size, (30, 30, 40))
    d = ImageDraw.Draw(img)
    for i in range(4):
        top = 300 + i * 60
        colour = (230, 180, 40) if i == highlight else (120, 120, 120)
        d.rectangle([400, top, 880, top + 40], fill=colour)
        d.text((420, top + 12), f"CHOICE {i}", fill=(0, 0, 0))
    return img


# Regions
check("parse_region accepts fractions", R.parse_region("0.1,0.2,0.3,0.4") == [0.1, 0.2, 0.3, 0.4])
for bad in ("1,2,3", "0.5,0.5,0,0.1", "-0.1,0,0.5,0.5", "0,0,1.5,0.2"):
    try:
        R.parse_region(bad)
        check(f"parse_region rejects {bad!r}", False)
    except ValueError:
        check(f"parse_region rejects {bad!r}", True)
check("region_pixels scales with the window", R.region_pixels([0.25, 0.5, 0.5, 0.25], (1280, 720)) == (320, 360, 960, 540)
      and R.region_pixels([0.25, 0.5, 0.5, 0.25], (2560, 1440)) == (640, 720, 1920, 1080))

# Signatures
a, b = menu(0), menu(1)
region = [0.3, 0.4, 0.4, 0.35]
sa, sb = R.signature(R.crop(a, region)), R.signature(R.crop(b, region))
check("signature has SIG_SIZE^2 values", len(sa) == R.SIG_SIZE ** 2)
check("same screen -> distance 0", R.distance(sa, R.signature(R.crop(menu(0), region))) == 0)
check("different highlight -> over the tolerance", R.distance(sa, sb) > R.DEFAULT_TOLERANCE)
big = menu(0).resize((2560, 1440))  # the same screen drawn in a bigger window
check("same screen at double size still matches",
      R.distance(sa, R.signature(R.crop(big, region))) <= R.DEFAULT_TOLERANCE)

def status(text):
    img = Image.new("RGB", (400, 120), (240, 240, 240))
    ImageDraw.Draw(img).text((300, 100), text, fill=(0, 0, 0))
    return img


tiny = [0.72, 0.8, 0.2, 0.15]
s2 = R.signature(R.crop(status("Ln 1, Col 2"), tiny))
s3 = R.signature(R.crop(status("Ln 1, Col 3"), tiny))
check("one changed digit: the mean alone would call it the same", R.distance(s2, s3) <= R.DEFAULT_TOLERANCE)
check("one changed digit: the spot check tells them apart", R.spot_distance(s2, s3) > R.DEFAULT_SPOT_TOLERANCE)

# Changed region: moving the highlight from line 0 to line 1 changes exactly those two bars
cr = R.changed_region(a, b)
check("changed_region finds a change", cr is not None)
if cr:
    left, top, right, bottom = R.region_pixels(cr, a.size)
    check("changed box covers both bars", left <= 400 and right >= 880 and top <= 300 and bottom >= 400)
    check("changed box leaves the other bars out", bottom < 420 + 20 + 0.02 * 720 + 1)
check("no change -> None", R.changed_region(a, menu(0)) is None)


def with_corner(img, colour):
    """The same screen with a small 'status' box in the bottom-right corner, like Notepad's Ln/Col."""
    img = img.copy()
    ImageDraw.Draw(img).rectangle([1150, 690, 1270, 715], fill=colour)
    return img


two = R.changed_regions(with_corner(a, (30, 30, 40)), with_corner(b, (250, 250, 250)))
check("two separate changes -> two patches", len(two) == 2)
check("biggest patch first (the menu, not the corner)", R.region_pixels(two[0], a.size)[1] < 400)
# A self-moving corner (animated background): it changes between the two no-key captures too.
noise_before, before = with_corner(a, (250, 250, 250)), with_corner(a, (200, 0, 0))
after = with_corner(b, (0, 200, 0))
only = R.changed_regions(before, after, noise_before)
check("self-moving part is ignored", len(only) == 1 and R.region_pixels(only[0], a.size)[1] < 400)

# Route files
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "routes", "test.json")
    route = R.new_route("Test Game", "Test Window", "boot_to_menu")
    route["steps"].append({"key": "enter"})
    R.add_checkpoint(route, "menu_line0", region, sa, note="line 0 highlighted")
    R.save(route, path)
    back = R.load(path)
    check("route round-trips", back == route)
    check("matches: right screen", R.matches(back, "menu_line0", a)[1])
    check("matches: wrong screen", not R.matches(back, "menu_line0", b)[1])
    back["steps"].append({"wait": "nope"})
    R.save(back, path)
    try:
        R.load(path)
        check("load rejects a wait for an unknown checkpoint", False)
    except ValueError:
        check("load rejects a wait for an unknown checkpoint", True)

print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
