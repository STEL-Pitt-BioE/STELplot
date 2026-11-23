"""3D graphs: scatter, line, surface, wireframe, and bars, with an optional fourth variable
shown as color (a color column in a 3D table, or the bar values of a grouped table)."""

__author__ = "Daniel Shiwarski"

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from matplotlib.colors import Normalize, to_rgba

from .lab_style import (AXIS_LENGTH_IN, DEFAULT_BOLD, DEFAULT_FONT_SIZE, DEFAULT_PALETTE,
                        DEFAULT_STYLE, apply_lab_style, palette_colors)

KINDS_3D = ["3D scatter", "3D line", "Surface", "Wireframe", "3D bars"]
COLOR_BY = ["Z value", "Color column (4th variable)", "Single color"]
GROUPED_COLOR_BY = ["Data set", "Value"]
PROJECTIONS = ["Perspective", "Orthographic"]


@dataclass
class View3DOptions:
    elev: float = 25.0
    azim: float = -60.0
    projection: str = "Perspective"
    color_by: str = "Z value"
    cmap: str = "Viridis"
    color_label: str = ""
    z_label: str = "Z"
    z_min: Optional[float] = None
    z_max: Optional[float] = None
    bar_width: float = 0.7          # fraction of the spacing between bars
    colorbar: bool = True


@dataclass
class XYZPlotOptions:
    plot_type: str = "3D scatter"
    title: str = ""
    x_label: str = "X"
    y_label: str = "Y"
    width_in: float = AXIS_LENGTH_IN * 1.5
    height_in: float = AXIS_LENGTH_IN * 1.5
    font_size: float = DEFAULT_FONT_SIZE
    bold: bool = DEFAULT_BOLD
    style: str = DEFAULT_STYLE
    palette: str = DEFAULT_PALETTE
    point_size: float = 4.0
    view3d: View3DOptions = field(default_factory=View3DOptions)
    frame: str = "Box"


def _axes3d(fig, opts, st, with_bar):
    """3D axes sized to the X and Y axis length settings, with room for labels."""
    w, h = opts.width_in, opts.height_in
    bar = 1.15 if with_bar else 0.0
    W, H = w + 0.6 + bar, h + 0.5 + (0.25 if opts.title else 0)
    fig.set_size_inches(W, H, forward=False)
    ax = fig.add_axes([0.3 / W, 0.25 / H, w / W, h / H], projection="3d")
    v = opts.view3d
    ax.view_init(elev=v.elev, azim=v.azim)
    ax.set_proj_type("ortho" if v.projection == "Orthographic" else "persp")
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((1, 1, 1, 0))
        axis.pane.set_edgecolor("#bfbfbf")
        axis._axinfo["grid"].update(color="#e3e3e3", linewidth=st["thin"])
        axis.line.set_linewidth(st["axis_line"])
    ax.tick_params(labelsize=opts.font_size, pad=0)
    from matplotlib.ticker import MaxNLocator
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.set_major_locator(MaxNLocator(nbins=4, steps=[1, 2, 2.5, 5, 10]))
    if opts.title:
        ax.set_title(opts.title, pad=4)
    return ax, W, H


def _colorbar(fig, mappable, opts, st, W, H, label):
    cax = fig.add_axes([(0.3 + opts.width_in + 0.6) / W, 0.25 / H + opts.height_in * 0.15 / H,
                        0.12 / W, opts.height_in * 0.7 / H])
    cb = fig.colorbar(mappable, cax=cax)
    cb.outline.set_linewidth(st["axis_line"])
    cb.ax.tick_params(width=st["axis_line"], length=st["tick_len"], labelsize=opts.font_size)
    cb.set_label(label, fontsize=opts.font_size + st["title_extra"])
    return cb


def _labels(ax, opts, st):
    fs = opts.font_size + st["title_extra"]
    ax.set_xlabel(opts.x_label, fontsize=fs, labelpad=1)
    ax.set_ylabel(opts.y_label, fontsize=fs, labelpad=1)
    ax.set_zlabel(opts.view3d.z_label, fontsize=fs, labelpad=4)


def _zlim(ax, z, v, floor=None):
    lo = float(np.nanmin(z)) if floor is None else min(floor, float(np.nanmin(z)))
    hi = float(np.nanmax(z))
    if hi <= lo:
        hi = lo + 1.0
    ax.set_zlim(v.z_min if v.z_min is not None else lo, v.z_max if v.z_max is not None else hi)


