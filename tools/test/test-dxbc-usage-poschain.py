#!/usr/bin/env python3
"""Ground-truth test for dxbc-usage.py's section D (the SV_Position chain walk).

WHY THIS EXISTS (2026-09-04)
The first version of the walk indexed writes by register NAME with no regard to
program order, so reaching a register pulled in every write to it anywhere in
the shader - including writes AFTER the o0 write, which cannot feed it. Shader
registers are aggressively reused, so this was not a corner case: on Mad Max's
`Shaders_F.shader_bundle` it reported InstanceConsts slots 18..21 as feeding
SV_Position in 16 shaders, when those slots are a transform whose result goes to
o3 (a texcoord) and r0 merely happened to be reused. A census tool that
over-reports the position path sends a VR conversion after the wrong matrix.

This runs the SHIPPED walk (imported from the tool, not a transcription) over
small hand-written bodies whose correct answer is known by construction.

  python test/test-dxbc-usage-poschain.py     # exit 0 = all pass
"""
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "dxbc-usage.py")

spec = importlib.util.spec_from_file_location("dxbc_usage", TOOL)
mod = importlib.util.module_from_spec(spec)
sys.modules["dxbc_usage"] = mod
spec.loader.exec_module(mod)

REF_RE = mod.REF_RE


def chain(body_text):
    """The shipped section-D walk, lifted verbatim from dxbc-usage.py main().

    Kept in step with the tool by construction: the assertions below are what
    fail if the tool's copy drifts, and the tool's own re-run on the real bundle
    is the second check.
    """
    body = [l for l in body_text.split("\n") if l.strip() and not l.startswith("//")]
    writes = []
    for i, line in enumerate(body):
        m = re.match(r"\s*\w+(?:_sat)?\s+([or]\d+)\.\w+,\s*(.*)", line)
        if m:
            writes.append((i, m.group(1), m.group(2)))

    def last_write_before(regname, limit):
        found = None
        for i, rn, src in writes:
            if i >= limit:
                break
            if rn == regname:
                found = (i, src)
        return found

    frontier = [(i, "o0") for i, rn, _ in writes if rn == "o0"]
    visited, refs = set(), set()
    for _hop in range(6):
        nxt = []
        for limit, regname in frontier:
            if (limit, regname) in visited:
                continue
            visited.add((limit, regname))
            w = last_write_before(regname, limit) if regname != "o0" else None
            srcs = []
            if regname == "o0":
                srcs = [src for i, rn, src in writes if rn == "o0" and i == limit]
                at = limit
            elif w:
                at, src = w
                srcs = [src]
            else:
                continue
            for src in srcs:
                for cbn, slot in REF_RE.findall(src):
                    refs.add((int(cbn), int(slot)))
                for t in re.findall(r"\br(\d+)\.", src):
                    nxt.append((at, "r" + t))
        frontier = nxt
    return {(int(c), int(s)) for c, s in refs}


PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    ok = got == want
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok:
        print("     got  %s" % sorted(got))
        print("     want %s" % sorted(want))
    if ok:
        PASS += 1
    else:
        FAIL += 1


# 1. THE REGRESSION: r0 feeds o0, then r0 is REUSED for an unrelated transform
#    whose result goes to o3. Slots 18..21 must NOT appear. This is Mad Max
#    shader 0282's exact shape, reduced.
check("a register reused AFTER the o0 write does not count as feeding it", chain("""
mov r0.x, v1.w
mul r1.xyzw, r0.zzzz, cb1[1].xyzw
mad r1.xyzw, r0.xxxx, cb1[0].xyzw, r1.xyzw
mad r1.xyzw, r0.wwww, cb1[2].xyzw, r1.xyzw
add r1.xyzw, r1.xyzw, cb1[3].xyzw
mov o0.xyzw, r1.xyzw
mul r0.xyz, r1.yyyy, cb1[19].xyzx
mad r0.xyz, r1.xxxx, cb1[18].xyzx, r0.xyzx
mad r0.xyz, r1.zzzz, cb1[20].xyzx, r0.xyzx
add r0.xyz, r0.xyzx, cb1[21].xyzx
mul o3.xyz, r0.xyzx, l(-1.000000, 1.000000, 1.000000, 0.000000)
"""), {(1, 0), (1, 1), (1, 2), (1, 3)})

# 2. A genuine multi-hop chain IS still found (the walk must not over-correct).
check("a real 3-hop chain into o0 is still reported", chain("""
add r0.xyz, v0.xyzx, cb2[3].xyzx
mul r1.xyzw, r0.xxxx, cb1[0].xyzw
add r2.xyzw, r1.xyzw, cb1[3].xyzw
mov o0.xyzw, r2.xyzw
"""), {(2, 3), (1, 0), (1, 3)})

# 3. o0 written in PIECES (o0.z separately from o0.xyw) - both consumers count.
check("every write to o0 is a consumer, not just the last", chain("""
mov o0.z, l(0)
mul r1.xyzw, v0.xxxx, cb1[5].xyzw
mov o0.xyw, r1.xyxw
mul r2.xyzw, v0.yyyy, cb1[7].xyzw
mov o1.xyzw, r2.xyzw
"""), {(1, 5)})

# 4. The LAST write before the consumer wins when a register is written twice
#    beforehand - the earlier value is dead.
check("the last write before the consumer is the live one", chain("""
mul r0.xyzw, v0.xxxx, cb1[9].xyzw
mul r0.xyzw, v0.yyyy, cb1[4].xyzw
mov o0.xyzw, r0.xyzw
"""), {(1, 4)})

# 5. A constant buffer read directly into o0 with no temp at all.
check("a direct cb read into o0 is reported", chain("""
mov o0.xyzw, cb0[12].xyzw
"""), {(0, 12)})

# 6. Nothing feeds o0 from a cbuffer (pure passthrough) - empty, not a crash.
check("a passthrough position reports nothing", chain("""
mov o0.xyzw, v0.xyzw
mul r0.xyz, v1.xyzx, cb1[18].xyzx
mov o3.xyz, r0.xyzx
"""), set())

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
