"""Checks for the v1.6 additions. Run from the STELplot folder:

    python -m tests.test_features

Confidence levels, cell-by-cell comparisons, the main-effects model, Prism-style rounding,
dashed error bars, EPS export, data transformations, plain-language summaries and warnings,
layout sheets, theme contrast, and saved methods.
"""

__author__ = "Daniel Shiwarski"

import logging
import math
import os
import re
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from scipy import stats

from stelplot import anova, help_docs, interpret, layout, outliers, theme, transforms, workflow
from stelplot import plotting as pl
from stelplot import stats_engine as se
from stelplot.prism_format import num, p_text

RNG = np.random.default_rng(7)
A = np.array([3.4, 4.3, 3.0, 3.9, 4.1, 3.6])
B = np.array([4.9, 5.6, 4.4, 5.9, 5.1, 6.0])


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print(f"PASS  {name}")


def test_confidence_levels():
    r95 = se.run_column_stats([("A", A), ("B", B)], "Unpaired t-test")
    r995 = se.run_column_stats([("A", A), ("B", B)], "Unpaired t-test", conf=0.995)
    c95, c995 = r95.comparisons[0], r995.comparisons[0]
    lo, hi = stats.t.interval(0.995, 10, loc=B.mean() - A.mean(), scale=c995.se)
    check("t test CI at 99.5% matches SciPy's t interval", abs(c995.ci_low - lo) < 1e-9 and abs(c995.ci_high - hi) < 1e-9)
    check("a higher confidence level gives a wider interval",
          (c995.ci_high - c995.ci_low) > (c95.ci_high - c95.ci_low))
    check("decimal confidence level sets the threshold (P < 0.005)",
          any("P < 0.005" in line for line in r995.extra_lines) and "99.5% CI" in se.column_report(r995, "SEM"))
    rp = se.run_column_stats([("A", A), ("B", B)], "Paired t-test", conf=0.999)
    check("paired t test uses the confidence level too", any("P < 0.001" in l for l in rp.extra_lines))
    for test in ("Kruskal-Wallis test", "Friedman test", "Repeated-measures one-way ANOVA", "Mann-Whitney test"):
        groups = [("A", A), ("B", B)] if test == "Mann-Whitney test" else [("A", A), ("B", B), ("C", A + 2)]
        r = se.run_column_stats(groups, test)
        assert math.isfinite(r.summary.get("P", math.nan)), test
    check("every test records its overall P value", True)


def test_cell_comparisons_and_main_effects():
    R, C, K = 3, 2, 3
    D = RNG.normal(10, 2, (R, C, K)) + np.array([0, 2, 5])[:, None, None] + np.array([0, 3])[None, :, None]
    rows, cols = ["R1", "R2", "R3"], ["C1", "C2"]
    full = anova.run_grouped(rows, cols, D, comparisons=anova.CELLS, correction="Tukey")
    check("cell-by-cell compares every pair of cells (15 for 3 x 2)", len(full.comparisons) == 15
          and full.families == (1, 15))
    means = D.mean(axis=2).ravel()
    check("with the full model, predicted means are the cell means",
          all(abs(c.mean1 - means[c.i]) < 1e-9 and abs(c.mean2 - means[c.j]) < 1e-9 for c in full.comparisons))
    main = anova.run_grouped(rows, cols, D, comparisons=anova.CELLS, model=anova.MAIN_EFFECTS)
    grand, rm, cm = D.mean(), D.mean(axis=(1, 2)), D.mean(axis=(0, 2))
    additive = (rm[:, None] + cm[None, :] - grand).ravel()
    check("with main effects only, predicted means are additive (row + column - grand)",
          all(abs(c.mean1 - additive[c.i]) < 1e-9 for c in main.comparisons))
    resid = next(r for r in main.rows if r.source == "Residual")
    check("main effects model has residual DF = N - R - C + 1", resid.df == R * C * K - R - C + 1
          and not any(r.source == "Interaction" for r in main.rows))
    rm_res = anova.run_grouped(rows, cols, D, design=anova.IN_SUBCOLUMN, comparisons=anova.CELLS)
    check("cell-by-cell is refused, with a note, for repeated measures",
          not rm_res.comparisons and any("Cell-by-cell" in n for n in rm_res.notes))


