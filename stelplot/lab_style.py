"""Lab plotting style for STELplot.

Two presets:

"Lab template" is measured from the lab's Prism SVG exports (PrismTemplates.pzfx):
Arial 7 pt numbering and labels, 8 pt axis titles and legends, 0.72 pt axes and
data lines, 0.36 pt outlines, 1.8 pt inward ticks, 50% fills, and Prism's heavy
asterisk. "Prism default" follows Prism's Format Axes defaults for a new graph
(Arial Bold 11/12/14 pt, 1 pt axes).

Edit this file to change the look of every figure.
"""

__author__ = "Daniel Shiwarski"

import matplotlib
from matplotlib import font_manager
from matplotlib.colors import to_rgb

# Lab template colors from the Prism exports, in the order Prism assigns them
LAB_COLORS = ["#000000", "#ff0066", "#107f80", "#40007f"]

# "Journal": colorblind-robust, muted journal tones (black, cobalt, ochre, teal, muted red,
# plum). Chosen by exhaustive search over moderate-chroma colors to maximize the smallest
# CIEDE2000 difference between any two colors, as solid colors and as 50% fills, under
# normal vision and simulated deuteranopia, protanopia, and tritanopia (Machado et al.
# 2009, severity 1.0). Worst-case difference: 20.8 for the first 2-3 colors, 11.1 for 4,
# 9.9 for all 6 (Okabe-Ito: 5.2; Tol muted: 6.3; Lab template: 8.3 on the same test).
JOURNAL_COLORS = ["#000000", "#1355AA", "#AE9122", "#13ADA6", "#C55C55", "#773E55"]

PALETTES = {
    "Journal": JOURNAL_COLORS,
    "Lab template": LAB_COLORS,
    # Okabe and Ito colorblind-safe palette
    "Okabe-Ito": ["#000000", "#E69F00", "#56B4E9", "#009E73", "#F0E442",
                  "#0072B2", "#D55E00", "#CC79A7"],
    # Paul Tol, Colour Schemes, SRON/EPS/TN/09-002 issue 3.2 (2021)
    "Tol muted": ["#332288", "#88CCEE", "#44AA99", "#117733", "#999933",
                  "#DDCC77", "#CC6677", "#882255", "#AA4499"],
    "Tol bright": ["#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377", "#BBBBBB"],
    "Lab navy/blue": ["#1F3864", "#2E75B6", "#6FA8DC", "#7F7F7F", "#C55A11", "#548235"],
    "Grayscale": ["#000000", "#595959", "#A6A6A6", "#D9D9D9"],
}
PALETTE_ALIASES = {"Colorblind safe": "Okabe-Ito"}   # name used before v1.4
BUILTIN_PALETTES = set(PALETTES)
DEFAULT_PALETTE = "Journal"

FONT_PREFERENCE = ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans"]
# Prism draws significance stars with the heavy asterisk from Zapf Dingbats
STAR_GLYPH = "\u2731"
STAR_FONT_PREFERENCE = ["Zapf Dingbats", "ZapfDingbatsITC", "Segoe UI Symbol", "DejaVu Sans"]

