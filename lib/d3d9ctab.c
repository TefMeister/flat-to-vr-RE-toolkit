/* d3d9ctab.c - see d3d9ctab.h.
 *
 * Format reference (D3DXSHADER_CONSTANTTABLE / D3DXSHADER_CONSTANTINFO):
 *
 *   token stream : [version][comment tokens...][instructions...][0x0000FFFF]
 *   comment token: low 16 bits == 0xFFFE, length in dwords = (tok >> 16) & 0x7FFF
 *   a CTAB comment's payload begins with the fourcc 'CTAB'
 *
 *   offsets below are relative to `base` = the byte after the fourcc:
 *     u32 size(0x1C), creator, version, constants, constant_info, flags, target
 *   each constant record (20 bytes):
 *     u32 name_offset; u16 register_set, register_index, register_count,
 *     reserved; u32 type_info, default_value
 *   the type block at type_info:
 *     u16 class, type, rows, columns, elements, struct_members
 */
#include "d3d9ctab.h"

typedef unsigned int   ct_u32;
typedef unsigned short ct_u16;
typedef unsigned char  ct_u8;

#define CT_FOURCC_CTAB 0x42415443u   /* 'CTAB' little-endian */
#define CT_TOK_END     0x0000FFFFu
#define CT_TOK_COMMENT 0x0000FFFEu

/* Unaligned little-endian reads. The bytecode is dword-aligned in practice, but
 * the CTAB's internal offsets are byte offsets and are not guaranteed to be, so
 * never dereference a cast pointer here. */
static ct_u32 rd32(const ct_u8 *p) {
    return (ct_u32)p[0] | ((ct_u32)p[1] << 8) | ((ct_u32)p[2] << 16) | ((ct_u32)p[3] << 24);
}
static ct_u16 rd16(const ct_u8 *p) {
    return (ct_u16)((ct_u32)p[0] | ((ct_u32)p[1] << 8));
}

static int parse_table(const ct_u8 *ctab, const ct_u8 *end,
                       d3d9ctab_visit_fn visit, void *user, d3d9ctab_info *info) {
    const ct_u8 *base = ctab + 4;            /* offsets are relative to here */
    if (base + 28 > end) return 0;

    ct_u32 size   = rd32(base + 0);
    ct_u32 nconst = rd32(base + 12);
    ct_u32 cinfo  = rd32(base + 16);
    ct_u32 target = rd32(base + 24);

    /* A table claiming thousands of constants is a misparse, not a shader. */
    if (size != 0x1C) return 0;
    if (nconst == 0 || nconst >= 512) return 0;
    /* Overflow-safe: cinfo + nconst*20 must stay inside the buffer. */
    if (cinfo > (ct_u32)(end - base)) return 0;
    if (nconst > ((ct_u32)(end - base) - cinfo) / 20u) return 0;

    if (info) {
        info->nconst = (int)nconst;
        info->is_vertex = 0;
        info->target[0] = 0;
        if (target < (ct_u32)(end - base)) {
            const ct_u8 *t = base + target;
            size_t i = 0;
            while (t + i < end && t[i] && i + 1 < sizeof info->target) {
                info->target[i] = (char)t[i]; ++i;
            }
            info->target[i] = 0;
            info->is_vertex = (info->target[0] == 'v');
        }
    }

    for (ct_u32 i = 0; i < nconst; ++i) {
        const ct_u8 *rec = base + cinfo + i * 20u;
        ct_u32 name_off = rd32(rec + 0);
        ct_u16 regset   = rd16(rec + 4);
        ct_u16 regidx   = rd16(rec + 6);
        ct_u16 regcount = rd16(rec + 8);
        ct_u32 typeinfo = rd32(rec + 12);
        if (name_off > (ct_u32)(end - base)) continue;

        d3d9ctab_constant c;
        c.name   = (const char *)(base + name_off);
        c.regset = (int)regset;
        c.reg    = (int)regidx;
        c.count  = (int)regcount;
        c.cls    = -1;
        c.rows   = 0;
        c.cols   = 0;
        /* The type block is optional information: if it does not fit, report
         * the constant without it rather than dropping the constant. */
        if (typeinfo + 8 <= (ct_u32)(end - base)) {
            const ct_u8 *t = base + typeinfo;
            c.cls  = (int)rd16(t + 0);
            c.rows = (int)rd16(t + 4);
            c.cols = (int)rd16(t + 6);
        }
        if (visit && !visit(user, &c)) break;
    }
    return 1;
}