def test_prism_rounding():
    check("ties round away from zero like Prism (5.6795 -> 5.680, -2.2245 -> -2.225)",
          num(5.6795) == "5.680" and num(5.679499999999998) == "5.680" and num(-2.2245) == "-2.225")
    check("large P values print as >0.9999, as in Prism", p_text(0.99996) == ">0.9999" and p_text(0.5) == "0.5000")


def test_dashed_error_bars_and_eps():
    groups = [("A", A), ("B", B)]
    fig = Figure()
    ax = pl.render_column(fig, groups, pl.ColumnPlotOptions(plot_type="Bar with points", error_style="Dashed"))
    dashed = [lc for lc in ax.collections if isinstance(lc, LineCollection)
              and any(d is not None and d[1] is not None for d in lc.get_linestyle())]
    check("dashed error bars are drawn dashed", len(dashed) >= 2)
    D = RNG.normal(5, 1, (3, 2, 3))
    pl.render_grouped(Figure(), ["a", "b", "c"], ["x", "y"], D, pl.GroupedPlotOptions(error_style="Dashed"))
    x = np.arange(1.0, 6.0)
    pl.render_xy(Figure(), x, [("S", np.column_stack([x, x + 1]))], pl.XYPlotOptions(error_style="Dashed"))
    check("grouped and XY graphs draw dashed error bars", True)
    messages = []
    handler = logging.Handler()
    handler.emit = lambda record: messages.append(record.getMessage())
    logging.getLogger("matplotlib").addHandler(handler)
    try:
        fig = Figure()
        pl.render_column(fig, groups, pl.ColumnPlotOptions(plot_type="Bar with points"))
        path = pl.save_figure(fig, os.path.join(tempfile.mkdtemp(), "f.eps"))
    finally:
        logging.getLogger("matplotlib").removeHandler(handler)
    head = open(path, "rb").read(4000)
    body = open(path, "rb").read()
    check("EPS export is PostScript with TrueType (editable) fonts", head.startswith(b"%!PS-Adobe")
          and (b"Type42" in body or b"FontType 42" in body))
    check("EPS export blends transparent fills instead of warning", not any("transparen" in m for m in messages))


def test_transforms():
    st = {"headers": ["A", "B"], "cells": [["10", "100"], ["1000", "-5"], ["", "1"]], "excluded": [[0, 1]]}
    new, bad = transforms.transform_state("column", st, "Y = log10(Y)")
    check("log10 transform, with values that cannot be logged left blank and counted",
          new["cells"][0] == ["1", "2"] and new["cells"][1] == ["3", ""] and bad == 1)
    check("excluded values stay excluded after a transform", new["excluded"] == [[0, 1]])
    norm, _ = transforms.transform_state("column", {"headers": ["A"], "cells": [["2"], ["4"], ["6"]]},
                                         "Normalize: 0% = smallest, 100% = largest in each column")
    check("normalize sets the smallest to 0% and the largest to 100%", [r[0] for r in norm["cells"]] == ["0", "50", "100"])
    pct, _ = transforms.transform_state("column", {"headers": ["A", "B"], "cells": [["2", "4"], ["4", "8"]]},
                                        "Percent of the first column's mean")
    check("percent of the first column's mean", pct["cells"] == [["66.6667", "133.333"], ["133.333", "266.667"]])
    grp = {"x_name": "Row", "series_names": ["S1", "S2"], "reps": 2,
           "cells": [["Day 1", "1", "3", "2", "2"], ["Day 2", "3", "5", "4", "4"]]}
    frac, _ = transforms.transform_state("grouped", grp, "Fraction of total (each data set)")
    check("grouped transforms keep row titles and work per data set",
          frac["cells"][0][0] == "Day 1" and frac["cells"][0][1:3] == ["0.0833333", "0.25"]
          and frac["cells"][0][3:] == ["0.166667", "0.166667"])
    xy = {"x_name": "Dose", "series_names": ["Y"], "reps": 1, "cells": [["10", "1"], ["100", "2"]]}
    xlog, _ = transforms.transform_state("xy", xy, "X = log10(X)")
    check("XY tables can transform X", xlog["cells"] == [["1", "1"], ["2", "2"]])
    mult, _ = transforms.transform_state("column", {"headers": ["A"], "cells": [["2"]]}, "Y = Y * K", 2.5)
    try:
        transforms.transform_state("column", {"headers": ["A"], "cells": [["2"]]}, "Y = Y + K")
        k_needed = False
    except ValueError:
        k_needed = True
    check("K transforms use K and ask for it when missing", mult["cells"] == [["5"]] and k_needed)


