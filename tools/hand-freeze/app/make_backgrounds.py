"""make_backgrounds.py -- draws the two pixel-art window backgrounds of Hand Freeze as looping GIFs.

summer.gif (switch OFF): sky, a pulsing sun, drifting clouds, green hills with swaying flowers.
winter.gif (switch ON):  night-blue sky, moon, falling snow, snowy hills and pines, icicles along the top.
Both are drawn at the app's low-res canvas size (W x H) and the app scales them up with hard pixel edges, so they
stay pixelated. Every animated thing moves a whole number of loops in FRAMES frames, so the GIF loops seamlessly.
    python make_backgrounds.py      (writes summer.gif and winter.gif next to this script)
"""
import math
import os
import random

from PIL import Image, ImageDraw

W, H = 210, 300          # must match the app's canvas (FreezeUi.cs CANVAS_W, CANVAS_H)
FRAMES, FRAME_MS = 16, 140
HERE = os.path.dirname(os.path.abspath(__file__))


def gradient(d, top, bottom, y0=0, y1=H):
    for y in range(y0, y1):
        t = (y - y0) / max(1, y1 - y0 - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))


def hill(d, base, amp, period, phase, color):
    pts = [(x, base - amp * math.sin(x / period + phase)) for x in range(0, W + 1)]
    d.polygon(pts + [(W, H), (0, H)], fill=color)


def summer():
    rnd = random.Random(7)
    flowers = [(rnd.randrange(W), rnd.randrange(250, H - 4), rnd.choice([(250, 90, 120), (255, 220, 80), (255, 255, 255), (200, 120, 255)]), rnd.random() * 6.28) for _ in range(70)]
    frames = []
    for f in range(FRAMES):
        t = f / FRAMES
        im = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(im)
        gradient(d, (70, 150, 235), (190, 225, 250), 0, 230)
        # sun with pulsing rays
        cx, cy = 168, 40
        for k in range(12):
            a = k * math.pi / 6 + t * math.pi / 6
            r1, r2 = 20, 27 + 3 * math.sin(t * 2 * math.pi * 2 + k)
            d.line([(cx + r1 * math.cos(a), cy + r1 * math.sin(a)), (cx + r2 * math.cos(a), cy + r2 * math.sin(a))], fill=(255, 230, 110), width=2)
        d.ellipse([cx - 15, cy - 15, cx + 15, cy + 15], fill=(255, 215, 70))
        d.ellipse([cx - 11, cy - 11, cx + 9, cy + 9], fill=(255, 235, 120))
        # clouds drifting one width per loop
        for (y, size, speed, off) in [(30, 1.0, 1, 10), (75, 0.8, 2, 120), (120, 1.2, 1, 60)]:
            x = (off + t * W * speed) % (W + 80) - 40
            for dx, dy, r in [(0, 0, 9), (10, -4, 11), (22, 0, 9), (12, 3, 8)]:
                rr = r * size
                d.ellipse([x + dx * size - rr, y + dy - rr * 0.7, x + dx * size + rr, y + dy + rr * 0.7], fill=(250, 252, 255))
        hill(d, 205, 10, 30, 0.5, (120, 190, 90))
        hill(d, 228, 8, 22, 2.0, (85, 165, 70))
        hill(d, 252, 6, 18, 4.0, (60, 140, 55))
        for (x, y, c, ph) in flowers:   # sway one pixel left and right
            sx = x + round(math.sin(t * 2 * math.pi + ph))
            d.line([(x, y + 3), (sx, y)], fill=(40, 110, 40))
            d.point([(sx, y), (sx - 1, y), (sx + 1, y), (sx, y - 1)], fill=c)
        frames.append(im)
    return frames


def winter():
    rnd = random.Random(3)
    flakes = [(rnd.randrange(W), rnd.randrange(H), rnd.choice([1, 1, 2, 3]), rnd.random() * 6.28) for _ in range(140)]
    stars = [(rnd.randrange(W), rnd.randrange(150), rnd.random() * 6.28) for _ in range(40)]
    icicles = [(x, rnd.randrange(6, 20)) for x in range(4, W, 9)]
    frames = []
    for f in range(FRAMES):
        t = f / FRAMES
        im = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(im)
        gradient(d, (12, 22, 60), (70, 110, 170), 0, 230)
        for (x, y, ph) in stars:
            if math.sin(t * 2 * math.pi + ph) > -0.3:
                d.point((x, y), fill=(220, 230, 255))
        d.ellipse([22, 26, 48, 52], fill=(235, 240, 255))
        d.ellipse([30, 26, 54, 50], fill=(22, 37, 78))   # crescent: the sky colour at that height
        hill(d, 205, 9, 28, 1.0, (190, 210, 235))
        for (x, s) in [(30, 1.0), (62, 0.8), (150, 1.1), (185, 0.9)]:   # snowy pines
            base = 212
            for i in range(3):
                w, top = (16 - i * 4) * s, base - (12 + i * 10) * s
                d.polygon([(x - w, base - i * 9 * s), (x + w, base - i * 9 * s), (x, top - 8 * s)], fill=(25, 70, 60))
                d.polygon([(x - w * 0.5, top + 2), (x + w * 0.5, top + 2), (x, top - 8 * s)], fill=(235, 245, 255))
            d.rectangle([x - 2, base, x + 2, base + 5], fill=(70, 50, 40))
        hill(d, 230, 7, 20, 3.0, (215, 230, 248))
        hill(d, 255, 5, 16, 5.0, (240, 247, 255))
        for (x, y, size, ph) in flakes:   # each flake falls exactly H*k pixels per loop, drifting sideways
            k = 1 if size == 1 else 2
            fy = (y + t * H * k) % H
            fx = (x + 4 * math.sin(t * 2 * math.pi + ph)) % W
            if size == 3:
                d.point([(fx, fy), (fx - 1, fy), (fx + 1, fy), (fx, fy - 1), (fx, fy + 1)], fill=(255, 255, 255))
            elif size == 2:
                d.rectangle([fx, fy, fx + 1, fy + 1], fill=(240, 248, 255))
            else:
                d.point((fx, fy), fill=(210, 225, 245))
        d.rectangle([0, 0, W, 3], fill=(225, 240, 255))   # frost along the top, icicles hanging off it
        for (x, ln) in icicles:
            ln2 = ln + (1 if math.sin(t * 2 * math.pi + x) > 0.9 else 0)
            d.polygon([(x - 3, 3), (x + 3, 3), (x, 3 + ln2)], fill=(200, 230, 255))
            d.line([(x - 1, 4), (x - 1, 2 + ln2 * 0.6)], fill=(255, 255, 255))
        frames.append(im)
    return frames


for name, frames in (("summer.gif", summer()), ("winter.gif", winter())):
    path = os.path.join(HERE, name)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=FRAME_MS, loop=0, optimize=False)
    frames[0].resize((W * 2, H * 2), Image.NEAREST).save(os.path.join(HERE, name.replace(".gif", "_preview.png")))
    print(name, os.path.getsize(path), "bytes")
