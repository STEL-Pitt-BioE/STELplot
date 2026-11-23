"""Headless checks for STELplot. Run from the STELplot folder:

    python -m tests.test_core

No GUI is needed. Each check prints PASS or raises an error.
"""

__author__ = "Daniel Shiwarski"

import math
import os
import tempfile

import numpy as np
from matplotlib.figure import Figure
from scipy import stats

from stelplot import stats_engine as se
from stelplot import plotting as pl

RNG = np.random.default_rng(7)
A = RNG.normal(10, 2, 8)
B = RNG.normal(13, 2, 8)
C = RNG.normal(15, 3, 8)


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print(f"PASS  {name}")


def test_t_tests():
    r = se.run_column_stats([("A", A), ("B", B)], "Unpaired t-test")
    ref = stats.ttest_ind(A, B)
    c = r.comparisons[0]
    check("unpaired t p matches SciPy", math.isclose(c.p, ref.pvalue, rel_tol=1e-12))
    check("unpaired CI excludes 0 exactly when p < 0.05",
          (c.ci_low > 0 or c.ci_high < 0) == (c.p < 0.05))
    r = se.run_column_stats([("A", A), ("B", B)], "Welch's t-test")
    ref = stats.ttest_ind(A, B, equal_var=False)
    check("Welch p matches SciPy", math.isclose(r.comparisons[0].p, ref.pvalue, rel_tol=1e-12))
    if hasattr(ref, "df"):
        check("Welch df matches SciPy", f"df = {se.fmt(float(ref.df))}" in r.omnibus)
    paired_b = A + RNG.normal(1, 0.5, A.size)
    r = se.run_column_stats([("A", A), ("B", paired_b)], "Paired t-test")
    ref = stats.ttest_rel(A, paired_b)
    check("paired t p matches SciPy", math.isclose(r.comparisons[0].p, ref.pvalue, rel_tol=1e-12))
    b_missing = paired_b.copy()
    b_missing[2] = np.nan
    r = se.run_column_stats([("A", A), ("B", b_missing)], "Paired t-test")
    check("paired t drops unmatched rows", "1 row(s)" in r.extra_lines[0])
    r = se.run_column_stats([("A", A), ("B", B), ("C", C)], "Unpaired t-test")
    check("two-group test refuses three columns", not r.ok)


def test_anova_tukey_dunnett():
    r = se.run_column_stats([("A", A), ("B", B), ("C", C)], "One-way ANOVA")
    f, p = stats.f_oneway(A, B, C)
    check("ANOVA F matches SciPy", se.fmt(float(f)) in r.omnibus)
    ref = stats.tukey_hsd(A, B, C)
    check("Tukey has 3 comparisons", len(r.comparisons) == 3)
    check("Tukey p matches SciPy",
          all(math.isclose(c.p, ref.pvalue[c.i, c.j], rel_tol=1e-9) for c in r.comparisons))
    check("Tukey diff is group1 minus group2",
          math.isclose(r.comparisons[0].diff, np.mean(A) - np.mean(B), rel_tol=1e-9))
    r = se.run_column_stats([("A", A), ("B", B), ("C", C)], "One-way ANOVA",
                            "Each vs. first column")
    check("Dunnett has k - 1 comparisons", len(r.comparisons) == 2)
    check("Dunnett CI contains diff",
          all(c.ci_low <= c.diff <= c.ci_high for c in r.comparisons))


def test_dunn():
    # With two groups, Dunn's z squared equals the tie-corrected Kruskal-Wallis H
    a = np.array([1, 2, 2, 3, 5, 8.0])
    b = np.array([2, 4, 6, 6, 9, 10, 11.0])
    _, _, _, z, _ = se.dunn_test([a, b], [(0, 1)])[0]
    h, _ = stats.kruskal(a, b)
    check("Dunn z^2 equals Kruskal-Wallis H for two groups", math.isclose(z * z, h, rel_tol=1e-10))
    out = se.dunn_test([A, B, C], [(0, 1), (0, 2), (1, 2)])
    check("Dunn p values are adjusted and bounded", all(0 <= o[4] <= 1 for o in out))
    r = se.run_column_stats([("A", A), ("B", B), ("C", C)], "Kruskal-Wallis test")
    check("Kruskal-Wallis runs with Dunn post hoc", r.ok and len(r.comparisons) == 3)


def test_nonparametric_two_group():
    r = se.run_column_stats([("A", A), ("B", B)], "Mann-Whitney test")
    ref = stats.mannwhitneyu(A, B, alternative="two-sided")
    check("Mann-Whitney p matches SciPy", math.isclose(r.comparisons[0].p, ref.pvalue))
    pb = A + RNG.normal(1, 0.5, A.size)
    r = se.run_column_stats([("A", A), ("B", pb)], "Wilcoxon signed-rank test")
    ref = stats.wilcoxon(A, pb)
    check("Wilcoxon p matches SciPy", math.isclose(r.comparisons[0].p, ref.pvalue))


