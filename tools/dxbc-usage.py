#!/usr/bin/env python3
"""dxbc-usage.py - which shader STAGES declare a constant buffer, and which of
its 16-byte slots the shader code actually READS, from disassembly.

dxbc-reflect.py answers "what layouts exist and where do they bind". This tool
answers the next question, which reflection cannot: for one named cbuffer,
which slots does each shader touch, and what does it do with them? It splits
every DXBC blob in a bundle/pack/.cso by stage (vs/ps/gs/hs/ds/cs), disassembles
each one with fxc -dumpbin, and tabulates references of the form cbN[slot]
where N is the register the named cbuffer binds to in that shader.

Why this matters for a VR conversion (learned on mad-max-vr, 2026-09-03):
  * two layouts of the same cbuffer name turned out to be the VERTEX and PIXEL
    views of it - a "shadow-pass variant" reading of a static census was wrong,
    and a live probe that never saw one of the two sizes bound was explained by
    the pixel side being allocated larger than declared (legal in D3D11);
  * a run of 4 contiguous frame-constant slots looked 4x4-shaped but was read
    as `xyz offset + w scale` by the shaders and two of its slots by nothing at
    all, while the real clip-space transform sat at slots 0..3, read as a
    mul/mad/mad/add chain straight into SV_Position - and varied per pass, so a
    "constant within the frame" filter excluded it by design.
Instruction-level usage is what separates those cases, and it is all on disk.

Needs fxc.exe (Windows Kits). Disassembly is cached beside the output so a
re-run is instant.

  usage:
    dxbc-usage.py <file> <cbuffer-name> [--slots 0-3,9,16-19] [--stage vs]
                  [--cache DIR] [--samples N] [--fxc PATH]

  prints:
    A. (size, stage) -> shader count, for the named cbuffer
    B. per (size, stage): slot -> number of shaders reading it
    C. sample instructions touching the requested slots (default: every slot)
    D. vertex shaders: the register chains that end in SV_Position (o0), i.e.
       which cbuffer/slots the clip-space position comes from
"""
import argparse
import collections
import glob
import importlib.util
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("dxbc_reflect", os.path.join(HERE, "dxbc-reflect.py"))
dr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dr)

STAGE = {0xFFFE: "vs", 0xFFFF: "ps", 0x4853: "hs", 0x4753: "gs", 0x4453: "ds", 0x4353: "cs"}
REF_RE = re.compile(r"\bcb(\d+)\[(\d+)\]")


def find_fxc(explicit):
    if explicit:
        return explicit
    hits = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\fxc.exe"))
    if not hits:
        sys.exit("fxc.exe not found under the Windows Kits; pass --fxc")
    return hits[-1]


def parse_slots(text):
    if not text:
        return None
    out = set()
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return out


def scan(data):
    """One record per DXBC blob: stage, cbuffers {name: size}, binds {b#: name}."""
    shaders = []
    for idx, (base, size) in enumerate(dr.find_dxbc(data)):
        rec = {"idx": idx, "base": base, "size": size, "stage": "?", "cbs": {}, "bind": {}}
        for fourcc, coff, _csize in dr.chunks(data, base):
            if fourcc != b"RDEF":
                continue
            # RDEF header: ..., version minor u8, major u8, program type u16 at +18
            prog = struct.unpack_from("<H", data, coff + 18)[0]
            rec["stage"] = STAGE.get(prog, "0x%04X" % prog)
            binds = dict(dr.parse_bindings(data, coff))
            for cb in dr.parse_rdef(data, coff):
                rec["cbs"][cb["name"]] = cb["size"]
                if binds.get(cb["name"]) is not None:
                    rec["bind"][binds[cb["name"]]] = cb["name"]
        shaders.append(rec)
    return shaders


