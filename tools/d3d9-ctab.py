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
    # The target string ("vs_3_0"/"ps_3_0") is in the header and is part of a
    # table's identity: the SAME constant name lands on a DIFFERENT register in
    # a vertex vs a pixel shader, so merging the two invents contradictions.
    tgt = cstr(data, base + target) if base + target < len(data) else ""
    if not re.match(r"^(vs|ps)_\d_\d$", tgt):
        tgt = "?"
    return rows, tgt


def collect(path):
    with open(path, "rb") as f:
        data = f.read()
    tables = {}
    seen = 0
    for m in re.finditer(b"CTAB", data):
        parsed = parse_ctab(data, m.start())
        if not parsed:
            continue
        rows, tgt = parsed
        seen += 1
        key = (tuple(sorted(rows)), tgt)
        tables[key] = tables.get(key, 0) + 1
    return seen, tables


def print_table(key, count):
    rows, tgt = key
    print("constant table  [%s]  (%d shaders)" % (tgt, count))
    for name, regset, regidx, regcount in rows:
        kind = ""
        if regcount == 4:
            kind = "  <- 4x4 matrix"
        elif regcount == 3:
            kind = "  <- 4x3 / 3x4"
        # Stage repeated on every row (not just the table header above) so a
        # row survives being grepped or copied out of context still knowing
        # which stage it is. Its absence here is what let a vertex-shader
        # ViewProjectionMatrix's c0 and a pixel-shader one's c3/c10 be read as
        # the same register — see enslaved-vr modding-notes 2026-09-02,
        # "view-projection c3/c10 are pixel shaders".
        print("    %-38s %-6s %-8s c%-4d x%-3d%s"
              % (name, tgt, REGSET.get(regset, "?%d" % regset), regidx, regcount, kind))
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("mode", choices=["list", "find", "summary"])
    ap.add_argument("pattern", nargs="?", help="regex (find mode), case-insensitive")
    ap.add_argument("--limit", type=int, default=20,
                    help="max tables to print; 0 = no limit")
    args = ap.parse_args()

    seen, tables = collect(args.file)
    if not seen:
        sys.exit("no parseable CTAB blocks found in %s "
                 "(shaders may be stripped, compressed or not D3D9)" % args.file)

    if args.mode == "summary":
        print("%s: %d shader constant tables, %d distinct layouts"
              % (args.file, seen, len(tables)))
        # Which register does each constant name usually land on? Keyed by
        # (stage, regidx, regcount), NOT just (regidx, regcount) - the same
        # name lands on a different register per stage (RHI reserves separate
        # vs/ps constant ranges), so merging vs and ps here is exactly the bug
        # that mis-staged Enslaved's c3/c10 ViewProjectionMatrix as a second
        # vertex-shader location when both were pixel shaders. See
        # enslaved-vr modding-notes 2026-09-02.
        where = collections.defaultdict(collections.Counter)
        total = collections.Counter()
        for (rows, tgt), n in tables.items():
            for name, regset, regidx, regcount in rows:
                where[name][(tgt, regidx, regcount)] += n
                total[name] += n
        print("\nMost common constants, and the register they land on (by stage):")
        for name, n in total.most_common(25):
            spots = where[name].most_common(2)
            desc = ", ".join("%s c%d x%d (%d)" % (t, r, c, k) for (t, r, c), k in spots)
            print("  %-38s in %-7d %s" % (name, n, desc))
        return

    if args.mode == "find":
        if not args.pattern:
            ap.error("find needs a pattern")
        rx = re.compile(args.pattern, re.I)
        matched = [(k, c) for k, c in sorted(tables.items(), key=lambda kv: -kv[1])
                   if any(rx.search(r[0]) for r in k[0])]
        if not matched:
            print("nothing matched %r" % args.pattern)
            return
        cap = len(matched) if args.limit == 0 else min(args.limit, len(matched))
        for key, count in matched[:cap]:
            print_table(key, count)
        # Truncating in silence is how a capped sample gets published as a total.
        print("%d layouts matched, %d shown, %d shaders in all matching layouts."
              % (len(matched), cap, sum(c for _, c in matched)))
        if cap < len(matched):
            print("%d layouts NOT shown - re-run with --limit 0 for all."
                  % (len(matched) - cap))
        return

    for n, (key, count) in enumerate(sorted(tables.items(), key=lambda kv: -kv[1])):
        if n >= args.limit:
            print("... %d more layouts" % (len(tables) - args.limit))
            break
        print_table(key, count)


if __name__ == "__main__":
    main()
