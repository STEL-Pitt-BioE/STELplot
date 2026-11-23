"""Checks for reading Prism 10/11 .prism files. Run from the STELplot folder:

    python -m tests.test_prism_bundle

A small synthetic .prism file, built with the layout found in a real Prism 11.1 file, is
always tested. If a lab .prism file is placed in tests/fixtures/private/ (not shipped),
STELplot is also compared with the Prism 11 results stored in that file.
"""

__author__ = "Daniel Shiwarski"

import json
import math
import os
import tempfile
import zipfile

import numpy as np

from stelplot import anova, prism_import
from stelplot import stats_engine as se

PRIVATE = os.path.join(os.path.dirname(__file__), "fixtures", "private",
                       "aortagen_migration_9_30_26.prism")


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print(f"PASS  {name}")


def matches(value, prism_value):
    if prism_value == 0:
        return abs(value) < 5e-4
    digits = 4 - int(math.floor(math.log10(abs(prism_value)))) - 1
    return round(value, digits) == round(prism_value, digits)


def build_bundle(path):
    files = {"document.json": json.dumps({"sheets": {"data": ["S1", "S2", "S3", "S4"]}})}

    def sheet(uid, title, fmt, dfmt, sets, table_uid, **extra):
        files[f"data/sheets/{uid}/sheet.json"] = json.dumps(
            {"uid": uid, "title": title,
             "table": dict(uid=table_uid, format=fmt, dataFormat=dfmt, dataSets=sets, **extra)})

    def data_set(uid, title, n_rep):
        files[f"data/sets/{uid}.json"] = json.dumps(
            {"uid": uid, "title": title, "replicates": [{"valueType": "real"}] * n_rep})

    sheet("S1", "Column test", "column", "y_single", ["A", "B"], "T1")
    data_set("A", "Control", 1)
    data_set("B", "Drug", 1)
    files["data/tables/T1/data.csv"] = "1.5,3\n2.5,4\n,5\n"
    sheet("S2", "Grouped test", "grouped", "y_replicates", ["C", "D"], "T2",
          replicatesCount=2, rowTitlesDataSet="RT")
    data_set("C", "Before", 2)
    data_set("D", "After", 2)
    files["data/tables/T2/data.csv"] = "Wild type,1,3,5,7\nMutant ,2,4,6,\n"
    sheet("S3", "XY test", "xy", "y_single", [], "T3")
    sheet("S4", "Summary data", "column", "mean_sd_n", ["E"], "T4")
    data_set("E", "Group", 3)
    with zipfile.ZipFile(path, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)


def test_synthetic_bundle():
    path = os.path.join(tempfile.mkdtemp(), "test.prism")
    build_bundle(path)
    tables = prism_import.read_any(path)
    check(".prism tables are read in Prism's order with the right kinds",
          [t.kind for t in tables] == ["column", "grouped", "unsupported", "unsupported"])
    col = tables[0].to_state()
    check(".prism column table keeps titles, values, and blanks for unequal n",
          col["headers"] == ["Control", "Drug"] and col["cells"][0] == ["1.5", "3"]
          and col["cells"][2] == ["", "5"])
    grp = tables[1].to_state()
    check(".prism grouped table keeps row titles and replicate order",
          grp["cells"][0] == ["Wild type", "1", "3", "5", "7"] and grp["reps"] == 2
          and grp["cells"][1] == ["Mutant", "2", "4", "6", ""])
    check(".prism XY tables point the user to .pzfx", ".pzfx" in tables[2].message)
    check(".prism summary (mean/SD/N) tables are refused with a reason", "raw values" in tables[3].message)
    check(".pzfx files still go through the XML reader",
          prism_import.read_any(os.path.join(os.path.dirname(__file__), "fixtures", "sample.pzfx"))[0].kind
          == "column")


