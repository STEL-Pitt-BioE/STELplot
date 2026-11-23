"""Plain-language summaries, warnings that flag problems, and help for each analysis.

Summaries describe what the numbers mean; warnings point to assumptions worth checking.
Neither replaces judgment about the experiment. Thresholds used for warnings:
normality P < 0.05 (Shapiro-Wilk), unequal SDs P < 0.05, Geisser-Greenhouse epsilon < 0.75,
fewer than 3 values in a group, R squared < 0.5 for curve fits.
"""

__author__ = "Daniel Shiwarski"

import math

import numpy as np

from .prism_format import num

PARAMETRIC = {"Unpaired t-test", "Welch's t-test", "Paired t-test", "One-way ANOVA",
              "Repeated-measures one-way ANOVA"}
NONPARAMETRIC_ALTERNATIVE = {
    "Unpaired t-test": "the Mann-Whitney test", "Welch's t-test": "the Mann-Whitney test",
    "Paired t-test": "the Wilcoxon signed-rank test", "One-way ANOVA": "the Kruskal-Wallis test",
    "Repeated-measures one-way ANOVA": "the Friedman test"}
NAMES = {"Unpaired t-test": "unpaired t test", "Welch's t-test": "Welch's t test",
         "Paired t-test": "paired t test", "Mann-Whitney test": "Mann-Whitney test",
         "Wilcoxon signed-rank test": "Wilcoxon signed-rank test", "One-way ANOVA": "one-way ANOVA",
         "Kruskal-Wallis test": "Kruskal-Wallis test",
         "Repeated-measures one-way ANOVA": "repeated-measures one-way ANOVA",
         "Friedman test": "Friedman test"}


def p_phrase(p):
    if p is None or not math.isfinite(p):
        return "P not available"
    if p < 0.0001:
        return "P < 0.0001"
    if p > 0.9999:
        return "P > 0.9999"
    return f"P = {p:.4f}"


def _chance(p):
    if p < 0.0001:
        return "fewer than 0.01% of"
    pct = p * 100
    return f"about {pct:.2g}% of" if pct < 10 else f"about {round(pct)}% of"


def _list(items, limit=4):
    items = list(items)
    if len(items) > limit:
        return "; ".join(items[:limit]) + f"; and {len(items) - limit} more"
    return "; ".join(items)


def _comparisons(comps, posthoc, alpha=0.05):
    if not comps:
        return ""
    sig = [c for c in comps if math.isfinite(c.p) and c.p < alpha]
    name = posthoc.split(" (")[0] if posthoc else "Multiple comparisons"
    text = f"{name}: {len(sig)} of {len(comps)} comparison(s) statistically significant"
    if sig:
        text += ": " + _list(f"{c.group1} vs. {c.group2} ({p_phrase(c.p)})" for c in sig)
    return text + "."


# ---------------------------------------------------------------------------
# Column tables
# ---------------------------------------------------------------------------

def column_summary(result):
    """(plain-language summary, list of warnings) for a column analysis."""
    test = result.test
    desc = [d for d in result.descriptives if d.n > 0]
    if not desc:
        return "", []
    if test == "None":
        sizes = ", ".join(f"{d.name} n = {d.n}" for d in desc)
        return (f"{len(desc)} group(s): {sizes}. Choose a test under Statistics to compare them.",
                _sample_warnings(result))
    if not result.ok:
        return f"The analysis did not run: {result.message}", []
    p = result.summary.get("P", math.nan)
    if test in ("Unpaired t-test", "Welch's t-test", "Paired t-test"):
        text = _t_summary(result, p)
    elif test in ("Mann-Whitney test", "Wilcoxon signed-rank test"):
        text = _rank_summary(result, p)
    else:
        text = _multi_summary(result, p)
    return text, column_warnings(result)


