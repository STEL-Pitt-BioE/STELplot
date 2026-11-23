"""STELplot checked against Prism 9.4.1 results stored in the lab's Prism template.

The data and Prism's reported values below were read from PrismTemplates.pzfx.
Run from the STELplot folder:

    python -m tests.test_prism
"""

__author__ = "Daniel Shiwarski"

import math
import os

import numpy as np
from scipy import stats

from stelplot import anova, prism_import
from stelplot import stats_engine as se


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print(f"PASS  {name}")


def matches(value, prism_value):
    """True when value rounds to Prism's displayed number (4 significant digits)."""
    if prism_value == 0:
        return abs(value) < 5e-4
    digits = 4 - int(math.floor(math.log10(abs(prism_value)))) - 1
    return round(value, digits) == round(prism_value, digits)


def test_one_way_tukey():
    groups = [("Untreated", np.array([3.4, 4.3, 3.0, 3.9, 4.1])),
              ("Placebo", np.array([2.3, 5.2, 4.5, 3.1, 5.0])),
              ("Treated", np.array([4.2, 7.8, 5.9, 6.4, 7.6]))]
    r = se.run_column_stats(groups, "One-way ANOVA")
    f, p = stats.f_oneway(*[g for _, g in groups])
    check("one-way F matches Prism (7.882)", matches(float(f), 7.882))
    check("one-way P matches Prism (0.0065)", round(float(p), 4) == 0.0065)
    check("R squared matches Prism (0.5678)", "R squared = 0.5678" in r.omnibus)
    check("Brown-Forsythe matches Prism (F (2, 12) = 1.212, P = 0.3316)",
          "F (2, 12) = 1.212, p = 0.3316" in r.extra_lines[0])
    check("Bartlett matches Prism (3.263, P = 0.1956)",
          "3.263, p = 0.1956" in r.extra_lines[1])
    prism = {("Untreated", "Placebo"): (-0.2800, -2.229, 1.669, 0.9227),
             ("Untreated", "Treated"): (-2.640, -4.589, -0.6912, 0.0092),
             ("Placebo", "Treated"): (-2.360, -4.309, -0.4112, 0.0183)}
    for c in r.comparisons:
        diff, lo, hi, padj = prism[(c.group1, c.group2)]
        check(f"Tukey {c.group1} vs. {c.group2} matches Prism",
              matches(c.diff, diff) and matches(c.ci_low, lo) and matches(c.ci_high, hi)
              and round(c.p, 4) == padj)


def _rm_template():
    rows = ["Wild type", "Tame", "Raging wild"]
    before = [[34, 12, 55], [65, 35, 99], [34, 12, 55]]   # replicate subcolumns, values by row
    after = [[54, 13, 79], [91, 29, 121], [91, 29, 121]]
    D = np.zeros((3, 2, 3))
    for k in range(3):
        D[:, 0, k] = before[k]
        D[:, 1, k] = after[k]
    return rows, ["Before", "After"], D


def test_two_way_rm():
    rows, cols, D = _rm_template()
    res = anova.run_grouped(rows, cols, D, design=anova.ACROSS_ROW,
                            comparisons="Compare columns within each row", gg=False)
    prism = {"Interaction": (1020, 4.652, 0.1489), "Row factor": (13502, 61.57, 0.0081),
             "Column factor": (2863, 13.05, 0.0083), "Subject": (3393, 15.47, 0.1070),
             "Residual": (1151, None, None)}
    for r in res.rows:
        ss, pct, p = prism[r.source]
        ok = matches(r.ss, ss) and (pct is None or matches(r.pct, pct))
        ok = ok and (p is None or round(r.p, 4) == p)
        check(f"RM two-way {r.source.lower()} matches Prism", ok)
    prism_mc = {"Wild type": (-34.33, -71.35, 2.685), "Tame": (-4.000, -41.02, 33.02),
                "Raging wild": (-37.33, -74.35, -0.3154)}
    check("RM comparisons use pooled residual error, as Prism does",
          "pooled residual error" in res.posthoc)
    for c in res.comparisons:
        diff, lo, hi = prism_mc[c.context]
        se_diff = abs(c.diff) and (c.ci_high - c.ci_low) / 2 / float(
            stats.t.ppf(1 - (-math.expm1(math.log1p(-0.05) / 3)) / 2, 6))
        check(f"Šídák {c.context} Before vs. After matches Prism (SE of diff. 11.31)",
              matches(c.diff, diff) and matches(c.ci_low, lo) and matches(c.ci_high, hi)
              and matches(se_diff, 11.31))


def test_importer():
    path = os.path.join(os.path.dirname(__file__), "fixtures", "sample.pzfx")
    tables = prism_import.read_pzfx(path)
    check("importer finds four tables", [t.kind for t in tables] ==
          ["column", "grouped", "xy", "unsupported"])
    col = tables[0].to_state()
    check("excluded Prism values come in marked as excluded, with their value kept",
          col["cells"][2][0] == "9.9" and [2, 0] in col["excluded"] and tables[0].excluded == 1
          and math.isnan(tables[0].columns[0][1][0][2]))
    grp = tables[1].to_state()
    check("grouped table keeps row titles and replicate order",
          grp["cells"][0] == ["Wild type", "1", "3", "5", "7"] and grp["reps"] == 2)
    xy = tables[2].to_state()
    check("XY table keeps the X title", xy["x_name"] == "Hours" and xy["cells"][2][:2] == ["2", "30"])
    check("summary (mean/SD/N) tables are refused with a reason", "raw values" in tables[3].message)


