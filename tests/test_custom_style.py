"""Checks for marker shapes and custom styles. Run from the STELplot folder:

    python -m tests.test_custom_style
"""

__author__ = "Daniel Shiwarski"

import os
import re
import tempfile

import numpy as np
from matplotlib.collections import PathCollection
from matplotlib.figure import Figure

from stelplot import lab_style as ls
from stelplot import plotting as pl
from stelplot import stats_engine as se

GROUPS = [("Control", np.array([3.4, 4.3, 3.0, 3.9, 4.1])),
          ("Drug A", np.array([2.3, 5.2, 4.5, 3.1, 5.0])),
          ("Drug B", np.array([4.2, 7.8, 5.9, 6.4, 7.6]))]


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print(f"PASS  {name}")


def scatter_sets(ax):
    return [c for c in ax.collections if isinstance(c, PathCollection) and len(c.get_offsets())]


def test_marker_shapes():
    st = ls.preset("Lab template")
    check("Vary by group uses the style's marker order",
          [pl.marker_for(pl.VARY_MARKERS, i, st) for i in range(3)] == ["o", "s", "^"])
    check("shapes are sized for equal visual weight; squares keep Prism's 1.414",
          abs(pl.marker_size(4, "^", st) - 4 * 1.253) < 1e-9 and abs(pl.marker_size(4, "s", st) - 4 * 1.414) < 1e-9)
    for plot_type in pl.PLOT_TYPES:
        for shape in pl.MARKER_CHOICES:
            for fill in pl.MARKER_FILLS:
                fig = Figure()
                ax = pl.render_column(fig, GROUPS, pl.ColumnPlotOptions(
                    plot_type=plot_type, marker=shape, marker_fill=fill, show_points=True))
                sets = scatter_sets(ax)
                if fill == "Open" and sets:
                    assert all(len(c.get_facecolors()) == 0 or c.get_facecolors()[0][3] == 0 for c in sets)
    check("every column plot type renders every marker shape, filled and open", True)
    fig = Figure()
    ax = pl.render_column(fig, GROUPS, pl.ColumnPlotOptions(marker=pl.VARY_MARKERS))
    verts = [len(c.get_paths()[0].vertices) for c in scatter_sets(ax)]
    check("groups get different shapes with Vary by group", len(set(verts)) == 3)
    D = np.arange(12, dtype=float).reshape(2, 2, 3)
    for ptype in pl.GROUPED_PLOT_TYPES:
        fig = Figure()
        pl.render_grouped(fig, ["R1", "R2"], ["A", "B"], D, pl.GroupedPlotOptions(
            plot_type=ptype, marker=pl.VARY_MARKERS, marker_fill="Open", show_points=True))
    x = np.arange(5.0)
    for shape in pl.MARKER_CHOICES:
        fig = Figure()
        pl.render_xy(fig, x, [("S", x[:, None]), ("T", 2 * x[:, None])], pl.XYPlotOptions(marker=shape))
    check("grouped and XY graphs render every marker shape", True)


def test_custom_styles():
    try:
        ls.register_style("Lab template", {"data_line": 2})
        protected = False
    except ValueError:
        protected = True
    check("built-in styles cannot be overwritten", protected)
    st = ls.register_style("Heavy lines", {"axis_line": 1.5, "data_line": 2.0, "bracket_line": 1.2,
                                           "tick_dir": "out", "tick_len": 3.0, "bar_width": 0.5,
                                           "markers": ["D", "o"], "fill_alpha": 0.3,
                                           "palette": ["#1355AA", "#C55C55"], "font_size": 99,
                                           "bogus": 1})
    check("custom style values are kept, out-of-range values clamped, unknown keys ignored",
          st["data_line"] == 2.0 and st["font_size"] == 24 and "bogus" not in st
          and st["thin"] == ls.preset("Lab template")["thin"])
    check("custom style appears in the style list and brings its own palette",
          "Heavy lines" in ls.style_names() and ls.PALETTES["Heavy lines"] == ["#1355AA", "#C55C55"])
    r = se.run_column_stats(GROUPS, "One-way ANOVA")
    fig = Figure()
    pl.render_column(fig, GROUPS, pl.ColumnPlotOptions(plot_type="Bar with points", style="Heavy lines",
                                                       palette="Heavy lines", font_size=st["font_size"]), r)
    path = os.path.join(tempfile.mkdtemp(), "heavy.svg")
    pl.save_figure(fig, path)
    svg = open(path, encoding="utf-8").read()
    widths = {float(w) for w in re.findall(r"stroke-width: ([\d.]+)", svg)}
    check("exported SVG uses the custom axis, data, and bracket line widths", {1.5, 2.0, 1.2} <= widths)
    check("exported SVG uses the custom colors and fill opacity",
          "#1355aa" in svg.lower() and "fill-opacity: 0.3" in svg)
    lib = os.path.join(tempfile.mkdtemp(), "styles.json")
    ls.save_style_library(lib)
    ls.remove_style("Heavy lines")
    check("removed styles leave the list", "Heavy lines" not in ls.style_names())
    names = ls.load_style_library(lib)
    check("style library saves and reloads", names == ["Heavy lines"]
          and ls.preset("Heavy lines")["data_line"] == 2.0)
    ls.remove_style("Heavy lines")


def test_transparent_export():
    from PIL import Image
    folder = tempfile.mkdtemp()
    r = se.run_column_stats(GROUPS, "One-way ANOVA")

    def export(name, transparent):
        fig = Figure()
        pl.render_column(fig, GROUPS, pl.ColumnPlotOptions(plot_type="Bar with points"), r)
        return pl.save_figure(fig, os.path.join(folder, name), transparent=transparent)

    def background(svg_path):
        svg = open(svg_path, encoding="utf-8").read()
        m = re.search(r'<g id="patch_1">\s*<path[^>]*style="fill: ?([^;"]+)', svg)
        return m.group(1) if m else "none"

    check("transparent SVG has no white background", background(export("t.svg", True)) == "none")
    check("default SVG keeps the white background", background(export("w.svg", False)) == "#ffffff")
    png = Image.open(export("t.png", True)).convert("RGBA")
    check("transparent PNG corners are clear", png.getpixel((0, 0))[3] == 0)
    tif = Image.open(export("t.tif", True)).convert("RGBA")
    check("TIFF stays white even when transparent is chosen", tif.getpixel((0, 0)) == (255, 255, 255, 255))


if __name__ == "__main__":
    test_marker_shapes()
    test_custom_styles()
    test_transparent_export()
    print("\nAll custom style checks passed.")
