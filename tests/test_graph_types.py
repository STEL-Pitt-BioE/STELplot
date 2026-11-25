"""Checks for the v1.9 graph additions. Run from the STELplot folder:

    python -m tests.test_graph_types

Summary marks drawn over points, grouped box plots, volcano plots (grouped and XY), area
plots, bar arrangements, horizontal graphs, right Y axes, circle heat maps, custom color
schemes, and 3D graphs.
"""

__author__ = "Daniel Shiwarski"

import json
import math
import os
import tempfile

import numpy as np
from matplotlib.collections import PathCollection, PolyCollection
from matplotlib.colors import to_hex
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from scipy import stats

from stelplot import interpret
from stelplot import lab_style as ls
from stelplot import plot3d as p3
from stelplot import plotting as pl
from stelplot import stats_engine as se
from stelplot import volcano

RNG = np.random.default_rng(19)
LABELS = ["Day 1", "Day 7", "Day 14"]
NAMES = ["Control", "Low", "High"]
D = np.stack([RNG.normal(10 + 2 * r, 1, (3, 4)) + np.array([0, 2, 4])[:, None] for r in range(3)])


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print(f"PASS  {name}")


def bars(ax):
    return [p for p in ax.patches if isinstance(p, Rectangle) and p.get_height() != 0
            and p.get_width() != 0]


def test_summary_over_points():
    groups = [("A", RNG.normal(5, 1, 10)), ("B", RNG.normal(7, 1, 10))]
    for pt in ("Scatter dot plot", "Bar with points", "Box plot"):
        fig = Figure()
        ax = pl.render_column(fig, groups, pl.ColumnPlotOptions(plot_type=pt, show_points=True))
        points = max(c.get_zorder() for c in ax.collections if isinstance(c, PathCollection))
        marks = [ln.get_zorder() for ln in ax.lines] + [c.get_zorder() for c in ax.collections
                                                         if not isinstance(c, PathCollection)]
        check(f"{pt}: mean, median, and error lines are drawn over the points",
              marks and min(marks) > points)
    fig = Figure()
    ax = pl.render_grouped(fig, LABELS, NAMES, D, pl.GroupedPlotOptions(show_points=True))
    points = max(c.get_zorder() for c in ax.collections if isinstance(c, PathCollection))
    errs = [c.get_zorder() for c in ax.collections if not isinstance(c, PathCollection)]
    check("grouped bars: error bars are drawn over the points", min(errs) > points)


def test_grouped_box_and_arrangements():
    fig = Figure()
    ax = pl.render_grouped(fig, LABELS, NAMES, D, pl.GroupedPlotOptions(plot_type=pl.GROUPED_BOX))
    medians = [ln for ln in ax.lines if len(ln.get_ydata()) == 2 and
               ln.get_ydata()[0] == ln.get_ydata()[1]]
    med = sorted(float(np.median(D[r, c])) for r in range(3) for c in range(3))
    drawn = sorted({round(float(ln.get_ydata()[0]), 9) for ln in medians})
    check("grouped box plot: one box per cell with the cell median",
          all(any(abs(m - d) < 1e-9 for d in drawn) for m in med))

    means = D.mean(axis=2)
    fig = Figure()
    ax = pl.render_grouped(fig, LABELS, NAMES, D, pl.GroupedPlotOptions(arrangement="Stacked"))
    tops = sorted(round(b.get_y() + b.get_height(), 9) for b in bars(ax))
    want = sorted(round(v, 9) for v in np.cumsum(means, axis=1).ravel())
    check("stacked bars: each segment starts where the one below ends",
          np.allclose(tops, want))
    fig = Figure()
    ax = pl.render_grouped(fig, LABELS, NAMES, D, pl.GroupedPlotOptions(arrangement="Superimposed"))
    xs = {round(b.get_x() + b.get_width() / 2, 9) for b in bars(ax)}
    front = {}
    for b in bars(ax):
        front.setdefault(round(b.get_x(), 6), []).append((b.get_zorder(), b.get_height()))
    check("superimposed bars share one position per row, shorter bars in front, solid fills",
          len(xs) == 3 and all(sorted(v)[-1][1] == min(h for _, h in v) for v in front.values())
          and all(b.get_facecolor()[3] == 1.0 for b in bars(ax)))
    fig = Figure()
    ax = pl.render_grouped(fig, LABELS, NAMES, D, pl.GroupedPlotOptions(arrangement="Separated"))
    check("separated bars: one block per data set, a tick for every bar",
          len(ax.get_xticks()) == 9 and len(bars(ax)) == 9)
    fig = Figure()
    ax = pl.render_grouped(fig, LABELS, NAMES, D, pl.GroupedPlotOptions(plot_type=pl.AREA,
                                                                        arrangement="Stacked"))
    polys = [c for c in ax.collections if isinstance(c, PolyCollection)]
    top = max(float(np.max(p.get_paths()[0].vertices[:, 1])) for p in polys)
    check("stacked area plot: one area per data set, reaching the summed means",
          len(polys) == 3 and abs(top - means.sum(axis=1).max()) < 1e-9)


