"""
Runs the experiments listed in SPEC.md and writes one CSV file per experiment
into results/. The figures are drawn from those CSV files by plots.py.

    python -m cachesim.experiments                  # all experiments
    python -m cachesim.experiments --only size l2   # just some of them
    python -m cachesim.experiments --no-plots       # CSV files only

Generate the traces first:  python -m cachesim.tracegen
"""
import argparse
import csv
import sys
import time
from pathlib import Path

from .config import build_hierarchy
from .trace import read_trace

KB = 1024
TRACE_DIR = Path("traces")
RESULT_DIR = Path("results")


# ---------------------------------------------------------------- helpers

def make_config(l1_size=32 * KB, l1_assoc=4, block=64, policy="LRU",
                l1d_write="wb", l2_write="wb", l2=True, l2_size=256 * KB,
                l2_assoc=8, t_mem=100):
    """Default hierarchy from SPEC.md with any parameter overridden."""
    cfg = {
        "timing": {"l1_hit": 1, "l2_hit": 10, "memory": t_mem},
        "l1i": {"size": l1_size, "block_size": block, "assoc": l1_assoc,
                "policy": policy},
        "l1d": {"size": l1_size, "block_size": block, "assoc": l1_assoc,
                "policy": policy, "write_policy": l1d_write},
    }
    if l2:
        cfg["l2"] = {"size": l2_size, "block_size": block, "assoc": l2_assoc,
                     "policy": policy, "write_policy": l2_write}
    return cfg


