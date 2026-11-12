"""
Draws the figures from the CSV files in results/ (written by experiments.py).
Nothing is simulated here, so restyling takes seconds.

    python -m cachesim.plots                    # every figure, both themes
    python -m cachesim.plots --theme report     # only the report figures
    python -m cachesim.plots --only matmul l2   # only some experiments

Two themes:
  report  white background, serif font, sized for an IEEE two-column page,
          saved as vector PDF plus a 300 dpi PNG  -> results/report/
  slides  dark background, large text, saved as PNG -> results/slides/
"""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")          # draw straight to files, no window needed
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, NullFormatter, NullLocator

RESULT_DIR = Path("results")

# One colour and marker per workload, the same in every figure.
# Colours are the Okabe-Ito colour-blind-safe set.
WORKLOAD_COLOR = {
    "random": "#0072B2", "vecadd": "#E69F00", "sequential": "#56B4E9",
    "strided": "#999999", "matmul_ijk": "#D55E00", "matmul_ikj": "#009E73",
    "matmul_blocked": "#CC79A7",
}
WORKLOAD_MARKER = {
    "random": "o", "vecadd": "s", "sequential": "P", "strided": "X",
    "matmul_ijk": "^", "matmul_ikj": "v", "matmul_blocked": "D",
}
NICE = {
    "random": "random", "vecadd": "vecadd", "sequential": "sequential",
    "strided": "strided", "matmul_ijk": "matmul ijk",
    "matmul_ikj": "matmul ikj", "matmul_blocked": "matmul blocked",
}
POLICY_COLOR = {"LRU": "#0072B2", "FIFO": "#E69F00", "RANDOM": "#009E73"}
WRITE_COLOR = {"WB+WB": "#0072B2", "WT+WB": "#E69F00", "WT+WT": "#D55E00"}
MISS_COLOR = {"compulsory": "#56B4E9", "capacity": "#E69F00", "conflict": "#D55E00"}
L2_COLOR = {"64K L2": "#9ecae1", "128K L2": "#6baed6",
            "256K L2": "#3182bd", "512K L2": "#08519c"}

THEMES = {
    "report": {
        "folder": "report",
        "formats": [("pdf", {}), ("png", {"dpi": 300})],
        "letters": True,            # label panels (a), (b), (c)
        "annot": 6.5,               # annotation font size
        "fg": "black",
        "rc": {
            "font.family": "serif",
            "font.serif": ["STIXGeneral", "Times New Roman", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
            "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
            "axes.linewidth": 0.6, "lines.linewidth": 1.2,
            "lines.markersize": 3.5, "grid.linewidth": 0.4,
            "xtick.major.width": 0.6, "ytick.major.width": 0.6,
            "figure.facecolor": "white", "axes.facecolor": "white",
            "savefig.facecolor": "white", "text.color": "black",
            "axes.labelcolor": "black", "xtick.color": "black",
            "ytick.color": "black", "axes.edgecolor": "black",
            "grid.color": "#cccccc",
        },
    },
    "slides": {
        "folder": "slides",
        "formats": [("png", {"dpi": 200})],
        "letters": False,
        "annot": 12,
        "fg": "#e8e8ec",
        "rc": {
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans"],
            "font.size": 14, "axes.labelsize": 14, "axes.titlesize": 14,
            "xtick.labelsize": 12, "ytick.labelsize": 12, "legend.fontsize": 12,
            "axes.linewidth": 1.0, "lines.linewidth": 2.6,
            "lines.markersize": 8, "grid.linewidth": 0.8,
            "xtick.major.width": 1.0, "ytick.major.width": 1.0,
            "figure.facecolor": "#12141a", "axes.facecolor": "#12141a",
            "savefig.facecolor": "#12141a", "text.color": "#e8e8ec",
            "axes.labelcolor": "#e8e8ec", "xtick.color": "#c9ccd6",
            "ytick.color": "#c9ccd6", "axes.edgecolor": "#8a8f9c",
            "grid.color": "#2c303a",
        },
    },
}

# figure sizes in inches: IEEE page is 7.16 in wide (3.5 in per column)
SIZES = {
    "exp1_size":   {"report": (7.16, 2.6), "slides": (12.5, 5.0)},
    "exp2_assoc":  {"report": (7.16, 2.5), "slides": (12.5, 5.0)},
    "exp3_block":  {"report": (7.16, 2.6), "slides": (12.5, 5.0)},
    "exp4_policy": {"report": (7.16, 2.7), "slides": (12.5, 5.2)},
    "exp5_write":  {"report": (7.16, 2.7), "slides": (12.5, 5.2)},
    "exp6_l2":     {"report": (3.5, 2.7),  "slides": (9.0, 5.2)},
    "exp7_matmul": {"report": (7.16, 2.6), "slides": (12.5, 5.0)},
}


# ---------------------------------------------------------------- helpers

def convert(text):
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def load(name):
    path = RESULT_DIR / f"{name}.csv"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run:  python -m cachesim.experiments")
    with open(path, newline="") as f:
        return [{k: convert(v) for k, v in raw.items()}
                for raw in csv.DictReader(f)]


def find(rows, **match):
    for r in rows:
        if all(r[k] == v for k, v in match.items()):
            return r
    raise KeyError(match)


def unique(rows, *keys):
    """Distinct combinations of the given columns, in order of appearance."""
    seen = []
    for r in rows:
        combo = tuple(r[k] for k in keys)
        if combo not in seen:
            seen.append(combo)
    return seen


def percent(ax, axis="y"):
    fmt = FuncFormatter(lambda v, _: f"{v * 100:g}%")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


def log_y(ax, ticks):
    """Log y axis with a few plain tick labels and no minor clutter."""
    ax.set_yscale("log")
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{t:g}" for t in ticks])
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_minor_formatter(NullFormatter())


def panel_title(ax, letter, text, th):
    ax.set_title(f"({letter}) {text}" if th["letters"] else text,
                 loc="left", pad=4)


def new_fig(name, ncols, th, sharey=False):
    w, h = SIZES[name]["report" if th["letters"] else "slides"]
    return plt.subplots(1, ncols, figsize=(w, h), sharey=sharey)


def line_panel(ax, rows, x_key, y_key, label_fn=None, logx=False):
    label_fn = label_fn or (lambda t: NICE[t])
    series = {}
    for r in rows:
        series.setdefault(r["trace"], []).append((r[x_key], r[y_key]))
    for trace, pts in series.items():
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=WORKLOAD_COLOR[trace],
                marker=WORKLOAD_MARKER[trace], label=label_fn(trace))
    xs_all = sorted({r[x_key] for r in rows})
    if logx:
        ax.set_xscale("log", base=2)
    ax.set_xticks(xs_all)
    ax.set_xticklabels([str(x) for x in xs_all])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.grid(True, alpha=0.6)
    ax.set_axisbelow(True)


