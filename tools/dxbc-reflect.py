#!/usr/bin/env python3
"""dxbc-reflect.py - read D3D10/11 shader reflection (RDEF) out of any file.

Most D3D11 games ship their shaders with the RDEF chunk intact, which means the
constant-buffer layout - buffer names, variable names, byte offsets, sizes and
register bindings - is sitting on disk in plain form. That is exactly the
information a VR conversion needs ("which cbuffer holds the view-projection, and
at what offset"), and reading it needs no debugger, no frame capture, and no
running process. It works even when the executable is packed or protected,
because the shaders are separate data.

Point it at a shader bundle, a pack file, or a single .cso - it scans for DXBC
containers anywhere in the file rather than assuming a format, so it does not
need to understand the game's archive.

  list     <file>            every distinct constant buffer, with variables
  find     <file> <regex>    only buffers/variables whose name matches
  summary  <file>            how many shaders, buffers, and the common names

Examples
--------
  python dxbc-reflect.py Shaders_F.shader_bundle summary
  python dxbc-reflect.py Shaders_F.shader_bundle find "view|proj|camera"
"""

import argparse
import collections
import re
import struct
import sys


def find_dxbc(data):
    """Yield (offset, size) for every DXBC container in `data`."""
    off = 0
    while True:
        i = data.find(b"DXBC", off)
        if i < 0:
            return
        if i + 32 <= len(data):
            size = struct.unpack_from("<I", data, i + 24)[0]
            # Sanity: the declared size must be plausible and fit.
            if 64 <= size <= 8 * 1024 * 1024 and i + size <= len(data):
                yield i, size
        off = i + 4


def chunks(data, base):
    """Yield (fourcc, offset, size) for a DXBC container at `base`."""
    count = struct.unpack_from("<I", data, base + 28)[0]
    if count > 32:
        return
    for n in range(count):
        coff = struct.unpack_from("<I", data, base + 32 + 4 * n)[0]
        c = base + coff
        if c + 8 > len(data):
            continue
        fourcc = data[c:c + 4]
        csize = struct.unpack_from("<I", data, c + 4)[0]
        yield fourcc, c + 8, csize


def cstr(data, at):
    end = data.find(b"\0", at)
    if end < 0:
        return ""
    return data[at:end].decode("latin-1", "replace")


def expand_type(data, at, type_off, base_offset, name, size, depth=0, out=None):
    """Flatten a variable, recursing into struct members.

    Games routinely wrap everything in one nested struct - Mad Max's whole
    per-object buffer is a single `InstanceConsts` member - so without walking
    the type tree the reflection says nothing useful. The type record is:

        uint16 class, type, rows, columns, elements, memberCount
        uint32 memberOffset -> memberCount * { uint32 nameOff, typeOff, offset }
    """
    if out is None:
        out = []
    if depth > 4 or type_off == 0 or at + type_off + 16 > len(data):
        out.append((name, base_offset, size))
        return out
    try:
        klass, vtype, rows, cols, elements, members, member_off = struct.unpack_from(
            "<HHHHHHI", data, at + type_off)
    except struct.error:
        out.append((name, base_offset, size))
        return out

    # class 5 == D3D_SVC_STRUCT. Anything else is a leaf as far as we care.
    if klass != 5 or members == 0 or members > 256:
        # Derive the leaf's size from its shape rather than trusting the
        # variable record, which only exists for top-level variables.
        # 0 = scalar, 1 = vector, 2 = matrix (column-major), 3 = matrix (rows).
        if klass == 2:
            unit = 16 * max(cols, 1)
        elif klass == 3:
            unit = 16 * max(rows, 1)
        elif klass == 1:
            unit = 4 * max(cols, 1)
        else:
            unit = 4
        n = max(elements, 1)
        # Prefer the size the reflection actually declares (top-level variables
        # have one); only derive it for nested members, which do not.
        out.append((name, base_offset, size if size else unit * n))
        return out

    for m in range(members):
        mb = at + member_off + m * 12
        if mb + 12 > len(data):
            break
        mname_off, mtype_off, moff = struct.unpack_from("<III", data, mb)
        mname = cstr(data, at + mname_off)
        expand_type(data, at, mtype_off, base_offset + moff,
                    "%s.%s" % (name, mname) if depth else mname,
                    0, depth + 1, out)
    # Fill in sizes from the gaps between consecutive members.
    return out


