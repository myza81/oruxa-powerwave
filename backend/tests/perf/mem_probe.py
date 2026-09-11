"""Cross-platform peak-memory probe for the performance baseline
(Pre-Advanced Foundation Slice F2).

Neither of the two "obvious" options works cleanly for this project's
actual environments (Windows dev machines, `ubuntu-latest` CI):

- `resource.getrusage()` is POSIX-only stdlib -- `import resource` raises
  `ModuleNotFoundError` on Windows, where this baseline's own first
  measurement run happens.
- `psutil` is not an existing dependency of this project (not in
  `backend/requirements*.txt`), and the task instructs against adding a
  new dependency purely for one benchmark.
- `tracemalloc` (stdlib, genuinely cross-platform) was considered and
  REJECTED for the headline memory number: COMTRADE/CSV import is
  almost entirely NumPy/pandas array allocation, and NumPy's C-level
  buffer allocator does not route through CPython's tracked allocator
  that `tracemalloc` observes by default -- it would report a
  near-zero peak for exactly the allocations this baseline cares about
  most (verified by direct inspection, not assumed).

This module reports the OS's own **peak RSS** (POSIX,
`resource.getrusage(RUSAGE_SELF).ru_maxrss`) / **peak working set size**
(Windows, `GetProcessMemoryInfo` via `ctypes` -- the same OS API
`psutil.Process.memory_info().peak_wset` itself calls internally, so
this is not a lesser measurement, just not a new dependency). Both are
stdlib-only (`resource`/`ctypes`), and both report the IDENTICAL
concept: a monotonically non-decreasing "high-water mark since process
start," never a delta and never a Python-allocation-only figure.

Because it is a high-water mark for the whole process, a meaningful
number requires measuring ONE isolated operation in a FRESH process
(see `baseline_runner.py`'s subprocess-per-phase design) -- calling
`peak_bytes()` twice within one long-lived process that already did
unrelated work earlier would report a contaminated, cumulative figure,
not the cost of the operation you actually care about.
"""

from __future__ import annotations

import platform


def peak_bytes() -> int:
    """OS-reported peak RSS / peak working set for the CURRENT process,
    in bytes, since process start."""
    if platform.system() == "Windows":
        return _peak_bytes_windows()
    return _peak_bytes_posix()


def _peak_bytes_posix() -> int:
    import resource

    ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports ru_maxrss in KiB; macOS (Darwin) reports it in bytes
    # -- a long-documented BSD/Linux libc divergence, not a bug here.
    # This project's CI runs on ubuntu-latest (see .github/workflows/
    # ci.yml), so the KiB path is what CI-reproduced numbers will use.
    return ru_maxrss * 1024 if platform.system() == "Linux" else ru_maxrss


def _peak_bytes_windows() -> int:
    import ctypes
    from ctypes import wintypes

    class _ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    # Explicit restype/argtypes are required here -- ctypes' default
    # (`c_int`) TRUNCATES the 64-bit pseudo-handle GetCurrentProcess()
    # returns on 64-bit Windows, which makes the later
    # GetProcessMemoryInfo call fail with an invalid-handle error.
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
    handle = kernel32.GetCurrentProcess()
    ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    if not ok:
        raise OSError(f"GetProcessMemoryInfo failed (GetLastError={ctypes.get_last_error()})")
    return int(counters.PeakWorkingSetSize)


def memory_metric_label() -> str:
    """Human-readable label for whichever metric `peak_bytes()` actually
    returned on THIS platform -- baseline reports must use this rather
    than a hardcoded "peak RSS" string, since the two platforms measure
    different (if analogous) OS concepts."""
    if platform.system() == "Windows":
        return "peak working set size (Windows GetProcessMemoryInfo)"
    if platform.system() == "Linux":
        return "peak RSS (Linux getrusage ru_maxrss)"
    return "peak RSS (POSIX getrusage ru_maxrss)"
