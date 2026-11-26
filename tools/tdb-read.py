#!/usr/bin/env python3
"""tdb-read.py -- read an RE Engine game's type database straight from its exe, with NO game running.

The exe carries the whole managed type database ("TDB"): every class, its fields (name, type, offset, constant
values of enums) and its methods (name, parameters, return type, the function's address). REFramework reads it
in the running game; this reads the same records off disk, so "what does app.X have" needs no launch.

    tdb-read.py <exe> find <regex>            type names that match
    tdb-read.py <exe> type <full name>        fields and methods of one type (own members only)
    tdb-read.py <exe> type <full name> --up   ... and of every parent type
    tdb-read.py <exe> who <regex>             every method or field whose NAME matches, with its type

Layout: version 69 (Resident Evil Village), read from REFramework's shared/sdk/RETypeDB.hpp (namespace tdb69)
and RETypeDefinition.hpp (RETypeDefVersion69). Other versions differ in bit widths and are refused, not guessed.
Read-only. Written 2026-11-26.
"""
import mmap
import re
import struct
import sys

TYPE_BITS = 18                 # TYPE_INDEX_BITS for version 69
TYPE_SIZE, METHOD_SIZE, FIELD_SIZE = 80, 16, 8
TYPE_IMPL_SIZE, METHOD_IMPL_SIZE, FIELD_IMPL_SIZE, PARAM_SIZE = 48, 12, 12, 12
FIELD_STATIC, FIELD_LITERAL = 0x10, 0x40
METHOD_STATIC = 0x10
LITERAL_KINDS = {"System.Boolean": "<?", "System.Byte": "<B", "System.SByte": "<b", "System.Int16": "<h",
                 "System.UInt16": "<H", "System.Int32": "<i", "System.UInt32": "<I", "System.Int64": "<q",
                 "System.UInt64": "<Q", "System.Single": "<f", "System.Double": "<d"}   # enums fall back to Int32


def bits(value, start, width):
    return (value >> start) & ((1 << width) - 1)


class Tdb:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.m = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        at = 0
        while True:
            at = self.m.find(b"TDB\x00", at)
            if at < 0:
                sys.exit("no type database found in this file")
            version = struct.unpack_from("<I", self.m, at + 4)[0]
            if 40 < version < 100:
                break
            at += 4
        if version != 69:
            sys.exit("type database version %d: only 69 is laid out here" % version)
        self.base = at
        (self.n_types, self.n_methods, self.n_fields, self.n_type_impl, self.n_field_impl, self.n_method_impl,
         _pi, _p, _e, self.n_params) = struct.unpack_from("<10I", self.m, at + 0x0C)
        self.n_strings, self.n_bytes = struct.unpack_from("<2I", self.m, at + 0x50)
        ptrs = struct.unpack_from("<17Q", self.m, at + 0x58)
        (self.p_modules, self.p_types, self.p_type_impl, self.p_methods, self.p_method_impl, self.p_fields,
         self.p_field_impl, _props, _prop_impl, _events, self.p_params, _attr, self.p_init, _attr2,
         self.p_strings, self.p_bytes, _intern) = [at + p for p in ptrs]
        self._names = {}
        # the image base and sections, to print a method's address as the running game has it
        pe = struct.unpack_from("<I", self.m, 0x3C)[0]
        self.image_base = struct.unpack_from("<Q", self.m, pe + 24 + 24)[0]

    def string(self, offset):
        start = self.p_strings + offset
        end = self.m.find(b"\x00", start)
        return self.m[start:end].decode("utf-8", "replace")

    def type_record(self, index):
        lo, hi, flags, size, fqn, crc, ctor, vt, member_method, member_field = struct.unpack_from(
            "<QQ8I", self.m, self.p_types + index * TYPE_SIZE)
        whole = lo | (hi << 64)
        return {
            "index": bits(whole, 0, TYPE_BITS), "parent": bits(whole, TYPE_BITS, TYPE_BITS),
            "declaring": bits(whole, 2 * TYPE_BITS, TYPE_BITS),
            "impl": bits(whole, 3 * TYPE_BITS + 10 + 2 * TYPE_BITS, TYPE_BITS),
            "member_method": member_method, "member_field": member_field, "size": size,
        }

    def type_impl(self, impl):
        name, namespace, _fs, _sfs, _mod, _rank, n_methods, n_fields = struct.unpack_from(
            "<4iBBHi", self.m, self.p_type_impl + impl * TYPE_IMPL_SIZE)
        return name, namespace, n_methods, n_fields

    def type_name(self, index, depth=0):
        if index in self._names:
            return self._names[index]
        if index == 0 or index >= self.n_types or depth > 8:
            return "?" if index else ""
        rec = self.type_record(index)
        name_at, namespace_at, _n, _f = self.type_impl(rec["impl"])
        name = self.string(name_at)
        if rec["declaring"] not in (0, index):
            name = self.type_name(rec["declaring"], depth + 1) + "." + name
        else:
            namespace = self.string(namespace_at)
            if namespace:
                name = namespace + "." + name
        self._names[index] = name
        return name

    def all_types(self):
        for i in range(1, self.n_types):
            yield i, self.type_name(i)

    def fields(self, index):
        rec = self.type_record(index)
        _n, _ns, _nm, n_fields = self.type_impl(rec["impl"])
        out = []
        for k in range(n_fields if rec["member_field"] else 0):
            out.append(self.field(rec["member_field"] + k))
        return out

    def field(self, i):
        whole = struct.unpack_from("<Q", self.m, self.p_fields + i * FIELD_SIZE)[0]
        declaring, impl, offset = bits(whole, 0, TYPE_BITS), bits(whole, TYPE_BITS, 20), bits(whole, TYPE_BITS + 20, 26)
        _attr, flags, a, b = struct.unpack_from("<HHII", self.m, self.p_field_impl + impl * FIELD_IMPL_SIZE)
        type_id, init_lo = bits(a, 0, 18), bits(a, 18, 14)
        name_at, init_hi = bits(b, 0, 30), bits(b, 30, 2)
        value = None
        type_name = self.type_name(type_id)
        if flags & FIELD_LITERAL:
            init_at = struct.unpack_from("<i", self.m, self.p_init + (init_lo | (init_hi << 14)) * 4)[0]
            if init_at >= 0:
                # a constant is stored at its own width; the bytes after it belong to the next one
                kind = LITERAL_KINDS.get(type_name, "<i")
                value = struct.unpack_from(kind, self.m, self.p_bytes + init_at)[0]
        return {"name": self.string(name_at), "type": type_name, "offset": offset, "flags": flags,
                "value": value, "declaring": declaring}

    def methods(self, index):
        rec = self.type_record(index)
        _n, _ns, n_methods, _nf = self.type_impl(rec["impl"])
        return [self.method(rec["member_method"] + k) for k in range(n_methods if rec["member_method"] else 0)]

    def method(self, i):
        whole, function = struct.unpack_from("<QQ", self.m, self.p_methods + i * METHOD_SIZE)
        declaring, impl, params_at = bits(whole, 0, 18), bits(whole, 18, 20), bits(whole, 38, 26)
        _attr, _vt, flags, _impl_flags, name_at = struct.unpack_from("<HhHHI", self.m,
                                                                    self.p_method_impl + impl * METHOD_IMPL_SIZE)
        n, _invoke, ret = struct.unpack_from("<HHI", self.m, self.p_bytes + params_at)
        ids = struct.unpack_from("<%dI" % n, self.m, self.p_bytes + params_at + 8) if n else ()
        return {"name": self.string(name_at), "ret": self.param(ret)[1], "params": [self.param(p) for p in ids],
                "static": bool(flags & METHOD_STATIC), "function": function, "declaring": declaring}

    def param(self, i):
        if i >= self.n_params:
            return ("?", "?")
        _attr, _init, a, b = struct.unpack_from("<HHII", self.m, self.p_params + i * PARAM_SIZE)
        return (self.string(bits(a, 0, 30)), self.type_name(bits(b, 0, 18)))

    def find_type(self, full_name):
        for i, name in self.all_types():
            if name == full_name:
                return i
        return None