def _t_summary(result, p):
    c = result.comparisons[0]
    a, b, d = c.group1, c.group2, c.diff
    alpha = 1 - result.conf
    level = format(round(result.conf * 100, 6), "g")
    direction = "higher" if d > 0 else ("lower" if d < 0 else "the same as")
    if result.test == "Paired t-test":
        first = (f"On average, {b} is {num(abs(d))} {direction} than {a} within each pair "
                 f"(mean of differences, {b} minus {a}: {num(d)}).")
    else:
        first = (f"The mean of {b} ({num(c.mean2)}) is {num(abs(d))} {direction} than the mean of "
                 f"{a} ({num(c.mean1)}).")
    ci = (f" The {level}% confidence interval for the difference runs from {num(c.ci_low)} to "
          f"{num(c.ci_high)}.")
    if p < alpha:
        verdict = (f" The difference is statistically significant ({p_phrase(p)}, "
                   f"{NAMES[result.test]}, threshold P < {format(round(alpha, 8), 'g')}). If the "
                   f"population means were equal, random sampling would give a difference this large "
                   f"or larger in {_chance(p)} experiments like this one.")
    else:
        verdict = (f" The difference is not statistically significant ({p_phrase(p)}, "
                   f"{NAMES[result.test]}). That does not show the means are equal; the confidence "
                   "interval shows the range of differences still consistent with the data.")
    return first + ci + verdict


def _rank_summary(result, p):
    c = result.comparisons[0]
    a, b = c.group1, c.group2
    da, db = result.descriptives[0], result.descriptives[1]
    if result.test == "Wilcoxon signed-rank test":
        first = f"The median of the paired differences ({b} minus {a}) is {num(c.diff)}."
    else:
        first = f"The median of {b} is {num(db.median)}; the median of {a} is {num(da.median)}."
    if p < 0.05:
        higher = b if c.diff > 0 else a
        verdict = (f" The difference is statistically significant ({p_phrase(p)}, "
                   f"{NAMES[result.test]}): values in {higher} tend to be larger.")
    else:
        verdict = (f" The difference is not statistically significant ({p_phrase(p)}, "
                   f"{NAMES[result.test]}).")
    return first + verdict


def _multi_summary(result, p):
    k = len([d for d in result.descriptives if d.n > 0])
    rank_based = result.test in ("Kruskal-Wallis test", "Friedman test")
    what = "distributions" if rank_based else "means"
    if p < 0.05:
        text = (f"The {k} groups' {what} differ more than expected by chance ({p_phrase(p)}, "
                f"{NAMES[result.test]}).")
    else:
        text = (f"There is no statistically significant difference among the {k} groups' {what} "
                f"({p_phrase(p)}, {NAMES[result.test]}).")
    if result.test == "One-way ANOVA" and "R squared" in result.summary:
        text += (f" Group membership accounts for {result.summary['R squared'] * 100:.3g}% of the "
                 "total variation.")
    mp = result.summary.get("matching_p")
    if mp is not None and math.isfinite(mp):
        text += (f" Matching was effective ({p_phrase(mp)}): values in the same row are correlated, "
                 "so the repeated-measures design added power." if mp < 0.05 else
                 f" Matching was not effective ({p_phrase(mp)}); an ordinary ANOVA may be as powerful.")
    comp = _comparisons(result.comparisons, result.posthoc)
    return text + (" " + comp if comp else "")


def _sample_warnings(result):
    out = []
    for d in result.descriptives:
        if 0 < d.n < 3:
            out.append(f"{d.name} has only {d.n} value(s). Results from so few values are unreliable, "
                       "and normality cannot be checked.")
    return out


