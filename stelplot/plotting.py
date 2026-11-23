"""Figure rendering for STELplot.

Each render function draws into a matplotlib Figure, so the same code makes
the on-screen preview and the exported file. Geometry follows the lab's Prism
template exports (see lab_style.py).
"""

__author__ = "Daniel Shiwarski"

import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

import numpy as np
from matplotlib.colors import to_rgba
from matplotlib.legend_handler import HandlerPatch
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullFormatter
from matplotlib.transforms import Bbox
from scipy.stats import gaussian_kde

from . import APP_NAME, __version__
from .lab_style import (AXIS_LENGTH_IN, BAR_WIDTH, COLUMN_CAP, COLUMN_MARGIN, DEFAULT_BOLD,
                        DEFAULT_FONT_SIZE, DEFAULT_PALETTE, DEFAULT_STYLE, GROUP_BAR, GROUP_CAP,
                        GROUP_MARGIN, GROUP_SPAN, STAR_GLYPH, STYLE_PRESETS, EQUAL_AREA,
                        MARKER_CODES, style_names,
                        apply_lab_style, band_colors, format_p, palette_colors, star_font)
from .stats_engine import error_halfwidth, finite, summary_values

PLOT_TYPES = ["Scatter dot plot", "Bar with points", "Box plot", "Violin plot",
              "Before-after (matched rows)", "Frequency distribution"]
GROUPED_BOX = "Grouped box plot"
AREA = "Area plot"
VOLCANO = "Volcano plot"
BARS_3D = "3D bars"
GROUPED_PLOT_TYPES = ["Grouped bars", "Grouped scatter dot plot", GROUPED_BOX,
                      "Line plot (mean ± error)", AREA, "Heat map", VOLCANO, BARS_3D]
XY_PLOT_TYPES = ["Points and lines", AREA, VOLCANO]
HISTOGRAM = "Frequency distribution"
HEAT_MAP = "Heat map"
# Prism's arrangements for grouped bars: side by side, one block per data set, stacked, overlapping
ARRANGEMENTS = ["Interleaved", "Separated", "Stacked", "Superimposed"]
ORIENTATIONS = ["Vertical", "Horizontal"]
HEAT_SHAPES = ["Squares", "Circles"]
# What colors the circles of a circle heat map (their size always shows the cell mean)
CIRCLE_COLORS = ["Same as size", "SD", "SEM", "Number of values", "Coefficient of variation"]
# Graph types that can put data sets on a second (right) Y axis
RIGHT_AXIS_TYPES = ("Grouped bars", "Grouped scatter dot plot", "Line plot (mean ± error)",
                    "Points and lines", AREA)
HIST_VALUES = ["Count", "Percent", "Fraction"]
HIST_STYLES = ["Bars", "Outline"]
HIST_Y_TITLES = {"Count": "Number of values", "Percent": "Percent of values",
                 "Fraction": "Fraction of values"}
# Perceptually uniform maps first (readable in grayscale and with color-vision deficiency)
HEAT_MAPS = {"Viridis": "viridis", "Cividis": "cividis", "Magma": "magma", "Blues": "Blues",
             "Red-blue (diverging)": "RdBu_r"}
POINT_LAYOUTS = ["Swarm", "Jitter"]
POINT_COLORS = ["Group color", "Black"]
BAR_STYLES = ["Filled", "Open"]
WHISKER_TYPES = ["Min to max", "Tukey (1.5 x IQR)"]
ANNOTATIONS = ["Stars", "Exact p values", "None"]
STYLES = list(STYLE_PRESETS)   # built-in styles; style_names() also lists custom ones
FRAMES = ["Open", "Box"]
LEGEND_POSITIONS = ["Inside upper left", "Inside upper right", "Above plot", "Right of plot", "None"]
XY_ERROR_DISPLAYS = ["Shaded band", "Error bars", "None"]
MARKER_FILLS = ["Filled", "Open"]
XY_MARKERS = ["o", "s", "^", "D", "v", "h"]
VARY_MARKERS = "Vary by group"
MARKER_CHOICES = list(MARKER_CODES) + [VARY_MARKERS]


def marker_for(choice, index, st):
    """Marker code for a group: one shape for all, or the style's sequence by group."""
    if choice == VARY_MARKERS:
        seq = st.get("markers") or XY_MARKERS
        return seq[index % len(seq)]
    return MARKER_CODES.get(choice, "o")


def marker_size(size, code, st):
    """Marker size giving every shape the same visual weight as a circle of `size`."""
    return size * (st.get("square_scale", 1.414) if code == "s" else EQUAL_AREA.get(code, 1.0))


Z_POINTS = 3      # individual values
Z_SUMMARY = 4     # means, medians, and error bars are drawn over the points


def _style_boxes(bp, colors, alpha, lw, thin, ms, fliers):
    """Box plot colors. The box fill sits under the points; the median, whiskers, and caps
    sit over them so they stay visible."""
    for i, c in enumerate(colors):
        bp["boxes"][i].set(facecolor=to_rgba(c, alpha), edgecolor=c, linewidth=lw, zorder=1)
        bp["medians"][i].set(color=c, linewidth=lw, zorder=Z_SUMMARY)
        for part in ("whiskers", "caps"):
            for line in bp[part][2 * i:2 * i + 2]:
                line.set(color=c, linewidth=lw, zorder=Z_SUMMARY)
        if fliers and i < len(bp["fliers"]):
            bp["fliers"][i].set(marker="o", markersize=ms * 0.8, markerfacecolor="none",
                                markeredgecolor=c, markeredgewidth=thin, zorder=Z_POINTS)


def _scatter(ax, x, y, color, code, size, filled, st, z):
    """Points of one shape, filled or open, sized for equal visual weight."""
    sz = marker_size(size, code, st)
    if filled:
        ax.scatter(x, y, s=sz ** 2, marker=code, facecolors=[color], edgecolors="none",
                   zorder=z, clip_on=False)
    else:
        ax.scatter(x, y, s=sz ** 2, marker=code, facecolors="none", edgecolors=[color],
                   linewidths=st["marker_edge"], zorder=z, clip_on=False)

EXPORT_FORMATS = {
    ".svg": "SVG for Illustrator (*.svg)",
    ".pdf": "PDF (*.pdf)",
    ".eps": "EPS (*.eps)",
    ".png": "PNG, 600 dpi (*.png)",
    ".tif": "TIFF, 600 dpi (*.tif)",
}

DASHED = (0, (3.0, 2.0))          # 2.16, 1.44 pt at 0.72 pt (violin median in the export)
ERROR_STYLES = ["Solid", "Dashed"]


def _style_errorbar(container, opts):
    """Dashed error bars (Prism 11 option). Caps stay solid."""
    if getattr(opts, "error_style", "Solid") == "Dashed":
        for lines in container[2]:
            lines.set_linestyle(DASHED)
    return container
DOTTED = (0, (0.0139, 2.0))       # round dots 1.44 pt apart at 0.72 pt (violin quartiles)
BAND_EDGE = (0, (3.0, 2.0))       # 1.08, 0.72 pt at 0.36 pt (XY band edges)
REF_DOTTED = (0, (0.007, 2.0))    # 2.88 pt dot spacing at 1.44 pt (XY reference line)


@dataclass
class ColumnPlotOptions:
    plot_type: str = "Scatter dot plot"
    ref_x: str = ""                         # histograms have a numeric X axis
    hist_bin_width: Optional[float] = None  # None: chosen automatically
    hist_bin_start: Optional[float] = None
    hist_values: str = "Count"
    hist_style: str = "Bars"
    error: str = "Mean with SEM"
    title: str = ""
    x_label: str = ""
    y_label: str = "Value"
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    width_in: float = AXIS_LENGTH_IN
    height_in: float = AXIS_LENGTH_IN
    font_size: float = DEFAULT_FONT_SIZE
    bold: bool = DEFAULT_BOLD
    style: str = DEFAULT_STYLE
    palette: str = DEFAULT_PALETTE
    point_size: float = 4.1          # Prism export: 4.08 pt circles
    marker: str = "Circle"
    marker_fill: str = "Filled"
    error_style: str = "Solid"
    show_points: bool = True
    point_layout: str = "Swarm"
    point_color: str = "Group color"
    bar_style: str = "Filled"
    whiskers: str = "Min to max"
    annotation: str = "Stars"
    show_ns: bool = True
    rotate_labels: bool = False
    frame: str = "Open"
    ref_y: str = ""
    log_y: bool = False
    orientation: str = "Vertical"


@dataclass
class VolcanoOptions:
    """Volcano plot settings, shared by grouped and XY tables."""
    fc_cutoff: float = 1.0            # |log2 fold change| at or above this counts as changed
    p_cutoff: float = 0.05
    use_fdr: bool = False             # threshold on Benjamini-Hochberg adjusted P values
    test: str = "Welch's t test"      # grouped tables only
    already_log: bool = False         # grouped tables only: values are log2 already
    p_input: str = "P value"          # XY tables only: Y holds P values or -log10(P)
    label_top: int = 10
    label_names: str = ""
    up_color: str = "#C55C55"
    down_color: str = "#1355AA"
    ns_color: str = "#A6A6A6"
    show_counts: bool = True


@dataclass
class GroupedPlotOptions:
    plot_type: str = "Grouped bars"
    heat_cmap: str = "Viridis"
    heat_values: bool = False
    heat_shape: str = "Squares"
    circle_color: str = "Same as size"
    circle_color_label: str = ""
    arrangement: str = "Interleaved"
    orientation: str = "Vertical"
    whiskers: str = "Min to max"
    right_series: tuple = ()          # data set names drawn on the right Y axis
    right_label: str = ""
    right_min: Optional[float] = None
    right_max: Optional[float] = None
    volcano: VolcanoOptions = None
    view3d: "View3DOptions" = None
    error: str = "SEM"
    title: str = ""
    x_label: str = ""
    y_label: str = "Value"
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    width_in: float = AXIS_LENGTH_IN
    height_in: float = AXIS_LENGTH_IN
    font_size: float = DEFAULT_FONT_SIZE
    bold: bool = DEFAULT_BOLD
    style: str = DEFAULT_STYLE
    palette: str = DEFAULT_PALETTE
    point_size: float = 3.0
    marker: str = "Circle"
    marker_fill: str = "Filled"
    error_style: str = "Solid"
    show_points: bool = False
    bar_style: str = "Filled"
    annotation: str = "Stars"
    show_ns: bool = True
    rotate_labels: bool = False
    legend: str = "Inside upper left"
    frame: str = "Open"
    ref_y: str = ""
    log_y: bool = False