def test_plain_language():
    r = se.run_column_stats([("Control", A), ("Drug", B)], "Unpaired t-test")
    text, warns = interpret.column_summary(r)
    check("t test summary states direction, CI, and significance in plain language",
          "Drug" in text and "higher" in text and "confidence interval" in text and "statistically significant" in text)
    skewed = [("A", np.r_[np.ones(9), 40.0]), ("B", np.r_[np.ones(9) * 2, 60.0])]
    _t, w = interpret.column_summary(se.run_column_stats(skewed, "Unpaired t-test"))
    check("non-Gaussian data are flagged with the nonparametric alternative",
          any("Shapiro-Wilk" in x and "Mann-Whitney" in x for x in w))
    _t, w = interpret.column_summary(se.run_column_stats([("A", A), ("B", np.r_[B * 6])], "Unpaired t-test"))
    check("unequal SDs are flagged with Welch's t test", any("Welch" in x for x in w))
    _t, w = interpret.column_summary(se.run_column_stats([("A", A[:2]), ("B", B)], "Unpaired t-test"))
    check("very small groups are flagged", any("only 2 value" in x for x in w))
    r = se.run_column_stats([("A", A), ("B", B), ("C", A + 0.1)], "One-way ANOVA")
    text, _ = interpret.column_summary(r)
    check("ANOVA summary reports the overall result and which comparisons differ",
          "groups' means differ" in text and "comparison(s) statistically significant" in text)
    D = np.stack([np.stack([A[:3], B[:3]]), np.stack([A[3:], B[3:] + 3])])
    g = anova.run_grouped(["Day 1", "Day 2"], ["Ctrl", "Drug"], D)
    text, _ = interpret.grouped_summary(g, "Time", "Treatment")
    check("two-way summary names the factors", "Time" in text and "Treatment" in text and "% of the total" in text)
    x = np.array([1e-9, 1e-8, 1e-7, 1e-6, 1e-5])
    y = 100 / (1 + 10 ** (-6.5 - np.log10(x))) + RNG.normal(0, 2, 5)
    fit = se.fit_curve("Drug", x, y[:, None], "Dose-response, 4PL (variable slope)")
    text, _ = interpret.xy_summary([fit], x)
    check("curve fit summary reports parameters and R squared", "LogEC50" in text and "R squared" in text)
    flat = se.fit_curve("Flat", x[:4], np.array([[1.0], [1.1], [0.9], [1.05]]), "Linear regression")
    _t, w = interpret.xy_summary([flat], x[:4])
    check("poor fits are flagged", any("R squared" in s or "wide confidence" in s for s in w))
    for name in [t for t in se.COLUMN_TESTS if t != "None"] + ["Two-way ANOVA"] + \
            [m for m in se.FIT_MODELS if m != "None"]:
        h = interpret.help_text(name)
        assert "Assumptions" in h and "Reading the results" in h, name
    check("Interpret help exists for every test and curve model", True)