def parse_rdef(data, at):
    """Parse an RDEF chunk whose payload starts at `at`. Returns cbuffer dicts."""
    try:
        (cb_count, cb_off, res_count, res_off,
         ver_minor, ver_major, prog_type, flags, creator_off) = struct.unpack_from(
            "<IIIIBBHII", data, at)
    except struct.error:
        return []

    # D3D11 shaders carry an extended header tagged RD11; their variable records
    # are 40 bytes rather than D3D10's 24. Guessing this wrong silently produces
    # garbage names, so it is detected rather than assumed.
    var_stride = 24
    if at + 32 <= len(data) and data[at + 28:at + 32] == b"RD11":
        var_stride = 40

    out = []
    for i in range(min(cb_count, 64)):
        base = at + cb_off + i * 24
        if base + 24 > len(data):
            break
        name_off, var_count, var_off, size, cbflags, cbtype = struct.unpack_from(
            "<IIIIII", data, base)
        cb = {
            "name": cstr(data, at + name_off),
            "size": size,
            "vars": [],
        }
        for v in range(min(var_count, 512)):
            vb = at + var_off + v * var_stride
            if vb + 24 > len(data):
                break
            vname_off, start, vsize, vflags, type_off, def_off = struct.unpack_from(
                "<IIIIII", data, vb)
            vname = cstr(data, at + vname_off)
            for lname, loff, lsize in expand_type(data, at, type_off, start, vname, vsize):
                cb["vars"].append({"name": lname, "offset": loff, "size": lsize})
        out.append(cb)
    return out


def collect(path):
    with open(path, "rb") as f:
        data = f.read()
    shaders = 0
    buffers = {}          # (name, size, vars-tuple) -> count
    for base, _size in find_dxbc(data):
        got = False
        for fourcc, coff, csize in chunks(data, base):
            if fourcc != b"RDEF":
                continue
            got = True
            for cb in parse_rdef(data, coff):
                key = (cb["name"], cb["size"],
                       tuple((v["name"], v["offset"], v["size"]) for v in cb["vars"]))
                buffers[key] = buffers.get(key, 0) + 1
        if got:
            shaders += 1
    return data, shaders, buffers


def print_cb(key, count):
    name, size, variables = key
    print("cbuffer %-32s size %5d bytes   (in %d shaders)" % (name, size, count))
    for vname, voff, vsize in variables:
        kind = ""
        if vsize == 64:
            kind = "  <- 4x4 matrix"
        elif vsize == 48:
            kind = "  <- 4x3 / 3x4 matrix"
        elif vsize == 16:
            kind = "  <- float4"
        print("    +%-5d %-44s %4d bytes%s" % (voff, vname, vsize, kind))
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("mode", choices=["list", "find", "summary"])
    ap.add_argument("pattern", nargs="?", help="regex (find mode), matched case-insensitively")
    ap.add_argument("--limit", type=int, default=40, help="max buffers to print")
    args = ap.parse_args()

    data, shaders, buffers = collect(args.file)

    if not shaders:
        sys.exit("no DXBC shaders with an RDEF chunk found in %s "
                 "(shaders may be stripped, compressed or encrypted)" % args.file)

    if args.mode == "summary":
        print("%s: %d DXBC shaders with reflection, %d distinct constant-buffer layouts"
              % (args.file, shaders, len(buffers)))
        by_name = collections.Counter()
        for (name, _s, _v), n in buffers.items():
            by_name[name] += n
        print("\nMost common constant-buffer names:")
        for name, n in by_name.most_common(20):
            print("  %-40s in %d shaders" % (name, n))
        return

    if args.mode == "find":
        if not args.pattern:
            ap.error("find needs a pattern")
        rx = re.compile(args.pattern, re.I)
        shown = 0
        for key, count in sorted(buffers.items(), key=lambda kv: -kv[1]):
            name, _size, variables = key
            if rx.search(name) or any(rx.search(v[0]) for v in variables):
                print_cb(key, count)
                shown += 1
                if shown >= args.limit:
                    break
        if not shown:
            print("nothing matched %r" % args.pattern)
        return

    for n, (key, count) in enumerate(sorted(buffers.items(), key=lambda kv: -kv[1])):
        if n >= args.limit:
            print("... %d more layouts" % (len(buffers) - args.limit))
            break
        print_cb(key, count)


if __name__ == "__main__":
    main()
