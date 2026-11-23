"""Colorblind-safety checks for the default Journal palette. Run from the STELplot folder:

    python -m tests.test_palette
"""

__author__ = "Daniel Shiwarski"

import numpy as np

from stelplot.color_check import ciede2000, worst_pair
from stelplot.lab_style import PALETTES, palette_colors


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print(f"PASS  {name}")


def test_ciede2000():
    d1 = ciede2000(np.array([50.0, 2.6772, -79.7751]), np.array([50.0, 0.0, -82.7485]))
    d2 = ciede2000(np.array([50.0, 2.5, 0.0]), np.array([73.0, 25.0, -18.0]))
    check("CIEDE2000 matches published test pairs (2.0425, 27.1492)",
          round(d1, 4) == 2.0425 and round(d2, 4) == 27.1492)


def test_journal_palette():
    pal = PALETTES["Journal"]
    scores = {n: worst_pair(pal[:n])[0] for n in range(2, 7)}
    check(f"Journal: first 2-3 colors differ by >= 20 under every vision type "
          f"({scores[2]:.1f}, {scores[3]:.1f})", scores[2] >= 20 and scores[3] >= 20)
    check(f"Journal: first 4 colors >= 11 ({scores[4]:.1f}); all 6 >= 9.5 ({scores[6]:.1f})",
          scores[4] >= 11 and scores[6] >= 9.5)
    others = {name: worst_pair(PALETTES[name][:6])[0] for name in ("Okabe-Ito", "Tol muted", "Lab template")}
    check("Journal beats Okabe-Ito, Tol muted, and the Lab template on the same test "
          + ", ".join(f"{k} {v:.1f}" for k, v in others.items()),
          all(scores[6] > v for v in others.values()))
    check("Journal is the default palette", palette_colors("Journal", 2) == pal[:2])
    check("projects saved with the old palette name still load",
          palette_colors("Colorblind safe", 3) == PALETTES["Okabe-Ito"][:3])


if __name__ == "__main__":
    test_ciede2000()
    test_journal_palette()
    print("\nAll palette checks passed.")