STYLE_PRESETS = {
    "Lab template": {
        "font_size": 7.0,          # numbering, group labels, bracket text
        "title_extra": 1.0,        # axis titles and legend: 8 pt
        "graph_title_extra": 2.0,  # graph title (not present in the exports; 9 pt is a choice)
        "bold": False,
        "line": 0.72,              # axes, ticks, error bars, mean lines, brackets
        "thin": 0.36,              # bar/violin outlines, XY connecting lines, band edges
        "tick_dir": "in",
        "tick_len": 1.8,
        "tick_pad_x": 1.6,         # tick label offset from the X axis (pt)
        "tick_pad_y": 0.72,        # tick label offset from the Y axis (pt)
        "labelpad": 3.3,           # axis title gap from tick labels (pt)
        "labelpad_x": 4.6,         # X title sits a little lower in the exports
        "labelpad_y": 3.3,
        "fixed_title_distances": None,
        "fill_alpha": 0.5,         # Prism fill-opacity 0.502
        "heavy_stars": True,
        "ref_line_width": 1.44,    # dotted reference line in the XY export
        "axis_line": 0.72,
        "data_line": 0.72,
        "bracket_line": 0.72,
        "marker_edge": 0.72,       # outline of open markers (XY export)
        "markers": ["o", "s", "^", "D", "v", "h"],
        "square_scale": 1.414,     # Prism squares are 1.414x the circle size
        "bar_width": 0.65,
        "font_family": None,       # None: Arial, or the closest installed font
        "palette": None,
    },
    "Prism default": {
        "font_size": 11.0,
        "title_extra": 1.0,
        "graph_title_extra": 3.0,
        "bold": True,
        "line": 1.0,
        "thin": 0.5,
        "tick_dir": "out",
        # Prism lists tick length as "Normal" without a number; 4 pt is an estimate
        "tick_len": 4.0,
        "tick_pad_x": 3.0,
        "tick_pad_y": 3.0,
        "labelpad": 4.0,
        "labelpad_x": 4.0,
        "labelpad_y": 4.0,
        "fixed_title_distances": (0.32, 0.42),  # X and Y title distances from the axes (in)
        "fill_alpha": 0.5,
        "heavy_stars": False,
        "ref_line_width": 2.0,
        "axis_line": 1.0,
        "data_line": 1.0,
        "bracket_line": 1.0,
        "marker_edge": 1.0,
        "markers": ["o", "s", "^", "D", "v", "h"],
        "square_scale": 1.414,
        "bar_width": 0.65,
        "font_family": None,
        "palette": None,
    },
}
DEFAULT_STYLE = "Lab template"
DEFAULT_FONT_SIZE = STYLE_PRESETS[DEFAULT_STYLE]["font_size"]
DEFAULT_BOLD = STYLE_PRESETS[DEFAULT_STYLE]["bold"]
AXIS_LENGTH_IN = 2.0       # Y axis length in every export; X varies (1.5 to 2.4 in)

# Column-graph geometry measured from the exports, in units of column spacing
COLUMN_MARGIN = 0.66       # axis end to first/last column center
BAR_WIDTH = 0.65           # bar width; also the mean/median line width
COLUMN_CAP = 0.25          # error bar cap width as a fraction of bar width
GROUP_MARGIN = 0.535       # grouped: axis end to first/last cluster center
GROUP_SPAN = 0.82          # grouped: total width of one cluster
GROUP_BAR = 0.89           # grouped: bar width as a fraction of its slot
GROUP_CAP = 0.49           # grouped: cap width as a fraction of bar width
XY_SQUARE_SCALE = 1.414    # Prism squares are 1.414x the circle diameter

STAR_THRESHOLDS = [(0.0001, "****"), (0.001, "***"), (0.01, "**"), (0.05, "*")]
STAR_LEGEND = "* p < 0.05, ** p < 0.01, *** p < 0.001, **** p < 0.0001"

_font_cache = {}


def _installed():
    if "names" not in _font_cache:
        _font_cache["names"] = {f.name for f in font_manager.fontManager.ttflist}
    return _font_cache["names"]


def available_font():
    """First font in FONT_PREFERENCE installed on this computer."""
    return next((f for f in FONT_PREFERENCE if f in _installed()), "DejaVu Sans")


def star_font():
    """Font for the heavy asterisk. DejaVu Sans ships with matplotlib, so one is always found."""
    return next((f for f in STAR_FONT_PREFERENCE if f in _installed()), "DejaVu Sans")


# Marker shapes. Sizes are scaled so shapes look equally heavy (equal area to the circle);
# squares use the style's square_scale instead, which defaults to Prism's 1.414.
MARKER_CODES = {"Circle": "o", "Square": "s", "Triangle": "^", "Inverted triangle": "v",
                "Diamond": "D", "Hexagon": "h"}
MARKER_NAMES = {code: name for name, code in MARKER_CODES.items()}
EQUAL_AREA = {"o": 1.0, "s": 0.886, "^": 1.253, "v": 1.253, "D": 0.886, "h": 1.100}