def test_orientation():
    groups = [("A", RNG.normal(5, 1, 8)), ("B", RNG.normal(9, 1, 8))]
    fig = Figure()
    ax = pl.render_column(fig, groups, pl.ColumnPlotOptions(plot_type="Bar with points",
                                                            orientation="Horizontal"))
    widths = sorted(b.get_width() for b in bars(ax))
    check("horizontal bars grow along X to the group means",
          np.allclose(widths, sorted(np.mean(v) for _, v in groups))
          and [t.get_text() for t in ax.get_yticklabels()] == ["A", "B"]
          and ax.get_ylim()[0] > ax.get_ylim()[1])
    fig = Figure()
    ax = pl.render_grouped(fig, LABELS, NAMES, D, pl.GroupedPlotOptions(orientation="Horizontal"))
    check("horizontal grouped bars: rows down the Y axis, values along X",
          [t.get_text() for t in ax.get_yticklabels()] == LABELS and ax.get_xlabel() == "Value")


def test_right_axis():
    big = D * np.array([1, 1, 40])[None, :, None]
    fig = Figure()
    ax = pl.render_grouped(fig, LABELS, NAMES, big, pl.GroupedPlotOptions(
        plot_type="Line plot (mean ± error)", right_series=("High",), right_label="High (mM)"))
    twins = [a for a in fig.axes if a is not ax and a.get_position().bounds == ax.get_position().bounds]
    check("grouped line plot: the chosen data set gets its own right Y axis",
          len(twins) == 1 and twins[0].get_ylabel() == "High (mM)"
          and twins[0].get_ylim()[1] > 10 * ax.get_ylim()[1])
    x = np.arange(5.0)
    fig = Figure()
    ax = pl.render_xy(fig, x, [("A", x[:, None]), ("B", 100 * x[:, None])],
                      pl.XYPlotOptions(right_series=("B",)))
    twins = [a for a in fig.axes if a is not ax]
    check("XY graph: a series on the right axis keeps the left axis scaled to the others",
          len(twins) == 1 and ax.get_ylim()[1] < 10 and twins[0].get_ylim()[1] >= 400)
    fig = Figure()
    ax = pl.render_xy(fig, x, [("A", x[:, None] + 1)], pl.XYPlotOptions(plot_type=pl.AREA))
    check("XY area plot fills down to zero",
          any(isinstance(c, PolyCollection) and np.isclose(c.get_paths()[0].vertices[:, 1].min(), 0)
              for c in ax.collections))