def disassemble(data, rec, cache, fxc):
    blob = os.path.join(cache, "%04d.dxbc" % rec["idx"])
    asm = os.path.join(cache, "%04d.asm" % rec["idx"])
    if not os.path.exists(asm):
        with open(blob, "wb") as f:
            f.write(data[rec["base"]:rec["base"] + rec["size"]])
        r = subprocess.run([fxc, "-nologo", "-dumpbin", blob], capture_output=True, text=True)
        with open(asm, "w") as f:
            f.write(r.stdout if r.returncode == 0 else "FXC-ERROR\n" + r.stderr)
    with open(asm) as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("cbuffer")
    ap.add_argument("--slots", default=None, help="slots to print samples for, e.g. 0-3,9,16-19")
    ap.add_argument("--stage", default=None, help="restrict to one stage (vs, ps, ...)")
    ap.add_argument("--cache", default=None, help="disassembly cache dir (default: <file>.dxbc-usage/)")
    ap.add_argument("--samples", type=int, default=6, help="sample instructions per (size, slot)")
    ap.add_argument("--fxc", default=None)
    a = ap.parse_args()

    fxc = find_fxc(a.fxc)
    cache = a.cache or (a.file + ".dxbc-usage")
    os.makedirs(cache, exist_ok=True)
    want = parse_slots(a.slots)

    with open(a.file, "rb") as f:
        data = f.read()
    shaders = scan(data)
    users = [s for s in shaders if a.cbuffer in s["cbs"] and (a.stage is None or s["stage"] == a.stage)]
    print("%d DXBC blobs, %d declare %s%s" % (len(shaders), len(users), a.cbuffer,
                                              " (stage %s)" % a.stage if a.stage else ""))
    if not users:
        return

    print("\nA. %s: (size, stage) -> shaders" % a.cbuffer)
    by = collections.Counter((s["cbs"][a.cbuffer], s["stage"]) for s in users)
    for (size, stage), n in sorted(by.items()):
        print("   size %5d  %s  %d" % (size, stage, n))

    hist = collections.defaultdict(collections.Counter)      # (size, stage) -> slot -> shaders
    samples = collections.defaultdict(list)                   # (size, stage, slot) -> lines
    pos_chain = collections.Counter()                         # vs: (size, cb#, slot) in the o0 chain
    errors = 0
    for s in users:
        asm = disassemble(data, s, cache, fxc)
        if asm.startswith("FXC-ERROR"):
            errors += 1
            continue
        size = s["cbs"][a.cbuffer]
        reg = next((b for b, n in s["bind"].items() if n == a.cbuffer), None)
        if reg is None:
            continue
        key = (size, s["stage"])
        body = [l for l in asm.split("\n") if l.strip() and not l.startswith("//")]
        seen = set()
        for line in body:
            for m in REF_RE.finditer(line):
                cbn, slot = int(m.group(1)), int(m.group(2))
                if cbn != reg:
                    continue
                seen.add(slot)
                if (want is None or slot in want) and len(samples[key + (slot,)]) < a.samples:
                    samples[key + (slot,)].append("[%04d %s] %s" % (s["idx"], s["stage"], line.strip()))
        for slot in seen:
            hist[key][slot] += 1
        if s["stage"] == "vs":
            # Walk back from the o0 write through the temps that feed it and
            # collect every cb reference on that path.
            #
            # ⚠️ PROGRAM ORDER IS LOAD-BEARING (fixed 2026-09-04). The first
            # version of this walk indexed every write by register NAME with no
            # regard to position in the shader, so reaching `r0` pulled in
            # *every* write to r0 anywhere in the body - including writes that
            # happen AFTER the o0 write and therefore cannot feed it. Registers
            # are aggressively reused, so that is not a corner case: in Mad Max
            # shader 0282, r0 feeds o0 near the top and is then reloaded with an
            # unrelated cb1[18..21] transform whose result goes to o3, and the
            # old walk reported slots 18..21 as feeding SV_Position in 16
            # shaders. They do not. Only writes strictly BEFORE the consumer are
            # candidates now, and each hop takes the LAST such write - which is
            # the one D3D bytecode semantics say is live.
            #
            # This still over-approximates in one direction on purpose: no
            # component masking (a write to r0.x is treated as a write to r0),
            # so a slot can be listed when only an unused channel of a shared
            # register carried it. It never under-approximates. Treat section D
            # as "these slots are on the position path", not as a proof that
            # every listed slot reaches o0.
            writes = []                       # (index, regname, sources) in program order
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

            # Every write to o0 is a consumer; o0.xyzw is often built in pieces.
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
            for cbn, slot in refs:
                name = s["bind"].get(cbn, "cb%d?" % cbn)
                pos_chain[(size, name, cbn, slot)] += 1
    if errors:
        print("\n(%d shaders failed to disassemble)" % errors)

    for key in sorted(hist):
        print("\nB. %s size %d, %s: slot -> shaders reading it" % (a.cbuffer, key[0], key[1]))
        print("   " + "  ".join("%d:%d" % (k, v) for k, v in sorted(hist[key].items())))

    print("\nC. sample instructions%s:" % (" for slots %s" % a.slots if a.slots else ""))
    for key in sorted(samples):
        print("  size %d %s slot %d:" % key)
        for line in samples[key]:
            print("     " + line)

    if pos_chain:
        print("\nD. vertex shaders: cbuffer slots on the register chain feeding SV_Position (o0)")
        print("   (%s size, cbuffer, b#, slot) -> shaders" % a.cbuffer)
        for k, v in sorted(pos_chain.items(), key=lambda kv: (-kv[1], kv[0])):
            print("   %s: %d" % (k, v))


if __name__ == "__main__":
    main()