@dataclass
class XYPlotOptions:
    plot_type: str = "Points and lines"
    right_series: tuple = ()
    right_label: str = ""
    right_min: Optional[float] = None
    right_max: Optional[float] = None
    volcano: VolcanoOptions = None
    error: str = "SEM"
    error_display: str = "Shaded band"
    title: str = ""
    x_label: str = "X"
    y_label: str = "Y"
    x_min: Optional[float] = None
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    width_in: float = AXIS_LENGTH_IN
    height_in: float = AXIS_LENGTH_IN
    font_size: float = DEFAULT_FONT_SIZE
    bold: bool = DEFAULT_BOLD
    style: str = DEFAULT_STYLE
    palette: str = DEFAULT_PALETTE
    point_size: float = 2.0
    marker: str = VARY_MARKERS
    marker_fill: str = "Filled"
    error_style: str = "Solid"
    log_x: bool = False
    connect: bool = True
    legend: str = "Inside upper left"
    fit_model: str = "None"
    frame: str = "Box"
    ref_x: str = ""
    ref_y: str = ""
    log_y: bool = False


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

FIT_PAD_IN = 0.05
NICE_STEPS = [1, 2, 5, 10]   # Prism favors few round intervals (0-150 by 50)


def _empty_state(fig, message, opts=None):
    w = opts.width_in if opts else AXIS_LENGTH_IN
    h = opts.height_in if opts else AXIS_LENGTH_IN
    fig.set_size_inches(w + 1.0, h + 0.6, forward=False)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.text(0.5, 0.5, message, ha="center", va="center", wrap=True, fontweight="normal",
            fontsize=10, color="#595959", transform=ax.transAxes)


def _new_axes(fig, opts):
    """Axes whose plotting area is exactly width_in x height_in (Prism's axis lengths)."""
    w, h = opts.width_in, opts.height_in
    fig.set_size_inches(w + 2.4, h + 1.8, forward=False)
    W, H = fig.get_size_inches()
    return fig.add_axes([1.4 / W, 1.0 / H, w / W, h / H])


def _frame(ax, opts, right_axis=False):
    box = opts.frame == "Box"
    ax.spines["top"].set_visible(box)
    ax.spines["right"].set_visible(box or right_axis)
    ax.tick_params(top=box, right=box and not right_axis, labeltop=False, labelright=False)


class _Flip:
    """Axes stand-in for horizontal graphs: renderers draw as if vertical and every call is
    passed on with X and Y swapped. Groups run top to bottom, values left to right."""

    def __init__(self, ax):
        self._ax = ax

    def __getattr__(self, name):
        return getattr(self._ax, name)

    @property
    def xaxis(self):
        return self._ax.yaxis

    @property
    def yaxis(self):
        return self._ax.xaxis

    def set_xlim(self, lo, hi):
        return self._ax.set_ylim(hi, lo)   # first group at the top

    def set_ylim(self, *a, **k):
        return self._ax.set_xlim(*a, **k)

    def get_ylim(self):
        return self._ax.get_xlim()

    def get_xlim(self):
        lo, hi = self._ax.get_ylim()
        return hi, lo

    def set_xticks(self, *a, **k):
        return self._ax.set_yticks(*a, **k)

    def set_yticks(self, *a, **k):
        return self._ax.set_xticks(*a, **k)

    def set_xticklabels(self, labels, **_k):   # angled names are not needed sideways
        return self._ax.set_yticklabels(labels)

    def set_xlabel(self, *a, **k):
        return self._ax.set_ylabel(*a, **k)

    def set_ylabel(self, *a, **k):
        return self._ax.set_xlabel(*a, **k)

    def bar(self, x, height, bottom=0, width=0.8, **k):
        return self._ax.barh(x, height, left=bottom, height=width, **k)

    def errorbar(self, x, y, yerr=None, **k):
        return self._ax.errorbar(y, x, xerr=yerr, **k)

    def hlines(self, y, xmin, xmax, **k):
        return self._ax.vlines(y, xmin, xmax, **k)

    def vlines(self, x, ymin, ymax, **k):
        return self._ax.hlines(x, ymin, ymax, **k)

    def plot(self, xs, ys, *a, **k):
        return self._ax.plot(ys, xs, *a, **k)

    def scatter(self, x, y, **k):
        return self._ax.scatter(y, x, **k)

    def fill_betweenx(self, y, x1, x2, **k):
        return self._ax.fill_between(y, x1, x2, **k)

    def fill_between(self, x, y1, y2=0, **k):
        return self._ax.fill_betweenx(x, y1, y2, **k)

    def axhline(self, y, **k):
        return self._ax.axvline(y, **k)

    def axvline(self, x, **k):
        return self._ax.axhline(x, **k)

    def boxplot(self, data, **k):
        return self._ax.boxplot(data, orientation="horizontal", **k)

    def text(self, x, y, s, ha="center", va="baseline", **k):
        # Bracket labels turn with the brackets and sit to their right
        return self._ax.text(y, x, s, rotation=270, ha="left" if va == "bottom" else "center",
                             va="center", rotation_mode="anchor", **k)


def _orient(ax, opts):
    """(axes to draw on, horizontal?) for the graph's orientation setting."""
    flip = getattr(opts, "orientation", "Vertical") == "Horizontal"
    return (_Flip(ax) if flip else ax), flip


def _real(ax):
    return ax._ax if isinstance(ax, _Flip) else ax


def nice_range(lo, hi, zero=True, headroom=1.1):
    """Axis limits that end on major ticks, with about 10% headroom above the data."""
    if not (math.isfinite(lo) and math.isfinite(hi)):
        return 0.0, 1.0
    if zero and lo >= 0:
        lo = 0.0
    top = hi + (hi - lo) * (headroom - 1.0)
    if top <= lo:
        top = lo + (abs(lo) or 1.0)
    ticks = MaxNLocator(nbins=5, steps=NICE_STEPS).tick_values(lo, top)
    tol = (top - lo) * 1e-9
    t0 = max([t for t in ticks if t <= lo + tol], default=ticks[0])
    t1 = min([t for t in ticks if t >= top - tol], default=ticks[-1])
    return float(t0), float(t1)


def _set_axis(ax, which, lo, hi, user_min, user_max, zero=True, headroom=1.1):
    t0, t1 = nice_range(lo, hi, zero, headroom)
    lo_final = user_min if user_min is not None else t0
    hi_final = user_max if user_max is not None else t1
    if hi_final <= lo_final:
        hi_final = lo_final + 1.0
    axis = ax.yaxis if which == "y" else ax.xaxis
    axis.set_major_locator(MaxNLocator(nbins=5, steps=NICE_STEPS))
    (ax.set_ylim if which == "y" else ax.set_xlim)(lo_final, hi_final)
    return lo_final, hi_final


def _parse_values(text):
    out = []
    for tok in re.split(r"[,;\s]+", text or ""):
        try:
            out.append(float(tok))
        except ValueError:
            continue
    return out


def _log10_pos(values):
    """log10 of positive values; NaN for zero, negative, and missing values."""
    v = np.asarray(values, float)
    out = np.full(v.shape, np.nan)
    ok = np.isfinite(v) & (v > 0)
    out[ok] = np.log10(v[ok])
    return out


def _log_label(t):
    value = 10.0 ** t
    return f"{value:g}" if 1e-4 <= value < 1e5 else f"$10^{{{int(round(t))}}}$"


def _log_summary(values, choice):
    """Center and error distances on a log10 axis, from statistics on the original values
    (so 'Mean with SD' is still the ordinary mean and SD). A lower bar at or below zero
    reaches the bottom of the axis (returned as infinity)."""
    c, lo, hi = summary_values(values, choice)
    if not (c > 0):
        return math.nan, 0.0, 0.0
    lc = math.log10(c)
    lower = (lc - math.log10(c - lo)) if (lo > 0 and c - lo > 0) else (math.inf if lo > 0 else 0.0)
    upper = math.log10(c + hi) - lc if hi > 0 else 0.0
    return lc, lower, upper


def _log_axis(ax, lo, hi, user_min, user_max):
    """Log scale drawn in log10 units: limits on whole decades, labels show real values."""
    if not (math.isfinite(lo) and math.isfinite(hi)):
        lo, hi = 0.0, 1.0
    y0, y1 = math.floor(lo + 1e-9), math.ceil(hi - 1e-9)
    if user_min is not None and user_min > 0:
        y0 = math.log10(user_min)
    if user_max is not None and user_max > 0:
        y1 = math.log10(user_max)
    if y1 <= y0:
        y1 = y0 + 1
    ax.set_ylim(y0, y1)
    majors = list(range(math.ceil(y0 - 1e-9), math.floor(y1 + 1e-9) + 1))
    ax.yaxis.set_major_locator(FixedLocator(majors))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda t, _pos: _log_label(t)))
    minors = [n + math.log10(m) for n in range(math.floor(y0) - 1, math.ceil(y1) + 1)
              for m in range(2, 10) if y0 <= n + math.log10(m) <= y1]
    ax.yaxis.set_minor_locator(FixedLocator(minors))
    ax.yaxis.set_minor_formatter(NullFormatter())
    return y0, y1


def _style_minor(ax, st, axis="y"):
    ax.tick_params(axis=axis, which="minor", length=st["tick_len"] * 0.55, width=st["axis_line"],
                   direction=st["tick_dir"])


def _reference_lines(ax, opts, st, log_y=False):
    w = st["ref_line_width"]
    for y in _parse_values(getattr(opts, "ref_y", "")):
        if log_y:
            if y <= 0:
                continue
            y = math.log10(y)
        ax.axhline(y, color="black", linewidth=w, linestyle=REF_DOTTED, dash_capstyle="round",
                   zorder=0.5)
    for x in _parse_values(getattr(opts, "ref_x", "")):
        ax.axvline(x, color="black", linewidth=w, linestyle=REF_DOTTED, dash_capstyle="round",
                   zorder=0.5)


