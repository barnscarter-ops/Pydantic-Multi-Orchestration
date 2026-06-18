#!/usr/bin/env python3
"""RAM usage monitor (stdlib only).

Samples system RAM usage at a fixed interval, logs each sample to a CSV file,
and prints a min/max/average summary after every cycle. Loops indefinitely.

Normal mode : 60 samples, one per minute (1 hour per cycle).
Demo mode   : 6 samples, one every 5 seconds (~30 seconds per cycle).

Primary RAM source is /proc/meminfo (Linux). A ctypes-based fallback is
provided for Windows (GlobalMemoryStatusEx). No third-party packages required.
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime

LOG_FILE = "ram_log.csv"
HEADER = ["timestamp", "used_mb", "percent"]

# (interval_seconds, samples_per_cycle)
NORMAL_MODE = (60, 60)   # every minute for an hour
DEMO_MODE = (5, 6)       # every 5 seconds for 30 seconds


# --------------------------------------------------------------------------- #
# RAM reading
# --------------------------------------------------------------------------- #
def _read_ram_linux():
    """Return (used_mb, percent) by parsing /proc/meminfo."""
    info = {}
    with open("/proc/meminfo", "r") as fh:
        for line in fh:
            key, _, rest = line.partition(":")
            # rest looks like '   16461176 kB'
            parts = rest.split()
            if parts:
                info[key] = int(parts[0])  # value in kB

    total_kb = info["MemTotal"]
    # MemAvailable is the best estimate of usable memory; fall back if absent.
    if "MemAvailable" in info:
        available_kb = info["MemAvailable"]
    else:
        available_kb = (
            info.get("MemFree", 0)
            + info.get("Buffers", 0)
            + info.get("Cached", 0)
        )

    used_kb = total_kb - available_kb
    used_mb = used_kb / 1024.0
    percent = (used_kb / total_kb) * 100.0 if total_kb else 0.0
    return round(used_mb, 1), round(percent, 1)


def _read_ram_windows():
    """Return (used_mb, percent) via ctypes GlobalMemoryStatusEx (Windows)."""
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))

    total = stat.ullTotalPhys
    used = total - stat.ullAvailPhys
    used_mb = used / (1024.0 * 1024.0)
    percent = float(stat.dwMemoryLoad)
    return round(used_mb, 1), round(percent, 1)


def read_ram():
    """Return (used_mb, percent) for the current platform."""
    if os.path.exists("/proc/meminfo"):
        return _read_ram_linux()
    if sys.platform.startswith("win"):
        return _read_ram_windows()
    raise RuntimeError(
        "Unsupported platform: no /proc/meminfo and not Windows."
    )


# --------------------------------------------------------------------------- #
# CSV logging
# --------------------------------------------------------------------------- #
def log_sample(used_mb, percent):
    """Append a single timestamped sample to the CSV log."""
    need_header = (not os.path.exists(LOG_FILE)) or os.path.getsize(LOG_FILE) == 0
    with open(LOG_FILE, "a", newline="") as fh:
        writer = csv.writer(fh)
        if need_header:
            writer.writerow(HEADER)
        timestamp = datetime.now().isoformat(timespec="seconds")
        writer.writerow([timestamp, used_mb, percent])


def summarize_cycle(num_samples):
    """Read the log and print min/max/avg for the last `num_samples` rows."""
    with open(LOG_FILE, "r", newline="") as fh:
        rows = list(csv.DictReader(fh))

    cycle = rows[-num_samples:]
    if not cycle:
        print("No samples recorded this cycle.")
        return

    used = [float(r["used_mb"]) for r in cycle]
    pct = [float(r["percent"]) for r in cycle]

    def stats(values):
        return min(values), max(values), sum(values) / len(values)

    u_min, u_max, u_avg = stats(used)
    p_min, p_max, p_avg = stats(pct)

    print("\n" + "=" * 48)
    print(f"Cycle summary ({len(cycle)} samples)")
    print(f"  Window : {cycle[0]['timestamp']}  ->  {cycle[-1]['timestamp']}")
    print(f"  used_mb : min={u_min:.1f}  max={u_max:.1f}  avg={u_avg:.1f}")
    print(f"  percent : min={p_min:.1f}  max={p_max:.1f}  avg={p_avg:.1f}")
    print("=" * 48 + "\n")


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
def run(interval_seconds, samples_per_cycle):
    cycle_num = 0
    while True:
        cycle_num += 1
        print(
            f"Starting cycle {cycle_num}: {samples_per_cycle} samples, "
            f"every {interval_seconds}s."
        )
        for i in range(samples_per_cycle):
            used_mb, percent = read_ram()
            log_sample(used_mb, percent)
            print(
                f"  [{i + 1}/{samples_per_cycle}] "
                f"used_mb={used_mb:.1f}  percent={percent:.1f}%"
            )
            # Don't sleep after the final sample of the cycle.
            if i < samples_per_cycle - 1:
                time.sleep(interval_seconds)
        summarize_cycle(samples_per_cycle)


def main():
    parser = argparse.ArgumentParser(
        description="Monitor RAM usage and log samples to ram_log.csv."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Demo mode: sample every 5s for 30s instead of every minute.",
    )
    args = parser.parse_args()

    interval, samples = DEMO_MODE if args.demo else NORMAL_MODE

    try:
        run(interval, samples)
    except KeyboardInterrupt:
        print("\nStopped by user. Goodbye.")
        sys.exit(0)


if __name__ == "__main__":
    main()