def test_volcano_statistics():
    p = np.array([0.01, 0.04, 0.03, 0.2, np.nan, 0.001])
    ok = p[np.isfinite(p)]
    order = np.argsort(ok)
    m = ok.size
    manual = np.empty(m)
    run = 1.0
    for rank in range(m - 1, -1, -1):          # Benjamini-Hochberg step-up, by hand
        i = order[rank]
        run = min(run, ok[i] * m / (rank + 1))
        manual[i] = run
    q = volcano.bh_adjust(p)
    check("Benjamini-Hochberg adjusted P values match the step-up procedure; blanks stay blank",
          np.allclose(q[np.isfinite(p)], manual) and np.isnan(q[4]))
    A = RNG.normal(10, 1, (6, 4))
    B = A + RNG.normal(0, 1, (6, 4))
    fc, pv = volcano.row_tests(2 ** A, 2 ** B)
    want = [stats.ttest_ind(2 ** B[r], 2 ** A[r], equal_var=False).pvalue for r in range(6)]
    check("each row's P value is Welch's t test and its fold change log2(mean B / mean A)",
          np.allclose(pv, want) and np.allclose(fc, np.log2((2 ** B).mean(1) / (2 ** A).mean(1))))
    fc2, _ = volcano.row_tests(A, B, already_log=True)
    check("for log2 data the fold change is the difference of means",
          np.allclose(fc2, B.mean(1) - A.mean(1)))
    status = volcano.classify(np.array([2, -2, 0.5, 2]), np.array([0.01, 0.01, 0.001, 0.2]), 1, 0.05)
    check("up and down need both the fold change and the P value cutoff",
          list(status) == [1, -1, 0, 0])


def test_volcano_graphs():
    n = 400
    rng = np.random.default_rng(5)
    A = rng.normal(20, 0.15, (n, 4))
    B = A + rng.normal(0, 0.15, (n, 4))
    B[:20] += 2.5
    B[20:30] -= 2.5
    Dv = np.stack([2 ** A, 2 ** B], axis=1)
    names = [f"P{i}" for i in range(n)]
    fig = Figure()
    v = pl.VolcanoOptions(label_top=5, label_names="P399")
    ax = pl.render_grouped(fig, names, ["WT", "KO"], Dv, pl.GroupedPlotOptions(
        plot_type=pl.VOLCANO, volcano=v, legend="Above plot"))
    t = fig.stel_volcano
    labels = [a.get_text() for a in ax.texts]
    check("grouped volcano plot finds the 20 raised and 10 lowered proteins",
          t["counts"]["Up"] == 20 and t["counts"]["Down"] == 10)
    check("labels the top rows by P plus the named ones",
          len(labels) == 6 and "P399" in labels)
    leg = [x.get_text() for x in ax.get_legend().get_texts()]
    check("legend gives the counts", leg[0] == "Down (10)" and leg[2] == "Up (20)")
    text = volcano.volcano_text(t)
    check("results list every changed row", text.count("  Up") + text.count("  Down") >= 30)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "v.csv")
        volcano.write_volcano_csv(path, t)
        rows = open(path, encoding="utf-8").read().splitlines()
        check("CSV export has a row for every protein", len(rows) == n + 1)
        svg = os.path.join(tmp, "v.svg")
        pl.save_figure(fig, svg)
        check("volcano SVG keeps labels as editable text", "P399" in open(svg, encoding="utf-8").read())

    fc = np.array([2.0, -2.0, 0.1, 1.5])
    p = np.array([1e-4, 1e-3, 0.5, 0.2])
    figs = []
    for kind, y in ((volcano.P_INPUTS[0], p), (volcano.P_INPUTS[1], -np.log10(p))):
        fig = Figure()
        pl.render_xy(fig, fc, [("P", y[:, None])], pl.XYPlotOptions(
            plot_type=pl.VOLCANO, volcano=pl.VolcanoOptions(p_input=kind)),
            row_titles=["a", "b", "c", "d"])
        figs.append(fig.stel_volcano)
    check("XY volcano: P values and -log10(P) give the same result, named by row titles",
          np.allclose(figs[0]["p"], figs[1]["p"]) and list(figs[0]["status"]) == [1, -1, 0, 0]
          and figs[0]["names"] == ["a", "b", "c", "d"])