def _legend(ax, handles, labels, opts, st, ncol=None):
    pos = opts.legend
    if pos == "None" or not handles:
        return
    fs = opts.font_size + st["title_extra"]

    def swatch(legend, orig_handle, xdescent, ydescent, width, height, fontsize):
        h = 3.2   # Prism legend swatches are 15.3 x 3.2 pt
        return Rectangle((-xdescent, -ydescent + (height - h) / 2), width, h)

    kw = dict(frameon=False, handlelength=15.3 / fs, handletextpad=8.6 / fs, labelspacing=0.55,
              borderaxespad=0.3, borderpad=0.2, columnspacing=1.5,
              handler_map={Rectangle: HandlerPatch(patch_func=swatch)})
    if pos == "Inside upper right":
        ax.legend(handles, labels, loc="upper right", **kw)
    elif pos == "Above plot":
        ax.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 1.02),
                  ncol=ncol or min(2, len(handles)), **kw)
    elif pos == "Right of plot":
        ax.legend(handles, labels, loc="upper left", bbox_to_anchor=(1.02, 1.0), **kw)
    else:
        ax.legend(handles, labels, loc="upper left", **kw)


def _extent(texts):
    return [t.get_window_extent() for t in texts if t.get_visible() and t.get_text()]


def _finish(fig, ax, opts, st, side=(), twins=()):
    """Place axis titles and size the figure around the exact plotting area.

    side: (axes, gap_in, width_in) placed to the right of the plot, full height (color bars).
    twins: axes that share the plotting area (a right Y axis).
    """
    ax = _real(ax)
    side = list(side) + [(t, None, None) for t in twins]
    if opts.title:
        y0, y1 = ax.get_ylim()
        top = getattr(ax, "stel_bracket_top", -math.inf)
        frac = max(1.0, (top - y0) / (y1 - y0)) if math.isfinite(top) else 1.0
        ax.set_title(opts.title, y=frac, pad=6)
    w, h = opts.width_in, opts.height_in
    dpi = fig.dpi
    ax.xaxis.labelpad = st["labelpad_x"]
    ax.yaxis.labelpad = st["labelpad_y"]
    fixed = st.get("fixed_title_distances")
    if fixed:
        fig.draw_without_rendering()
        axbox = ax.get_window_extent()
        xt = _extent(ax.get_xticklabels())
        need_x = ((axbox.y0 - min(b.y0 for b in xt)) / dpi + 0.06) if xt else 0.0
        ax.xaxis.set_label_coords(0.5, -max(fixed[0], need_x) / h)
        yt = _extent(ax.get_yticklabels())
        need_y = ((axbox.x0 - min(b.x0 for b in yt)) / dpi + 0.06) if yt else 0.0
        ax.yaxis.set_label_coords(-max(fixed[1], need_y) / w, 0.5)
    fig.draw_without_rendering()
    tight = ax.get_tightbbox()
    for extra, _gap, _width in side:
        tight = Bbox.union([tight, extra.get_tightbbox()])
    axbox = ax.get_window_extent()
    left = max((axbox.x0 - tight.x0) / dpi, 0) + FIT_PAD_IN
    right = max((tight.x1 - axbox.x1) / dpi, 0) + FIT_PAD_IN
    bottom = max((axbox.y0 - tight.y0) / dpi, 0) + FIT_PAD_IN
    top = max((tight.y1 - axbox.y1) / dpi, 0) + FIT_PAD_IN
    W, H = left + w + right, bottom + h + top
    fig.set_size_inches(W, H, forward=False)
    ax.set_position([left / W, bottom / H, w / W, h / H])
    for extra, gap, width in side:
        if gap is None:
            extra.set_position([left / W, bottom / H, w / W, h / H])
        else:
            extra.set_position([(left + w + gap) / W, bottom / H, width / W, h / H])


def _swarm_offsets(values, bin_height, step, max_half_width):
    """Spread overlapping points sideways, similar to Prism scatter plots."""
    if values.size == 0:
        return np.zeros(0)
    order = np.argsort(values, kind="stable")
    v = values[order]
    offsets = np.zeros(v.size)
    start = 0
    while start < v.size:
        end = start
        while end + 1 < v.size and v[end + 1] - v[start] < bin_height:
            end += 1
        m = end - start + 1
        offs = (np.arange(m) - (m - 1) / 2.0) * step
        widest = np.max(np.abs(offs)) if m > 1 else 0.0
        if widest > max_half_width:
            offs *= max_half_width / widest
        offsets[start:end + 1] = offs
        start = end + 1
    out = np.empty_like(offsets)
    out[order] = offsets
    return out


def _jitter_offsets(values, max_half_width, seed):
    rng = np.random.default_rng(seed)
    return rng.uniform(-max_half_width, max_half_width, values.size)


def violin_shape(v, width=BAR_WIDTH):
    """Violin outline: y grid and half-width from a Gaussian KDE (Scott's bandwidth),
    truncated at the data range. Returns None when a KDE cannot be formed."""
    v = finite(v)
    if v.size < 2 or np.ptp(v) == 0:
        return None
    try:
        kde = gaussian_kde(v)
    except (ValueError, np.linalg.LinAlgError):
        return None
    ys = np.linspace(v.min(), v.max(), 256)
    dens = kde(ys)
    return ys, (width / 2) * dens / dens.max()


def violin_point_offsets(v, shape, layout, bin_height, step, seed, fill=0.92):
    """Sideways offsets that keep points inside the violin and follow its shape.

    Each point's spread is limited by the violin's half-width at that point's value, so
    points crowd where the distribution is wide and thin out in the tails (a sina layout).
    Jitter places points at random within that width; Swarm spaces them evenly.
    """
    ys, half = shape
    rng = np.random.default_rng(seed)
    width = fill * np.interp(v, ys, half)
    if layout == "Jitter":
        return rng.uniform(-1.0, 1.0, v.size) * width
    order = np.argsort(v, kind="stable")
    vs = v[order]
    offs = np.zeros(v.size)
    start = 0
    while start < v.size:
        end = start
        while end + 1 < v.size and vs[end + 1] - vs[start] < bin_height:
            end += 1
        m = end - start + 1
        if m > 1:
            w = fill * float(np.interp(vs[start:end + 1].mean(), ys, half))
            spread = min((m - 1) * step / 2.0, w)
            # Shuffle positions within the bin so sorted values don't form diagonal stripes
            offs[start:end + 1] = rng.permutation(np.linspace(-spread, spread, m))
        start = end + 1
    out = np.empty_like(offs)
    out[order] = offs
    # A bin spans a small range of values; keep every point within its own violin width
    return np.clip(out, -width, width)


def _assign_levels(comparisons):
    """Stack brackets so overlapping comparisons sit on different levels."""
    levels, placed = [], []
    for comp in sorted(comparisons, key=lambda c: (abs(c.j - c.i), min(c.i, c.j))):
        lo, hi = sorted((comp.i, comp.j))
        level = 0
        while True:
            if level == len(levels):
                levels.append([])
            if all(hi < a or lo > b for a, b in levels[level]):
                levels[level].append((lo, hi))
                placed.append((comp, level, lo, hi))
                break
            level += 1
    return placed, len(levels)


# ---------------------------------------------------------------------------
# Significance brackets (Prism style)
# ---------------------------------------------------------------------------

def _bracket_layout(comps, xpos_of, tops, per_pt, x_per_pt, fs):
    """Lay out brackets the way Prism draws them.

    All first-level brackets share one height above the tallest data; each leg
    drops to just above its own column (or above a lower bracket's label); ends
    that meet at a shared column are pulled apart. Returns (segments, texts, top).
    """
    placed, n_levels = _assign_levels(comps)
    if not placed:
        return [], [], -math.inf
    gap0, step = 1.4 * fs, 2.6 * fs
    text_off, text_h, leg_gap, clear, min_leg, shrink = 0.75 * fs, 0.75 * fs, 0.7 * fs, 1.4, 1.5, 2.9
    spanned = {idx for _, _, lo, hi in placed for idx in range(lo, hi + 1) if idx in tops}
    base = max(tops[i] for i in spanned) + gap0 * per_pt
    ends = Counter((level, idx) for _, level, lo, hi in placed for idx in (lo, hi))
    segments, texts, drawn = [], [], []
    for comp, level, lo, hi in sorted(placed, key=lambda t: t[1]):
        y = base + level * step * per_pt
        x1, x2 = xpos_of(lo), xpos_of(hi)
        if ends[(level, lo)] > 1:
            x1 += shrink * x_per_pt
        if ends[(level, hi)] > 1:
            x2 -= shrink * x_per_pt

        def leg_bottom(idx):
            ob = tops.get(idx, base) + leg_gap * per_pt
            for l2, h2, y2 in drawn:
                if l2 <= idx <= h2:
                    ob = max(ob, y2 + (text_off + text_h + clear) * per_pt)
            return min(ob, y - min_leg * per_pt)

        segments.append(([x1, x1, x2, x2], [leg_bottom(lo), y, y, leg_bottom(hi)]))
        texts.append(((x1 + x2) / 2, y, comp))
        drawn.append((lo, hi, y))
    top = base + (n_levels - 1) * step * per_pt + (text_off + text_h) * per_pt
    return segments, texts, top


def _draw_brackets(ax, segments, texts, opts, st, per_pt):
    fs = opts.font_size
    heavy = st["heavy_stars"]
    for xs, ys in segments:
        ax.plot(xs, ys, color="black", linewidth=st["bracket_line"], solid_capstyle="round",
                solid_joinstyle="miter", clip_on=False, zorder=6)
    for x, y, comp in texts:
        if opts.annotation == "Stars" and comp.summary != "ns":
            n = len(comp.summary)
            if heavy:
                ax.text(x, y + 0.75 * fs * per_pt, STAR_GLYPH * n, ha="center", va="baseline",
                        fontsize=fs, fontfamily=star_font(), fontweight="normal",
                        clip_on=False, zorder=6)
            else:
                ax.text(x, y - 0.28 * fs * per_pt, "*" * n, ha="center", va="baseline",
                        fontsize=fs, clip_on=False, zorder=6)
        else:
            text = comp.summary if opts.annotation == "Stars" else format_p(comp.p)
            ax.text(x, y + 0.75 * fs * per_pt if heavy else y + 1.5 * per_pt, text,
                    ha="center", va="baseline" if heavy else "bottom",
                    fontsize=fs if opts.annotation == "Stars" else fs - 0.5,
                    clip_on=False, zorder=6)