int d3d9ctab_parse(const void *bytecode, size_t max_bytes,
                   d3d9ctab_visit_fn visit, void *user, d3d9ctab_info *info) {
    if (info) { info->nconst = 0; info->is_vertex = 0; info->target[0] = 0; }
    if (!bytecode) return 0;
    if (max_bytes == 0) max_bytes = D3D9CTAB_MAX_SHADER_BYTES;

    const ct_u8 *p   = (const ct_u8 *)bytecode;
    const ct_u8 *end = p + max_bytes;

    /* Version token: 0xFFFExxxx (vertex) or 0xFFFFxxxx (pixel). Anything else is
     * not a shader and we refuse to walk it. */
    if (p + 4 > end) return 0;
    ct_u32 hi = rd32(p) >> 16;
    if (hi != 0xFFFEu && hi != 0xFFFFu) return 0;
    p += 4;

    /* CTAB is emitted in the comment block that precedes the code, so the walk
     * stops at the first non-comment token. That bounds the scan tightly and
     * means a malformed instruction stream is never interpreted. */
    while (p + 4 <= end) {
        ct_u32 tok = rd32(p);
        if (tok == CT_TOK_END) break;
        if ((tok & 0x0000FFFFu) != CT_TOK_COMMENT) break;

        ct_u32 len_dw = (tok >> 16) & 0x7FFFu;
        const ct_u8 *payload = p + 4;
        if (len_dw > ((ct_u32)(end - payload)) / 4u) return 0;   /* overflow-safe */
        const ct_u8 *next = payload + (size_t)len_dw * 4u;

        if (len_dw >= 1 && rd32(payload) == CT_FOURCC_CTAB) {
            /* Bound the table by the comment's own payload, not the whole
             * buffer: a truncated CTAB must fail rather than read neighbours. */
            return parse_table(payload, next, visit, user, info);
        }
        p = next;
    }
    return 0;
}

/* ---- wants ---------------------------------------------------------------- */
typedef struct {
    const d3d9ctab_want *wants;
    int nwants;
} want_ctx;

static int name_eq(const char *p, const char *lit) {
    /* `p` points into the bounded buffer and the table's strings are
     * NUL-terminated within it; compare without running past either. */
    while (*p && *lit) { if (*p != *lit) return 0; ++p; ++lit; }
    return *p == 0 && *lit == 0;
}

static int want_visit(void *user, const d3d9ctab_constant *c) {
    want_ctx *ctx = (want_ctx *)user;
    for (int i = 0; i < ctx->nwants; ++i) {
        const d3d9ctab_want *w = &ctx->wants[i];
        if (w->regset != c->regset) continue;
        if (!name_eq(c->name, w->name)) continue;
        if (w->out_reg)   *w->out_reg   = c->reg;
        if (w->out_count) *w->out_count = c->count;
        if (w->out_class) *w->out_class = c->cls;
        break;
    }
    return 1;
}

int d3d9ctab_parse_wants(const void *bytecode, size_t max_bytes,
                         const d3d9ctab_want *wants, int nwants,
                         d3d9ctab_info *info) {
    want_ctx ctx;
    ctx.wants = wants;
    ctx.nwants = nwants;
    return d3d9ctab_parse(bytecode, max_bytes, want_visit, &ctx, info);
}

/* ---- registry -------------------------------------------------------------
 * Fixed-capacity open addressing with linear probing over caller-supplied
 * storage. Each slot is `const void *key` followed by the caller's record.
 */
/* Each slot begins with `const void *key`, per the header's contract, so the
 * key is directly addressable and correctly aligned. */
static ct_u8 *slot_at(const d3d9ctab_registry *r, int i) {
    return (ct_u8 *)r->slots + (size_t)i * r->slotsize;
}
static const void *slot_key(const d3d9ctab_registry *r, int i) {
    return *(const void *const *)slot_at(r, i);
}
static void slot_setkey(const d3d9ctab_registry *r, int i, const void *k) {
    *(const void **)slot_at(r, i) = k;
}
static ct_u8 *slot_rec(const d3d9ctab_registry *r, int i) {
    return slot_at(r, i) + sizeof(const void *);
}
static void copy_bytes(ct_u8 *dst, const ct_u8 *src, size_t n) {
    for (size_t i = 0; i < n; ++i) dst[i] = src[i];
}