def test_lab_file_against_prism():
    if not os.path.exists(PRIVATE):
        print("SKIP  lab .prism file not in tests/fixtures/private")
        return
    T = {t.title: t for t in prism_import.read_any(PRIVATE)}
    col = lambda title: [(n, np.array(s[0], float)) for n, s in T[title].columns]
    check("all 17 data tables in the lab file are found", len(T) >= 16)
    r = se.run_column_stats(col("CP s6 vs CA s4 migrated"), "Welch's t-test")
    c = r.comparisons[0]
    check("Welch's t test matches Prism 11 (t 24.57, df 1147, B - A 70.45, CI 64.83 to 76.08)",
          "t = 24.57, df = 1147" in r.omnibus and matches(c.diff, 70.45) and matches(c.ci_low, 64.83)
          and matches(c.ci_high, 76.08) and matches(c.se, 2.868))
    t = T["% migrated grouped"]
    R, C, K = len(t.row_titles), len(t.columns), t.replicates
    D = np.array([[t.columns[c][1][k][r] for c in range(C) for k in range(K)]
                  for r in range(R)]).reshape(R, C, K)
    res = anova.run_grouped(t.row_titles, [c[0] for c in t.columns], D)
    rows = {r.source: r for r in res.rows}
    expect = {"Interaction": (193.6, 0.4676, 0.7130), "Row factor": (371.6, 0.8977, 0.4834),
              "Column factor": (860.7, 6.237, 0.0371)}
    check("ordinary two-way ANOVA matches Prism 11 (SS, F, P for every source)",
          all(matches(rows[k].ss, ss) and matches(rows[k].f, f) and round(rows[k].p, 4) == p
              for k, (ss, f, p) in expect.items()) and matches(rows["Residual"].ss, 1104))
    cd = res.col_diff
    check("ordinary two-way difference between column means matches Prism 11",
          matches(cd["diff"], -14.67) and matches(cd["se"], 5.873) and matches(cd["ci"][0], -28.21)
          and matches(cd["ci"][1], -1.124))
    r = se.run_column_stats(col("all groups at 300"), "One-way ANOVA")
    q = [11.92, 19.96, 30.36, 7.870, 17.01, 8.312]
    s = [5.410, 5.125, 4.348, 4.808, 3.970, 3.572]
    check("one-way ANOVA with unequal n matches Prism 11 (F 179.5, Tukey SE and q)",
          matches(r.summary["F"], 179.5) and matches(r.summary["R squared"], 0.09195)
          and all(matches(c.stat, qq) and matches(c.se, ss) for c, qq, ss in zip(r.comparisons, q, s)))
    r = se.run_column_stats(col("% migrated all groups"), "Repeated-measures one-way ANOVA",
                            "All pairs", gg=True)
    adj = [0.6002, 0.2880, 0.0107, 0.9991, 0.0102, 0.0217]
    q = [1.900, 3.183, 11.90, 0.1770, 12.08, 9.264]
    check("RM one-way ANOVA with Geisser-Greenhouse matches Prism 11 (F (1.544, 4.631) = 20.12)",
          "F (1.544, 4.631) = 20.12" in r.omnibus and "0.5145" in r.extra_lines[1])
    check("Tukey after RM one-way ANOVA matches Prism 11 (adjusted P and q, DF = n - 1)",
          all(round(c.p, 4) == a and matches(c.stat, qq) and c.df == 3
              for c, a, qq in zip(r.comparisons, adj, q)))
    from stelplot.prism_format import ci_text, num, p_text
    res = anova.run_grouped(t.row_titles, [c[0] for c in t.columns], D, comparisons=anova.CELLS,
                            correction="Tukey", model=anova.MAIN_EFFECTS)
    rows = {r.source: r for r in res.rows}
    check("two-way ANOVA, main effects only, matches Prism 11 (F (3, 11) = 1.050, F (1, 11) = 7.297)",
          num(rows["Row factor"].f) == "1.050" and p_text(rows["Row factor"].p) == "0.4090"
          and num(rows["Column factor"].f) == "7.297" and p_text(rows["Column factor"].p) == "0.0206"
          and int(rows["Residual"].df) == 11 and num(res.col_diff["se"]) == "5.430")
    prism_cells = [  # Prism 11: Tukey, compare cell means regardless of rows and columns
        ("-14.67", "-34.64 to 5.307", "0.2176"), ("1.204", "-27.05 to 29.45", ">0.9999"),
        ("-13.46", "-48.06 to 21.13", "0.8260"), ("5.680", "-22.57 to 33.93", "0.9933"),
        ("-8.989", "-43.59 to 25.61", "0.9723"), ("12.29", "-15.96 to 40.54", "0.7419"),
        ("-2.375", "-36.97 to 32.22", ">0.9999"), ("15.87", "-18.73 to 50.47", "0.6950"),
        ("1.204", "-27.05 to 29.45", ">0.9999"), ("20.35", "-14.25 to 54.95", "0.4355"),
        ("5.680", "-22.57 to 33.93", "0.9933"), ("26.96", "-7.636 to 61.56", "0.1718"),
        ("12.29", "-15.96 to 40.54", "0.7419"), ("-14.67", "-34.64 to 5.307", "0.2176")]
    mine = [(num(c.diff), ci_text(c.ci_low, c.ci_high), p_text(c.p)) for c in res.comparisons[:14]]
    check("cell-by-cell Tukey comparisons match Prism 11 (first 14 of 28: LS mean diff, CI, adjusted P)",
          mine == prism_cells and len(res.comparisons) == 28)


if __name__ == "__main__":
    test_synthetic_bundle()
    test_lab_file_against_prism()
    print("\nAll .prism checks passed.")