def _is_grid(x, y):
    xs, ys = np.unique(x), np.unique(y)
    if xs.size < 2 or ys.size < 2 or xs.size * ys.size != x.size:
        return None
    pairs = {(a, b) for a, b in zip(x, y)}
    return (xs, ys) if len(pairs) == x.size else None


def render_xyz(fig, x, y, z, color, opts):
    """3D graph from a 3D table. color (optional) is the fourth variable for each row."""
    from .plotting import colormap, _empty_state
    fig.clear()
    fig.stel_notes = []
    st = apply_lab_style(opts.font_size, opts.bold, opts.style)
    x, y, z = (np.asarray(a, float) for a in (x, y, z))
    c = np.asarray(color, float) if color is not None else np.full(x.shape, np.nan)
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    kind = opts.plot_type
    v = opts.view3d
    by = v.color_by
    if by == COLOR_BY[1] and not np.isfinite(c[ok]).any():
        fig.stel_notes.append("The Color column is empty, so color shows Z instead.")
        by = COLOR_BY[0]
    if by == COLOR_BY[1]:
        missing = int(np.sum(ok & ~np.isfinite(c)))
        if missing:
            fig.stel_notes.append(f"{missing} row(s) have no color value and are drawn gray.")
    x, y, z, c = x[ok], y[ok], z[ok], c[ok]
    need = 3 if kind in ("Surface", "Wireframe") else 1
    if x.size < need:
        _empty_state(fig, "Enter X, Y, and Z values in the first three columns.\nThe fourth column "
                          "(optional) sets the color." if x.size == 0 else
                     "A surface needs at least three points that are not on one line.", opts)
        return None
    shade = z if by == COLOR_BY[0] else c
    single = by == COLOR_BY[2]
    cmap = colormap(v.cmap)
    good = shade[np.isfinite(shade)]
    norm = Normalize(float(good.min()) if good.size else 0.0, float(good.max()) if good.size else 1.0)
    if norm.vmax <= norm.vmin:
        norm = Normalize(norm.vmin, norm.vmin + 1.0)
    base_color = palette_colors(opts.palette, 2)[1 if palette_colors(opts.palette, 1)[0] == "#000000"
                                                 else 0]

    def colors_for(values):
        if single:
            return [to_rgba(base_color)] * len(values)
        return [cmap(norm(val)) if np.isfinite(val) else to_rgba("#bfbfbf") for val in values]

    with_bar = not single and v.colorbar
    ax, W, H = _axes3d(fig, opts, st, with_bar)
    size = opts.point_size ** 2
    if kind == "3D scatter":
        ax.scatter(x, y, z, s=size, c=colors_for(shade), edgecolors="none", depthshade=False)
    elif kind == "3D line":
        ax.plot(x, y, z, color="#404040" if not single else base_color, linewidth=st["data_line"])
        ax.scatter(x, y, z, s=size, c=colors_for(shade), edgecolors="none", depthshade=False)
    elif kind in ("Surface", "Wireframe"):
        grid = _is_grid(x, y)
        if grid is not None:
            xs, ys = grid
            Z = np.full((ys.size, xs.size), np.nan)
            S = np.full((ys.size, xs.size), np.nan)
            ix, iy = np.searchsorted(xs, x), np.searchsorted(ys, y)
            Z[iy, ix] = z
            S[iy, ix] = shade
            X, Y = np.meshgrid(xs, ys)
        if kind == "Surface" and grid is not None:
            # Color each patch by the mean of its four corners
            corners = np.stack([S[:-1, :-1], S[1:, :-1], S[:-1, 1:], S[1:, 1:]])
            with np.errstate(all="ignore"):
                patch = np.nanmean(corners, axis=0)
            faces = np.array(colors_for(patch.ravel())).reshape(patch.shape + (4,))
            ax.plot_surface(X, Y, Z, facecolors=faces, linewidth=0, antialiased=True, shade=False,
                            rstride=1, cstride=1)
        elif kind == "Wireframe" and grid is not None:
            ax.plot_wireframe(X, Y, Z, color=base_color if single else "#404040",
                              linewidth=st["thin"])
            if not single:
                ax.scatter(x, y, z, s=size * 0.6, c=colors_for(shade), edgecolors="none",
                           depthshade=False)
        else:
            from matplotlib.tri import Triangulation
            try:
                tri = Triangulation(x, y)
            except (ValueError, RuntimeError):
                _empty_state(fig, "These X and Y values cannot form a surface (they may lie on one "
                                  "line).", opts)
                return None
            if kind == "Wireframe":
                ax.plot_trisurf(tri, z, color=(0, 0, 0, 0), edgecolor="#404040",
                                linewidth=st["thin"])
            else:
                surf = ax.plot_trisurf(tri, z, linewidth=0, antialiased=True, shade=False)
                faces = shade[tri.triangles]
                face_vals = np.array([np.nanmean(f) if np.isfinite(f).any() else np.nan
                                      for f in faces])
                surf.set_facecolor(colors_for(face_vals))
                surf.set_edgecolor("none")
    elif kind == "3D bars":
        def width(vals):
            u = np.unique(vals)
            return (float(np.min(np.diff(u))) if u.size > 1 else 1.0) * v.bar_width
        dx, dy = width(x), width(y)
        floor = 0.0 if v.z_min is None else v.z_min
        ax.bar3d(x - dx / 2, y - dy / 2, np.full(x.size, floor), dx, dy, z - floor,
                 color=colors_for(shade), edgecolor="#404040", linewidth=st["thin"] * 0.5,
                 shade=True)
        _zlim(ax, z, v, floor=floor)
    if kind != "3D bars":
        _zlim(ax, z, v)
    _labels(ax, opts, st)
    if with_bar:
        from matplotlib.cm import ScalarMappable
        label = v.color_label or (v.z_label if by == COLOR_BY[0] else "Color")
        _colorbar(fig, ScalarMappable(norm=norm, cmap=cmap), opts, st, W, H, label)
    return ax