def test_circle_heat_map():
    fig = Figure()
    ax = pl.render_grouped(fig, LABELS, NAMES, D, pl.GroupedPlotOptions(
        plot_type=pl.HEAT_MAP, heat_shape="Circles", circle_color="SD"))
    sc = [c for c in ax.collections if isinstance(c, PathCollection)][0]
    means = D.mean(axis=2)
    sizes = np.asarray(sc.get_sizes())
    check("circle area is proportional to the cell mean",
          np.allclose(sizes / sizes.max(), (means / means.max()).ravel()))
    sd = pl.circle_color_values(D, "SD")
    check("circle color can show the SD of each cell", np.allclose(sd, D.std(axis=2, ddof=1)))
    other = (list(reversed(LABELS)), ["High", "Low", "Control"], np.arange(9.0).reshape(3, 3, 1))
    matched = pl.match_cells(LABELS, NAMES, other)
    check("another table's values line up by row and data set name",
          matched[0, 0] == other[2][2, 2, 0] and matched[2, 2] == other[2][0, 0, 0])


def test_custom_colors():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            ls.register_palette("Journal", ["#000000"])
            ok = False
        except ValueError:
            ok = True
        check("built-in color schemes cannot be replaced", ok)
        cols = ls.register_palette("Test scheme", ["#112233", "#ff8800", "nope", "#00AA88"])
        check("a color scheme keeps valid colors in order", cols == ["#112233", "#FF8800", "#00AA88"])
        check("graphs use the scheme's colors", pl.palette_colors("Test scheme", 4)[3] == "#112233")
        cmap = pl.colormap("Test scheme")
        check("a scheme can be a heat map gradient",
              to_hex(cmap(0.0)) == "#112233" and to_hex(cmap(1.0)) == "#00aa88"
              and "Test scheme" in pl.heat_map_names())
        path = os.path.join(tmp, "styles.json")
        ls.save_style_library(path)
        ls.remove_palette("Test scheme")
        check("removed schemes leave the palette list", "Test scheme" not in ls.PALETTES)
        ls.load_style_library(path)
        check("schemes are saved to and loaded from the style library",
              ls.PALETTES.get("Test scheme") == cols
              and json.load(open(path))["palettes"]["Test scheme"] == cols)
        ls.remove_palette("Test scheme")


def test_3d():
    gx, gy = np.meshgrid(np.linspace(0, 4, 5), np.linspace(0, 3, 4))
    x, y = gx.ravel(), gy.ravel()
    z = x + y
    c = x * y
    for kind in p3.KINDS_3D:
        for by in p3.COLOR_BY:
            fig = Figure()
            ax = p3.render_xyz(fig, x, y, z, c, p3.XYZPlotOptions(
                plot_type=kind, view3d=p3.View3DOptions(color_by=by)))
            assert ax is not None and ax.name == "3d", (kind, by)
    check("3D scatter, line, surface, wireframe, and bars draw with every color choice", True)
    fig = Figure()
    ax = p3.render_xyz(fig, x, y, z, c, p3.XYZPlotOptions(
        plot_type="3D scatter", view3d=p3.View3DOptions(color_by=p3.COLOR_BY[1], cmap="Viridis")))
    fig.draw_without_rendering()   # 3D collections set their colors when first drawn
    face = ax.collections[0].get_facecolors()
    cmap = pl.colormap("Viridis")
    want = [cmap((v - c.min()) / (c.max() - c.min())) for v in c]
    drawn = {tuple(np.round(f, 6)) for f in face}
    expected = {tuple(np.round(w, 6)) for w in want}
    check("the fourth variable sets each point's color, across the whole color scale",
          drawn <= expected and tuple(np.round(cmap(0.0), 6)) in drawn
          and tuple(np.round(cmap(1.0), 6)) in drawn)
    check("a color bar shows the fourth variable's scale",
          len(fig.axes) == 2 and fig.axes[1].get_ylabel() == "Color")
    check("grid data are recognized for smooth surfaces",
          p3._is_grid(x, y) is not None and p3._is_grid(x[:-1], y[:-1]) is None)
    fig = Figure()
    ax = p3.render_xyz(fig, x, y, z, None, p3.XYZPlotOptions(plot_type="3D bars"))
    check("3D bars rise from zero to each Z value", math.isclose(ax.get_zlim()[0], 0.0)
          and ax.get_zlim()[1] >= z.max())
    fig = Figure()
    ax = pl.render_grouped(fig, LABELS, NAMES, D, pl.GroupedPlotOptions(plot_type=pl.BARS_3D))
    check("grouped table: 3D bars with rows and data sets on the floor axes",
          [t.get_text() for t in ax.get_yticklabels()] == NAMES)
    with tempfile.TemporaryDirectory() as tmp:
        for ext in (".svg", ".pdf", ".png"):
            fig = Figure()
            p3.render_xyz(fig, x, y, z, c, p3.XYZPlotOptions(plot_type="Surface"))
            pl.save_figure(fig, os.path.join(tmp, "s" + ext))
        check("3D graphs export as SVG, PDF, and PNG",
              all(os.path.getsize(os.path.join(tmp, "s" + e)) > 0 for e in (".svg", ".pdf", ".png")))


