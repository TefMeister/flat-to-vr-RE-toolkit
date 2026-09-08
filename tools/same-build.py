"""
same-build.py - is this deployed DLL/EXE built from the same source as that one?

WHY THIS EXISTS
    CONVENTIONS.md tells a session to "rebuild and compare the hash" to decide
    whether the file sitting in a game folder is the current build. On every
    project checked so far that comparison CANNOT WORK unmodified: a PE carries
    build timestamps that change on every link, so two builds of identical source
    have different hashes. The session then either re-deploys needlessly or, worse,
    concludes the deployed build is stale and goes looking for a difference that
    is not there.

    Found twice on 2026-09-08, on two different projects:
      doom-2016-vr   6 bytes differed: COFF TimeDateStamp + the EXPORT directory's
      mad-max-vr     6 bytes differed: COFF TimeDateStamp + the DEBUG directory's

    Note those are DIFFERENT second fields. Hard-coding offsets from one binary
    gets the other wrong - the first attempt on Mad Max reported "REAL CODE
    DIFFERENCE" for a file that was byte-identical apart from timestamps. So this
    parses the PE instead of assuming.

WHAT IT IGNORES, AND WHY THAT IS SAFE
    Exactly three things, all of them stamped by the linker rather than derived
    from your source: the COFF header TimeDateStamp, and the TimeDateStamp of
    each entry in the export and debug data directories. Everything else - code,
    data, relocations, and the CodeView PDB GUID (itself a hash of the debug
    info, so a genuine code change moves it) - must match byte for byte.

    It is therefore a STRICTER test than a size or version check and a LOOSER one
    than sha256. It answers "same source?", not "same bytes?".

THE BETTER FIX, where you own the build
    Add `-Wl,--no-insert-timestamp` to the link and the hashes match outright.
    Do that, and keep this for binaries built before the flag was added, or built
    by a toolchain that ignores it.

Usage:
    python same-build.py <fresh-build> <deployed-file>
    -> exit 0 same source, 1 real difference, 2 could not compare
"""
import struct
import sys


def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def timestamp_fields(b):
    """File offsets of every linker-written timestamp in this PE."""
    e = _u32(b, 0x3C)
    if b[e:e + 4] != b"PE\0\0":
        raise ValueError("not a PE file")
    out = set(range(e + 8, e + 12))                     # COFF TimeDateStamp

    nsec = _u16(b, e + 6)
    opt_size = _u16(b, e + 20)
    opt = e + 24
    magic = _u16(b, opt)
    ddir = opt + (112 if magic == 0x20B else 96)        # PE32+ vs PE32
    sect = opt + opt_size

    def rva_to_off(rva):
        for i in range(nsec):
            s = sect + i * 40
            va, vsz = struct.unpack_from("<II", b, s + 12)
            rsz, rptr = struct.unpack_from("<II", b, s + 16)
            if va <= rva < va + max(vsz, rsz):
                return rptr + (rva - va)
        return None

    # Data directory 0 = export table. IMAGE_EXPORT_DIRECTORY.TimeDateStamp is at +4.
    exp_rva, exp_sz = struct.unpack_from("<II", b, ddir)
    if exp_rva and exp_sz:
        o = rva_to_off(exp_rva)
        if o is not None:
            out |= set(range(o + 4, o + 8))

    # Data directory 6 = debug. Each IMAGE_DEBUG_DIRECTORY is 28 bytes,
    # TimeDateStamp at +4.
    dbg_rva, dbg_sz = struct.unpack_from("<II", b, ddir + 6 * 8)
    if dbg_rva and dbg_sz:
        o = rva_to_off(dbg_rva)
        if o is not None:
            for i in range(dbg_sz // 28):
                out |= set(range(o + i * 28 + 4, o + i * 28 + 8))
    return out


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    a = open(sys.argv[1], "rb").read()
    b = open(sys.argv[2], "rb").read()

    if len(a) != len(b):
        print("DIFFERENT SIZE: %d vs %d - not the same build" % (len(a), len(b)))
        return 1
    try:
        ignore = timestamp_fields(a) | timestamp_fields(b)
    except Exception as exc:                                  # noqa: BLE001
        print("could not parse as PE (%s); falling back to an exact compare" % exc)
        ignore = set()

    diff = [i for i in range(len(a)) if a[i] != b[i]]
    real = [i for i in diff if i not in ignore]

    print("size              : %d bytes" % len(a))
    print("differing bytes   : %d" % len(diff))
    print("of those, in a linker timestamp field: %d" % (len(diff) - len(real)))
    if real:
        print("REAL differences  : %d at %s%s"
              % (len(real), [hex(x) for x in real[:16]],
                 " ..." if len(real) > 16 else ""))
        print("\nVERDICT: DIFFERENT SOURCE - the deployed file is NOT this build.")
        return 1
    print("\nVERDICT: SAME SOURCE - differs only in linker-written timestamps.")
    return 0


sys.exit(main())
