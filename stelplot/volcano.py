"""Volcano plots: log2 fold change against -log10(P), for proteomics and other omics data.

Grouped tables: each row is one protein, gene, or site, and the first two data sets on the
graph are compared (the second against the first) with a t test on each row. XY tables:
X holds log2 fold changes already computed, Y holds their P values.

Multiple comparisons: Benjamini and Hochberg (1995), J R Stat Soc B 57:289-300, the
step-up false discovery rate procedure, through scipy.stats.false_discovery_control.
"""

__author__ = "Daniel Shiwarski"

import math
import re

import numpy as np
from matplotlib.lines import Line2D
from scipy import stats

from .stats_engine import finite

TESTS = ["Welch's t test", "Unpaired t test (equal SD)"]
P_INPUTS = ["P value", "-log10(P)"]
STATUS = ("Down", "Not sig", "Up")


def bh_adjust(p):
    """Benjamini-Hochberg adjusted P values (q values); NaN stays NaN."""
    p = np.asarray(p, float)
    q = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    if ok.any():
        q[ok] = stats.false_discovery_control(np.clip(p[ok], 0.0, 1.0), method="bh")
    return q


def row_tests(A, B, test=TESTS[0], already_log=False):
    """log2 fold change (B over A) and t test P value for each row.

    A, B: rows x replicates. With already_log, values are log2 and the fold change is the
    difference of means; otherwise it is log2 of the ratio of means, which needs both means
    above zero. Rows with fewer than two values in either group get no P value.
    """
    n = A.shape[0]
    fc = np.full(n, np.nan)
    p = np.full(n, np.nan)
    for r in range(n):
        a, b = finite(A[r]), finite(B[r])
        if not (a.size and b.size):
            continue
        ma, mb = float(np.mean(a)), float(np.mean(b))
        if already_log:
            fc[r] = mb - ma
        elif ma > 0 and mb > 0:
            fc[r] = math.log2(mb / ma)
        if a.size >= 2 and b.size >= 2:
            if np.ptp(a) == 0 and np.ptp(b) == 0:
                p[r] = 1.0 if ma == mb else 0.0
            else:
                with np.errstate(all="ignore"):
                    p[r] = float(stats.ttest_ind(b, a, equal_var=test != TESTS[0]).pvalue)
    return fc, p


def classify(fc, p_used, fc_cut, p_cut):
    """-1 down, 0 not significant, 1 up."""
    sig = np.isfinite(fc) & np.isfinite(p_used) & (p_used < p_cut)
    out = np.zeros(fc.shape, int)
    out[sig & (fc >= fc_cut)] = 1
    out[sig & (fc <= -fc_cut)] = -1
    return out


def volcano_table(names, fc, p, vopts):
    q = bh_adjust(p)
    used = q if vopts.use_fdr else p
    status = classify(fc, used, vopts.fc_cutoff, vopts.p_cutoff)
    keep = np.isfinite(fc) & np.isfinite(p)
    return {"names": list(names), "fc": fc, "p": p, "q": q, "status": status, "keep": keep,
            "use_fdr": vopts.use_fdr, "fc_cutoff": vopts.fc_cutoff, "p_cutoff": vopts.p_cutoff,
            "counts": {s: int(np.sum(keep & (status == v))) for s, v in zip(STATUS, (-1, 0, 1))}}


def _fmt(v, digits=4):
    if not np.isfinite(v):
        return ""
    return f"{v:.3g}" if abs(v) < 1e-3 and v != 0 else f"{v:.{digits}g}"


def volcano_text(table, limit=200):
    """Results panel text: thresholds, counts, and the significant rows by P value."""
    c = table["counts"]
    which = "Benjamini-Hochberg adjusted P" if table["use_fdr"] else "P"
    lines = [f"Volcano plot: |log2 fold change| >= {table['fc_cutoff']:g} and {which} < "
             f"{table['p_cutoff']:g}",
             f"Up: {c['Up']}   Down: {c['Down']}   Not significant: {c['Not sig']}   "
             f"(rows with a fold change and P value: {int(np.sum(table['keep']))})", ""]
    sig = [i for i in np.argsort(np.nan_to_num(table["p"], nan=2.0)) if table["status"][i] != 0
           and table["keep"][i]]
    rows = [["Name", "log2 FC", "P", "Adjusted P (BH)", "Change"]]
    for i in sig[:limit]:
        rows.append([table["names"][i], _fmt(table["fc"][i]), _fmt(table["p"][i]),
                     _fmt(table["q"][i]), "Up" if table["status"][i] > 0 else "Down"])
    widths = [max(len(r[k]) for r in rows) for k in range(5)]
    lines += ["  ".join(v.ljust(w) if k == 0 else v.rjust(w) for k, (v, w) in enumerate(zip(r, widths)))
              for r in rows]
    if len(sig) > limit:
        lines.append(f"... and {len(sig) - limit} more (Export results saves every row).")
    if not sig:
        lines.append("No rows pass both thresholds.")
    return "\n".join(lines)