def show_type(tdb, index):
    rec = tdb.type_record(index)
    print("== %s   (parent: %s; size 0x%x)" % (tdb.type_name(index), tdb.type_name(rec["parent"]) or "-", rec["size"]))
    for f in tdb.fields(index):
        kind = "const " if f["flags"] & FIELD_LITERAL else "static" if f["flags"] & FIELD_STATIC else "      "
        tail = " = %d" % f["value"] if f["value"] is not None else ""
        print("  field  %s +0x%-4x %-40s %s%s" % (kind, f["offset"], f["type"], f["name"], tail))
    for m in tdb.methods(index):
        params = ", ".join("%s %s" % (t, n) for n, t in m["params"])
        where = "0x%x" % m["function"] if m["function"] else "-"
        print("  method %s %s %s(%s)   @%s" % ("static" if m["static"] else "      ", m["ret"], m["name"], params, where))


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    tdb = Tdb(sys.argv[1])
    command, arg = sys.argv[2], sys.argv[3]
    if command == "find":
        want = re.compile(arg, re.I)
        for i, name in tdb.all_types():
            if want.search(name):
                print("%6d  %s" % (i, name))
    elif command == "type":
        index = tdb.find_type(arg)
        if index is None:
            sys.exit("no type named %s (try: find)" % arg)
        show_type(tdb, index)
        while "--up" in sys.argv:
            index = tdb.type_record(index)["parent"]
            if index == 0 or tdb.type_name(index) in ("System.Object", "via.Behavior", "via.Component", ""):
                break
            show_type(tdb, index)
    elif command == "who":
        want = re.compile(arg, re.I)
        for i in range(tdb.n_methods):
            m = tdb.method(i)
            if want.search(m["name"]):
                print("method  %s.%s(%s)" % (tdb.type_name(m["declaring"]), m["name"],
                                              ", ".join(t for _n, t in m["params"])))
        for i in range(tdb.n_fields):
            f = tdb.field(i)
            if want.search(f["name"]):
                print("field   %s.%s : %s" % (tdb.type_name(f["declaring"]), f["name"], f["type"]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
