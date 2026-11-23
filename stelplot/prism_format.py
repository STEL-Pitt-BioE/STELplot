"""Results in Prism's sheet layout.

Row labels, ordering, number formatting, and CSV quoting follow the Prism 9
results sheets exported from the lab template (one-way ANOVA and two-way RM
ANOVA). Multiple-comparison sheets follow the layout Prism stores in the
template file. The ordinary two-way layout is adapted from the RM layout and
has not been compared with a Prism export.
"""

__author__ = "Daniel Shiwarski"

import math
import string

from .lab_style import star_label

WIDTH = 6  # Prism results sheets export six columns


def _round_half_up(v, digits):
    """Round like Prism (and by hand): ties go away from zero. Floating-point noise is removed
    first, so a value computed as 5.67949999999 is treated as the 5.6795 it represents."""
    from decimal import ROUND_HALF_UP, Decimal
    d = Decimal(f"{v:.12g}")
    return format(d.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP), "f")


def num(v):
    """Prism number format: 4 significant digits; values of 1000 or more print whole."""
    if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return ""
    if isinstance(v, int):
        return f"{v:d}"
    if abs(v) >= 1000:
        return _round_half_up(v, 0)
    if v == 0:
        return "0"
    digits = max(4 - int(math.floor(math.log10(abs(v)))) - 1, 0)
    text = _round_half_up(v, digits)
    if abs(float(text)) >= 10 ** (4 - digits) and digits > 0:   # 9.9996 rounds to 10.000
        text = _round_half_up(v, digits - 1)
    if text in ("-0", "-0.0", "-0.00", "-0.000"):
        text = text[1:]
    return text


def p_text(p):
    if p is None or not math.isfinite(p):
        return ""
    if p < 0.0001:
        return "<0.0001"
    if p > 0.9999:
        return ">0.9999"
    return f"{p:.4f}"


def p_eq(p):
    t = p_text(p)
    return "" if not t else ("P" + t if t.startswith(("<", ">")) else "P=" + t)


def yes_no(flag):
    return "Yes" if flag else "No"


def letters(k):
    letters_ = string.ascii_uppercase
    if k <= 0:
        return ""
    last = letters_[k - 1] if k <= 26 else str(k)
    return f"A-{last}" if k > 1 else "A"


def ci_text(lo, hi):
    if not (math.isfinite(lo) and math.isfinite(hi)):
        return ""
    return f"{num(lo)} to {num(hi)}"


def _pad(row):
    row = list(row)
    return row + [""] * (WIDTH - len(row)) if len(row) < WIDTH else row


def write_csv(path, rows):
    """Write rows the way Prism does: a field is quoted when it contains a space or comma."""
    def cell(v):
        v = "" if v is None else str(v)
        if any(ch in v for ch in ' ,"'):
            return '"' + v.replace('"', '""') + '"'
        return v
    with open(path, "w", encoding="utf-8", newline="") as fh:
        for row in rows:
            fh.write(",".join(cell(v) for v in _pad(row)) + "\n")


# ---------------------------------------------------------------------------
# One-way ANOVA
# ---------------------------------------------------------------------------

def one_way_rows(result, table_title):
    sm = result.summary
    k, n_total = sm["k"], sm["n_total"]
    rows = [["Table Analyzed", table_title], ["Data sets analyzed", letters(k)],
            ["Distribution assumption", "Normal (Gaussian)"], [],
            ["ANOVA summary"],
            ["  F", num(sm["F"])],
            ["  P value", p_text(sm["P"])],
            ["  P value summary", star_label(sm["P"])],
            ["  Significant diff. among means (P < 0.05)?", yes_no(sm["P"] < 0.05)],
            ["  R squared", num(sm["R squared"])], []]
    if "Brown-Forsythe" in sm:
        f, dfn, dfd, p = sm["Brown-Forsythe"]
        rows += [["Brown-Forsythe test"],
                 ["  F (DFn, DFd)", f"{num(f)} ({dfn}, {dfd})"],
                 ["  P value", p_text(p)],
                 ["  P value summary", star_label(p)],
                 ["  Are SDs significantly different (P < 0.05)?", yes_no(p < 0.05)], []]
    if "Bartlett" in sm:
        b, p = sm["Bartlett"]
        rows += [["Bartlett's test"],
                 ["  Bartlett's statistic (corrected)", num(b)],
                 ["  P value", p_text(p)],
                 ["  P value summary", star_label(p)],
                 ["  Are SDs significantly different (P < 0.05)?", yes_no(p < 0.05)], []]
    rows.append(["ANOVA table", "SS", "DF", "MS", "F (DFn, DFd)", "P value"])
    for source, ss, df, ms, f, dfn, dfd, p in result.table:
        f_txt = f"F ({dfn}, {dfd}) = {num(f)}" if math.isfinite(f) else ""
        rows.append([f"  {source}", num(ss), str(df), num(ms), f_txt, p_eq(p)])
    rows += [[], ["Data summary"],
             ["  Number of treatments (columns)", str(k)],
             ["  Number of values (total)", str(n_total)]]
    return rows