# Editable style settings: key, label, kind, and limits. Used by the style editor and to
# validate styles loaded from files.
STYLE_FIELDS = [
    ("font_family", "Font", "font", None),
    ("font_size", "Numbering size (pt)", "float", (4, 24, 0.5)),
    ("title_extra", "Axis titles and legend, larger by (pt)", "float", (0, 12, 0.5)),
    ("graph_title_extra", "Graph title, larger by (pt)", "float", (0, 16, 0.5)),
    ("bold", "Bold text", "bool", None),
    ("axis_line", "Axes and ticks (pt)", "float", (0.1, 5, 0.05)),
    ("data_line", "Error bars and mean/median lines (pt)", "float", (0.1, 5, 0.05)),
    ("bracket_line", "Significance brackets (pt)", "float", (0.1, 5, 0.05)),
    ("thin", "Outlines and XY connecting lines (pt)", "float", (0.05, 5, 0.05)),
    ("ref_line_width", "Reference lines (pt)", "float", (0.1, 6, 0.05)),
    ("tick_dir", "Tick direction", "choice", ["in", "out", "inout"]),
    ("tick_len", "Tick length (pt)", "float", (0, 12, 0.1)),
    ("markers", "Marker order for Vary by group", "markers", None),
    ("marker_edge", "Open marker outline (pt)", "float", (0.1, 3, 0.05)),
    ("square_scale", "Square size relative to circle", "float", (0.5, 2, 0.01)),
    ("fill_alpha", "Fill opacity (0 to 1)", "float", (0, 1, 0.05)),
    ("bar_width", "Bar and violin width (fraction of spacing)", "float", (0.2, 0.95, 0.01)),
    ("heavy_stars", "Prism heavy asterisks for significance", "bool", None),
    ("palette", "Colors", "colors", None),
]
CUSTOM_STYLES = {}


def preset(name):
    """Settings for a built-in or custom style, with any missing keys filled in."""
    base = dict(STYLE_PRESETS[DEFAULT_STYLE])
    base.update(STYLE_PRESETS.get(name) or CUSTOM_STYLES.get(name) or {})
    return base


def style_names():
    return list(STYLE_PRESETS) + sorted(CUSTOM_STYLES)


def _is_hex(c):
    return isinstance(c, str) and len(c) == 7 and c[0] == "#" and all(
        ch in "0123456789abcdefABCDEF" for ch in c[1:])


def validate_style(values):
    """Clean a style dictionary: clamp numbers to their limits and drop invalid entries."""
    out = {}
    for key, _label, kind, spec in STYLE_FIELDS:
        if key not in values:
            continue
        v = values[key]
        if kind == "float":
            try:
                lo, hi, _step = spec
                out[key] = float(min(max(float(v), lo), hi))
            except (TypeError, ValueError):
                pass
        elif kind == "bool":
            out[key] = bool(v)
        elif kind == "choice" and v in spec:
            out[key] = v
        elif kind == "font":
            out[key] = str(v) if v else None
        elif kind == "markers" and isinstance(v, (list, tuple)):
            codes = [m for m in v if m in EQUAL_AREA]
            if codes:
                out[key] = codes
        elif kind == "colors":
            if v is None:
                out[key] = None
            elif isinstance(v, (list, tuple)):
                cols = [c for c in v if _is_hex(c)]
                out[key] = cols or None
    if "axis_line" in out:
        out["line"] = out["axis_line"]
    return out


def register_style(name, values):
    """Add or replace a custom style. Built-in style names cannot be replaced."""
    name = (name or "").strip()
    if not name:
        raise ValueError("A style needs a name.")
    if name in STYLE_PRESETS:
        raise ValueError(f"'{name}' is a built-in style. Save your changes under a new name.")
    clean = validate_style(values)
    style = dict(STYLE_PRESETS[DEFAULT_STYLE])
    style.update(clean)
    CUSTOM_STYLES[name] = style
    if style.get("palette"):
        PALETTES[name] = list(style["palette"])
    elif name not in BUILTIN_PALETTES:
        PALETTES.pop(name, None)
    return style


def remove_style(name):
    CUSTOM_STYLES.pop(name, None)
    if name not in BUILTIN_PALETTES:
        PALETTES.pop(name, None)


def style_definition(name):
    """The editable part of a custom style, for saving to a file or a project."""
    st = CUSTOM_STYLES.get(name)
    return None if st is None else {k: st[k] for k, *_ in STYLE_FIELDS if k in st}


def load_style_library(path):
    """Register every style in a JSON library file. Returns the names loaded."""
    import json
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    names = []
    for name, values in (data.get("styles", data) if isinstance(data, dict) else {}).items():
        if isinstance(values, dict) and name not in STYLE_PRESETS:
            register_style(name, values)
            names.append(name)
    return names