def test_template_file():
    """Runs only when the lab's Prism template is present in tests/fixtures."""
    path = os.path.join(os.path.dirname(__file__), "fixtures", "PrismTemplates.pzfx")
    if not os.path.exists(path):
        print("SKIP  lab template not found")
        return
    tables = {t.title: t for t in prism_import.read_pzfx(path)}
    t = tables["Bar Mean Error all PointsViolin Graph"]
    groups = [(name, np.array(subs[0], float)) for name, subs in t.columns]
    r = se.run_column_stats(groups, "One-way ANOVA")
    check("four-group ANOVA with Prism-excluded values matches Prism (F (3, 1292) = 54.66)",
          "F (3, 1292) = 54.66" in r.omnibus and "R squared = 0.1126" in r.omnibus)
    check("four-group Brown-Forsythe and Bartlett match Prism",
          "= 3.524, p = 0.0145" in r.extra_lines[0] and "27.93" in r.extra_lines[1])
    prism = [(28.31, 20.54, 36.08), (-3.760, -10.42, 2.902), (21.85, 14.52, 29.19),
             (-32.07, -40.11, -24.03), (-6.456, -15.06, 2.151), (25.61, 17.99, 33.24)]
    check("all six Tukey differences and CIs match Prism",
          all(matches(c.diff, d) and matches(c.ci_low, lo) and matches(c.ci_high, hi)
              for c, (d, lo, hi) in zip(r.comparisons, prism)))


def _compare_csv(prism_name, write):
    path = os.path.join(os.path.dirname(__file__), "fixtures", "prism_results", prism_name)
    if not os.path.exists(path):
        print(f"SKIP  {prism_name} not found")
        return
    import tempfile
    out = os.path.join(tempfile.mkdtemp(), "stelplot.csv")
    write(out)
    norm = lambda line: line.rstrip("\r\n").replace('"    Mean of Before "', '"    Mean of Before"')
    prism = [norm(x) for x in open(path, encoding="utf-8")]
    mine = [norm(x) for x in open(out, encoding="utf-8")][:len(prism)]
    same = sum(a == b for a, b in zip(prism, mine))
    check(f"{prism_name}: all {len(prism)} lines identical to Prism's sheet ({same} match)",
          same == len(prism))


def test_prism_sheets():
    groups = [("Untreated", np.array([3.4, 4.3, 3.0, 3.9, 4.1])),
              ("Placebo", np.array([2.3, 5.2, 4.5, 3.1, 5.0])),
              ("Treated", np.array([4.2, 7.8, 5.9, 6.4, 7.6]))]
    r = se.run_column_stats(groups, "One-way ANOVA")
    _compare_csv("Ordinary_one-way_ANOVA_of_Column_Data_All_Points_Shown.csv",
                 lambda out: se.write_column_csv(out, r, "Column Data All Points Shown"))
    prism_details = [(0.7305, 0.5421), (0.7305, 5.111), (0.7305, 4.569)]
    check("Tukey test details (SE of diff., q, DF) match Prism",
          all(matches(c.se, s_) and matches(c.stat, q) and c.df == 12
              for c, (s_, q) in zip(r.comparisons, prism_details)))
    rows, cols, D = _rm_template()
    res = anova.run_grouped(rows, cols, D, design=anova.ACROSS_ROW,
                            comparisons="Compare columns within each row", gg=False)
    _compare_csv("2way_ANOVA_of_Column_Data_Grouped__RM_Two-way_ANOVA__rows_.csv",
                 lambda out: anova.write_grouped_csv(out, res, rows, cols, D,
                                                     "Column Data Grouped: RM Two-way ANOVA (rows)",
                                                     "Row Factor", "Time"))
    prism_mc = {"Wild type": (0.0672, 3.036), "Tame": (0.9815, 0.3538), "Raging wild": (0.0483, 3.302)}
    check("Šídák adjusted P values and t match Prism's stored results",
          all(round(c.p, 4) == prism_mc[c.context][0] and matches(c.stat, prism_mc[c.context][1])
              for c in res.comparisons))
    cd = res.col_diff
    check("difference between column means matches Prism (-25.22, SE 6.528, -41.20 to -9.248)",
          matches(cd["means"][0], 44.56) and matches(cd["means"][1], 69.78)
          and matches(cd["diff"], -25.22) and matches(cd["se"], 6.528)
          and matches(cd["ci"][0], -41.20) and matches(cd["ci"][1], -9.248))


def test_template_sheet_four_groups():
    path = os.path.join(os.path.dirname(__file__), "fixtures", "PrismTemplates.pzfx")
    if not os.path.exists(path):
        print("SKIP  lab template not found")
        return
    t = {t.title: t for t in prism_import.read_pzfx(path)}["Bar Mean Error all PointsViolin Graph"]
    groups = [(name, np.array(subs[0], float)) for name, subs in t.columns]
    r = se.run_column_stats(groups, "One-way ANOVA")
    _compare_csv("Ordinary_one-way_ANOVA_of_Bar_Mean_Error_all_PointsViolin_Graph.csv",
                 lambda out: se.write_column_csv(out, r, "Bar Mean Error all PointsViolin Graph"))


if __name__ == "__main__":
    test_one_way_tukey()
    test_two_way_rm()
    test_importer()
    test_template_file()
    test_prism_sheets()
    test_template_sheet_four_groups()
    print("\nAll Prism comparison checks passed.")