def render_grouped_bars3d(fig, row_labels, col_names, D, opts, st):
    """3D bars from a grouped table: rows along one axis, data sets along the other, and the
    cell mean as height. Color shows the data set, or the value on a color scale."""
    from .plotting import colormap
    from .stats_engine import finite
    v = opts.view3d or View3DOptions(color_by="Data set")
    R, C, _ = D.shape
    means = np.full((R, C), np.nan)
    for r in range(R):
        for c in range(C):
            vals = finite(D[r, c])
            if vals.size:
                means[r, c] = float(np.mean(vals))
    by_value = v.color_by == "Value"
    cmap = colormap(v.cmap)
    good = means[np.isfinite(means)]
    norm = Normalize(float(min(good.min(), 0)), float(good.max()) if good.size else 1.0)
    proxy = XYZPlotOptions(title=opts.title, x_label=opts.x_label, y_label="", view3d=v,
                           width_in=opts.width_in, height_in=opts.height_in,
                           font_size=opts.font_size, bold=opts.bold, style=opts.style,
                           palette=opts.palette)
    ax, W, H = _axes3d(fig, proxy, st, by_value and v.colorbar)
    pal = palette_colors(opts.palette, C)
    rr, cc = np.nonzero(np.isfinite(means))
    dz = means[rr, cc]
    floor = 0.0 if v.z_min is None else v.z_min
    w = v.bar_width
    colors = ([cmap(norm(val)) for val in dz] if by_value else [to_rgba(pal[c]) for c in cc])
    ax.bar3d(rr - w / 2, cc - w / 2, np.full(dz.size, floor), w, w, dz - floor, color=colors,
             edgecolor="#404040", linewidth=st["thin"] * 0.5, shade=True)
    ax.set_xticks(range(R))
    ax.set_xticklabels(row_labels, fontsize=opts.font_size)
    ax.set_yticks(range(C))
    ax.set_yticklabels(col_names, fontsize=opts.font_size)
    _zlim(ax, dz, v, floor=floor)
    fs = opts.font_size + st["title_extra"]
    if opts.x_label:
        ax.set_xlabel(opts.x_label, fontsize=fs)
    ax.set_zlabel(opts.y_label if opts.y_label else v.z_label, fontsize=fs)
    if by_value and v.colorbar:
        from matplotlib.cm import ScalarMappable
        _colorbar(fig, ScalarMappable(norm=norm, cmap=cmap), proxy, st, W, H,
                  v.color_label or opts.y_label)
    return ax