def save_style_library(path, names=None):
    import json
    names = sorted(CUSTOM_STYLES) if names is None else names
    data = {"stelplot_styles": 1, "styles": {n: style_definition(n) for n in names
                                             if n in CUSTOM_STYLES}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)


def apply_lab_style(font_size=DEFAULT_FONT_SIZE, bold=DEFAULT_BOLD, style=DEFAULT_STYLE):
    """Apply a style preset to matplotlib and return the preset values."""
    st = preset(style)
    font = st.get("font_family") if st.get("font_family") in _installed() else available_font()
    weight = "bold" if bold else "normal"
    title_size = font_size + st["title_extra"]
    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": [font],
        "font.weight": weight,
        "font.size": font_size,
        "axes.titlesize": font_size + st["graph_title_extra"],
        "axes.titleweight": "bold",
        "axes.labelsize": title_size,
        "axes.labelweight": weight,
        "axes.labelpad": st["labelpad"],
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
        "legend.fontsize": title_size,
        "axes.linewidth": st["axis_line"],
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "black",
        "axes.labelcolor": "black",
        "axes.facecolor": "none",
        "axes.grid": False,
        "xtick.color": "black",
        "ytick.color": "black",
        "xtick.direction": st["tick_dir"],
        "ytick.direction": st["tick_dir"],
        "xtick.major.size": st["tick_len"],
        "ytick.major.size": st["tick_len"],
        "xtick.major.width": st["axis_line"],
        "ytick.major.width": st["axis_line"],
        "xtick.major.pad": st["tick_pad_x"],
        "ytick.major.pad": st["tick_pad_y"],
        "xtick.minor.size": st["tick_len"] / 2,
        "ytick.minor.size": st["tick_len"] / 2,
        "xtick.minor.width": st["axis_line"] / 2,
        "ytick.minor.width": st["axis_line"] / 2,
        "xtick.minor.visible": False,
        "ytick.minor.visible": False,
        "lines.linewidth": st["data_line"],
        "lines.solid_capstyle": "round",
        "lines.dash_capstyle": "round",
        "patch.linewidth": st["thin"],
        "legend.frameon": False,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.transparent": False,
        "mathtext.fontset": "custom",
        "mathtext.rm": font,
        "mathtext.it": f"{font}:italic",
        "mathtext.bf": f"{font}:bold",
        "mathtext.sf": font,
        "mathtext.default": "bf" if bold else "regular",
        # Keep text as editable text in Illustrator
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    return st


def palette_colors(name, n):
    """Return n colors from the named palette, cycling if needed."""
    name = PALETTE_ALIASES.get(name, name)
    cols = PALETTES.get(name, PALETTES[DEFAULT_PALETTE])
    return [cols[i % len(cols)] for i in range(n)]


def tint(color, amount):
    """Blend a color toward white. 0 keeps the color, 1 gives white."""
    r, g, b = to_rgb(color)
    return (r + (1 - r) * amount, g + (1 - g) * amount, b + (1 - b) * amount)


def shade(color, amount):
    """Blend a color toward black. 0 keeps the color, 1 gives black."""
    r, g, b = to_rgb(color)
    return (r * (1 - amount), g * (1 - amount), b * (1 - amount))


def is_neutral(color):
    r, g, b = to_rgb(color)
    return max(r, g, b) - min(r, g, b) < 0.08


def band_colors(color):
    """Fill and dashed-edge colors for a shaded error band.

    Matches the XY export for black (#cccccc fill, #b3b3b3 edge); colored series
    use a lighter fill and a darker edge, similar to the export's pink band.
    """
    if is_neutral(color):
        return tint(color, 0.8), tint(color, 0.7)
    return tint(color, 0.55), shade(color, 0.5)


def star_label(p):
    """Return the significance summary for a p value."""
    if p is None or p != p:
        return ""
    for threshold, label in STAR_THRESHOLDS:
        if p < threshold:
            return label
    return "ns"


def format_p(p):
    """Format a p value the way Prism reports it."""
    if p is None or p != p:
        return "p = n/a"
    if p < 0.0001:
        return "p < 0.0001"
    if p > 0.9999:
        return "p > 0.9999"
    return f"p = {p:.4f}"