def _place_brackets(ax, comps_by_family, opts, st, y0, y1, ax_h_pt, x_per_pt):
    """Lay out every bracket family; with a box frame, raise the Y axis to fit them."""
    def layout(lo, hi):
        per_pt = (hi - lo) / ax_h_pt
        out, top = [], -math.inf
        for comps, xpos_of, tops in comps_by_family:
            seg, txt, t = _bracket_layout(comps, xpos_of, tops, per_pt, x_per_pt, opts.font_size)
            out.append((seg, txt))
            top = max(top, t)
        return out, top, per_pt

    out, top, per_pt = layout(y0, y1)
    if opts.frame == "Box" and top > y1 and opts.y_max is None:
        y0, y1 = nice_range(y0, top, zero=False, headroom=1.0)
        ax.set_ylim(y0, y1)
        out, top, per_pt = layout(y0, y1)
    for seg, txt in out:
        _draw_brackets(ax, seg, txt, opts, st, per_pt)
    ax.stel_bracket_top = top
    return y0, y1


# ---------------------------------------------------------------------------
# Column graphs
# ---------------------------------------------------------------------------

def render_column(fig, groups, opts, stats_result=None):
    """Draw a column graph. groups: list of (name, values)."""
    fig.clear()
    fig.stel_notes = []
    fig.stel_frequency = None
    st = apply_lab_style(opts.font_size, opts.bold, opts.style)
    if opts.plot_type == HISTOGRAM:
        return _render_histogram(fig, groups, opts, st)
    data = [(name, finite(values)) for name, values in groups]
    raw = [np.asarray(values, float) for (name, values), (_, v) in zip(groups, data) if v.size > 0]
    data = [(name, v) for name, v in data if v.size > 0]
    log_y = bool(getattr(opts, "log_y", False))
    log_summ = None
    if log_y and data:
        kept, kept_raw, log_summ, dropped = [], [], [], 0
        for (name, v), a in zip(data, raw):
            pos = v[v > 0]
            dropped += int(v.size - pos.size)
            if pos.size:
                log_summ.append(_log_summary(pos, opts.error))
                kept.append((name, np.log10(pos)))
                kept_raw.append(_log10_pos(a))
        data, raw = kept, kept_raw
        if dropped:
            fig.stel_notes.append(f"{dropped} value(s) at or below zero are not shown on the log axis; "
                                  "the statistics still include them.")
    if not data:
        _empty_state(fig, "No values above zero to show on a log axis." if log_y else
                     "Type or paste values into the grid.\nEach column is one group.", opts)
        return None

    ax = _new_axes(fig, opts)
    _frame(ax, opts)
    ax, flip = _orient(ax, opts)
    k = len(data)
    xpos = np.arange(k)
    colors = palette_colors(opts.palette, k)
    ms = opts.point_size
    pt = opts.plot_type
    alpha = st["fill_alpha"]
    lw, thin = st["data_line"], st["thin"]
    bw = st["bar_width"]
    filled = opts.marker_fill != "Open"

    x_lo, x_hi = -COLUMN_MARGIN, k - 1 + COLUMN_MARGIN
    ax.set_xlim(x_lo, x_hi)
    # Lengths of the group axis and the value axis (swapped when the graph is horizontal)
    ax_w_pt, ax_h_pt = opts.width_in * 72, opts.height_in * 72
    if flip:
        ax_w_pt, ax_h_pt = ax_h_pt, ax_w_pt
    spacing_pt = ax_w_pt / (x_hi - x_lo)
    x_per_pt = 1.0 / spacing_pt
    capsize = 0.5 * COLUMN_CAP * bw * spacing_pt

    summ = log_summ if log_y else [summary_values(v, opts.error) for _, v in data]
    centers = np.array([s[0] for s in summ])
    lower = np.array([s[1] for s in summ])
    upper = np.array([s[2] for s in summ])
    show_points = opts.show_points or pt in ("Scatter dot plot", "Before-after (matched rows)")

    col_tops = {}
    for i, (_, v) in enumerate(data):
        top = float(v.max()) if (show_points or pt in ("Box plot", "Violin plot")) else -math.inf
        if pt in ("Scatter dot plot", "Bar with points"):
            top = max(top, centers[i] + upper[i])
        col_tops[i] = top
    all_vals = np.concatenate([v for _, v in data])
    lows = [float(all_vals.min())]
    if pt in ("Scatter dot plot", "Bar with points"):
        bottoms = (centers - lower)[np.isfinite(centers - lower)]
        if bottoms.size:
            lows.append(float(bottoms.min()))
    if log_y:
        y0, y1 = _log_axis(ax, min(lows), max(col_tops.values()), opts.y_min, opts.y_max)
        lower = np.where(np.isfinite(lower), lower, centers - (y0 - 1.0))   # reach the axis bottom
    else:
        # Bars and dot plots start at zero like Prism; distributions use the data range
        y0, y1 = _set_axis(ax, "y", min(lows), max(col_tops.values()), opts.y_min, opts.y_max,
                           zero=pt not in ("Box plot", "Violin plot"))
    base = y0 if log_y else 0.0   # a log axis has no zero, so bars start at its bottom

    comps = []
    if stats_result is not None and stats_result.ok and opts.annotation != "None":
        comps = [c for c in stats_result.comparisons if opts.show_ns or c.p < 0.05]
    if comps:
        y0, y1 = _place_brackets(ax, [(comps, lambda i: float(i), col_tops)], opts, st,
                                 y0, y1, ax_h_pt, x_per_pt)
    y_per_pt = (y1 - y0) / ax_h_pt
    max_half = 0.3 if pt == "Scatter dot plot" else 0.22

    def draw_points(i, v, color, z):
        code = marker_for(opts.marker, i, st)
        size = marker_size(ms, code, st)
        if opts.point_layout == "Jitter":
            offs = _jitter_offsets(v, max_half * 0.8, seed=1000 + i)
        else:
            offs = _swarm_offsets(v, size * y_per_pt, 1.41 * size * x_per_pt, max_half)
        face = "black" if opts.point_color == "Black" else color
        _scatter(ax, i + offs, v, face, code, ms, filled, st, z)

    def draw_error(i, color, z):
        if lower[i] > 0 or upper[i] > 0:
            _style_errorbar(ax.errorbar([i], [centers[i]], yerr=[[lower[i]], [upper[i]]], fmt="none",
                                        ecolor=color, elinewidth=lw, capsize=capsize, capthick=lw,
                                        zorder=z), opts)

    if pt == "Scatter dot plot":
        for i, ((_, v), c) in enumerate(zip(data, colors)):
            draw_points(i, v, c, 3)
            ax.hlines(centers[i], i - bw / 2, i + bw / 2, colors=[c], linewidth=lw,
                      zorder=4)
            draw_error(i, c, 4)

    elif pt == "Bar with points":
        for i, ((_, v), c) in enumerate(zip(data, colors)):
            if opts.bar_style == "Filled":
                ax.bar(i, centers[i] - base, bottom=base, width=bw, facecolor=to_rgba(c, alpha),
                       edgecolor=c, linewidth=thin, zorder=1)
            else:
                ax.bar(i, centers[i] - base, bottom=base, width=bw, facecolor="none", edgecolor=c,
                       linewidth=lw, zorder=1)
            draw_error(i, c, Z_SUMMARY)
            if opts.show_points:
                draw_points(i, v, c, 3)

    elif pt == "Box plot":
        tukey = opts.whiskers.startswith("Tukey")
        bp = ax.boxplot([v for _, v in data], positions=xpos, widths=bw,
                        whis=1.5 if tukey else (0, 100),
                        showfliers=tukey and not opts.show_points,
                        patch_artist=True, manage_ticks=False)
        _style_boxes(bp, colors, alpha, lw, thin, ms, tukey and not opts.show_points)
        if opts.show_points:
            for i, ((_, v), c) in enumerate(zip(data, colors)):
                draw_points(i, v, c, 3)

    elif pt == "Violin plot":
        for i, ((_, v), c) in enumerate(zip(data, colors)):
            q1, med, q3 = np.percentile(v, [25, 50, 75])
            shape = violin_shape(v, bw)
            if shape is not None:
                ys, half = shape
                ax.fill_betweenx(ys, i - half, i + half, facecolor=to_rgba(c, alpha),
                                 edgecolor="none", zorder=1)
                ax.plot(np.r_[i - half, (i + half)[::-1], i - half[0]],
                        np.r_[ys, ys[::-1], ys[0]], color=c, linewidth=thin, zorder=2)
                width_at = lambda q: float(np.interp(q, ys, half))
                ax.plot([i - width_at(med), i + width_at(med)], [med, med], color=c,
                        linewidth=lw, linestyle=DASHED, zorder=3)
                for q in (q1, q3):
                    ax.plot([i - width_at(q), i + width_at(q)], [q, q], color=c, linewidth=lw,
                            linestyle=DOTTED, dash_capstyle="round", zorder=3)
            if opts.show_points:
                if shape is None:
                    draw_points(i, v, c, 2.5)
                else:
                    code = marker_for(opts.marker, i, st)
                    size = marker_size(ms, code, st)
                    offs = violin_point_offsets(v, shape, opts.point_layout, size * y_per_pt,
                                                1.41 * size * x_per_pt, seed=1000 + i)
                    face = "black" if opts.point_color == "Black" else c
                    # Points sit under the median and quartile lines so those stay visible
                    _scatter(ax, i + offs, v, face, code, ms, filled, st, 2.5)

    elif pt == "Before-after (matched rows)":
        n_rows = max(a.size for a in raw)
        Y = np.full((n_rows, k), np.nan)
        for j, a in enumerate(raw):
            Y[:a.size, j] = a
        for r in range(n_rows):
            ok = np.isfinite(Y[r])
            if ok.sum() >= 2:
                ax.plot(xpos[ok], Y[r, ok], color="#8C8C8C", linewidth=thin, zorder=2)
        for i, c in enumerate(colors):
            col = Y[:, i][np.isfinite(Y[:, i])]
            face = "black" if opts.point_color == "Black" else c
            _scatter(ax, np.full(col.size, i), col, face, marker_for(opts.marker, i, st), ms,
                     filled, st, 3)

    _reference_lines(ax, opts, st, log_y=log_y)
    ax.set_xticks(xpos)
    if opts.rotate_labels:
        ax.set_xticklabels([n for n, _ in data], rotation=45, ha="right", rotation_mode="anchor")
    else:
        ax.set_xticklabels([n for n, _ in data])
    ax.set_ylabel(opts.y_label)
    if opts.x_label:
        ax.set_xlabel(opts.x_label)
    if flip:
        _real(ax).tick_params(axis="y", pad=3)
    _finish(fig, ax, opts, st)
    if log_y:
        _style_minor(_real(ax), st, "x" if flip else "y")
    return _real(ax)