def bar_panel(ax, categories, series, colors, th, value_labels=False, fmt="{:.1f}"):
    """Grouped bars. series = {name: [one number per category]}."""
    n = len(series)
    width = 0.8 / n
    for i, (name, ys) in enumerate(series.items()):
        xs = [c + (i - (n - 1) / 2) * width for c in range(len(categories))]
        ax.bar(xs, ys, width * 0.92, label=name, color=colors[name])
        if value_labels:
            for x, y in zip(xs, ys):
                ax.text(x, y, fmt.format(y), ha="center", va="bottom",
                        fontsize=th["annot"])
    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels(categories)
    ax.grid(True, axis="y", alpha=0.6)
    ax.grid(False, axis="x")
    ax.set_axisbelow(True)


def note(ax, th, text, xy, xytext):
    ax.annotate(text, xy=xy, xytext=xytext, fontsize=th["annot"], color=th["fg"],
                arrowprops=dict(arrowstyle="->", color=th["fg"],
                                lw=0.7 if th["letters"] else 1.4))


def cat_label(trace, cfg):
    return f"{NICE[trace].replace(' ', chr(10))}\n{cfg}"


def clean(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


# ---------------------------------------------------------------- figures

def fig_size(th):
    rows = load("exp1_size")
    fig, axes = new_fig("exp1_size", 2, th)
    line_panel(axes[0], rows, "l1_kb", "l1d_miss_rate", logx=True)
    line_panel(axes[1], rows, "l1_kb", "amat", logx=True)
    percent(axes[0])
    log_y(axes[1], [1, 2, 5, 10, 20, 50])
    axes[0].set_ylabel("L1D miss rate")
    axes[1].set_ylabel("AMAT (cycles)")
    panel_title(axes[0], "a", "miss rate", th)
    panel_title(axes[1], "b", "average memory access time", th)
    axes[0].legend(loc="center left", bbox_to_anchor=(0.0, 0.62), frameon=False)
    note(axes[0], th, "B (16 KB)\nfits in L1", xy=(16, 0.0211), xytext=(17, 0.16))
    for ax in axes:
        ax.set_xlabel("L1 cache size (KB)")
        clean(ax)
    return fig


def fig_assoc(th):
    rows = load("exp2_assoc")
    cases = unique(rows, "trace", "l1_kb")
    assocs = [a for (a,) in unique([r for r in rows if r["trace"] == cases[0][0]], "assoc")]
    fig, axes = new_fig("exp2_assoc", len(cases), th, sharey=True)
    for k, (ax, (trace, kb)) in enumerate(zip(axes, cases)):
        bottom = [0.0] * len(assocs)
        for key in ("compulsory", "capacity", "conflict"):
            vals = []
            for a in assocs:
                r = find(rows, trace=trace, assoc=a)
                vals.append(r[f"l1d_{key}"] / r["l1d_accesses"])
            ax.bar(range(len(assocs)), vals, bottom=bottom, label=key,
                   color=MISS_COLOR[key], width=0.75)
            bottom = [b + v for b, v in zip(bottom, vals)]
        ax.set_xticks(range(len(assocs)))
        ax.set_xticklabels([str(a) for a in assocs])
        ax.set_xlabel("associativity (ways)")
        ax.grid(True, axis="y", alpha=0.6)
        ax.set_axisbelow(True)
        panel_title(ax, "abc"[k], f"{NICE[trace]}, {kb} KB L1D", th)
        clean(ax)
    percent(axes[0])
    axes[0].set_ylabel("L1D miss rate")
    axes[0].legend(loc="upper right", frameon=False, title="miss type",
                   title_fontsize=th["rc"]["legend.fontsize"])
    return fig


def fig_block(th):
    rows = load("exp3_block")
    kb_of = {t: kb for t, kb in unique(rows, "trace", "l1_kb")}
    label = lambda t: f"{NICE[t]} ({kb_of[t]} KB)"
    for r in rows:
        r["mem_read_mb"] = r["mem_read_bytes"] / 1e6
    fig, axes = new_fig("exp3_block", 3, th)
    line_panel(axes[0], rows, "block", "l1d_miss_rate", label, logx=True)
    line_panel(axes[1], rows, "block", "amat", label, logx=True)
    line_panel(axes[2], rows, "block", "mem_read_mb", label, logx=True)
    for ax in axes[:3]:
        ax.set_yscale("log")
    axes[0].set_yticks([0.01, 0.1, 1])
    axes[0].set_yticklabels(["1%", "10%", "100%"])
    log_y(axes[1], [1, 2, 5, 10, 20, 50, 100])
    log_y(axes[2], [0.1, 1, 10])
    axes[0].yaxis.set_minor_locator(NullLocator())
    axes[0].yaxis.set_minor_formatter(NullFormatter())
    axes[0].set_ylabel("L1D miss rate")
    axes[1].set_ylabel("AMAT (cycles)")
    axes[2].set_ylabel("data read from memory (MB)")
    panel_title(axes[0], "a", "miss rate", th)
    panel_title(axes[1], "b", "AMAT", th)
    panel_title(axes[2], "c", "memory traffic", th)
    axes[0].legend(loc="center right", bbox_to_anchor=(1.0, 0.7), frameon=False,
                   fontsize=th["rc"]["legend.fontsize"] - 1, title="workload (L1D)",
                   title_fontsize=th["rc"]["legend.fontsize"] - 1)
    for ax in axes:
        ax.set_xlabel("block size (bytes)")
        clean(ax)
    return fig


def fig_policy(th):
    rows = load("exp4_policy")
    cases = unique(rows, "trace", "l1_kb", "assoc")
    cats = [cat_label(t, f"{a}-way {kb} KB") for t, kb, a in cases]
    policies = [p for (p,) in unique(rows, "policy")]
    fig, axes = new_fig("exp4_policy", 2, th)
    for ax, key, ylabel in ((axes[0], "l1d_miss_rate", "L1D miss rate"),
                            (axes[1], "amat", "AMAT (cycles)")):
        series = {p: [find(rows, trace=t, policy=p, l1_kb=kb, assoc=a)[key]
                      for t, kb, a in cases] for p in policies}
        bar_panel(ax, cats, series, POLICY_COLOR, th)
        ax.set_ylabel(ylabel)
        clean(ax)
    percent(axes[0])
    panel_title(axes[0], "a", "miss rate", th)
    panel_title(axes[1], "b", "AMAT", th)
    axes[0].legend(loc="upper right", frameon=False)
    return fig


def fig_write(th):
    rows = load("exp5_write")
    cases = unique(rows, "trace", "l1_kb")
    cats = [cat_label(t, f"{kb} KB L1D") for t, kb in cases]
    combos = [c for (c,) in unique(rows, "L1D+L2")]
    panels = [("amat", "AMAT (cycles)", 1.0, "AMAT", True),
              ("l2_accesses", "accesses reaching L2 (millions)", 1e6, "L2 traffic", False),
              ("mem_write_bytes", "bytes written to memory (KB)", 1024, "memory writes", False)]
    fig, axes = new_fig("exp5_write", 3, th)
    for k, (ax, (key, ylabel, div, title, labels)) in enumerate(zip(axes, panels)):
        series = {c: [find(rows, trace=t, l1_kb=kb, **{"L1D+L2": c})[key] / div
                      for t, kb in cases] for c in combos}
        bar_panel(ax, cats, series, WRITE_COLOR, th, value_labels=labels)
        ax.set_ylabel(ylabel)
        panel_title(ax, "abc"[k], title, th)
        clean(ax)
    axes[0].set_ylim(top=axes[0].get_ylim()[1] * 1.08)
    axes[1].legend(loc="upper left", frameon=False, title="L1D + L2",
                   title_fontsize=th["rc"]["legend.fontsize"])
    return fig


def fig_l2(th):
    rows = load("exp6_l2")
    cases = unique(rows, "trace", "l1_kb")
    cats = [cat_label(t, f"{kb} KB L1D") for t, kb in cases]
    sizes = [s for (s,) in unique(rows, "l2_kb") if s > 0]
    fig, axes = new_fig("exp6_l2", 1, th)
    ax = axes if not hasattr(axes, "__len__") else axes[0]
    series = {}
    for s in sizes:
        series[f"{s}K L2"] = [find(rows, trace=t, l1_kb=kb, l2_kb=s)["amat"]
                              / find(rows, trace=t, l1_kb=kb, l2_kb=0)["amat"]
                              for t, kb in cases]
    bar_panel(ax, cats, series, L2_COLOR, th)
    ax.axhline(1.0, color=th["fg"], lw=0.8 if th["letters"] else 1.5, ls="--")
    ax.text(len(cases) - 0.5, 1.02, "no L2", ha="right", va="bottom",
            fontsize=th["annot"], color=th["fg"])
    ax.set_ylim(0, 1.55)
    ax.set_ylabel("AMAT relative to no L2")
    ax.legend(loc="upper right", ncol=2, frameon=False)
    seq_first = (0 - (len(series) - 1) / 2 * (0.8 / len(series)), series["64K L2"][0])
    note(ax, th, "slower than\nno L2", xy=seq_first, xytext=(-0.45, 1.33))
    clean(ax)
    return fig


def fig_matmul(th):
    rows = load("exp7_matmul")
    names = {"matmul_ijk": "ijk", "matmul_ikj": "ikj",
             "matmul_blocked": "blocked (8x8 tiles)"}
    fig, axes = new_fig("exp7_matmul", 2, th)
    line_panel(axes[0], rows, "l1_kb", "l1d_miss_rate", lambda t: names[t], logx=True)
    line_panel(axes[1], rows, "l1_kb", "amat", lambda t: names[t], logx=True)
    percent(axes[0])
    axes[0].set_ylabel("L1D miss rate")
    axes[1].set_ylabel("AMAT (cycles)")
    panel_title(axes[0], "a", "miss rate", th)
    panel_title(axes[1], "b", "AMAT", th)
    axes[1].legend(loc="upper right", frameon=False, title="loop order",
                   title_fontsize=th["rc"]["legend.fontsize"])
    note(axes[0], th, "tiles do not\nfit in 2 KB", xy=(2, 0.1448), xytext=(2.5, 0.175))
    note(axes[0], th, "B (16 KB)\nfits in L1", xy=(16, 0.0211), xytext=(17.5, 0.08))
    for ax in axes:
        ax.set_xlabel("L1 cache size (KB)")
        clean(ax)
    return fig


# name used on the command line -> (figure function, file name)
FIGURES = {
    "size": (fig_size, "exp1_size"),
    "assoc": (fig_assoc, "exp2_assoc"),
    "block": (fig_block, "exp3_block"),
    "policy": (fig_policy, "exp4_policy"),
    "write": (fig_write, "exp5_write"),
    "l2": (fig_l2, "exp6_l2"),
    "matmul": (fig_matmul, "exp7_matmul"),
}


def make_figures(names=None, themes=None):
    """Draw and save the figures for the given experiments and themes."""
    for theme_name in themes or THEMES:
        th = THEMES[theme_name]
        out = RESULT_DIR / th["folder"]
        out.mkdir(parents=True, exist_ok=True)
        for name in names or FIGURES:
            draw, file_name = FIGURES[name]
            with plt.rc_context(th["rc"]):
                fig = draw({**th, "rc": th["rc"]})
                fig.tight_layout()
                for ext, kwargs in th["formats"]:
                    fig.savefig(out / f"{file_name}.{ext}", **kwargs)
                plt.close(fig)
        print(f"{theme_name}: figures written to {out}/")


def main():
    parser = argparse.ArgumentParser(description="Draw figures from results/*.csv")
    parser.add_argument("--theme", choices=list(THEMES), help="only this theme")
    parser.add_argument("--only", nargs="+", choices=list(FIGURES),
                        help="only these experiments")
    args = parser.parse_args()
    make_figures(args.only, [args.theme] if args.theme else None)


if __name__ == "__main__":
    main()