def comparison_rows(comparisons, posthoc, families, header_note=None, grouped=False):
    """Prism multiple-comparisons sheet: summary table, then test details."""
    if not comparisons:
        return []
    name = posthoc.split(" (")[0] if posthoc else "Multiple comparisons"
    rows = []
    if header_note:
        rows += [[header_note], []]
    rows += [["Number of families", str(families[0])],
             ["Number of comparisons per family", str(families[1])],
             ["Alpha", "0.05"], [],
             [name, "Mean Diff.", "95.00% CI of diff.", "Below threshold?", "Summary",
              "Adjusted P Value"]]

    def label_rows(fn):
        out, last = [], None
        for c in comparisons:
            if grouped:
                pair = f"  {c.group1} - {c.group2}"
                if pair != last:
                    out.append([pair])
                    last = pair
                out.append([f"    {c.context}"] + fn(c))
            else:
                out.append([f"  {c.group1} vs. {c.group2}"] + fn(c))
        return out

    rows += label_rows(lambda c: [num(c.diff), ci_text(c.ci_low, c.ci_high), yes_no(c.p < 0.05),
                                  c.summary, p_text(c.p)])
    if any(math.isfinite(c.se) for c in comparisons):
        stat = comparisons[0].stat_name or "t"
        nlab = ("N1", "N2") if grouped else ("n1", "n2")
        rows += [[], ["Test details", "Mean 1", "Mean 2", "Mean Diff.", "SE of diff.", nlab[0],
                      nlab[1], stat, "DF"]]
        rows += label_rows(lambda c: [num(c.mean1), num(c.mean2), num(c.diff), num(c.se),
                                      str(c.n1), str(c.n2), num(c.stat),
                                      str(int(c.df)) if math.isfinite(c.df) else ""])
    return rows


# ---------------------------------------------------------------------------
# Two-way ANOVA (ordinary and repeated measures)
# ---------------------------------------------------------------------------

def _source_name(source, row_factor, col_factor):
    return {"Interaction": f"{row_factor} x {col_factor}", "Row factor": row_factor,
            "Column factor": col_factor}.get(source, source)


def two_way_rows(res, table_title, row_factor="Row Factor", col_factor="Column Factor"):
    from .anova import ACROSS_ROW
    rm = res.design != "No matching"
    rows = [["Table Analyzed", table_title], []]
    if rm:
        matching = "Across row" if res.design == ACROSS_ROW else "Stacked in subcolumns"
        rows += [["Two-way RM ANOVA", f"Matching: {matching}"],
                 ["    Assume sphericity?", yes_no(not res.gg_applied)]]
        if res.gg_applied:
            rows.append(["    Geisser-Greenhouse's epsilon", num(res.epsilon)])
        rows += [["    Alpha", "0.05"], []]
    else:
        rows += [["Two-way ANOVA", "Ordinary"], ["    Alpha", "0.05"], []]
    rows.append(["Source of Variation", "% of total variation", "P value", "P value summary",
                 "Significant?"])
    for r in res.rows:
        if r.source in ("Residual", "Total"):
            continue
        rows.append([f"    {_source_name(r.source, row_factor, col_factor)}", num(r.pct),
                     p_text(r.p), star_label(r.p), yes_no(r.p < 0.05)])
    rows += [[], ["ANOVA table", "SS", "DF", "MS", "F (DFn, DFd)", "P value"]]
    for r in res.rows:
        f_txt = (f"F ({num(r.df)}, {num(r.df_den)}) = {num(r.f)}" if math.isfinite(r.f) else "")
        rows.append([f"    {_source_name(r.source, row_factor, col_factor)}", num(r.ss), num(r.df),
                     num(r.ms), f_txt, p_eq(r.p)])
    cd = res.col_diff
    if cd:
        rows += [[], ["Difference between column means"],
                 [f"    Mean of {cd['names'][0]}", num(cd["means"][0])],
                 [f"    Mean of {cd['names'][1]}", num(cd["means"][1])],
                 ["    Difference between means", num(cd["diff"])],
                 ["    SE of difference", num(cd["se"])],
                 ["    95% CI of difference", ci_text(*cd["ci"])]]
    ds = res.data_summary
    if ds:
        rows += [[], ["Data summary"],
                 [f"    Number of columns ({col_factor})", str(ds["columns"])],
                 [f"    Number of rows ({row_factor})", str(ds["rows"])]]
        if "subjects" in ds:
            rows.append(["    Number of subjects (Subject)", str(ds["subjects"])])
            rows.append(["    Number of missing values", str(ds["missing"])])
        else:
            rows.append(["    Number of values", str(ds["values"])])
    return rows


def grouped_comparison_note(comparisons_mode, n_cols):
    if comparisons_mode == "Compare columns within each row":
        return ("Compare each cell mean with the other cell mean in that row" if n_cols == 2
                else "Compare each cell mean with the other cell means in that row")
    if comparisons_mode == "Compare each column to the first, within each row":
        return "Compare each cell mean with the first cell mean in that row"
    if comparisons_mode == "Compare rows within each column":
        return "Compare each cell mean with the other cell means in that column"
    if comparisons_mode == "Compare cell means regardless of rows and columns":
        return "Compare cell means regardless of rows and columns"
    return None


def rows_to_text(rows):
    """Aligned plain text for the results panel."""
    rows = [list(r) for r in rows]
    width = max((len(r) for r in rows), default=0)
    rows = [r + [""] * (width - len(r)) for r in rows]
    widths = [max(len(str(r[c])) for r in rows) for c in range(width)]
    out = []
    for r in rows:
        if not any(str(v) for v in r):
            out.append("")
        elif len([v for v in r if str(v)]) == 1 and str(r[0]):
            out.append(str(r[0]))
        else:
            out.append("  ".join(str(v).ljust(w) for v, w in zip(r, widths)).rstrip())
    return "\n".join(out)
