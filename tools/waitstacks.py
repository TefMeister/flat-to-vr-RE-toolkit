#!/usr/bin/env python3
"""waitstacks.py: where do the game's threads WAIT?  A stack sampler that never freezes the game.

Every --interval ms it suspends ONE named thread for well under a millisecond, reads its call stack
(dbghelp StackWalk64), resumes it, and moves on.  At the end it prints, per thread, the most common
stacks with their share of samples: a thread that spends 40 % of its samples inside xrWaitFrame is
waiting 40 % of the frame there.

    python waitstacks.py --proc SHProto-Win64-Shipping            # 5 s, GameThread + RenderThread + RHIThread
    python waitstacks.py --proc MyGame --seconds 8 --threads RenderThread --frames 12 --top 10
    python waitstacks.py --proc MyGame --list                     # the named threads, to pick from

--proc is the executable name without .exe.  The thread defaults are Unreal Engine's names; other engines
name their threads differently, so run --list first.

Made 2026-11-05 for the Silent Hill 2 optimiser (step 2) after a debugger attach froze the game for good;
it found the frame-time wait there (a UEVR plugin rewriting a file several times a frame).
Windows x64 only.  Needs no symbols: module+offset is printed where no export name is known.
"""
import argparse, collections, ctypes, ctypes.wintypes as wt, sys, time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
dbg = ctypes.WinDLL("dbghelp", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

PROCESS_ALL = 0x1F0FFF
THREAD_ALL = 0x1FFFFF
TH32CS_SNAPTHREAD = 0x4
CONTEXT_AMD64_CONTROL_INTEGER = 0x100003
IMAGE_FILE_MACHINE_AMD64 = 0x8664

class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", ctypes.c_long), ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", wt.DWORD)]

k32.OpenProcess.restype = wt.HANDLE
k32.OpenThread.restype = wt.HANDLE
k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.GetThreadDescription.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
k32.LocalFree.argtypes = [ctypes.c_void_p]
k32.GetThreadContext.argtypes = [wt.HANDLE, ctypes.c_void_p]
dbg.SymInitialize.argtypes = [wt.HANDLE, ctypes.c_char_p, wt.BOOL]
dbg.SymSetOptions.argtypes = [wt.DWORD]
dbg.SymFromAddr.argtypes = [wt.HANDLE, ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64), ctypes.c_void_p]
dbg.SymGetModuleBase64.restype = ctypes.c_uint64
dbg.SymGetModuleBase64.argtypes = [wt.HANDLE, ctypes.c_uint64]
dbg.SymFunctionTableAccess64.restype = ctypes.c_void_p
dbg.SymFunctionTableAccess64.argtypes = [wt.HANDLE, ctypes.c_uint64]
dbg.StackWalk64.argtypes = [wt.DWORD, wt.HANDLE, wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
psapi.GetModuleFileNameExW.argtypes = [wt.HANDLE, wt.HANDLE, ctypes.c_wchar_p, wt.DWORD]


def find_pid(name):
    import subprocess
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith('"'):
            return int(line.split('","')[1])
    raise SystemExit(f"{name}.exe is not running")


def list_threads(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32(); te.dwSize = ctypes.sizeof(te)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def thread_name(h):
    p = ctypes.c_wchar_p()
    if k32.GetThreadDescription(h, ctypes.byref(p)) >= 0 and p.value:
        s = p.value; k32.LocalFree(p); return s
    return ""


class Symbolizer:
    def __init__(self, hproc):
        self.h = hproc
        dbg.SymSetOptions(0x2 | 0x4 | 0x10)  # SYMOPT_UNDNAME | SYMOPT_DEFERRED_LOADS | SYMOPT_LOAD_LINES
        if not dbg.SymInitialize(hproc, None, True):
            print("SymInitialize failed", ctypes.get_last_error(), file=sys.stderr)
        self.cache = {}
        self.modnames = {}

    def module(self, base):
        if base in self.modnames: return self.modnames[base]
        buf = ctypes.create_unicode_buffer(520)
        n = psapi.GetModuleFileNameExW(self.h, wt.HANDLE(base), buf, 520)
        name = buf.value.replace("\\", "/").rsplit("/", 1)[-1] if n else f"{base:#x}"
        self.modnames[base] = name
        return name

    def name(self, addr):
        if addr in self.cache: return self.cache[addr]
        base = dbg.SymGetModuleBase64(self.h, addr)
        mod = self.module(base) if base else "?"
        buf = ctypes.create_string_buffer(88 + 1000)
        ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32))[0] = 88          # SizeOfStruct
        ctypes.cast(ctypes.byref(buf, 80), ctypes.POINTER(ctypes.c_uint32))[0] = 1000  # MaxNameLen
        disp = ctypes.c_uint64(0)
        if dbg.SymFromAddr(self.h, addr, ctypes.byref(disp), buf):
            sym = ctypes.string_at(ctypes.addressof(buf) + 84).decode(errors="replace")
            s = f"{mod}!{sym}+{disp.value:#x}"
        else:
            s = f"{mod}+{addr - base:#x}" if base else f"{addr:#x}"
        self.cache[addr] = s
        return s


