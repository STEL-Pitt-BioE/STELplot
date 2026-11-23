"""Colorblind-safety check for palettes.

Simulates deuteranopia, protanopia, and tritanopia with the Machado, Oliveira &
Fernandes (2009) matrices at full severity (doi:10.1109/TVCG.2009.113) and measures
color differences with CIEDE2000. A palette's score is its weakest pair: the smallest
difference between any two colors, as solid colors and as 50% fills (STELplot's bar
fill), across normal vision and the three simulations.
"""

__author__ = "Daniel Shiwarski"

from itertools import combinations

import numpy as np

CVD = {
    "protanopia": np.array([[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216],
                            [-0.003882, -0.048116, 1.051998]]),
    "deuteranopia": np.array([[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413],
                              [-0.011820, 0.042940, 0.968881]]),
    "tritanopia": np.array([[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602],
                            [0.004733, 0.691367, 0.303900]]),
}
VISION = ["normal", "deuteranopia", "protanopia", "tritanopia"]
_M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
               [0.0193339, 0.1191920, 0.9503041]])


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


def simulate(rgb, kind):
    """sRGB color as seen with the given color vision deficiency."""
    return rgb if kind == "normal" else to_srgb(CVD[kind] @ to_linear(rgb))


def lab(rgb):
    xyz = _M @ to_linear(rgb) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def ciede2000(lab1, lab2):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    cb = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    g = 0.5 * (1 - np.sqrt(cb ** 7 / (cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    dlp, dcp = L2 - L1, c2p - c1p
    dh = h2p - h1p
    if c1p * c2p == 0:
        dh = 0.0
    elif dh > 180:
        dh -= 360
    elif dh < -180:
        dh += 360
    dhp = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh / 2))
    lbp, cbp = (L1 + L2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    else:
        hbp = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    rc = 2 * np.sqrt(cbp ** 7 / (cbp ** 7 + 25 ** 7))
    sl = 1 + 0.015 * (lbp - 50) ** 2 / np.sqrt(20 + (lbp - 50) ** 2)
    sc, sh = 1 + 0.045 * cbp, 1 + 0.015 * cbp * t
    rt = -np.sin(np.radians(60 * np.exp(-((hbp - 275) / 25) ** 2))) * rc
    return float(np.sqrt((dlp / sl) ** 2 + (dcp / sc) ** 2 + (dhp / sh) ** 2
                         + rt * (dcp / sc) * (dhp / sh)))


def worst_pair(colors, fill_alpha=0.5):
    """Return (smallest difference, vision type, 'solid' or 'fill', color 1, color 2)."""
    worst = (np.inf, None, None, None, None)
    for kind in VISION:
        for variant in ("solid", "fill"):
            rgbs = [hex_rgb(h) if variant == "solid" else fill_alpha * hex_rgb(h) + (1 - fill_alpha)
                    for h in colors]
            labs = [lab(simulate(c, kind)) for c in rgbs]
            for (i, a), (j, b) in combinations(enumerate(labs), 2):
                d = ciede2000(a, b)
                if d < worst[0]:
                    worst = (d, kind, variant, colors[i], colors[j])
    return worst
