#!/usr/bin/env python3
"""d3d9-ctab.py - read D3D9 shader constant tables (CTAB) out of any file.

The Direct3D 9 counterpart to `dxbc-reflect.py`. Compiled D3D9 shaders carry a
`CTAB` comment block naming every constant and giving its **register index** -
which is exactly the question a VR conversion asks first ("which constant
register holds the view-projection?"). Like RDEF on D3D11, it is plain data on
disk: no debugger, no frame capture, no running game.

It scans for `CTAB` blocks anywhere in a file, so it works on shader caches,
package files and loose compiled shaders without understanding the container.

  list    <file>            every distinct constant table
  find    <file> <regex>    only tables containing a matching constant name
  summary <file>            how many tables, and the most common constants
                            with the register they land on

Register sets (`regset`): 0 = bool, 1 = int4, 2 = float4, 3 = sampler.

Examples
--------
  python d3d9-ctab.py RefShaderCache-PC-D3D-SM3.upk summary
  python d3d9-ctab.py RefShaderCache-PC-D3D-SM3.upk find "viewproj|camera"
"""

import argparse
import collections
import re
import struct
import sys

REGSET = {0: "bool", 1: "int4", 2: "float4", 3: "sampler"}


def cstr(data, at):
    end = data.find(b"\0", at)
    return data[at:end].decode("latin-1", "replace") if end >= 0 else ""


def parse_ctab(data, ct):
    """Parse the CTAB whose 'CTAB' fourcc is at `ct`. Returns a list of rows."""
    base = ct + 4                       # table offsets are relative to here
    try:
        (size, creator, version, nconst,
         cinfo, flags, target) = struct.unpack_from("<7I", data, base)
    except struct.error:
        return None
    # Sanity: a shader with thousands of constants is a misparse, not a shader.
    if not (0 < nconst < 512):
        return None
    if base + cinfo + nconst * 20 > len(data):
        return None
    rows = []
    for i in range(nconst):
        o = base + cinfo + i * 20
        name_off, regset, regidx, regcount, _res, _ti, _dv = struct.unpack_from(
            "<IHHHHII", data, o)
        if base + name_off >= len(data):
            return None
        rows.append((cstr(data, base + name_off), regset, regidx, regcount))
    return rows


def collect(path):
    with open(path, "rb") as f:
        data = f.read()
    tables = {}
    seen = 0
    for m in re.finditer(b"CTAB", data):
        rows = parse_ctab(data, m.start())
        if not rows:
            continue
        seen += 1
        key = tuple(sorted(rows))
        tables[key] = tables.get(key, 0) + 1
    return seen, tables


def print_table(key, count):
    print("constant table  (%d shaders)" % count)
    for name, regset, regidx, regcount in key:
        kind = ""
        if regcount == 4:
            kind = "  <- 4x4 matrix"
        elif regcount == 3:
            kind = "  <- 4x3 / 3x4"
        print("    %-38s %-8s c%-4d x%-3d%s"
              % (name, REGSET.get(regset, "?%d" % regset), regidx, regcount, kind))
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("mode", choices=["list", "find", "summary"])
    ap.add_argument("pattern", nargs="?", help="regex (find mode), case-insensitive")
    ap.add_argument("--limit", type=int, default=20, help="max tables to print")
    args = ap.parse_args()

    seen, tables = collect(args.file)
    if not seen:
        sys.exit("no parseable CTAB blocks found in %s "
                 "(shaders may be stripped, compressed or not D3D9)" % args.file)

    if args.mode == "summary":
        print("%s: %d shader constant tables, %d distinct layouts"
              % (args.file, seen, len(tables)))
        # Which register does each constant name usually land on?
        where = collections.defaultdict(collections.Counter)
        total = collections.Counter()
        for key, n in tables.items():
            for name, regset, regidx, regcount in key:
                where[name][(regidx, regcount)] += n
                total[name] += n
        print("\nMost common constants, and the register they land on:")
        for name, n in total.most_common(25):
            spots = where[name].most_common(2)
            desc = ", ".join("c%d x%d (%d)" % (r, c, k) for (r, c), k in spots)
            print("  %-38s in %-7d %s" % (name, n, desc))
        return

    if args.mode == "find":
        if not args.pattern:
            ap.error("find needs a pattern")
        rx = re.compile(args.pattern, re.I)
        shown = 0
        for key, count in sorted(tables.items(), key=lambda kv: -kv[1]):
            if any(rx.search(r[0]) for r in key):
                print_table(key, count)
                shown += 1
                if shown >= args.limit:
                    break
        if not shown:
            print("nothing matched %r" % args.pattern)
        return

    for n, (key, count) in enumerate(sorted(tables.items(), key=lambda kv: -kv[1])):
        if n >= args.limit:
            print("... %d more layouts" % (len(tables) - args.limit))
            break
        print_table(key, count)


if __name__ == "__main__":
    main()