static unsigned slot_hash(const d3d9ctab_registry *r, const void *key) {
    /* Fibonacci hashing: the low bits of a heap pointer are mostly constant, so
     * mixing before masking matters. */
    unsigned long long x = (unsigned long long)(size_t)key;
    x *= 0x9E3779B97F4A7C15ull;
    return (unsigned)(x >> 40) & (unsigned)(r->capacity - 1);
}

void d3d9ctab_registry_init(d3d9ctab_registry *r, void *slots, int capacity,
                            size_t slotsize, size_t recsize) {
    if (!r) return;
    r->slots = slots;
    r->capacity = capacity;
    r->slotsize = slotsize;
    r->recsize = recsize;
    r->count = 0;
    for (int i = 0; i < capacity; ++i) slot_setkey(r, i, 0);
}

int d3d9ctab_registry_put(d3d9ctab_registry *r, const void *key, const void *rec) {
    if (!r || !r->slots || !key || !rec) return 0;
    unsigned h = slot_hash(r, key);
    for (int probe = 0; probe < r->capacity; ++probe) {
        int i = (int)((h + (unsigned)probe) & (unsigned)(r->capacity - 1));
        const void *k = slot_key(r, i);
        if (k == 0) {
            slot_setkey(r, i, key);
            copy_bytes(slot_rec(r, i), (const ct_u8 *)rec, r->recsize);
            ++r->count;
            return 1;
        }
        if (k == key) {                       /* same shader re-created: refresh */
            copy_bytes(slot_rec(r, i), (const ct_u8 *)rec, r->recsize);
            return 1;
        }
    }
    return 0;   /* full - the caller should log this, never guess a register */
}

const void *d3d9ctab_registry_get(const d3d9ctab_registry *r, const void *key) {
    if (!r || !r->slots || !key) return 0;
    unsigned h = slot_hash(r, key);
    for (int probe = 0; probe < r->capacity; ++probe) {
        int i = (int)((h + (unsigned)probe) & (unsigned)(r->capacity - 1));
        const void *k = slot_key(r, i);
        if (k == 0) return 0;
        if (k == key) return slot_rec(r, i);
    }
    return 0;
}

/* Backward-shift deletion. Simply clearing a slot under linear probing breaks
 * lookups of later keys whose probe run passes through it, so the run is
 * compacted: any following entry whose ideal slot is at or before the hole is
 * moved into it. Slots are copied whole, so no temporary record buffer is
 * needed and there is no maximum record size. */
void d3d9ctab_registry_remove(d3d9ctab_registry *r, const void *key) {
    if (!r || !r->slots || !key) return;
    unsigned mask = (unsigned)(r->capacity - 1);
    unsigned h = slot_hash(r, key);
    int hole = -1;
    for (int probe = 0; probe < r->capacity; ++probe) {
        int i = (int)((h + (unsigned)probe) & mask);
        const void *k = slot_key(r, i);
        if (k == 0) return;                   /* not present */
        if (k == key) { hole = i; break; }
    }
    if (hole < 0) return;
    --r->count;

    int i = hole;
    for (;;) {
        int j = i;
        for (;;) {
            j = (int)(((unsigned)j + 1u) & mask);
            const void *kj = slot_key(r, j);
            if (kj == 0) { slot_setkey(r, i, 0); return; }
            unsigned kh = slot_hash(r, kj);
            /* Can kj legally live at i? Only if its ideal slot is not strictly
             * inside the (i, j] window - the standard cyclic test. */
            int movable = (i <= j)
                ? (kh <= (unsigned)i || kh > (unsigned)j)
                : (kh <= (unsigned)i && kh > (unsigned)j);
            if (movable) {
                copy_bytes(slot_at(r, i), slot_at(r, j), r->slotsize);
                i = j;
                break;
            }
        }
    }
}

int d3d9ctab_registry_count(const d3d9ctab_registry *r) {
    return r ? r->count : 0;
}