def write_volcano_csv(path, table):
    import csv
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Name", "log2 fold change", "P value", "Adjusted P (Benjamini-Hochberg)",
                    "-log10(P)", "Change"])
        for i, name in enumerate(table["names"]):
            p = table["p"][i]
            w.writerow([name, _fmt(table["fc"][i], 6), _fmt(p, 6), _fmt(table["q"][i], 6),
                        _fmt(-math.log10(p), 6) if np.isfinite(p) and p > 0 else "",
                        {1: "Up", -1: "Down"}.get(int(table["status"][i]), "Not significant")
                        if table["keep"][i] else "Not tested"])


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _label_positions(px, py, texts, side, w_pt, h_pt, fs):
    """Place labels beside their points without overlapping each other (greedy, in points)."""
    placed, out = [], []
    lh = fs * 1.15
    for x, y, text, s in zip(px, py, texts, side):
        tw = 0.56 * fs * len(text)
        best = None
        for step in (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6):
            for direction in ((s, -s) if step else (s,)):
                dx = direction * 4.0
                dy = step * lh
                x0 = x + dx if direction > 0 else x + dx - tw
                y0 = y + dy - lh / 2
                box = (x0, y0, x0 + tw, y0 + lh)
                if box[0] < 0 or box[2] > w_pt or box[1] < 0 or box[3] > h_pt + lh:
                    continue
                if all(box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]
                       for b in placed):
                    best = (dx, dy, direction, box)
                    break
            if best:
                break
        if best is None:
            out.append(None)
            continue
        placed.append(best[3])
        out.append(best[:3])
    return out


def draw_volcano(fig, table, opts, st, x_label, y_label):
    from .plotting import (_finish, _frame, _legend, _new_axes, _set_axis, marker_size)
    v = opts.volcano
    keep = table["keep"]
    if not keep.any():
        from .plotting import _empty_state
        _empty_state(fig, "No rows have both a fold change and a P value yet.", opts)
        return None
    fc = table["fc"]
    pv = table["q"] if table["use_fdr"] else table["p"]
    with np.errstate(divide="ignore"):
        y = -np.log10(pv)
    finite_y = y[keep & np.isfinite(y)]
    cap = (float(finite_y.max()) if finite_y.size else 1.0) * 1.05 + 0.1
    zero_p = keep & ~np.isfinite(y)
    if zero_p.any():
        fig.stel_notes.append(f"{int(zero_p.sum())} row(s) have P = 0 and are drawn at the top of "
                              "the axis.")
        y = np.where(zero_p, cap, y)
    ax = _new_axes(fig, opts)
    _frame(ax, opts)
    status = table["status"]
    size = marker_size(opts.point_size, "o", st) ** 2
    colors = {-1: v.down_color, 0: v.ns_color, 1: v.up_color}
    handles, labels = [], []
    for s_val, name in zip((-1, 0, 1), STATUS):
        m = keep & (status == s_val)
        ax.scatter(fc[m], y[m], s=size, facecolors=[colors[s_val]], edgecolors="none",
                   alpha=0.7 if s_val == 0 else 0.9, zorder=2 if s_val == 0 else 3, clip_on=False)
        handles.append(Line2D([], [], linestyle="none", marker="o", markerfacecolor=colors[s_val],
                              markeredgecolor="none", markersize=marker_size(opts.point_size, "o", st)))
        word = {"Down": "Down", "Not sig": "Not significant", "Up": "Up"}[name]
        labels.append(f"{word} ({table['counts'][name]})" if v.show_counts else word)
    big = float(np.max(np.abs(fc[keep]))) if keep.any() else 1.0
    big = max(big, v.fc_cutoff * 1.2)
    x0, x1 = _set_axis(ax, "x", -big, big, opts.x_min if hasattr(opts, "x_min") else None,
                       opts.x_max if hasattr(opts, "x_max") else None, zero=False, headroom=1.02)
    if not (hasattr(opts, "x_min") and (opts.x_min is not None or opts.x_max is not None)):
        edge = max(abs(x0), abs(x1))
        ax.set_xlim(-edge, edge)
    y0, y1 = _set_axis(ax, "y", 0.0, float(np.max(y[keep])), opts.y_min, opts.y_max)
    dash = dict(color="black", linewidth=st["thin"], linestyle=(0, (3.0, 2.0)), zorder=1)
    for xv in (-v.fc_cutoff, v.fc_cutoff):
        ax.axvline(xv, **dash)
    if 0 < v.p_cutoff < 1:
        ax.axhline(-math.log10(v.p_cutoff), **dash)

    # Labels: the most significant changed rows, plus any named in the settings
    wanted = [n.strip().lower() for n in re.split(r"[,;\n]+", v.label_names or "") if n.strip()]
    names = table["names"]
    order = [i for i in np.argsort(np.nan_to_num(pv, nan=2.0)) if keep[i] and status[i] != 0]
    chosen = order[:max(0, int(v.label_top))]
    chosen += [i for i, n in enumerate(names) if keep[i] and str(n).lower() in wanted
               and i not in chosen]
    if chosen:
        xl, yl = ax.get_xlim(), ax.get_ylim()
        w_pt, h_pt = opts.width_in * 72, opts.height_in * 72
        px = [(fc[i] - xl[0]) / (xl[1] - xl[0]) * w_pt for i in chosen]
        py = [(y[i] - yl[0]) / (yl[1] - yl[0]) * h_pt for i in chosen]
        fs = opts.font_size - 1
        side = [1 if fc[i] >= 0 else -1 for i in chosen]
        spots = _label_positions(px, py, [str(names[i]) for i in chosen], side, w_pt, h_pt, fs)
        missed = 0
        for i, spot in zip(chosen, spots):
            if spot is None:
                missed += 1
                continue
            dx, dy, direction = spot
            ax.annotate(str(names[i]), xy=(fc[i], y[i]), xytext=(dx, dy),
                        textcoords="offset points", fontsize=fs, va="center",
                        ha="left" if direction > 0 else "right", zorder=5, annotation_clip=False,
                        arrowprops=(dict(arrowstyle="-", linewidth=st["thin"], color="#404040",
                                         shrinkA=0, shrinkB=1.5) if dy else None))
        if missed:
            fig.stel_notes.append(f"{missed} label(s) did not fit without overlapping and were left "
                                  "off; enlarge the graph or label fewer rows.")
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    _legend(ax, handles, labels, opts, st, ncol=3)
    fig.stel_volcano = table
    _finish(fig, ax, opts, st)
    return ax


