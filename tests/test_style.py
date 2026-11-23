"""Exported SVGs checked against the lab's Prism template exports.

Reference values were measured from the Prism 9 SVG exports of PrismTemplates.pzfx
(Prism exports at 99.6% scale; nominal values are listed). Run from the STELplot folder:

    python -m tests.test_style
"""

__author__ = "Daniel Shiwarski"

import os
import re
import tempfile

import numpy as np
from matplotlib.figure import Figure

from stelplot import anova
from stelplot import plotting as pl
from stelplot import stats_engine as se
from stelplot.lab_style import STAR_GLYPH

PRISM = {
    "numbering_pt": 7.0, "axis_title_pt": 8.0, "line_pt": 0.72, "thin_pt": 0.36,
    "tick_pt": 1.8, "fill_opacity": 0.5, "colors": ["#000000", "#ff0066", "#107f80"],
    "violin_median_dash": "2.16,1.44", "band_edge_dash": "1.08,0.72",
}

GROUPS = [("Untreated", np.array([3.4, 4.3, 3.0, 3.9, 4.1])),
          ("Placebo", np.array([2.3, 5.2, 4.5, 3.1, 5.0])),
          ("Treated", np.array([4.2, 7.8, 5.9, 6.4, 7.6]))]


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print(f"PASS  {name}")


def export(render, *args):
    fig = Figure()
    render(fig, *args)
    path = os.path.join(tempfile.mkdtemp(), "figure.svg")
    pl.save_figure(fig, path)
    return open(path, encoding="utf-8").read()


def font_sizes(svg):
    return {float(v) for v in re.findall(r"font-size: ([\d.]+)px", svg)}


def test_bar_graph():
    r = se.run_column_stats(GROUPS, "One-way ANOVA")
    opts = pl.ColumnPlotOptions(plot_type="Bar with points", error="Mean with SEM",
                                y_label="Relative Expression (a.u.)", width_in=1.8,
                                palette="Lab template")
    svg = export(pl.render_column, GROUPS, opts, r)
    check("numbering 7 pt and axis title 8 pt, as in the Prism export",
          {PRISM["numbering_pt"], PRISM["axis_title_pt"]} <= font_sizes(svg))
    check("axes, error bars, and brackets are 0.72 pt", f"stroke-width: {PRISM['line_pt']}" in svg)
    check("bar outlines are 0.36 pt", f"stroke-width: {PRISM['thin_pt']}" in svg)
    check("bars are filled at 50% opacity, as in the export",
          f"fill-opacity: {PRISM['fill_opacity']}" in svg)
    ticks = re.findall(r'<path id="m[0-9a-f]+" d="M 0 0 \s*L (-?[\d.]+) (-?[\d.]+)', svg)
    lengths = {abs(float(x)) + abs(float(y)) for x, y in ticks}
    check("ticks are 1.8 pt long", PRISM["tick_pt"] in lengths)
    check("Lab template colors appear in the export when chosen",
          all(c in svg for c in PRISM["colors"]))
    default = export(pl.render_column, GROUPS, pl.ColumnPlotOptions(plot_type="Bar with points"), r)
    from stelplot.lab_style import PALETTES
    check("default exports use the colorblind-robust Journal palette",
          all(c.lower() in default.lower() for c in PALETTES["Journal"][:3]))
    check("significance stars use Prism's heavy asterisk", STAR_GLYPH in svg)
    check("text stays editable (no outlined glyphs)", "<text" in svg and "<use xlink:href=\"#DejaVu" not in svg)
    check("text is regular weight in the Lab template", "font-weight: bold" not in svg)


def test_violin_and_reference_line():
    opts = pl.ColumnPlotOptions(plot_type="Violin plot", show_points=False, frame="Box", ref_y="5",
                                annotation="None")
    svg = export(pl.render_column, GROUPS, opts, None)
    check("violin median is dashed 2.16, 1.44 pt as in the export",
          f"stroke-dasharray: {PRISM['violin_median_dash']}" in svg)
    check("violin quartiles are dotted with round caps", "stroke-linecap: round" in svg)
    check("reference line is a dotted 1.44 pt line", "stroke-width: 1.44" in svg)


def test_xy_band():
    x = np.array([0, 6, 12, 24, 48, 72.0])
    y1 = np.column_stack([x * 1.2 + 40 + d for d in (-3, 0, 3)])
    y2 = np.column_stack([x * 0.7 + 30 + d for d in (-4, 0, 4)])
    opts = pl.XYPlotOptions(x_label="Hours", y_label="Percent change", width_in=1.5)
    svg = export(pl.render_xy, x, [("Control", y1), ("Treated", y2)], opts, [])
    check("XY error band edges are dashed 1.08, 0.72 pt", f"stroke-dasharray: {PRISM['band_edge_dash']}" in svg)
    check("XY band for black uses #cccccc, as in the export", "#cccccc" in svg)
    check("XY connecting lines are 0.36 pt", f"stroke-width: {PRISM['thin_pt']}" in svg)


def test_grouped_legend():
    rows, cols = ["Wild type", "Tame"], ["Before", "After"]
    D = np.array([[[34, 65, 34], [54, 91, 91]], [[12, 35, 12], [13, 29, 29]]], float)
    res = anova.run_grouped(rows, cols, D, design=anova.ACROSS_ROW,
                            comparisons="Compare columns within each row", gg=False)
    fig = Figure()
    ax = pl.render_grouped(fig, rows, cols, D, pl.GroupedPlotOptions(), res)
    leg = ax.get_legend()
    check("grouped graph shows a legend with one swatch per data set",
          leg is not None and [t.get_text() for t in leg.get_texts()] == cols)
    fig.draw_without_rendering()
    sw = leg.legend_handles[0].get_window_extent()
    w_pt, h_pt = sw.width * 72 / fig.dpi, sw.height * 72 / fig.dpi
    check(f"legend swatches are flat bars like Prism's 15.3 x 3.2 pt (got {w_pt:.1f} x {h_pt:.1f})",
          abs(w_pt - 15.3) < 1.0 and abs(h_pt - 3.2) < 0.8)


if __name__ == "__main__":
    test_bar_graph()
    test_violin_and_reference_line()
    test_xy_band()
    test_grouped_legend()
    print("\nAll style checks passed.")
