#!/usr/bin/env python3
"""static-disasm.py - engine-agnostic static disassembly helper for flat-to-VR RE work.

Reads a PE off disk (no debugger, no launching the game) and answers the three
questions that come up in every project:

  func   <va>   what does the function at this virtual address do, and what does it call?
  xrefs  <va>   who references this virtual address (E8/E9 rel32 calls+jumps, absolute immediates)?
  at     <va>   a flat window of instructions at this address
  info          image base, bitness and section map

Virtual addresses are given the way the notes record them: either absolute
(0x005B1690) or as a module-relative RVA (+0x1B1690). Both forms are accepted.

Requires: pefile, capstone.

Examples
--------
  python static-disasm.py Psychonauts.exe info
  python static-disasm.py Psychonauts.exe func 0x5B1690
  python static-disasm.py Psychonauts.exe func 0x5B1690 --depth 2
  python static-disasm.py Psychonauts.exe xrefs 0x6AEF20
  python static-disasm.py Psychonauts.exe at 0x5B1630 --count 40
"""

import argparse
import os
import sys

try:
    import pefile
except ImportError:
    sys.exit("pefile is required:  python -m pip install pefile")
try:
    import capstone
except ImportError:
    sys.exit("capstone is required:  python -m pip install capstone")


class RawImage:
    """A raw memory image dumped from a live process, addressed by VA.

    Needed whenever the file on disk is packed, encrypted or self-modifying and
    so does not contain the code that actually runs - dump the module out of the
    running process once, then analyse it here forever without a debugger.
    Manhunt (RenderWare, packed .text) is the case this was written for.

    The dump is assumed to be a contiguous image starting at `base`, i.e. what
    a "dump this module" tool produces. If the dump happens to start with a PE
    header, its ImageBase is read from it and `base` need not be supplied.
    """

    def __init__(self, path, base=None, is64=False):
        with open(path, "rb") as f:
            self.data = f.read()
        self.name = os.path.basename(path)
        if base is None:
            if self.data[:2] != b"MZ":
                sys.exit("raw dump does not start with a PE header; pass --base")
            e = int.from_bytes(self.data[0x3C:0x40], "little")
            if self.data[e:e + 4] != b"PE\0\0":
                sys.exit("raw dump has no PE signature; pass --base")
            machine = int.from_bytes(self.data[e + 4:e + 6], "little")
            is64 = machine == 0x8664
            off = e + (0x30 if is64 else 0x34)
            base = int.from_bytes(self.data[off:off + (8 if is64 else 4)], "little")
        self.base = base
        self.is64 = is64
        self.sections = [{
            "name": "raw", "va": base, "vsize": len(self.data),
            "data": self.data, "exec": True,
        }]
        mode = capstone.CS_MODE_64 if is64 else capstone.CS_MODE_32
        self.md = capstone.Cs(capstone.CS_ARCH_X86, mode)
        self.md.detail = True

    def section_of(self, va):
        s = self.sections[0]
        return s if s["va"] <= va < s["va"] + s["vsize"] else None

    def read(self, va, size):
        s = self.section_of(va)
        if s is None:
            return None
        off = va - s["va"]
        return s["data"][off:off + size]

    def parse_va(self, text):
        text = text.strip()
        if text.startswith("+"):
            return self.base + int(text[1:], 16)
        v = int(text, 16)
        return v if v >= self.base else self.base + v

    def label(self, va):
        return "%s+0x%X" % (self.name, va - self.base)