def walk(hproc, hthr, max_frames):
    ctx = ctypes.create_string_buffer(1232 + 64)
    aligned = (ctypes.addressof(ctx) + 15) & ~15
    ctypes.cast(aligned + 0x30, ctypes.POINTER(ctypes.c_uint32))[0] = CONTEXT_AMD64_CONTROL_INTEGER
    if not k32.GetThreadContext(hthr, aligned):
        return None
    rip = ctypes.cast(aligned + 0xF8, ctypes.POINTER(ctypes.c_uint64))[0]
    rsp = ctypes.cast(aligned + 0x98, ctypes.POINTER(ctypes.c_uint64))[0]
    rbp = ctypes.cast(aligned + 0xA0, ctypes.POINTER(ctypes.c_uint64))[0]
    frame = ctypes.create_string_buffer(512)
    u64 = ctypes.POINTER(ctypes.c_uint64); u32 = ctypes.POINTER(ctypes.c_uint32)
    base = ctypes.addressof(frame)
    for off, val in ((0, rip), (32, rbp), (48, rsp)):          # AddrPC, AddrFrame, AddrStack
        ctypes.cast(base + off, u64)[0] = val
        ctypes.cast(base + off + 12, u32)[0] = 3                # AddrModeFlat
    pcs = []
    for _ in range(max_frames):
        if not dbg.StackWalk64(IMAGE_FILE_MACHINE_AMD64, hproc, hthr, frame, aligned, None,
                               dbg.SymFunctionTableAccess64, dbg.SymGetModuleBase64, None):
            break
        pc = ctypes.cast(base, u64)[0]
        if pc == 0: break
        pcs.append(pc)
    return pcs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proc", required=True, help="the game's executable name without .exe")
    ap.add_argument("--seconds", type=float, default=5)
    ap.add_argument("--interval", type=float, default=4, help="ms between samples of one thread")
    ap.add_argument("--threads", default="GameThread,RenderThread,RHIThread", help="thread names, comma separated; 'main' = the first thread")
    ap.add_argument("--frames", type=int, default=10)
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--list", action="store_true", help="only list the named threads and leave")
    a = ap.parse_args()

    pid = find_pid(a.proc)
    hproc = k32.OpenProcess(PROCESS_ALL, False, pid)
    if not hproc: raise SystemExit(f"cannot open process {pid}: {ctypes.get_last_error()}")
    sym = Symbolizer(hproc)
    tids = list_threads(pid)
    handles = {}
    for tid in tids:
        h = k32.OpenThread(THREAD_ALL, False, tid)
        if h: handles[tid] = h
    names = {tid: thread_name(h) for tid, h in handles.items()}
    if a.list:
        for tid, n in sorted(names.items(), key=lambda x: x[1]):
            if n: print(f"{tid:>6}  {n}")
        return
    wanted = [w.strip() for w in a.threads.split(",") if w.strip()]
    targets = []
    for w in wanted:
        if w == "main":
            targets.append((tids[0], "main"))
            continue
        hits = [tid for tid, n in names.items() if n == w]
        if not hits:
            print(f"no thread named {w}; named threads: {sorted(set(n for n in names.values() if n))}")
            continue
        targets.append((hits[0], w))
    stacks = {name: collections.Counter() for _, name in targets}
    tops = {name: collections.Counter() for _, name in targets}
    counts = {name: 0 for _, name in targets}
    end = time.perf_counter() + a.seconds
    while time.perf_counter() < end:
        for tid, name in targets:
            h = handles[tid]
            if k32.SuspendThread(h) == 0xFFFFFFFF: continue
            try:
                pcs = walk(hproc, h, a.frames)
            finally:
                k32.ResumeThread(h)
            if not pcs: continue
            counts[name] += 1
            key = tuple(sym.name(pc) for pc in pcs)
            stacks[name][key] += 1
            # the first frame outside the kernel-side wait: the thing that is waiting
            waiter = next((f for f in key if not f.lower().startswith(("ntdll", "kernelbase", "kernel32", "win32u"))), key[0])
            tops[name][waiter] += 1
        time.sleep(a.interval / 1000)
    for _, name in targets:
        n = counts[name] or 1
        print(f"\n=== {name}: {counts[name]} samples ===")
        print("-- who is waiting / working (first frame outside the system DLLs):")
        for w, c in tops[name].most_common(a.top):
            print(f"  {100*c/n:5.1f} %  {w}")
        print("-- the most common stacks:")
        for st, c in stacks[name].most_common(a.top):
            print(f"  {100*c/n:5.1f} %")
            for f in st: print(f"        {f}")


if __name__ == "__main__":
    main()