def _y_title(opts, use_fdr, default_titles):
    if opts.y_label and opts.y_label not in default_titles:
        return opts.y_label
    return "−log$_{10}$(adjusted P)" if use_fdr else "−log$_{10}$(P)"


def render_grouped_volcano(fig, row_labels, col_names, D, opts, st):
    from .plotting import VolcanoOptions, _empty_state
    v = opts.volcano or VolcanoOptions()
    opts.volcano = v
    if D.shape[1] < 2:
        _empty_state(fig, "A volcano plot compares two data sets.\nEnter replicates for both "
                          "(the second is compared with the first).", opts)
        return None
    if D.shape[1] > 2:
        fig.stel_notes.append(f"Volcano plots compare the first two data sets on the graph "
                              f"({col_names[1]} vs {col_names[0]}); the others are not used.")
    fc, p = row_tests(D[:, 0, :], D[:, 1, :], v.test, v.already_log)
    if not v.already_log:
        bad = int(np.sum([(finite(D[r, 0]).size and finite(D[r, 1]).size and not np.isfinite(fc[r]))
                          for r in range(D.shape[0])]))
        if bad:
            fig.stel_notes.append(f"{bad} row(s) have a mean at or below zero, so no fold change. "
                                  "If the data are already log2, check 'Values are log2'.")
    few = int(np.sum(np.isfinite(fc) & ~np.isfinite(p)))
    if few:
        fig.stel_notes.append(f"{few} row(s) have fewer than two values in a data set and get no "
                              "P value.")
    table = volcano_table(row_labels, fc, p, v)
    x_label = (opts.x_label or
               f"log$_2$ fold change ({col_names[1]} / {col_names[0]})")
    return draw_volcano(fig, table, opts, st, x_label, _y_title(opts, v.use_fdr, ("", "Value")))


def render_xy_volcano(fig, x, series, opts, st, row_titles=None):
    from .plotting import VolcanoOptions, _empty_state
    v = opts.volcano or VolcanoOptions()
    opts.volcano = v
    if not series:
        _empty_state(fig, "Enter log2 fold changes as X and their P values as Y.", opts)
        return None
    name, Y = series[0]
    Y = np.asarray(Y, float)
    Y = Y[:, None] if Y.ndim == 1 else Y
    if len(series) > 1 or Y.shape[1] > 1:
        fig.stel_notes.append(f"Volcano plots use the first Y column of {name}; other columns are "
                              "not used.")
    fc = np.asarray(x, float)
    raw = Y[:, 0]
    if v.p_input == P_INPUTS[1]:
        p = np.where(np.isfinite(raw), 10.0 ** (-raw), np.nan)
    else:
        p = np.where(np.isfinite(raw) & (raw >= 0) & (raw <= 1), raw, np.nan)
        bad = int(np.sum(np.isfinite(raw) & ~np.isfinite(p)))
        if bad:
            fig.stel_notes.append(f"{bad} Y value(s) are not P values (0 to 1). If Y holds "
                                  "-log10(P), choose that under 'Y values are'.")
    n = fc.size
    titles = list(row_titles or [])[:n] + [""] * max(0, n - len(row_titles or []))
    names = [t or f"Row {i + 1}" for i, t in enumerate(titles)]
    table = volcano_table(names, fc, p, v)
    x_label = opts.x_label if opts.x_label not in ("", "X") else "log$_2$ fold change"
    return draw_volcano(fig, table, opts, st, x_label, _y_title(opts, v.use_fdr, ("", "Y")))
