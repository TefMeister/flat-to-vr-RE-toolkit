/* d3d9ctab.h - read a Direct3D 9 shader constant table (CTAB) at runtime, and
 * keep a pointer-keyed map of what each shader wants.
 *
 * WHY THIS IS IN THE TOOLKIT
 * --------------------------
 * Every D3D9-era flat-to-VR conversion asks the same question at the same
 * moment: *which constant register does this particular shader put the camera
 * matrix in?* The answer travels inside the bytecode, in the `CTAB` comment
 * block, and it is available at Create{Vertex,Pixel}Shader time - before the
 * shader is ever used.
 *
 * It has to be per-shader because the register is NOT fixed:
 *
 *   alan-wake-vr    g_mViewToClip at c0 in 2,238 shaders and c192 in 2,084 -
 *                   a 192-register skinning palette displaces it
 *   prince-of-persia-2008-vr
 *                   g_WorldViewProj at c0 in 6,292 and c128 in 2,016 - same
 *                   story, a 128-register palette
 *   alice-madness-returns-vr
 *                   NvStereoFixTexture at s1 (14,221), s3 (202), s0 (46),
 *                   s2 (10) - the sampler varies too
 *
 * A fixed register corrupts the other half of the corpus, silently, in a way
 * that renders. Three projects independently needed this; the parser was
 * written twice before being factored here.
 *
 * SAFETY - read before changing the walker
 * ----------------------------------------
 * `CreateVertexShader(const DWORD *pFunction, ...)` passes NO LENGTH. The token
 * stream is self-delimiting (it ends with 0x0000FFFF), so the walk must be
 * driven by the tokens themselves and must refuse to run past a cap. Every read
 * here is bounds-checked and every length is validated overflow-safely before
 * use. This parses data supplied by the game, inside the game's own process; it
 * must never be the thing that faults.
 *
 * Dependency-free on purpose: no windows.h, no d3d9.h, no CRT string calls, no
 * allocation. That keeps it unit-testable on the host, which is how it was
 * validated - see the per-project suites, which between them check it against
 * 9,971 (Alan Wake) and 45,832 (Alice) real shipped shaders.
 */
#ifndef D3D9CTAB_H
#define D3D9CTAB_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* D3DXREGISTER_SET */
#define D3D9CTAB_RS_BOOL    0
#define D3D9CTAB_RS_INT4    1
#define D3D9CTAB_RS_FLOAT4  2
#define D3D9CTAB_RS_SAMPLER 3

/* D3DXPARAMETER_CLASS - the field most tooling ignores and the one that decides
 * whether a per-eye edit must be transposed. MATRIX_ROWS means register i holds
 * ROW i; MATRIX_COLUMNS means it holds COLUMN i, and the same formula then needs
 * a completely different implementation. Always confirm against the bytecode
 * too: four consecutive `dp4` against c0..c3 means rows; four `mul`/`mad`
 * accumulating a float4 means columns. */
#define D3D9CTAB_CLASS_SCALAR         0
#define D3D9CTAB_CLASS_VECTOR         1
#define D3D9CTAB_CLASS_MATRIX_ROWS    2
#define D3D9CTAB_CLASS_MATRIX_COLUMNS 3
#define D3D9CTAB_CLASS_OBJECT         4
#define D3D9CTAB_CLASS_STRUCT         5

#define D3D9CTAB_REG_NONE (-1)
/* Sanity cap on one shader. The largest in any shipped bank seen so far is far
 * under this; it exists to bound a malformed stream. */
#define D3D9CTAB_MAX_SHADER_BYTES (512 * 1024)

typedef struct {
    int nconst;      /* constants in the table                        */
    int is_vertex;   /* 1 = vs_*, 0 = ps_*                            */
    char target[12]; /* "vs_3_0" / "ps_3_0", NUL-terminated           */
} d3d9ctab_info;

/* One constant, as the visitor sees it. `cls` is D3D9CTAB_CLASS_* or -1 when the
 * type block could not be read safely. */
typedef struct {
    const char *name;
    int regset;   /* D3D9CTAB_RS_*        */
    int reg;      /* register index       */
    int count;    /* register count       */
    int cls;      /* D3D9CTAB_CLASS_*, or -1 */
    int rows, cols;
} d3d9ctab_constant;

/* Return 0 to stop iterating early, non-zero to continue. */
typedef int (*d3d9ctab_visit_fn)(void *user, const d3d9ctab_constant *c);

/* Walk a D3D9 shader's token stream and visit every constant in its CTAB.
 * `bytecode` points at the version token (what CreateShader is handed).
 * `max_bytes` 0 = D3D9CTAB_MAX_SHADER_BYTES. `info` may be NULL.
 * Returns 1 if a CTAB was found and parsed, 0 otherwise. */
int d3d9ctab_parse(const void *bytecode, size_t max_bytes,
                   d3d9ctab_visit_fn visit, void *user, d3d9ctab_info *info);

/* ---- convenience: match a fixed set of names -------------------------------
 * The common case. Every entry whose `name` and `regset` match has its register
 * (and optionally count and class) written out. Fields not found are left as
 * the caller initialised them - so initialise to D3D9CTAB_REG_NONE.
 */
typedef struct {
    const char *name;
    int         regset;
    int        *out_reg;    /* required */
    int        *out_count;  /* may be NULL */
    int        *out_class;  /* may be NULL */
} d3d9ctab_want;

int d3d9ctab_parse_wants(const void *bytecode, size_t max_bytes,
                         const d3d9ctab_want *wants, int nwants,
                         d3d9ctab_info *info);

/* ---- pointer-keyed registry ------------------------------------------------
 * Maps the interface pointer CreateShader returned to whatever record the caller
 * keeps. Storage is caller-supplied, so there is no allocation and the record
 * type stays the caller's own. Capacity MUST be a power of two.
 *
 *   static struct { const void *key; my_regs rec; } slots[8192];
 *   d3d9ctab_registry reg;
 *   d3d9ctab_registry_init(&reg, slots, 8192, sizeof slots[0], sizeof(my_regs));
 */
typedef struct {
    void  *slots;
    int    capacity;      /* power of two */
    size_t slotsize;      /* sizeof one slot: key pointer + record */
    size_t recsize;
    int    count;
} d3d9ctab_registry;

void d3d9ctab_registry_init(d3d9ctab_registry *r, void *slots, int capacity,
                            size_t slotsize, size_t recsize);
/* 1 if stored; 0 if the table is full. Re-putting an existing key replaces its
 * record, which is what shader-pointer reuse after a Release requires. */
int  d3d9ctab_registry_put(d3d9ctab_registry *r, const void *key, const void *rec);
/* NULL when the key was never registered. */
const void *d3d9ctab_registry_get(const d3d9ctab_registry *r, const void *key);
void d3d9ctab_registry_remove(d3d9ctab_registry *r, const void *key);
int  d3d9ctab_registry_count(const d3d9ctab_registry *r);

#ifdef __cplusplus
}
#endif

#endif /* D3D9CTAB_H */