def column_warnings(result):
    w = _sample_warnings(result)
    test, sm = result.test, result.summary
    if test in PARAMETRIC:
        bad = [(name, p) for name, _w, p in result.normality if p == p and p < 0.05]
        if bad:
            names = ", ".join(name for name, _ in bad)
            low = min(p for _, p in bad)
            w.append(f"{names} {'fails' if len(bad) == 1 else 'fail'} the Shapiro-Wilk normality test "
                     f"(lowest {p_phrase(low)}). Consider {NONPARAMETRIC_ALTERNATIVE[test]} or a log "
                     "transformation (Analysis > Transform data). With large samples this test flags "
                     "small departures that may not matter.")
    if test == "Unpaired t-test" and "F test" in sm and sm["F test"][3] < 0.05:
        w.append(f"The two SDs differ (F test, {p_phrase(sm['F test'][3])}). Welch's t test does not "
                 "assume equal SDs.")
    if test == "One-way ANOVA" and "Brown-Forsythe" in sm and sm["Brown-Forsythe"][3] < 0.05:
        w.append(f"The group SDs differ (Brown-Forsythe test, {p_phrase(sm['Brown-Forsythe'][3])}). "
                 "ANOVA assumes equal SDs; consider a log transformation or the Kruskal-Wallis test.")
    if sm.get("dropped"):
        w.append(f"{sm['dropped']} row(s) had a value in only one column and were left out of the "
                 "paired test.")
    if sm.get("rm_excluded"):
        w.append(f"{sm['rm_excluded']} row(s) with a missing value were left out. Repeated-measures "
                 "ANOVA needs complete rows.")
    eps = sm.get("epsilon")
    if eps is not None and math.isfinite(eps) and eps < 0.75 and not sm.get("gg_applied"):
        w.append(f"Geisser-Greenhouse epsilon is {eps:.3f}, which suggests the sphericity assumption "
                 "is violated. Turn on the Geisser-Greenhouse correction.")
    p = sm.get("P", math.nan)
    comps = [c for c in result.comparisons if math.isfinite(c.p)]
    if len(result.descriptives) > 2 and comps and math.isfinite(p):
        if p >= 0.05 and any(c.p < 0.05 for c in comps):
            w.append("The overall test is not significant, but at least one multiple comparison is. "
                     "Interpret that comparison with caution.")
        if p < 0.05 and not any(c.p < 0.05 for c in comps):
            w.append("The overall test is significant, but no single comparison is. The difference "
                     "may be spread across several groups.")
    return w


# ---------------------------------------------------------------------------
# Grouped tables
# ---------------------------------------------------------------------------

def grouped_summary(res, row_factor="Row Factor", col_factor="Column Factor"):
    if res is None:
        return "", []
    if not res.ok:
        return f"The analysis did not run: {res.message}", []
    names = {"Interaction": f"The interaction between {row_factor} and {col_factor}",
             "Row factor": row_factor, "Column factor": col_factor}
    parts, inter_sig = [], False
    for r in res.rows:
        if r.source not in names or not math.isfinite(r.p):
            continue
        sig = r.p < 0.05
        inter_sig |= sig and r.source == "Interaction"
        pct = f" accounts for {r.pct:.3g}% of the total variation" if math.isfinite(r.pct) else ""
        parts.append(f"{names[r.source]}{pct} ({p_phrase(r.p)}; "
                     f"{'statistically significant' if sig else 'not statistically significant'}).")
    text = " ".join(parts)
    if inter_sig:
        text += (f" Because the interaction is significant, the effect of {col_factor} differs between "
                 f"levels of {row_factor}; interpret the main effects with care.")
    comp = _comparisons(res.comparisons, res.posthoc)
    return text + (" " + comp if comp else ""), grouped_warnings(res)


def grouped_warnings(res):
    w = list(res.notes)
    singles = [f"{rl}/{cn}" for rl, cn, n, *_ in res.cells if n == 1]
    if singles:
        w.append(f"{len(singles)} cell(s) have a single value ({_list(singles, 3)}).")
    if math.isfinite(res.epsilon) and res.epsilon < 0.75 and not res.gg_applied:
        w.append(f"Geisser-Greenhouse epsilon is {res.epsilon:.3f}; the sphericity assumption looks "
                 "doubtful. Turn on the Geisser-Greenhouse correction.")
    return w


# ---------------------------------------------------------------------------
# XY tables
# ---------------------------------------------------------------------------