def test_volcano_interpret():
    rng = np.random.default_rng(8)
    n = 300
    A = rng.normal(20, 0.2, (n, 4))
    B = A + rng.normal(0, 0.2, (n, 4))
    B[:12] += 2.0
    B[12:20] -= 2.0
    Dv = np.stack([2 ** A, 2 ** B], axis=1)
    fig = Figure()
    pl.render_grouped(fig, [f"P{i}" for i in range(n)], ["WT", "KO"], Dv,
                      pl.GroupedPlotOptions(plot_type=pl.VOLCANO, volcano=pl.VolcanoOptions()))
    vt = fig.stel_volcano
    text, warnings = interpret.volcano_summary(vt)
    check("volcano summary names the comparison, the counts, the cutoffs, and the test",
          f"{vt['counts']['Up']} are higher in KO than in WT" in text
          and f"{vt['counts']['Down']} are lower in KO than in WT" in text
          and "2-fold" in text and "Welch's t test" in text)
    check("unadjusted P on many rows warns about chance hits and suggests the FDR option",
          any("by chance alone" in w and "Benjamini-Hochberg" in w for w in warnings))
    fig = Figure()
    pl.render_grouped(fig, [f"P{i}" for i in range(n)], ["WT", "KO"], Dv, pl.GroupedPlotOptions(
        plot_type=pl.VOLCANO, volcano=pl.VolcanoOptions(use_fdr=True)))
    text, warnings = interpret.volcano_summary(fig.stel_volcano)
    check("with adjusted P the summary states the false discovery rate and drops the warning",
          "false discoveries" in text and not any("by chance alone" in w for w in warnings))
    fig = Figure()
    pl.render_xy(fig, np.array([2.0, -2.0, 0.1]), [("P", np.array([[1e-4], [1e-3], [0.5]]))],
                 pl.XYPlotOptions(plot_type=pl.VOLCANO, volcano=pl.VolcanoOptions()))
    text, warnings = interpret.volcano_summary(fig.stel_volcano)
    check("XY volcano summary uses up and down, and notes the P values were entered",
          "1 are up" in text and any("were entered" in w for w in warnings))
    help_ = interpret.help_text("Volcano plot")
    check("Interpret explains volcano plots, not two-way ANOVA",
          help_.startswith("Volcano plot") and "false discovery rate" in help_
          and "Two-way" not in help_)


if __name__ == "__main__":
    test_summary_over_points()
    test_grouped_box_and_arrangements()
    test_orientation()
    test_right_axis()
    test_volcano_statistics()
    test_volcano_graphs()
    test_circle_heat_map()
    test_custom_colors()
    test_3d()
    test_volcano_interpret()
    print("\nAll graph type checks passed.")