# ---------------------------------------------------------------------------
# Frequency distributions (histograms)
# ---------------------------------------------------------------------------

def _nice_width(w):
    exp = math.floor(math.log10(w))
    f = w / 10 ** exp
    for n in (1, 2, 2.5, 5, 10):
        if f <= n + 1e-9:
            return n * 10 ** exp
    return 10 ** (exp + 1)


def frequency_table(groups, bin_width=None, bin_start=None, values="Count"):
    """Bins shared by every column, and the count in each bin.

    Bins include their lower edge and exclude the upper edge, except the last bin, which
    includes both. With no bin width, a round width is chosen with the Freedman-Diaconis
    rule (Sturges' rule if the interquartile range is zero).
    """
    data = [(name, finite(v)) for name, v in groups]
    data = [(name, v) for name, v in data if v.size]
    if not data:
        return None
    allv = np.concatenate([v for _, v in data])
    lo, hi = float(allv.min()), float(allv.max())
    auto = bin_width is None or not bin_width > 0
    if auto:
        q1, q3 = np.percentile(allv, [25, 75])
        n = allv.size
        w = 2 * (q3 - q1) / n ** (1 / 3) if q3 > q1 else (hi - lo) / max(1, math.ceil(math.log2(n) + 1))
        bin_width = _nice_width(w) if w > 0 else 1.0
    start = math.floor(lo / bin_width) * bin_width if bin_start is None else float(bin_start)
    n_bins = max(1, int(math.ceil((hi - start) / bin_width - 1e-9)))
    if start + n_bins * bin_width < hi:
        n_bins += 1
    if n_bins > 2000:
        raise ValueError(f"A bin width of {bin_width:g} makes {n_bins} bins. Choose a larger width.")
    edges = start + bin_width * np.arange(n_bins + 1)
    series = []
    for name, v in data:
        counts, _ = np.histogram(v, edges)
        n = v.size
        shown = (counts * 100.0 / n if values == "Percent" else
                 counts / n if values == "Fraction" else counts.astype(float))
        series.append((name, counts, shown, n, int(np.sum(v < start))))
    return {"edges": edges, "width": float(bin_width), "auto": auto, "series": series,
            "values": values}


def _edge(v):
    """Bin edges print plainly (3, 2.5, 0.125) without trailing zeros or float noise."""
    return format(float(f"{v:.10g}"), "g")


def frequency_text(table):
    """The frequency table as aligned text for the results panel."""
    from .prism_format import num
    edges = table["edges"]
    header = ["Bin start", "Bin end", "Bin center"] + [name for name, *_ in table["series"]]
    rows = [header]
    for b in range(len(edges) - 1):
        row = [_edge(edges[b]), _edge(edges[b + 1]), _edge((edges[b] + edges[b + 1]) / 2)]
        for _name, counts, shown, _n, _below in table["series"]:
            row.append(str(int(counts[b])) if table["values"] == "Count" else num(shown[b]))
        rows.append(row)
    widths = [max(len(r[c]) for r in rows) for c in range(len(header))]
    lines = ["  ".join(v.rjust(wd) if i else v.ljust(wd) for i, (v, wd) in enumerate(zip(r, widths)))
             for r in rows]
    how = "chosen automatically" if table["auto"] else "as entered"
    unit = {"Count": "counts", "Percent": "percent of each column's values",
            "Fraction": "fraction of each column's values"}[table["values"]]
    return (f"Frequency distribution (bin width {_edge(table['width'])}, {how}; {unit})\n"
            + "\n".join(lines))


def _render_histogram(fig, groups, opts, st):
    try:
        table = frequency_table(groups, opts.hist_bin_width, opts.hist_bin_start, opts.hist_values)
    except ValueError as exc:
        _empty_state(fig, str(exc), opts)
        fig.stel_notes.append(str(exc))
        return None
    if table is None:
        _empty_state(fig, "Type or paste values into the grid.\nEach column is one data set.", opts)
        return None
    ax = _new_axes(fig, opts)
    _frame(ax, opts)
    edges, width = table["edges"], table["width"]
    centers = (edges[:-1] + edges[1:]) / 2
    colors = palette_colors(opts.palette, len(table["series"]))
    handles, names, top = [], [], 0.0
    for (name, _counts, shown, _n, below), c in zip(table["series"], colors):
        if opts.hist_style == "Outline":
            ax.stairs(shown, edges, color=c, linewidth=st["data_line"], zorder=2)
            handles.append(Line2D([], [], color=c, linewidth=st["data_line"]))
        else:
            ax.bar(centers, shown, width=width, facecolor=to_rgba(c, st["fill_alpha"]), edgecolor=c,
                   linewidth=st["thin"], zorder=1)
            handles.append(Rectangle((0, 0), 1, 1, facecolor=to_rgba(c, st["fill_alpha"]),
                                     edgecolor=c, linewidth=st["thin"]))
        names.append(name)
        top = max(top, float(np.max(shown)) if shown.size else 0.0)
        if below:
            fig.stel_notes.append(f"{name}: {below} value(s) fall below the first bin and are not "
                                  "counted.")
    ax.set_xlim(edges[0], edges[-1])
    ax.xaxis.set_major_locator(MaxNLocator(nbins=6, steps=NICE_STEPS))
    _set_axis(ax, "y", 0.0, top or 1.0, opts.y_min, opts.y_max)
    _reference_lines(ax, opts, st)
    for x in _parse_values(getattr(opts, "ref_x", "")):
        ax.axvline(x, color="black", linewidth=st["ref_line_width"], linestyle=REF_DOTTED,
                   dash_capstyle="round", zorder=0.5)
    ax.set_xlabel(opts.x_label or opts.y_label)
    ax.set_ylabel(HIST_Y_TITLES.get(opts.hist_values, "Number of values"))
    if len(names) > 1:
        from types import SimpleNamespace
        _legend(ax, handles, names, SimpleNamespace(legend="Inside upper right",
                                                    font_size=opts.font_size), st)
    fig.stel_frequency = table
    _finish(fig, ax, opts, st)
    return ax


# ---------------------------------------------------------------------------
# Grouped graphs (two-way layouts)
# ---------------------------------------------------------------------------

def _cell_summary(Dsrc, Dp, error, log_y):
    """Mean and error distances per cell (rows x data sets), on the drawn scale."""
    R, C, _ = Dsrc.shape
    means = np.full((R, C), np.nan)
    err_lo = np.zeros((R, C))
    err_hi = np.zeros((R, C))
    for r in range(R):
        for c in range(C):
            v = finite(Dsrc[r, c])
            if v.size:
                m, e = float(np.mean(v)), float(error_halfwidth(v, error))
                if log_y:   # statistics on the original values, drawn on the log axis
                    means[r, c] = math.log10(m) if m > 0 else np.nan
                    if not np.isfinite(means[r, c]):
                        continue
                    err_lo[r, c] = (means[r, c] - math.log10(m - e) if (e > 0 and m - e > 0)
                                    else (math.inf if e > 0 else 0.0))
                    err_hi[r, c] = math.log10(m + e) - means[r, c] if e > 0 else 0.0
                else:
                    means[r, c], err_lo[r, c], err_hi[r, c] = m, e, e
    return means, err_lo, err_hi


def _value_axis(ax, lows, highs, user_min, user_max, log_y, zero=True):
    if log_y:
        return _log_axis(ax, min(lows), max(highs), user_min, user_max)
    return _set_axis(ax, "y", min(lows), max(highs), user_min, user_max, zero=zero)


