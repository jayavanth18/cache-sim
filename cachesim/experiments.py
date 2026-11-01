"""
Runs the experiments listed in SPEC.md. Each one writes a CSV file and a
PNG plot into results/.

    python -m cachesim.experiments                  # all experiments
    python -m cachesim.experiments --only size l2   # just some of them

Generate the traces first:  python -m cachesim.tracegen
"""
import argparse
import csv
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")          # draw straight to files, no window needed
import matplotlib.pyplot as plt

from .config import build_hierarchy
from .trace import read_trace

KB = 1024
TRACE_DIR = Path("traces")
RESULT_DIR = Path("results")
COLORS = ["#4c78a8", "#f58518", "#54a24b", "#e45756", "#b279a2"]

plt.rcParams.update({
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.axisbelow": True,
})


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


def find(rows, **match):
    for r in rows:
        if all(r[k] == v for k, v in match.items()):
            return r
    raise KeyError(match)


def line_panel(ax, rows, label_fn, x_key, y_key, ylabel, logx=False, logy=False):
    series = {}
    for r in rows:
        series.setdefault(label_fn(r), []).append((r[x_key], r[y_key]))
    for i, (label, pts) in enumerate(series.items()):
        xs, ys = zip(*pts)
        ax.plot(xs, ys, marker="o", color=COLORS[i % len(COLORS)], label=label)
    xs_all = sorted({r[x_key] for r in rows})
    if logx:
        ax.set_xscale("log", base=2)
    ax.set_xticks(xs_all)
    ax.set_xticklabels([str(x) for x in xs_all])
    ax.minorticks_off()
    if logy:
        ax.set_yscale("log")
    ax.set_ylabel(ylabel)


def bar_panel(ax, categories, values, ylabel, logy=False):
    """Grouped bars. values = {series name: [one number per category]}."""
    n = len(values)
    width = 0.8 / n
    for i, (name, ys) in enumerate(values.items()):
        xs = [c + (i - (n - 1) / 2) * width for c in range(len(categories))]
        ax.bar(xs, ys, width, label=name, color=COLORS[i % len(COLORS)])
    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels(categories)
    ax.set_ylabel(ylabel)
    if logy:
        ax.set_yscale("log")
        ax.set_ylim(bottom=1)      # AMAT can't go below the 1-cycle L1 hit time


def save_fig(fig, name):
    fig.tight_layout()
    fig.savefig(RESULT_DIR / f"{name}.png", dpi=200)
    plt.close(fig)


# ------------------------------------------------------------ experiments

def exp_size():
    """1. L1 cache size vs miss rate and AMAT."""
    traces = ["random", "vecadd", "matmul_ijk", "matmul_blocked"]
    sizes = [1, 2, 4, 8, 16, 32, 64]                      # KB
    runs = [(t, {"l1_kb": kb}, make_config(l1_size=kb * KB))
            for t in traces for kb in sizes]
    rows = sweep("exp1_size", runs)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    line_panel(axes[0], rows, lambda r: r["trace"], "l1_kb", "l1d_miss_rate",
               "L1D miss rate", logx=True)
    line_panel(axes[1], rows, lambda r: r["trace"], "l1_kb", "amat",
               "AMAT (cycles)", logx=True, logy=True)
    for ax in axes:
        ax.set_xlabel("L1 cache size (KB)")
    axes[0].legend()
    save_fig(fig, "exp1_size")


def exp_assoc():
    """2. Associativity vs miss rate, split into the three miss types."""
    cases = [("vecadd", 32), ("strided", 32), ("matmul_ijk", 8)]   # trace, L1 KB
    assocs = [1, 2, 4, 8, "full"]
    runs = [(t, {"assoc": a, "l1_kb": kb}, make_config(l1_size=kb * KB, l1_assoc=a))
            for t, kb in cases for a in assocs]
    rows = sweep("exp2_assoc", runs)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    kinds = [("l1d_compulsory", "compulsory"), ("l1d_capacity", "capacity"),
             ("l1d_conflict", "conflict")]
    for ax, (t, kb) in zip(axes, cases):
        bottom = [0.0] * len(assocs)
        for i, (key, label) in enumerate(kinds):
            vals = []
            for a in assocs:
                r = find(rows, trace=t, assoc=a)
                vals.append(r[key] / r["l1d_accesses"])
            ax.bar(range(len(assocs)), vals, bottom=bottom, label=label,
                   color=[COLORS[0], COLORS[1], COLORS[3]][i])
            bottom = [b + v for b, v in zip(bottom, vals)]
        ax.set_xticks(range(len(assocs)))
        ax.set_xticklabels([str(a) for a in assocs])
        ax.set_xlabel("associativity (ways)")
        ax.set_title(f"{t}  ({kb}K L1D)")
    axes[0].set_ylabel("L1D miss rate")
    axes[0].legend()
    save_fig(fig, "exp2_assoc")