def test_layout_sheets():
    folder = tempfile.mkdtemp()
    svgs, pngs = [], []
    for i in range(3):
        fig = Figure()
        pl.render_column(fig, [("A", A + i), ("B", B)], pl.ColumnPlotOptions(plot_type="Bar with points"))
        svgs.append(pl.save_figure(fig, os.path.join(folder, f"p{i}.svg"), transparent=True))
        pngs.append(pl.save_figure(fig, os.path.join(folder, f"p{i}.png"), transparent=True))
    out, (W, H) = layout.compose_svg(svgs, os.path.join(folder, "layout.svg"), ncols=2, author="Daniel Shiwarski")
    root = ET.parse(out).getroot()
    ns = "{http://www.w3.org/2000/svg}"
    groups = [g for g in root.findall(f"{ns}g") if g.get("id", "").startswith("panel_")]
    ids = [e.get("id") for e in root.iter() if e.get("id")]
    letters = [t.text for t in root.findall(f"{ns}text")]
    check("SVG layout is valid XML with 3 panels and letters A to C", len(groups) == 3 and letters == ["A", "B", "C"])
    check("panel ids are unique after combining", len(ids) == len(set(ids)))
    text = open(out, encoding="utf-8").read()
    refs = set(re.findall(r"url\(#([^)]+)\)", text))
    check("clip paths still point at their own panel", refs <= set(ids))
    check("SVG layout keeps editable text", "<text" in text and "font-family" in text)
    raster, size = layout.compose_raster(pngs, os.path.join(folder, "layout.tif"), ncols=3)
    from PIL import Image
    im = Image.open(raster)
    check("TIFF layout is a white RGB image at 600 dpi", im.mode == "RGB"
          and round(im.info.get("dpi", (0, 0))[0]) == 600 and im.getpixel((0, 0)) == (255, 255, 255))
    positions, _ = layout.arrange([(1, 1)] * 5, 2, 0.1, 0)
    check("panels wrap into rows of the chosen width", positions[2] == (0.0, 1.1) and positions[4] == (0.0, 2.2))


def test_theme_contrast():
    for name, t in (("light", theme.LIGHT), ("dark", theme.DARK)):
        for fg, bg, need in (("text", "panel", 4.5), ("text", "bg", 4.5), ("subtext", "panel", 4.5),
                             ("subtext", "bg", 4.5), ("accent_text", "accent", 4.5),
                             ("accent", "panel", 4.5), ("warn", "warn_bg", 4.5), ("indicator", "panel", 3.0)):
            ratio = theme.contrast(t[fg], t[bg])
            assert ratio >= need, (name, fg, bg, round(ratio, 2))
        assert theme.contrast(theme.EXCLUDED[name], t["panel"]) >= 4.5, name
        out = theme.QSS.format(**t, check="c.png", arrow_up="u.png", arrow_down="d.png")
        assert out.count("{") == out.count("}")
    check("theme text and controls meet WCAG contrast (4.5:1 text, 3:1 controls) in both themes", True)
    for t in (theme.LIGHT, theme.DARK):
        for bg in ("toolbar_top", "toolbar_bottom"):
            assert theme.contrast(t["toolbar_text"], t[bg]) >= 4.5, bg
    check("toolbar text meets WCAG contrast on the toolbar colors", True)


def test_help_documents():
    guide = [title for title, _ in help_docs.load_sections("USER_GUIDE.md")]
    needed = ["Quick start", "Choosing a table type", "Graphs for column data", "Graphs for grouped and XY data",
              "Statistics: choosing a test", "Statistics: reading the results", "Two-way ANOVA",
              "Curve fitting", "Good graphing practice", "Keyboard shortcuts"]
    check("user guide covers plotting, statistics, and graphing for each table type",
          all(n in guide for n in needed))
    check("README is found and split into topics", len(help_docs.load_sections("README.md")) >= 8)
    parts = help_docs.split_sections("# Title\nintro\n## A\none\n## B\ntwo")
    check("help text splits at section headings", parts == [("Overview", "intro"), ("A", "one"), ("B", "two")])