def xy_summary(fits, x=None):
    if not fits:
        return "", []
    parts, w = [], []
    xs = np.asarray(x, float) if x is not None else np.array([])
    for f in fits:
        if not f.ok:
            w.append(f"{f.series}: the fit did not converge or could not run ({f.message}).")
            continue
        shown = ", ".join(f"{name} = {num(v)} (95% CI {num(lo)} to {num(hi)})"
                          for name, v, _se, lo, hi in f.params[:3])
        derived = "".join(f"; {name} = {txt}" for name, txt in f.derived if name != "Note")
        parts.append(f"{f.series} ({f.model}): {shown}{derived}; R squared = {f.r2:.3f}.")
        if math.isfinite(f.r2) and f.r2 < 0.5:
            w.append(f"{f.series}: R squared is {f.r2:.2f}, so the curve explains little of the "
                     "variation. Check the model choice and the data.")
        wide = [name for name, v, _se, lo, hi in f.params
                if not (math.isfinite(lo) and math.isfinite(hi)) or (v != 0 and hi - lo > 10 * abs(v))]
        if wide:
            w.append(f"{f.series}: wide confidence intervals for {', '.join(wide)}. The data may not "
                     "define these parameters well (for dose-response curves, check that both "
                     "plateaus are covered).")
        if f.model.startswith("Dose-response") and xs.size:
            pos = xs[np.isfinite(xs) & (xs > 0)]
            log_ec50 = next((v for name, v, *_ in f.params if name == "LogEC50"), math.nan)
            if pos.size and math.isfinite(log_ec50) and not (
                    np.log10(pos.min()) <= log_ec50 <= np.log10(pos.max())):
                w.append(f"{f.series}: the EC50 lies outside the range of concentrations tested.")
        if f.n <= len(f.params) + 1:
            w.append(f"{f.series}: only {f.n} points for {len(f.params)} parameters.")
    return " ".join(parts), w


# ---------------------------------------------------------------------------
# Interpret: what each analysis does and how to read it
# ---------------------------------------------------------------------------