def test_fits():
    x = np.array([0.001, 0.01, 0.1, 1, 10, 100.0])
    true = (5.0, 95.0, math.log10(0.5), 1.2)
    y = se._four_pl(x, *true)
    reps = np.column_stack([y, y + 0.5, y - 0.5])
    f = se.fit_curve("S", x, reps, "Dose-response, 4PL (variable slope)")
    check("4PL fit recovers LogEC50", f.ok and math.isclose(f.values[2], true[2], abs_tol=0.02))
    check("4PL reports EC50", any(name == "EC50" for name, _ in f.derived))
    t = np.array([0, 1, 2, 4, 8, 16.0])
    yd = se._decay(t, 100, 10, 0.3)
    f = se.fit_curve("D", t, np.column_stack([yd, yd * 1.01]), "One-phase exponential decay")
    check("decay fit recovers K", f.ok and math.isclose(f.values[2], 0.3, rel_tol=0.05))
    f = se.fit_curve("L", t, np.column_stack([2 * t + 1, 2 * t + 1.2]), "Linear regression")
    check("linear fit recovers slope", f.ok and math.isclose(f.values[0], 2.0, rel_tol=1e-6))
    f = se.fit_curve("bad", np.array([1, 2.0]), np.array([[1.0], [2.0]]),
                     "Dose-response, 4PL (variable slope)")
    check("fit with too few points fails cleanly", not f.ok)


def test_render_and_export():
    groups = [("Control", A), ("Drug A", B), ("Drug B", C)]
    res = se.run_column_stats(groups, "One-way ANOVA")
    out_dir = tempfile.mkdtemp()
    for plot_type in pl.PLOT_TYPES:
        opts = pl.ColumnPlotOptions(plot_type=plot_type, y_label="Stiffness (kPa)")
        fig = Figure(figsize=(opts.width_in, opts.height_in))
        pl.render_column(fig, groups, opts, res)
        for ext in pl.EXPORT_FORMATS:
            path = os.path.join(out_dir, f"{plot_type.replace(' ', '_')}{ext}")
            pl.save_figure(fig, path, title=plot_type)
            check(f"{plot_type} exports {ext}", os.path.getsize(path) > 500)
    svg = open(os.path.join(out_dir, "Scatter_dot_plot.svg"), encoding="utf-8").read()
    check("SVG keeps text editable", "<text" in svg and "font-family" in svg.replace("font:", "font-family"))
    pdf = open(os.path.join(out_dir, "Scatter_dot_plot.pdf"), "rb").read()
    check("PDF author metadata set", b"Daniel Shiwarski" in pdf)

    x = np.array([0.01, 0.1, 1, 10, 100.0])
    y1 = se._four_pl(x, 0, 100, 0, 1)[:, None] + RNG.normal(0, 3, (5, 3))
    y2 = se._four_pl(x, 0, 80, 1, 1)[:, None] + RNG.normal(0, 3, (5, 3))
    fits = [se.fit_curve(n, x, y, "Dose-response, 4PL (variable slope)")
            for n, y in [("Vehicle", y1), ("Drug", y2)]]
    opts = pl.XYPlotOptions(log_x=True, fit_model="Dose-response, 4PL (variable slope)")
    fig = Figure(figsize=(opts.width_in, opts.height_in))
    pl.render_xy(fig, x, [("Vehicle", y1), ("Drug", y2)], opts, fits)
    pl.save_figure(fig, os.path.join(out_dir, "xy.svg"))
    check("XY with fits renders", True)

    fig = Figure(figsize=(2.5, 2.5))
    pl.render_column(fig, [("Empty", np.array([np.nan]))], pl.ColumnPlotOptions())
    check("empty grid shows a message instead of crashing", True)