def render_grouped(fig, row_labels, col_names, D, opts, result=None, color_source=None):
    """Clustered graphs: one cluster per row, one color per data set.

    D has shape rows x data sets x replicates (NaN for blanks). color_source, optional, is
    another grouped table (row labels, data set names, values) whose cell means color the
    circles of a circle heat map.
    """
    from .anova import clean_grouped

    fig.clear()
    fig.stel_notes = []
    fig.stel_volcano = None
    st = apply_lab_style(opts.font_size, opts.bold, opts.style)
    row_labels, col_names, D = clean_grouped(row_labels, col_names, D)
    if not row_labels:
        _empty_state(fig, "Enter a label for each row and\nreplicate values for each data set.", opts)
        return None
    pt = opts.plot_type
    if pt == HEAT_MAP:
        return _render_heatmap(fig, row_labels, col_names, D, opts, st, color_source)
    if pt == VOLCANO:
        from .volcano import render_grouped_volcano
        return render_grouped_volcano(fig, row_labels, col_names, D, opts, st)
    if pt == BARS_3D:
        from .plot3d import render_grouped_bars3d
        return render_grouped_bars3d(fig, row_labels, col_names, D, opts, st)

    box = pt == GROUPED_BOX
    area = pt == AREA
    line = pt.startswith("Line")
    scatter = pt == "Grouped scatter dot plot"
    arrangement = opts.arrangement if pt in ("Grouped bars", AREA) else "Interleaved"
    if area and arrangement not in ("Stacked", "Superimposed"):
        arrangement = "Superimposed"
    stacked = arrangement == "Stacked"
    log_y = bool(getattr(opts, "log_y", False))
    if log_y and stacked:
        fig.stel_notes.append("Stacked graphs use a linear Y axis; the log scale setting is ignored.")
        log_y = False
    Dsrc, Dp = D, D
    if log_y:
        dropped = int(np.sum(np.isfinite(D) & (D <= 0)))
        if dropped:
            fig.stel_notes.append(f"{dropped} value(s) at or below zero are not shown on the log axis; "
                                  "the statistics still include them.")
        Dsrc = np.where(np.isfinite(D) & (D > 0), D, np.nan)
        Dp = _log10_pos(D)

    R, C, _ = D.shape
    flip = getattr(opts, "orientation", "Vertical") == "Horizontal"
    right = [c for c, n in enumerate(col_names) if n in set(opts.right_series or ())]
    if right and (pt not in RIGHT_AXIS_TYPES or flip or stacked or arrangement == "Separated"):
        fig.stel_notes.append("A right Y axis is available for vertical interleaved or superimposed "
                              "bars, scatter, line, and area graphs; all data sets use the left axis.")
        right = []
    if right and len(right) == C:
        right = right[1:] if C > 1 else []
    on_right = np.array([c in right for c in range(C)])

    fig_ax = _new_axes(fig, opts)
    _frame(fig_ax, opts, right_axis=bool(right))
    ax = _Flip(fig_ax) if flip else fig_ax
    ax2 = fig_ax.twinx() if right else None
    if ax2 is not None:
        ax2.spines["top"].set_visible(opts.frame == "Box")
        ax2.spines["left"].set_visible(False)
    colors = palette_colors(opts.palette, C)
    ms = opts.point_size
    alpha, lw, thin = st["fill_alpha"], st["data_line"], st["thin"]
    filled = opts.marker_fill != "Open"
    show_points = (opts.show_points or scatter) and not (stacked or area)

    # Where each bar or point cluster sits along the group axis
    slot = GROUP_SPAN / C
    if arrangement == "Separated":
        gap = 1.0
        xmat = np.array([[c * (R + gap) + r for c in range(C)] for r in range(R)], float)
        bar_w = GROUP_BAR * 0.8
        x_lo, x_hi = -GROUP_MARGIN, (C - 1) * (R + gap) + R - 1 + GROUP_MARGIN
        ticks, tick_labels = xmat.T.ravel(), [row_labels[r] for c in range(C) for r in range(R)]
        if not flip and max(len(t) for t in tick_labels) * R * C * opts.font_size * 0.55 > \
                opts.width_in * 72 * 0.9:
            from dataclasses import replace
            opts = replace(opts, rotate_labels=True)   # long names would run into each other
    else:
        if arrangement in ("Stacked", "Superimposed") or area:
            offsets = np.zeros(C)
            bar_w = GROUP_SPAN * GROUP_BAR
        else:
            offsets = (np.arange(C) - (C - 1) / 2.0) * (0.06 if line else slot)
            bar_w = slot * GROUP_BAR
        xmat = np.arange(R)[:, None] + offsets[None, :]
        x_lo, x_hi = ((-0.15, R - 0.85) if (area and R > 1) else (-GROUP_MARGIN, R - 1 + GROUP_MARGIN))
        ticks, tick_labels = np.arange(R), list(row_labels)
    ax.set_xlim(x_lo, x_hi)
    ax2 is not None and ax2.set_xlim(x_lo, x_hi)
    ax_w_pt, ax_h_pt = opts.width_in * 72, opts.height_in * 72
    if flip:
        ax_w_pt, ax_h_pt = ax_h_pt, ax_w_pt
    x_per_pt = (x_hi - x_lo) / ax_w_pt
    capsize = 0.5 * GROUP_CAP * bar_w / x_per_pt

    means, err_lo, err_hi = _cell_summary(Dsrc, Dp, opts.error, log_y)
    bottoms = np.zeros((R, C))
    if stacked:
        run = np.zeros(R)
        for c in range(C):
            bottoms[:, c] = run
            run = run + np.nan_to_num(means[:, c])
        err_lo = np.zeros((R, C))   # stacked segments show the upward error only
    tops = bottoms + means + err_hi
    for r in range(R):
        for c in range(C):
            v = finite(Dp[r, c])
            if v.size and (show_points or box):
                tops[r, c] = max(tops[r, c], float(v.max())) if np.isfinite(tops[r, c]) else float(v.max())

    def axis_range(cols):
        sel = [c for c in range(C) if (c in cols)]
        vals = finite(Dp[:, sel, :])
        t = tops[:, sel]
        t = t[np.isfinite(t)]
        b = (bottoms + means - err_lo)[:, sel]
        b = b[np.isfinite(b)]
        lows = []
        if log_y or show_points or box or line or scatter:
            lows.append(float(vals.min()) if vals.size else 0.0)
        else:
            lows.append(0.0)
        if b.size:
            lows.append(float(b.min()))
        if box:
            lows = [float(vals.min())] if vals.size else [0.0]
        return lows, [float(t.max()) if t.size else 1.0]

    left_cols = [c for c in range(C) if not on_right[c]]
    lows, highs = axis_range(left_cols)
    y0, y1 = _value_axis(ax, lows, highs, opts.y_min, opts.y_max, log_y, zero=not box)
    if ax2 is not None:
        lows2, highs2 = axis_range(right)
        r0, r1 = _value_axis(ax2, lows2, highs2, opts.right_min, opts.right_max, log_y, zero=not box)
    base = y0 if log_y else 0.0
    err_lo = np.where(np.isfinite(err_lo), err_lo, means - (y0 - 1.0))

    brackets_ok = (arrangement == "Interleaved" and not line and not area and not right)
    if result is not None and result.ok and opts.annotation != "None" and brackets_ok:
        families = {}
        for comp in result.comparisons:
            if comp.cluster >= 0 and (opts.show_ns or comp.p < 0.05):
                families.setdefault(comp.cluster, []).append(comp)
        fams = [(comps, (lambda r: (lambda c: float(xmat[r, c])))(r),
                 {c: tops[r, c] for c in range(C) if np.isfinite(tops[r, c])})
                for r, comps in families.items()]
        if fams:
            y0, y1 = _place_brackets(ax, fams, opts, st, y0, y1, ax_h_pt, x_per_pt)
    elif result is not None and result.ok and opts.annotation != "None" and result.comparisons \
            and not line:
        fig.stel_notes.append("Comparison brackets are drawn only on interleaved graphs with one "
                              "Y axis.")

    def y_per_pt_of(c):
        if on_right[c]:
            a, b = ax2.get_ylim()
            return (b - a) / ax_h_pt
        return (y1 - y0) / ax_h_pt

    rank = np.argsort(np.argsort(-np.nan_to_num(means, nan=-np.inf), axis=1), axis=1)
    area_rank = np.argsort(np.argsort(-np.nanmean(np.where(np.isfinite(means), means, np.nan), axis=0)))
    handles = []
    for c, color in enumerate(colors):
        target = ax2 if on_right[c] else ax
        xs = xmat[:, c]
        ok = np.isfinite(means[:, c])
        z_off = c * 0.01 if arrangement == "Superimposed" else 0.0
        if pt == "Grouped bars":
            face = to_rgba(color, alpha) if opts.bar_style == "Filled" else "none"
            if arrangement == "Superimposed" and opts.bar_style == "Filled":
                face = _opaque(face)   # overlapping see-through fills would mix colors
            heights = means[:, c] - (0 if stacked else base)
            for r in np.nonzero(ok)[0]:
                # Superimposed: shorter bars sit in front of taller ones
                z = 1.1 + 0.4 * rank[r, c] / max(C - 1, 1) if arrangement == "Superimposed" else 1
                target.bar(xs[r], heights[r], bottom=bottoms[r, c] if stacked else base, width=bar_w,
                           facecolor=face, edgecolor=color,
                           linewidth=thin if opts.bar_style == "Filled" else lw, zorder=z)
            handles.append(Rectangle((0, 0), 1, 1, facecolor=face, edgecolor=color,
                                     linewidth=thin))
        elif area:
            lo_edge = bottoms[:, c] if stacked else np.full(R, base)
            hi_edge = bottoms[:, c] + means[:, c]
            if stacked:
                fill, z_fill = to_rgba(color, alpha), 1
            else:   # solid fills, largest area at the back, so each area keeps its own color
                fill, z_fill = _opaque(to_rgba(color, alpha)), 1.1 + 0.4 * area_rank[c] / max(C - 1, 1)
            target.fill_between(xs[ok], lo_edge[ok], hi_edge[ok], facecolor=fill,
                                edgecolor="none", linewidth=0, zorder=z_fill)
            target.plot(xs[ok], hi_edge[ok], color=color, linewidth=lw, zorder=2 + z_off,
                        clip_on=False)
            handles.append(Rectangle((0, 0), 1, 1, facecolor=to_rgba(color, alpha), edgecolor=color,
                                     linewidth=thin))
        elif box:
            cells = [(xs[r], finite(Dp[r, c])) for r in range(R) if finite(Dp[r, c]).size]
            if cells:
                tukey = getattr(opts, "whiskers", "Min to max").startswith("Tukey")
                bp = target.boxplot([v for _, v in cells], positions=[x for x, _ in cells],
                                    widths=bar_w, whis=1.5 if tukey else (0, 100),
                                    showfliers=tukey and not opts.show_points, patch_artist=True,
                                    manage_ticks=False)
                _style_boxes(bp, [color] * len(cells), alpha, lw, thin, ms,
                             tukey and not opts.show_points)
            handles.append(Rectangle((0, 0), 1, 1, facecolor=to_rgba(color, alpha), edgecolor=color,
                                     linewidth=thin))
        elif line:
            code = marker_for(opts.marker, c, st)
            mk = dict(marker=code, markersize=marker_size(ms, code, st),
                      markerfacecolor=color if filled else "none",
                      markeredgecolor="none" if filled else color,
                      markeredgewidth=0 if filled else st["marker_edge"])
            target.plot(xs[ok], means[ok, c], color=color, linewidth=thin, zorder=Z_SUMMARY, **mk)
            handles.append(Line2D([], [], color=color, linewidth=thin, **mk))
        else:
            target.hlines(means[ok, c], xs[ok] - bar_w / 2, xs[ok] + bar_w / 2, colors=[color],
                          linewidth=lw, zorder=Z_SUMMARY)
            code = marker_for(opts.marker, c, st)
            handles.append(Line2D([], [], color=color, linestyle="none", marker=code,
                                  markersize=marker_size(ms, code, st),
                                  markerfacecolor=color if filled else "none",
                                  markeredgecolor="none" if filled else color,
                                  markeredgewidth=0 if filled else st["marker_edge"]))
        err_ok = ok & ((err_lo[:, c] > 0) | (err_hi[:, c] > 0))
        if err_ok.any() and not (box or area):
            centers = bottoms[:, c] + means[:, c]
            _style_errorbar(target.errorbar(xs[err_ok], centers[err_ok],
                                            yerr=[err_lo[err_ok, c], err_hi[err_ok, c]], fmt="none",
                                            ecolor=color, elinewidth=lw, capsize=capsize,
                                            capthick=lw, zorder=Z_SUMMARY + z_off), opts)
        if show_points:
            ypp = y_per_pt_of(c)
            for r in range(R):
                v = finite(Dp[r, c])
                if v.size == 0:
                    continue
                offs = (np.zeros(v.size) if line else
                        _swarm_offsets(v, ms * ypp, 1.41 * ms * x_per_pt, bar_w * 0.4))
                _scatter(target, xs[r] + offs, v, color, marker_for(opts.marker, c, st), ms, filled,
                         st, Z_POINTS)

    _reference_lines(ax, opts, st, log_y=log_y)
    ax.set_xticks(ticks)
    if opts.rotate_labels:
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", rotation_mode="anchor")
    else:
        ax.set_xticklabels(tick_labels)
    ax.set_ylabel(opts.y_label)
    if opts.x_label:
        ax.set_xlabel(opts.x_label)
    if ax2 is not None:
        ax2.set_ylabel(opts.right_label or ", ".join(col_names[c] for c in right))
        ax2.tick_params(axis="y", direction=st["tick_dir"], length=st["tick_len"],
                        width=st["axis_line"])
    if flip:
        fig_ax.tick_params(axis="y", pad=3)
    if arrangement == "Separated" and C > 1:
        # Name each block of bars beside the plot, across from its bars
        for c in range(C):
            mid = c * (R + 1.0) + (R - 1) / 2.0
            if flip:
                fig_ax.annotate(col_names[c], xy=(1, mid), xycoords=("axes fraction", "data"),
                                xytext=(4, 0), textcoords="offset points", rotation=270,
                                ha="center", va="center", fontsize=opts.font_size + st["title_extra"])
            else:
                fig_ax.annotate(col_names[c], xy=(mid, 1), xycoords=("data", "axes fraction"),
                                xytext=(0, 4), textcoords="offset points", ha="center",
                                va="bottom", fontsize=opts.font_size + st["title_extra"])
    elif opts.legend != "None":
        lopts = opts
        if flip and opts.legend.startswith("Inside"):
            from dataclasses import replace
            lopts = replace(opts, legend="Right of plot")   # bars start at the left edge
        _legend(fig_ax, handles, col_names, lopts, st)
    _finish(fig, fig_ax, opts, st, twins=[ax2] if ax2 is not None else ())
    if log_y:
        _style_minor(fig_ax, st, "x" if flip else "y")
        if ax2 is not None:
            _style_minor(ax2, st, "y")
    return fig_ax