HELP = {
    "Unpaired t-test": (
        "Compares the means of two independent groups.",
        "Values are independent, each group is sampled from a roughly Gaussian population, and the "
        "two populations have similar SDs.",
        "The difference between means (B minus A) and its confidence interval show the size of the "
        "effect. The P value asks how often random sampling would give a difference at least this "
        "large if the population means were equal.",
        "If the F test shows the SDs differ, use Welch's t test. If the data are clearly not "
        "Gaussian, consider the Mann-Whitney test or a log transformation."),
    "Welch's t-test": (
        "Compares two independent means without assuming equal SDs.",
        "Values are independent and each group is roughly Gaussian.",
        "Read the difference, its confidence interval, and P as for the unpaired t test. Degrees of "
        "freedom are adjusted for unequal SDs, so they are often not a whole number.",
        "A reasonable default when group SDs may differ."),
    "Paired t-test": (
        "Compares two matched measurements (for example, before and after in the same sample).",
        "Pairs are independent of each other and the paired differences are roughly Gaussian.",
        "The mean of the differences (B minus A) and its confidence interval show the typical change "
        "within a pair. P asks how often a mean difference this large would occur if the true mean "
        "difference were zero.",
        "Each row must be one matched pair. Rows missing a partner value are left out."),
    "Mann-Whitney test": (
        "Compares two independent groups using ranks rather than raw values.",
        "Values are independent. No Gaussian assumption.",
        "A small P means values in one group tend to be larger than in the other. It is not strictly "
        "a test of medians unless the two distributions have the same shape.",
        "Has less power than a t test when data really are Gaussian, especially with small samples."),
    "Wilcoxon signed-rank test": (
        "Compares two matched measurements using ranks of the paired differences.",
        "Pairs are independent and the differences are roughly symmetric around their median.",
        "A small P means the paired differences are consistently above or below zero.",
        "Use when paired differences are clearly not Gaussian."),
    "One-way ANOVA": (
        "Tests whether three or more group means differ, then compares pairs with a multiple "
        "comparisons test.",
        "Values are independent, groups are roughly Gaussian, and SDs are similar (checked by the "
        "Brown-Forsythe and Bartlett tests).",
        "The overall P asks whether all means could plausibly be equal. Multiple comparisons (Tukey "
        "for all pairs, Dunnett against the first column) say which pairs differ, with P values "
        "adjusted for the number of comparisons.",
        "Choose the comparisons before looking at the data. If SDs differ, consider a log "
        "transformation or the Kruskal-Wallis test."),
    "Kruskal-Wallis test": (
        "Compares three or more independent groups using ranks.",
        "Values are independent. No Gaussian assumption.",
        "A small P means at least one group tends to have larger values. Dunn's test compares pairs "
        "of groups by their mean ranks.",
        "Has less power than ANOVA when data really are Gaussian."),
    "Repeated-measures one-way ANOVA": (
        "Compares three or more matched measurements, with each row as one subject.",
        "Subjects are independent, residuals are roughly Gaussian, and sphericity holds (the "
        "Geisser-Greenhouse correction relaxes this).",
        "The treatment P asks whether the column means could be equal. 'Was the matching effective?' "
        "tests whether rows are correlated; if not, an ordinary ANOVA may be as good.",
        "Rows with a missing value are left out. Keep the Geisser-Greenhouse correction on unless "
        "you have a reason not to."),
    "Friedman test": (
        "Compares three or more matched measurements using ranks within each row.",
        "Rows (subjects) are independent. No Gaussian assumption.",
        "A small P means at least one column tends to rank higher within subjects. Dunn's test "
        "compares pairs of columns.",
        "Rows with a missing value are left out."),
    "Two-way ANOVA": (
        "Splits the variation into two factors (rows and data sets) and their interaction.",
        "Values in each cell are independent and roughly Gaussian with similar SDs. Repeated-measures "
        "designs assume sphericity, which the Geisser-Greenhouse correction relaxes.",
        "Each factor's P asks whether it shifts the means overall. A significant interaction means "
        "the effect of one factor depends on the level of the other, so main effects alone can "
        "mislead. Multiple comparisons test the specific differences you choose.",
        "'Main effects only' assumes no interaction. Cell-by-cell comparisons compare every cell "
        "with every other, which costs power because the number of comparisons grows quickly."),
    "Linear regression": (
        "Fits a straight line, Y = slope * X + intercept, by least squares.",
        "Points are independent, the relationship is linear, and scatter around the line is "
        "Gaussian with constant SD.",
        "The slope and its confidence interval give the change in Y per unit X. R squared is the "
        "fraction of Y variation explained by the line.",
        "Look at the residuals: a curved pattern means a straight line is the wrong model."),
    "Dose-response, 4PL (variable slope)": (
        "Fits a sigmoidal curve with bottom and top plateaus, LogEC50, and Hill slope. Enter X as "
        "concentrations; STELplot takes their logarithm.",
        "Points are independent and scatter is Gaussian with constant SD.",
        "EC50 is the concentration giving a response halfway between bottom and top. The Hill slope "
        "describes steepness (1 is a standard curve).",
        "Wide confidence intervals usually mean the data do not reach one or both plateaus; extend "
        "the concentration range."),
    "One-phase exponential decay": (
        "Fits Y = (Y0 - Plateau) * exp(-K * X) + Plateau.",
        "Points are independent and scatter is Gaussian with constant SD.",
        "K is the rate constant; the half-life is ln(2)/K in the units of X.",
        "Data should extend long enough for the curve to approach its plateau."),
    "One-phase association": (
        "Fits Y = Y0 + (Plateau - Y0) * (1 - exp(-K * X)).",
        "Points are independent and scatter is Gaussian with constant SD.",
        "K is the rate constant; the half-time is ln(2)/K in the units of X.",
        "Data should extend long enough for the curve to approach its plateau."),
}


def help_text(name):
    """Plain-text Interpret help for a test, analysis, or curve model."""
    key = "Two-way ANOVA" if name.startswith("Two-way") else name
    if key not in HELP:
        return ("Choose a test or analysis to see how to interpret it.\n\nReport the test you used, "
                "the P value, and an effect size with its confidence interval.")
    what, assumes, read, check = HELP[key]
    return (f"{name}\n\nWhat it does\n{what}\n\nAssumptions\n{assumes}\n\nReading the results\n{read}"
            f"\n\nWorth checking\n{check}")