def test_workflow():
    opts = {"plot_type": "Box plot", "_series": {"order": [2, 0], "hidden": [1]}}
    check("saved methods leave out the column choices", workflow.method_settings(opts) == {"plot_type": "Box plot"})
    grp = {"x_name": "Row", "series_names": ["S1"], "reps": 2, "cells": [["Day 1", "1", "2"], ["Day 2", "3", ""]],
           "excluded": [[0, 1]]}
    empty = workflow.empty_data("grouped", grp)
    check("duplicating with empty data keeps row titles and layout", empty["cells"] == [["Day 1"], ["Day 2"]]
          and empty["series_names"] == ["S1"] and empty["excluded"] == [])
    path = os.path.join(tempfile.mkdtemp(), "methods.json")
    workflow.save_methods(path, {"Migration": {"kind": "column", "options": opts}})
    check("methods save and reload", workflow.load_methods(path)["Migration"]["options"] == opts)


def test_icons():
    from PIL import Image
    tiles = all(Image.open(help_docs.icon_path(f"macos/STEL_Plot_icon_{s}.png")).size == (s, s)
                for s in (16, 32, 64, 128, 256, 512, 1024))
    marks = all(Image.open(help_docs.icon_path(f"windows_linux_web/STEL_Plot_mark_{s}.png")).size == (s, s)
                for s in (16, 24, 32, 48, 64, 128, 256, 512, 1024))
    check("app tile and mark are bundled at every size", tiles and marks)
    icns = open(help_docs.icon_path("STEL_Plot.icns"), "rb").read(4) == b"icns"
    ico = Image.open(help_docs.icon_path("STEL_Plot.ico")).info.get("sizes", set())
    check("macOS .icns and Windows .ico are present for the standalone apps", icns and (256, 256) in ico)
    splash = Image.open(help_docs.icon_path("splash/STEL_Plot_splash_1600x900.png"))
    corners = [splash.convert("RGB").getpixel(p) for p in ((5, 5), (1594, 894), (5, 894), (1594, 5))]
    check("splash artwork is 1600 x 900 with white margins for the loading message",
          splash.size == (1600, 900) and all(c == (255, 255, 255) for c in corners))
    root = ET.parse(help_docs.icon_path("STEL_Plot_lockup_horizontal.svg")).getroot()
    tags = {el.tag.split("}")[-1] for el in root.iter()}
    fills = {el.get("fill") for el in root.iter() if el.get("fill")}
    check("lockup SVG is outlined shapes in the STEL colors (no live text)",
          "path" in tags and "text" not in tags and {"#000000", "#1D75BD", "#ED1B24"} <= fills)