def mem_latency(block):
    """Memory latency that grows with block size: 60 cycles to the first
    word, then 5 cycles per 8 bytes. Gives exactly 100 cycles at 64 B."""
    return 60 + (block // 8) * 5


def run_one(trace, cfg):
    """Run one trace through one configuration and collect the numbers."""
    h = build_hierarchy(cfg)
    h.run(read_trace(TRACE_DIR / f"{trace}.din"))
    s = h.summary()
    d = s["l1d"]
    l2 = s["l2"]
    return {
        "accesses": s["accesses"],
        "total_cycles": s["total_cycles"],
        "amat": round(s["amat"], 4),
        "l1d_accesses": d["accesses"],
        "l1d_miss_rate": round(d["misses"] / d["accesses"], 6) if d["accesses"] else 0.0,
        "l1d_compulsory": d["compulsory"],
        "l1d_capacity": d["capacity"],
        "l1d_conflict": d["conflict"],
        "l1d_writebacks": d["writebacks"],
        "l2_accesses": l2["accesses"] if l2 else 0,
        "l2_miss_rate": round(l2["misses"] / l2["accesses"], 6) if l2 and l2["accesses"] else "",
        "mem_read_bytes": s["mem_read_bytes"],
        "mem_write_bytes": s["mem_write_bytes"],
    }


def sweep(name, runs):
    """runs = list of (trace, params, config). Runs them all, saves a CSV."""
    rows = []
    for trace, params, cfg in runs:
        t0 = time.time()
        row = {**params, "trace": trace, **run_one(trace, cfg)}
        rows.append(row)
        label = ", ".join(f"{k}={v}" for k, v in params.items())
        print(f"  {trace:15s} {label:34s} AMAT {row['amat']:8.3f}   "
              f"L1D miss {row['l1d_miss_rate']:.4f}   ({time.time() - t0:.1f}s)")
    RESULT_DIR.mkdir(exist_ok=True)
    with open(RESULT_DIR / f"{name}.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


# ------------------------------------------------------------ experiments

def exp_size():
    """1. L1 cache size vs miss rate and AMAT."""
    traces = ["random", "vecadd", "matmul_ijk", "matmul_blocked"]
    sizes = [1, 2, 4, 8, 16, 32, 64]                      # KB
    sweep("exp1_size", [(t, {"l1_kb": kb}, make_config(l1_size=kb * KB))
                        for t in traces for kb in sizes])


def exp_assoc():
    """2. Associativity vs miss rate, split into the three miss types."""
    cases = [("vecadd", 32), ("strided", 32), ("matmul_ijk", 8)]   # trace, L1 KB
    assocs = [1, 2, 4, 8, "full"]
    sweep("exp2_assoc",
          [(t, {"assoc": a, "l1_kb": kb}, make_config(l1_size=kb * KB, l1_assoc=a))
           for t, kb in cases for a in assocs])


def exp_block():
    """3. Block size vs miss rate, AMAT and memory traffic."""
    cases = [("random", 32), ("vecadd", 32), ("matmul_blocked", 4)]
    blocks = [16, 32, 64, 128, 256]
    sweep("exp3_block",
          [(t, {"block": b, "l1_kb": kb, "mem_cycles": mem_latency(b)},
            make_config(l1_size=kb * KB, block=b, t_mem=mem_latency(b)))
           for t, kb in cases for b in blocks])


def exp_policy():
    """4. Replacement policy: LRU vs FIFO vs Random."""
    cases = [("vecadd", 32, 2), ("matmul_ijk", 4, 4), ("matmul_ikj", 4, 4),
             ("matmul_blocked", 4, 4)]                    # trace, L1 KB, ways
    policies = ["LRU", "FIFO", "RANDOM"]
    sweep("exp4_policy",
          [(t, {"policy": p, "l1_kb": kb, "assoc": a},
            make_config(l1_size=kb * KB, l1_assoc=a, policy=p))
           for t, kb, a in cases for p in policies])


def exp_write():
    """5. Write-back vs write-through."""
    cases = [("vecadd", 32), ("matmul_ikj", 4), ("matmul_blocked", 4)]
    combos = [("WB+WB", "wb", "wb"), ("WT+WB", "wt", "wb"), ("WT+WT", "wt", "wt")]
    sweep("exp5_write",
          [(t, {"L1D+L2": name, "l1_kb": kb},
            make_config(l1_size=kb * KB, l1d_write=w1, l2_write=w2))
           for t, kb in cases for name, w1, w2 in combos])


def exp_l2():
    """6. Effect of adding an L2 cache."""
    cases = [("sequential", 32), ("random", 32), ("vecadd", 32),
             ("matmul_ikj", 4)]
    l2_sizes = [0, 64, 128, 256, 512]                     # KB, 0 = no L2
    runs = []
    for t, kb in cases:
        for s in l2_sizes:
            cfg = make_config(l1_size=kb * KB, l2=s > 0, l2_size=max(s, 1) * KB)
            runs.append((t, {"l2_kb": s, "l1_kb": kb}, cfg))
    sweep("exp6_l2", runs)


def exp_matmul():
    """7. Matrix multiply: loop order and blocking, across L1 sizes."""
    orders = ["matmul_ijk", "matmul_ikj", "matmul_blocked"]
    sizes = [2, 4, 8, 16, 32]                             # KB
    sweep("exp7_matmul", [(t, {"l1_kb": kb}, make_config(l1_size=kb * KB))
                          for t in orders for kb in sizes])


EXPERIMENTS = {
    "size": exp_size,
    "assoc": exp_assoc,
    "block": exp_block,
    "policy": exp_policy,
    "write": exp_write,
    "l2": exp_l2,
    "matmul": exp_matmul,
}


def main():
    parser = argparse.ArgumentParser(description="Run the cache experiments")
    parser.add_argument("--only", nargs="+", choices=list(EXPERIMENTS),
                        help="run only these experiments")
    parser.add_argument("--no-plots", action="store_true",
                        help="write the CSV files but don't draw figures")
    args = parser.parse_args()

    if not (TRACE_DIR / "matmul_ikj.din").exists():
        sys.exit("Traces not found. Run:  python -m cachesim.tracegen")

    names = args.only or list(EXPERIMENTS)
    start = time.time()
    for name in names:
        print(f"\n[{name}] {EXPERIMENTS[name].__doc__}")
        EXPERIMENTS[name]()
    print(f"\nSimulations done in {time.time() - start:.0f} s. "
          f"CSV files are in {RESULT_DIR}/")

    if not args.no_plots:
        from .plots import make_figures
        make_figures(names)


if __name__ == "__main__":
    main()