def _opaque(rgba):
    """A see-through color as the solid color it shows on white."""
    r, g, b, a = rgba
    return (r * a + 1 - a, g * a + 1 - a, b * a + 1 - a, 1.0)


def match_cells(row_labels, col_names, source):
    """Cell means of another grouped table lined up with these rows and data sets: matched by
    row label and data set name where they agree, otherwise by position. NaN where missing."""
    src_rows, src_cols, src = source
    src = np.asarray(src, float)
    R, C = len(row_labels), len(col_names)
    out = np.full((R, C), np.nan)
    row_index = {lab: i for i, lab in enumerate(src_rows)}
    col_index = {name: j for j, name in enumerate(src_cols)}
    by_label = all(lab in row_index for lab in row_labels)
    by_name = all(name in col_index for name in col_names)
    for r, lab in enumerate(row_labels):
        i = row_index[lab] if by_label else r
        for c, name in enumerate(col_names):
            j = col_index[name] if by_name else c
            if i < src.shape[0] and j < src.shape[1]:
                v = finite(src[i, j])
                if v.size:
                    out[r, c] = float(np.mean(v))
    return out


def colormap(name):
    """A heat map color scale: a built-in map, or a custom color scheme run as a gradient."""
    import matplotlib
    from matplotlib.colors import LinearSegmentedColormap
    from .lab_style import CUSTOM_PALETTES
    if name in CUSTOM_PALETTES and len(CUSTOM_PALETTES[name]) >= 2:
        return LinearSegmentedColormap.from_list(name, CUSTOM_PALETTES[name])
    return matplotlib.colormaps[HEAT_MAPS.get(name, "viridis")].copy()


def heat_map_names():
    from .lab_style import CUSTOM_PALETTES
    return list(HEAT_MAPS) + [n for n, cols in CUSTOM_PALETTES.items() if len(cols) >= 2]


def circle_color_values(D, choice, color_source=None, row_labels=None, col_names=None):
    """The value that colors each circle: the cell mean, a spread measure, n, or another table."""
    R, C, _ = D.shape
    if choice not in CIRCLE_COLORS[1:]:
        if color_source is not None:
            return match_cells(row_labels, col_names, color_source)
        choice = "Same as size"
    out = np.full((R, C), np.nan)
    for r in range(R):
        for c in range(C):
            v = finite(D[r, c])
            if not v.size:
                continue
            m = float(np.mean(v))
            sd = float(np.std(v, ddof=1)) if v.size > 1 else np.nan
            out[r, c] = {"Same as size": m, "SD": sd,
                         "SEM": sd / math.sqrt(v.size) if v.size > 1 else np.nan,
                         "Number of values": float(v.size),
                         "Coefficient of variation": (100 * sd / m if m else np.nan)}[choice]
    return out


def _render_heatmap(fig, row_labels, col_names, D, opts, st, color_source=None):
    """Cell means as colors (rows x data sets), with a color bar. As circles, each circle's area
    shows the cell mean and its color shows a second value."""
    R, C, _ = D.shape
    means = np.full((R, C), np.nan)
    for r in range(R):
        for c in range(C):
            v = finite(D[r, c])
            if v.size:
                means[r, c] = float(np.mean(v))
    circles = getattr(opts, "heat_shape", "Squares") == "Circles"
    shade_by = means
    color_title = opts.y_label
    if circles:
        choice = getattr(opts, "circle_color", "Same as size")
        shade_by = circle_color_values(D, choice, color_source, row_labels, col_names)
        if choice != "Same as size":
            color_title = getattr(opts, "circle_color_label", "") or (
                choice if choice in CIRCLE_COLORS else choice.replace("Table: ", ""))
    ax = _new_axes(fig, opts)
    cmap = colormap(opts.heat_cmap)
    cmap.set_bad("#e6e6e6")
    finite_shade = shade_by[np.isfinite(shade_by)]
    if not finite_shade.size:
        finite_shade = np.array([0.0, 1.0])
        fig.stel_notes.append("No color values for these cells; check the circle color setting.")
    vmin = opts.y_min if opts.y_min is not None else float(finite_shade.min())
    vmax = opts.y_max if opts.y_max is not None else float(finite_shade.max())
    if vmax <= vmin:
        vmax = vmin + 1.0
    if circles:
        from matplotlib.colors import Normalize
        cell_pt = min(opts.width_in * 72 / C, opts.height_in * 72 / R)
        d_max = 0.92 * cell_pt
        big = float(np.nanmax(np.abs(means))) if np.isfinite(means).any() else 1.0
        big = big or 1.0
        if np.any(means[np.isfinite(means)] < 0):
            fig.stel_notes.append("Circle sizes show the size of each mean; negative means are "
                                  "drawn by their absolute value.")
        rr, cc = np.nonzero(np.isfinite(means))
        sizes = (d_max * np.sqrt(np.abs(means[rr, cc]) / big)) ** 2
        colors_now = shade_by[rr, cc]
        norm = Normalize(vmin, vmax)
        face = [cmap(norm(v)) if np.isfinite(v) else cmap.get_bad() for v in colors_now]
        ax.scatter(cc, rr, s=sizes, c=face, edgecolors="none", zorder=2)
        ax.set_xlim(-0.5, C - 0.5)
        ax.set_ylim(R - 0.5, -0.5)
        from matplotlib.cm import ScalarMappable
        im = ScalarMappable(norm=norm, cmap=cmap)
        ax.set_aspect("auto")
        ax.grid(which="minor", color="#d9d9d9", linewidth=st["thin"])
    else:
        im = ax.imshow(np.ma.masked_invalid(shade_by), cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto",
                       interpolation="nearest")
        ax.grid(which="minor", color="white", linewidth=st["axis_line"] * 1.5)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks(np.arange(C))
    ax.set_yticks(np.arange(R))
    if opts.rotate_labels:
        ax.set_xticklabels(col_names, rotation=45, ha="right", rotation_mode="anchor")
    else:
        ax.set_xticklabels(col_names)
    ax.set_yticklabels(row_labels)
    ax.tick_params(which="major", length=0)
    ax.set_xticks(np.arange(C + 1) - 0.5, minor=True)
    ax.set_yticks(np.arange(R + 1) - 0.5, minor=True)
    ax.tick_params(which="minor", length=0)
    if opts.heat_values and not circles:
        for r in range(R):
            for c in range(C):
                if np.isfinite(means[r, c]):
                    red, green, blue, _a = cmap((means[r, c] - vmin) / (vmax - vmin))
                    light = 0.2126 * red + 0.7152 * green + 0.0722 * blue > 0.5
                    ax.text(c, r, f"{means[r, c]:.3g}", ha="center", va="center",
                            fontsize=opts.font_size, color="black" if light else "white")
    W, H = fig.get_size_inches()
    gap, bar_w = 0.12, 0.12
    cax = fig.add_axes([(1.4 + opts.width_in + gap) / W, 1.0 / H, bar_w / W, opts.height_in / H])
    cb = fig.colorbar(im, cax=cax)
    cb.outline.set_linewidth(st["axis_line"])
    cb.ax.tick_params(width=st["axis_line"], length=st["tick_len"], labelsize=opts.font_size)
    cb.set_label(color_title, fontsize=opts.font_size + st["title_extra"])
    side = [(cax, gap, bar_w)]
    if circles:
        # Size key: three circles at round values up to the largest mean
        lax = fig.add_axes([0.9, 0.1, 0.05, 0.5])
        lax.set_axis_off()
        steps = MaxNLocator(nbins=4, steps=NICE_STEPS).tick_values(0, big)
        keys = [v for v in steps if 0 < v <= big * 1.0001][-3:] or [big]
        handles = [Line2D([], [], linestyle="none", marker="o", markeredgecolor="none",
                          markerfacecolor="#7f7f7f", markersize=d_max * math.sqrt(v / big))
                   for v in keys]
        lax.legend(handles, [f"{v:g}" for v in keys], loc="upper left", frameon=False,
                   title=opts.y_label, title_fontsize=opts.font_size + st["title_extra"],
                   fontsize=opts.font_size, labelspacing=0.75 * d_max / opts.font_size,
                   handlelength=d_max / opts.font_size, borderaxespad=0, handletextpad=0.8,
                   alignment="left")
        side.append((lax, gap + bar_w + 0.75, 0.3))
    if opts.x_label:
        ax.set_xlabel(opts.x_label)
    fig.stel_heatmap = means
    _finish(fig, ax, opts, st, side=side)
    return ax


# ---------------------------------------------------------------------------
# XY graphs
# ---------------------------------------------------------------------------