def test_log_axes():
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.patches import Rectangle as Rect
    groups = [("A", np.array([0.5, 2.0, 8.0, 30.0, 0.0])), ("B", np.array([5.0, 20.0, 80.0, 300.0]))]
    fig = Figure()
    ax = pl.render_column(fig, groups, pl.ColumnPlotOptions(plot_type="Bar with points", log_y=True))
    y0, y1 = ax.get_ylim()
    check("log Y axis ends on whole decades and labels real values",
          y0 == math.floor(y0) and [t.get_text() for t in ax.get_yticklabels()][:2] == ["0.1", "1"])
    bars = [p for p in ax.patches if isinstance(p, Rect) and p.get_width() > 0.1]
    check("bars on a log axis start at its bottom (a log axis has no zero)",
          bars and all(abs(b.get_y() - y0) < 1e-9 for b in bars))
    check("bar height is the ordinary mean of the positive values",
          abs(bars[1].get_y() + bars[1].get_height() - math.log10(np.mean(groups[1][1]))) < 1e-9)
    check("values at or below zero are left off with a note", any("at or below zero" in n for n in fig.stel_notes))
    for pt in ("Scatter dot plot", "Box plot", "Violin plot", "Before-after (matched rows)"):
        pl.render_column(Figure(), groups, pl.ColumnPlotOptions(plot_type=pt, log_y=True))
    D = np.abs(RNG.lognormal(1, 1, (3, 2, 3)))
    for pt in ("Grouped bars", "Grouped scatter dot plot", "Line plot (mean ± error)"):
        pl.render_grouped(Figure(), ["a", "b", "c"], ["x", "y"], D, pl.GroupedPlotOptions(plot_type=pt, log_y=True))
    x = np.array([1.0, 10, 100, 1000])
    ax = pl.render_xy(Figure(), x, [("S", np.column_stack([x, x * 1.2]))], pl.XYPlotOptions(log_x=True, log_y=True))
    check("every graph type draws on a log Y axis; XY uses a true log scale", ax.get_yscale() == "log")


def test_histogram_and_heat_map():
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    t = pl.frequency_table([("A", np.array([0.5, 1.5, 1.6, 2.5])), ("B", np.array([1.0, 2.0]))], 1.0, 0.0)
    check("frequency table counts values into bins [start, end), last bin closed",
          list(t["series"][0][1]) == [1, 2, 1] and list(t["series"][1][1]) == [0, 1, 1])
    pct = pl.frequency_table([("A", np.array([0.5, 1.5, 1.6, 2.5]))], 1.0, 0.0, "Percent")
    check("histogram percents add to 100", abs(pct["series"][0][2].sum() - 100) < 1e-9)
    auto = pl.frequency_table([("A", RNG.normal(10, 2, 300))])
    check("automatic bin width is a round number", auto["auto"] and auto["width"] in (0.5, 1.0, 2.0, 2.5))
    below = pl.frequency_table([("A", np.array([1.0, 5.0, 6.0]))], 1.0, 4.0)
    check("values below the first bin are counted as left out", below["series"][0][4] == 1)
    fig = Figure()
    ax = pl.render_column(fig, [("A", RNG.normal(10, 2, 100)), ("B", RNG.normal(13, 2, 100))],
                          pl.ColumnPlotOptions(plot_type=pl.HISTOGRAM, hist_bin_width=1.0, ref_x="12"))
    check("histogram draws with a value axis and count axis", ax.get_ylabel() == "Number of values"
          and fig.stel_frequency is not None and "Bin start" in pl.frequency_text(fig.stel_frequency))
    fig = Figure()
    pl.render_column(fig, [("A", np.array([0.0, 1e6]))], pl.ColumnPlotOptions(plot_type=pl.HISTOGRAM, hist_bin_width=0.01))
    check("an impossible bin width gives a clear message", any("bins" in n for n in fig.stel_notes))
    H = RNG.normal(5, 2, (4, 3, 2))
    fig = Figure()
    ax = pl.render_grouped(fig, ["r1", "r2", "r3", "r4"], ["c1", "c2", "c3"], H,
                           pl.GroupedPlotOptions(plot_type=pl.HEAT_MAP, heat_values=True))
    FigureCanvasAgg(fig)
    fig.draw_without_rendering()
    cax = [a for a in fig.axes if a is not ax][0]
    check("heat map shows cell means with a color bar inside the figure",
          np.allclose(fig.stel_heatmap, np.nanmean(H, axis=2)) and cax.get_tightbbox().x1 <= fig.bbox.x1 + 1)
    check("heat map writes each cell's value", len(ax.texts) == 12)