def test_prism_layout():
    """Exact plotting area and preset text settings for every graph type."""
    from stelplot import lab_style as ls
    import matplotlib
    groups = [("Control", A), ("Drug A", B), ("Drug B", C)]
    res = se.run_column_stats(groups, "One-way ANOVA")
    for style in ls.STYLE_PRESETS:
        st = ls.preset(style)
        for plot_type in pl.PLOT_TYPES:
            opts = pl.ColumnPlotOptions(plot_type=plot_type, y_label="Stiffness (kPa)", x_label="Group",
                                        title="Data 1", style=style, font_size=st["font_size"],
                                        bold=st["bold"], width_in=1.8)
            fig = Figure()
            ax = pl.render_column(fig, groups, opts, res)
            W, H = fig.get_size_inches()
            pos = ax.get_position()
            check(f"{style} / {plot_type}: plotting area is exactly 1.80 x 2.00 in",
                  abs(pos.width * W - 1.8) < 1e-9 and abs(pos.height * H - 2.0) < 1e-9)
        rc = matplotlib.rcParams
        check(f"{style}: numbering {st['font_size']:g} pt, axis titles {st['font_size'] + 1:g} pt",
              rc["xtick.labelsize"] == st["font_size"] and rc["axes.labelsize"] == st["font_size"] + 1)
        check(f"{style}: {st['line']} pt axes, {st['tick_len']} pt ticks pointing {st['tick_dir']}",
              rc["axes.linewidth"] == st["line"] and rc["xtick.major.size"] == st["tick_len"]
              and rc["xtick.direction"] == st["tick_dir"])
    check("Lab template is regular weight; Prism default is bold",
          not ls.preset("Lab template")["bold"] and ls.preset("Prism default")["bold"])
    for render, opts, args in [
            (pl.render_grouped, pl.GroupedPlotOptions(),
             (["R1", "R2"], ["A", "B"], np.arange(12, dtype=float).reshape(2, 2, 3))),
            (pl.render_xy, pl.XYPlotOptions(), (np.arange(5.0), [("S", np.arange(5.0)[:, None])]))]:
        fig = Figure()
        ax = render(fig, *args, opts)
        W, H = fig.get_size_inches()
        pos = ax.get_position()
        check(f"{render.__name__}: plotting area is exactly 2.00 x 2.00 in",
              abs(pos.width * W - 2.0) < 1e-9 and abs(pos.height * H - 2.0) < 1e-9)
    check("Prism-like auto range: data up to 7.8 gives an axis of 0 to 10",
          pl.nice_range(0, 7.8) == (0.0, 10.0))
    check("Prism-like auto range: data up to 121 gives 0 to 150, 72 h gives 0 to 80",
          pl.nice_range(0, 121) == (0.0, 150.0) and pl.nice_range(0, 72) == (0.0, 80.0))


def test_violin_points_follow_shape():
    """Violin points stay inside the outline and crowd where the distribution is wide."""
    from matplotlib.collections import PathCollection
    rng = np.random.default_rng(1)
    bimodal = np.r_[rng.normal(20, 4, 450), rng.normal(60, 6, 150)]
    groups = [("Bimodal", bimodal), ("Skewed", rng.gamma(2.0, 30.0, 700))]
    for layout in pl.POINT_LAYOUTS:
        fig = Figure()
        ax = pl.render_column(fig, groups, pl.ColumnPlotOptions(plot_type="Violin plot",
                                                                point_layout=layout, point_size=2.0))
        pts = [c for c in ax.collections if isinstance(c, PathCollection) and len(c.get_offsets()) > 50]
        inside, follows = True, True
        for i, (name, vals) in enumerate(groups):
            ys, half = pl.violin_shape(vals)
            off = np.asarray(pts[i].get_offsets())
            dx = np.abs(off[:, 0] - i)
            inside &= bool(np.all(dx <= np.interp(off[:, 1], ys, half) + 1e-9))
        off = np.asarray(pts[0].get_offsets())
        dx = np.abs(off[:, 0])
        near_peak = dx[np.abs(off[:, 1] - 20) < 3].mean()
        near_trough = dx[np.abs(off[:, 1] - 40) < 3]
        follows = near_trough.size == 0 or near_peak > 2 * near_trough.mean()
        check(f"violin points ({layout}) stay inside the violin outline", inside)
        check(f"violin points ({layout}) spread wider at the peak than in the trough", follows)


def test_clipboard_quotes():
    from stelplot.clipboard import parse_clipboard
    rows = parse_clipboard('"Casted ctrl"\t"Casted ECM"\r\n12.4\t3.29\r\n5.63\t\r\n')
    check("pasted titles lose the quotes Excel and Prism add",
          rows[0] == ["Casted ctrl", "Casted ECM"] and rows[1] == ["12.4", "3.29"] and rows[2] == ["5.63", ""])
    rows = parse_clipboard('\u201cDay 1\u201d\t"multi\nline"\n1\t2')
    check("curly quotes and quoted line breaks are handled",
          rows[0] == ["Day 1", "multi\nline"] and rows[1] == ["1", "2"])


if __name__ == "__main__":
    test_t_tests()
    test_anova_tukey_dunnett()
    test_dunn()
    test_nonparametric_two_group()
    test_fits()
    test_render_and_export()
    test_prism_layout()
    test_violin_points_follow_shape()
    test_clipboard_quotes()
    print("\nAll checks passed.")