def exp_block():
    """3. Block size vs miss rate, AMAT and memory traffic."""
    cases = [("random", 32), ("vecadd", 32), ("matmul_blocked", 4)]
    blocks = [16, 32, 64, 128, 256]
    runs = [(t, {"block": b, "l1_kb": kb, "mem_cycles": mem_latency(b)},
             make_config(l1_size=kb * KB, block=b, t_mem=mem_latency(b)))
            for t, kb in cases for b in blocks]
    rows = sweep("exp3_block", runs)
    for r in rows:
        r["mem_read_mb"] = r["mem_read_bytes"] / 1e6

    label = lambda r: f"{r['trace']} ({r['l1_kb']}K L1D)"
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    line_panel(axes[0], rows, label, "block", "l1d_miss_rate", "L1D miss rate",
               logx=True, logy=True)
    line_panel(axes[1], rows, label, "block", "amat", "AMAT (cycles)", logx=True, logy=True)
    line_panel(axes[2], rows, label, "block", "mem_read_mb",
               "data read from memory (MB)", logx=True, logy=True)
    for ax in axes:
        ax.set_xlabel("block size (bytes)")
    axes[0].legend(fontsize=8)
    save_fig(fig, "exp3_block")


def exp_policy():
    """4. Replacement policy: LRU vs FIFO vs Random."""
    cases = [("vecadd", 32, 2), ("matmul_ijk", 4, 4), ("matmul_ikj", 4, 4),
             ("matmul_blocked", 4, 4)]                    # trace, L1 KB, ways
    policies = ["LRU", "FIFO", "RANDOM"]
    runs = [(t, {"policy": p, "l1_kb": kb, "assoc": a},
             make_config(l1_size=kb * KB, l1_assoc=a, policy=p))
            for t, kb, a in cases for p in policies]
    rows = sweep("exp4_policy", runs)

    cats = [f"{t}\n{a}-way, {kb}K" for t, kb, a in cases]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for ax, key, ylabel in ((axes[0], "l1d_miss_rate", "L1D miss rate"),
                            (axes[1], "amat", "AMAT (cycles)")):
        values = {p: [find(rows, trace=t, policy=p)[key] for t, _, _ in cases]
                  for p in policies}
        bar_panel(ax, cats, values, ylabel)
        ax.tick_params(axis="x", labelsize=8)
    axes[0].legend()
    save_fig(fig, "exp4_policy")


def exp_write():
    """5. Write-back vs write-through."""
    cases = [("vecadd", 32), ("matmul_ikj", 4), ("matmul_blocked", 4)]
    combos = [("WB+WB", "wb", "wb"), ("WT+WB", "wt", "wb"), ("WT+WT", "wt", "wt")]
    runs = [(t, {"L1D+L2": name, "l1_kb": kb},
             make_config(l1_size=kb * KB, l1d_write=w1, l2_write=w2))
            for t, kb in cases for name, w1, w2 in combos]
    rows = sweep("exp5_write", runs)

    cats = [f"{t}\n({kb}K L1D)" for t, kb in cases]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    panels = [("amat", "AMAT (cycles)", False, 1.0),
              ("l2_accesses", "accesses reaching L2 (millions)", False, 1e6),
              ("mem_write_bytes", "bytes written to memory (KB)", False, 1024)]
    for ax, (key, ylabel, logy, div) in zip(axes, panels):
        values = {name: [find(rows, trace=t, **{"L1D+L2": name})[key] / div
                         for t, _ in cases] for name, _, _ in combos}
        bar_panel(ax, cats, values, ylabel, logy=logy)
        ax.tick_params(axis="x", labelsize=8)
    axes[1].legend(title="L1D + L2", loc="upper left")
    save_fig(fig, "exp5_write")


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
    rows = sweep("exp6_l2", runs)

    cats = [f"{t}\n({kb}K L1D)" for t, kb in cases]
    fig, ax = plt.subplots(figsize=(9, 4))
    values = {("no L2" if s == 0 else f"{s}K L2"):
              [find(rows, trace=t, l2_kb=s)["amat"] for t, _ in cases]
              for s in l2_sizes}
    bar_panel(ax, cats, values, "AMAT (cycles)", logy=True)
    ax.legend()
    save_fig(fig, "exp6_l2")


def exp_matmul():
    """7. Matrix multiply: loop order and blocking, across L1 sizes."""
    orders = ["matmul_ijk", "matmul_ikj", "matmul_blocked"]
    sizes = [2, 4, 8, 16, 32]                             # KB
    runs = [(t, {"l1_kb": kb}, make_config(l1_size=kb * KB))
            for t in orders for kb in sizes]
    rows = sweep("exp7_matmul", runs)

    names = {"matmul_ijk": "ijk", "matmul_ikj": "ikj",
             "matmul_blocked": "blocked (8x8 tiles)"}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    line_panel(axes[0], rows, lambda r: names[r["trace"]], "l1_kb",
               "l1d_miss_rate", "L1D miss rate", logx=True)
    line_panel(axes[1], rows, lambda r: names[r["trace"]], "l1_kb",
               "amat", "AMAT (cycles)", logx=True)
    for ax in axes:
        ax.set_xlabel("L1 cache size (KB)")
    axes[0].legend(title="loop order")
    save_fig(fig, "exp7_matmul")


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
    args = parser.parse_args()

    if not (TRACE_DIR / "matmul_ikj.din").exists():
        sys.exit("Traces not found. Run:  python -m cachesim.tracegen")

    start = time.time()
    for name in args.only or EXPERIMENTS:
        print(f"\n[{name}] {EXPERIMENTS[name].__doc__}")
        EXPERIMENTS[name]()
    print(f"\nDone in {time.time() - start:.0f} s. Results are in {RESULT_DIR}/")


if __name__ == "__main__":
    main()