def xy_summary(x, y_matrix, error_kind):
    """Mean and error bar per X value. Returns x, mean, err, n arrays."""
    x = np.asarray(x, float)
    y = np.asarray(y_matrix, float)
    if y.ndim == 1:
        y = y[:, None]
    rows = []
    for xi, row in zip(x, y):
        vals = finite(row)
        if math.isfinite(xi) and vals.size:
            rows.append((xi, float(np.mean(vals)), error_halfwidth(vals, error_kind), vals.size))
    rows.sort(key=lambda r: r[0])
    if not rows:
        return (np.zeros(0),) * 4
    arr = np.array(rows)
    return arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]


def render_xy(fig, x, series, opts, fits=None, row_titles=None):
    """XY graph. series: list of (name, y_matrix rows x replicates). row_titles (optional)
    label points on a volcano plot."""
    fig.clear()
    fig.stel_notes = []
    fig.stel_volcano = None
    st = apply_lab_style(opts.font_size, opts.bold, opts.style)
    if getattr(opts, "plot_type", "") == VOLCANO:
        from .volcano import render_xy_volcano
        return render_xy_volcano(fig, x, series, opts, st, row_titles)
    area = getattr(opts, "plot_type", "") == AREA
    fits = {f.series: f for f in (fits or [])}
    log_y = bool(getattr(opts, "log_y", False))
    plotted, dropped = [], 0
    for name, y in series:
        xs, mean, err, _n = xy_summary(x, y, opts.error)
        if opts.log_x:
            keep = xs > 0
            xs, mean, err = xs[keep], mean[keep], err[keep]
        if log_y:
            keep = mean > 0
            dropped += int(np.sum(~keep))
            xs, mean, err = xs[keep], mean[keep], err[keep]
        if xs.size:
            plotted.append((name, xs, mean, err))
    if dropped:
        fig.stel_notes.append(f"{dropped} point(s) with a mean at or below zero are not shown on the "
                              "log Y axis.")
    if not plotted:
        _empty_state(fig, "Enter X values in the first column\nand Y replicates beside them.", opts)
        return None

    right_names = set(getattr(opts, "right_series", ()) or ())
    on_right = [name in right_names for name, *_ in plotted]
    if all(on_right):
        on_right = [False] + on_right[1:]
    has_right = any(on_right)
    main = _new_axes(fig, opts)
    _frame(main, opts, right_axis=has_right)
    ax2 = main.twinx() if has_right else None
    if ax2 is not None:
        ax2.spines["top"].set_visible(opts.frame == "Box")
        ax2.spines["left"].set_visible(False)
    colors = palette_colors(opts.palette, len(plotted))
    lw, thin = st["data_line"], st["thin"]
    handles = []
    y_floor = {}
    for side, target in ((False, main), (True, ax2)):
        if log_y and target is not None:
            target.set_yscale("log")
            sel = [p for p, r in zip(plotted, on_right) if r == side]
            if not sel:
                continue
            lows = np.concatenate([np.where(p[2] - p[3] > 0, p[2] - p[3], p[2]) for p in sel])
            user = opts.right_min if side else opts.y_min
            y_floor[side] = (user if user is not None and user > 0
                             else 10.0 ** math.floor(math.log10(float(lows.min()))))
    for k, ((name, xs, mean, err), c) in enumerate(zip(plotted, colors)):
        ax = ax2 if on_right[k] else main
        floor = y_floor.get(on_right[k])
        lower = np.maximum(mean - err, floor) if log_y else mean - err
        marker = marker_for(opts.marker, k, st)
        size = marker_size(opts.point_size, marker, st)
        filled = opts.marker_fill == "Filled"
        mstyle = dict(marker=marker, markersize=size,
                      markerfacecolor=c if filled else "none",
                      markeredgecolor="none" if filled else c,
                      markeredgewidth=0 if filled else st["marker_edge"])
        fit = fits.get(name)
        has_fit = fit is not None and fit.ok
        show_err = np.any(err > 0)
        if area:
            base = floor if log_y else 0.0
            ax.fill_between(xs, np.full(xs.size, base), mean, facecolor=to_rgba(c, st["fill_alpha"]),
                            edgecolor="none", linewidth=0, zorder=0.8 + 0.01 * k)
        if show_err and opts.error_display == "Shaded band":
            fill, edge = band_colors(c)
            ax.fill_between(xs, lower, mean + err, facecolor=fill, edgecolor="none",
                            linewidth=0, zorder=1)
            for yy in (lower, mean + err):
                ax.plot(xs, yy, color=edge, linewidth=thin, linestyle=BAND_EDGE,
                        dash_capstyle="round", zorder=1.5)
        elif show_err and opts.error_display == "Error bars":
            _style_errorbar(ax.errorbar(xs, mean, yerr=[mean - lower, err], fmt="none", ecolor=c,
                                        elinewidth=lw, capsize=2.5, capthick=lw, zorder=2), opts)
        connect = opts.connect and not has_fit
        ax.plot(xs, mean, linestyle="-" if connect else "none", color=c, linewidth=thin,
                zorder=3, clip_on=False, **mstyle)
        handles.append(Line2D([], [], color=c, linewidth=thin,
                              linestyle="-" if (connect or has_fit) else "none", **mstyle))
        if has_fit:
            lo, hi = float(np.min(xs)), float(np.max(xs))
            grid = (np.logspace(math.log10(lo), math.log10(hi), 300) if opts.log_x
                    else np.linspace(lo, hi, 300))
            with np.errstate(all="ignore"):
                ax.plot(grid, fit.predict(grid), color=c, linewidth=lw, zorder=2)

    ax = main
    all_x = np.concatenate([p[1] for p in plotted])
    if opts.log_x:
        ax.set_xscale("log")
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v:g}"))
        if opts.x_min is not None or opts.x_max is not None:
            ax.set_xlim(left=opts.x_min, right=opts.x_max)
    else:
        _set_axis(ax, "x", float(all_x.min()), float(all_x.max()), opts.x_min, opts.x_max)
    for side, target in ((False, main), (True, ax2)):
        sel = [p for p, r in zip(plotted, on_right) if r == side]
        if target is None or not sel:
            continue
        lo_y = min(float(np.min(p[2] - p[3])) for p in sel)
        hi_y = max(float(np.max(p[2] + p[3])) for p in sel)
        if area and not log_y:
            lo_y = min(lo_y, 0.0)
        user_min, user_max = (opts.right_min, opts.right_max) if side else (opts.y_min, opts.y_max)
        if log_y:
            floor = y_floor[side]
            top = (user_max if user_max is not None and user_max > floor
                   else 10.0 ** math.ceil(math.log10(hi_y)))
            target.set_ylim(floor, top)
            target.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v:g}"))
            target.yaxis.set_minor_formatter(NullFormatter())
        else:
            _set_axis(target, "y", lo_y, hi_y, user_min, user_max)
    _reference_lines(ax, opts, st)
    ax.set_xlabel(opts.x_label)
    ax.set_ylabel(opts.y_label)
    if ax2 is not None:
        ax2.set_ylabel(opts.right_label or ", ".join(p[0] for p, r in zip(plotted, on_right) if r))
        ax2.tick_params(axis="y", direction=st["tick_dir"], length=st["tick_len"],
                        width=st["axis_line"])
    if len(plotted) > 1:
        _legend(ax, handles, [p[0] for p in plotted], opts, st)
    _finish(fig, ax, opts, st, twins=[ax2] if ax2 is not None else ())
    if log_y:
        _style_minor(ax, st, "y")
        if ax2 is not None:
            _style_minor(ax2, st, "y")
    if opts.log_x:
        _style_minor(ax, st, "x")
    return ax


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _blend(rgba):
    r, g, b, a = rgba
    return (r * a + (1 - a), g * a + (1 - a), b * a + (1 - a), 1.0)


def _flatten_alpha(fig):
    """Replace partly transparent colors with the same color blended onto white (for EPS)."""
    from matplotlib.collections import Collection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.colors import to_rgba
    for artist in fig.findobj():
        if isinstance(artist, Patch) and artist is not fig.patch:
            for get, put in ((artist.get_facecolor, artist.set_facecolor),
                             (artist.get_edgecolor, artist.set_edgecolor)):
                c = to_rgba(get())
                if 0 < c[3] < 1:
                    put(_blend(c))
            artist.set_alpha(None)
        elif isinstance(artist, Collection):
            for get, put in ((artist.get_facecolors, artist.set_facecolors),
                             (artist.get_edgecolors, artist.set_edgecolors)):
                cols = np.array(get(), dtype=float)
                if cols.size and ((cols[:, 3] > 0) & (cols[:, 3] < 1)).any():
                    put([_blend(c) if 0 < c[3] < 1 else tuple(c) for c in cols])
            artist.set_alpha(None)
        elif isinstance(artist, Line2D):
            c = to_rgba(artist.get_color(), artist.get_alpha())
            if 0 < c[3] < 1:
                artist.set_color(_blend(c))
                artist.set_alpha(None)


def save_figure(fig, path, author="Daniel Shiwarski", title="", trim=True, transparent=False,
                dpi=600):
    """Save a figure with lab settings. Vector formats keep editable text.

    transparent=True leaves out the white background in SVG, PDF, and PNG files. TIFF files
    always get a white background, since many journals require opaque TIFFs.
    """
    ext = os.path.splitext(path)[1].lower()
    kwargs = {}
    if transparent and ext not in (".tif", ".tiff"):
        kwargs["transparent"] = True
    else:
        kwargs["facecolor"] = "white"
    if trim:
        kwargs.update(bbox_inches="tight", pad_inches=0.03)
    creator = f"{APP_NAME} {__version__}"
    if ext == ".pdf":
        meta = {"Author": author, "Title": title, "Creator": creator}
    elif ext == ".svg":
        meta = {"Creator": author, "Title": title, "Description": f"Created with {creator}"}
    elif ext == ".png":
        meta = {"Author": author, "Title": title, "Software": creator}
        kwargs["dpi"] = dpi
    elif ext == ".eps":
        # PostScript has no transparency: blend partly transparent fills with white first
        meta = {"Creator": creator}
        _flatten_alpha(fig)
    elif ext in (".tif", ".tiff"):
        meta = None
        kwargs["dpi"] = dpi
        kwargs["pil_kwargs"] = {"compression": "tiff_lzw"}
    else:
        raise ValueError(f"Unsupported file type: {ext or 'none'}")
    if meta:
        kwargs["metadata"] = {k: v for k, v in meta.items() if v}
    fig.savefig(path, **kwargs)
    return path