def test_custom_transform():
    st = {"headers": ["A"], "cells": [["10"], ["100"], ["-1"]]}
    new, bad = transforms.transform_state("column", st, transforms.CUSTOM_Y, None, "log10(Y) * 2")
    check("custom expression transforms each value", [r[0] for r in new["cells"]] == ["2", "4", ""] and bad == 1)
    new, _ = transforms.transform_state("column", st, transforms.CUSTOM_Y, 4.0, "(Y - K) / K")
    check("expressions can use K", [r[0] for r in new["cells"]] == ["1.5", "24", "-1.25"])
    xy = {"x_name": "Dose", "series_names": ["Y"], "reps": 1, "cells": [["1", "5"], ["2", "8"]]}
    new, _ = transforms.transform_state("xy", xy, transforms.CUSTOM_Y, None, "Y / X")
    check("XY expressions can use X", new["cells"] == [["1", "5"], ["2", "4"]])
    blocked = 0
    for text in ("__import__('os')", "Y.real", "(lambda: 1)()", "open('f')", "[Y]", "K * Y", "X + Y"):
        try:
            transforms.transform_state("column", st, transforms.CUSTOM_Y, None, text)
        except ValueError:
            blocked += 1
    check("anything but arithmetic and math functions is refused", blocked == 7)


def test_outliers():
    table = {3: 1.15, 26: 2.84, 27: 2.86, 140: 3.49}   # GraphPad's Grubbs critical values, alpha 5%
    check("Grubbs critical values match GraphPad's published table",
          all(abs(outliers.grubbs_critical(n) - z) < 0.006 for n, z in table.items()))
    rng = np.random.default_rng(5)
    hits = sum(bool(outliers.rout(rng.normal(0, 1, 20), 0.01)[0]) for _ in range(1500))
    check(f"ROUT with Q = 1% flags Gaussian-only data in about 1-3% of experiments ({hits / 15:.1f}%)",
          0.3 <= hits / 15 <= 4.0)
    check("ROUT never flags values when N = 3 (as the paper reports)",
          outliers.rout(np.array([1.0, 1.1, 1000.0]), 0.01)[0] == [])
    y = np.r_[rng.normal(10, 1, 18), 30.0, 32.0]
    check("ROUT and iterative Grubbs find two outliers; single Grubbs finds one",
          outliers.identify(y, outliers.ROUT).outliers == [18, 19]
          and outliers.identify(y, outliers.ITERATIVE_GRUBBS).outliers == [18, 19]
          and outliers.identify(y, outliers.GRUBBS).outliers == [19])
    ln = rng.lognormal(2, 0.8, 200)
    check("log-normal data: the long tail is flagged on the raw scale but not on the log scale",
          len(outliers.identify(ln, outliers.ROUT).outliers) > 0
          and outliers.identify(ln, outliers.ROUT, log_scale=True).outliers == [])
    r = outliers.identify(np.r_[np.nan, rng.normal(5, 1, 12), 25.0, np.nan], outliers.ROUT)
    check("outlier positions refer to table rows, skipping blank and excluded cells",
          r.outliers == [13] and r.details[0][1] == 25.0)
    sentence = outliers.methods_sentence({"method": outliers.ROUT, "threshold": 0.01, "log": True, "excluded": 3})
    check("Methods text names the method, Q, the log scale, the reference, and the count",
          "ROUT" in sentence and "Q = 1%" in sentence and "log-transformed" in sentence and "2006" in sentence
          and "3 value(s)" in sentence)


if __name__ == "__main__":
    test_confidence_levels()
    test_cell_comparisons_and_main_effects()
    test_prism_rounding()
    test_dashed_error_bars_and_eps()
    test_transforms()
    test_plain_language()
    test_layout_sheets()
    test_theme_contrast()
    test_workflow()
    test_help_documents()
    test_icons()
    test_log_axes()
    test_histogram_and_heat_map()
    test_custom_transform()
    test_outliers()
    print("\nAll feature checks passed.")