class Image:
    """A PE mapped the way the loader would map it, so VAs work directly."""

    def __init__(self, path):
        self.pe = pefile.PE(path, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.is64 = self.pe.FILE_HEADER.Machine == 0x8664
        self.name = os.path.basename(path)
        self.sections = []
        for s in self.pe.sections:
            sname = s.Name.rstrip(b"\x00").decode("latin-1")
            self.sections.append({
                "name": sname,
                "va": self.base + s.VirtualAddress,
                "vsize": max(s.Misc_VirtualSize, s.SizeOfRawData),
                "data": s.get_data(),
                "exec": bool(s.Characteristics & 0x20000000),
            })
        mode = capstone.CS_MODE_64 if self.is64 else capstone.CS_MODE_32
        self.md = capstone.Cs(capstone.CS_ARCH_X86, mode)
        self.md.detail = True

    def section_of(self, va):
        for s in self.sections:
            if s["va"] <= va < s["va"] + s["vsize"]:
                return s
        return None

    def read(self, va, size):
        s = self.section_of(va)
        if s is None:
            return None
        off = va - s["va"]
        return s["data"][off:off + size]

    def parse_va(self, text):
        text = text.strip()
        if text.startswith("+"):
            return self.base + int(text[1:], 16)
        v = int(text, 16)
        # A bare value below the image base is treated as a module-relative RVA.
        return v if v >= self.base else self.base + v

    def label(self, va):
        return "%s+0x%X" % (self.name, va - self.base)


def disasm_function(img, va, max_insns=400):
    """Linear sweep from `va`, stopping at the first ret not jumped over."""
    out, calls = [], []
    data = img.read(va, max_insns * 15)
    if not data:
        return None, None
    furthest_jump = va
    for ins in img.md.disasm(data, va):
        out.append(ins)
        m = ins.mnemonic
        if m == "call":
            op = ins.operands[0] if ins.operands else None
            if op is not None and op.type == capstone.x86.X86_OP_IMM:
                calls.append((ins.address, op.imm))
        elif m.startswith("j"):
            op = ins.operands[0] if ins.operands else None
            if op is not None and op.type == capstone.x86.X86_OP_IMM:
                furthest_jump = max(furthest_jump, op.imm)
        elif m.startswith("ret") and ins.address >= furthest_jump:
            break
        if len(out) >= max_insns:
            break
    return out, calls


def print_function(img, va, depth, seen, indent=""):
    if va in seen:
        print("%s; (already shown) %s / 0x%08X" % (indent, img.label(va), va))
        return
    seen.add(va)
    insns, calls = disasm_function(img, va)
    if insns is None:
        print("%s; 0x%08X is not inside any mapped section" % (indent, va))
        return
    print("%s;=== %s   (VA 0x%08X, %d insns) ===" % (indent, img.label(va), va, len(insns)))
    for ins in insns:
        print("%s0x%08X  %-20s %s %s" % (
            indent, ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))
    if depth > 1:
        for site, target in calls:
            print()
            print("%s; ---- called from 0x%08X ----" % (indent, site))
            print_function(img, target, depth - 1, seen, indent + "    ")


def find_xrefs(img, target):
    hits = []
    width = 8 if img.is64 else 4
    needle = target.to_bytes(width, "little")
    for s in img.sections:
        data, base = s["data"], s["va"]
        start = 0
        while True:
            i = data.find(needle, start)
            if i < 0:
                break
            hits.append((base + i, s["name"], "absolute pointer/immediate"))
            start = i + 1
        if not s["exec"]:
            continue
        for opcode, kind in ((0xE8, "call rel32"), (0xE9, "jmp rel32")):
            start = 0
            while True:
                i = data.find(bytes([opcode]), start)
                if i < 0 or i + 5 > len(data):
                    break
                rel = int.from_bytes(data[i + 1:i + 5], "little", signed=True)
                if base + i + 5 + rel == target:
                    hits.append((base + i, s["name"], kind))
                start = i + 1
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help="path to the .exe or .dll")
    ap.add_argument("mode", choices=["func", "xrefs", "at", "info"])
    ap.add_argument("va", nargs="?", help="virtual address (0x..., or +RVA)")
    ap.add_argument("--depth", type=int, default=1, help="follow calls this many levels (func)")
    ap.add_argument("--count", type=int, default=32, help="instruction count (at)")
    ap.add_argument("--raw", action="store_true",
                    help="treat the input as a RAW memory image dumped from a live process, "
                         "not a PE on disk. Use this when the on-disk file is packed and its "
                         "code is only real once the process has unpacked it.")
    ap.add_argument("--base", help="image base of a --raw dump (default: read from its PE header)")
    ap.add_argument("--x64", action="store_true", help="force 64-bit decoding for a --raw dump")
    args = ap.parse_args()

    if args.raw:
        img = RawImage(args.image,
                       base=int(args.base, 16) if args.base else None,
                       is64=args.x64)
    else:
        img = Image(args.image)

    if args.mode == "info":
        print("%s  %s  ImageBase 0x%X" % (img.name, "x64" if img.is64 else "x86", img.base))
        for s in img.sections:
            print("  %-10s VA 0x%08X  size 0x%-8X %s" % (
                s["name"], s["va"], s["vsize"], "EXEC" if s["exec"] else ""))
        return

    if not args.va:
        ap.error("this mode needs an address")
    va = img.parse_va(args.va)

    if args.mode == "func":
        print_function(img, va, args.depth, set())
    elif args.mode == "at":
        data = img.read(va, args.count * 15)
        if not data:
            sys.exit("0x%08X is not inside any mapped section" % va)
        for n, ins in enumerate(img.md.disasm(data, va)):
            if n >= args.count:
                break
            print("0x%08X  %-20s %s %s" % (
                ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))
    elif args.mode == "xrefs":
        hits = find_xrefs(img, va)
        if not hits:
            print("no references to 0x%08X found" % va)
        for addr, sect, kind in hits:
            print("0x%08X  [%s]  %s" % (addr, sect, kind))


if __name__ == "__main__":
    main()
