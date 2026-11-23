"""Statistics for STELplot.

All tests use SciPy. Dunn's test is implemented here because SciPy does not
include it; it follows Dunn (1964) with the tie correction and a Bonferroni
adjustment across the family of comparisons.
"""

__author__ = "Daniel Shiwarski"

import csv
import inspect
import math
import platform
import warnings
from dataclasses import dataclass, field

import numpy as np
import scipy
from scipy import stats
from scipy.optimize import OptimizeWarning, curve_fit

from . import __version__, APP_NAME
from .lab_style import STAR_LEGEND, star_label, format_p

NAN = float("nan")

# ---------------------------------------------------------------------------
# Test catalog
# ---------------------------------------------------------------------------

COLUMN_TESTS = [
    "None",
    "Unpaired t-test",
    "Welch's t-test",
    "Paired t-test",
    "Mann-Whitney test",
    "Wilcoxon signed-rank test",
    "One-way ANOVA",
    "Kruskal-Wallis test",
    "Repeated-measures one-way ANOVA",
    "Friedman test",
]
TWO_GROUP_TESTS = {"Unpaired t-test", "Welch's t-test", "Paired t-test",
                   "Mann-Whitney test", "Wilcoxon signed-rank test"}
PAIRED_TESTS = {"Paired t-test", "Wilcoxon signed-rank test"}
RM_TESTS = {"Repeated-measures one-way ANOVA", "Friedman test"}
MULTI_GROUP_TESTS = {"One-way ANOVA", "Kruskal-Wallis test"} | RM_TESTS

COMPARISON_MODES = ["All pairs", "Each vs. first column"]
ERROR_TYPES = ["SD", "SEM", "95% CI", "None"]
# Prism's "Plot" choices for column graphs
COLUMN_SUMMARIES = ["Mean with SD", "Mean with SEM", "Mean with 95% CI", "Mean only",
                    "Median only", "Median with interquartile range"]
LEGACY_SUMMARY = {"SD": "Mean with SD", "SEM": "Mean with SEM", "95% CI": "Mean with 95% CI",
                  "None": "Mean only"}
SHOWN = {"Mean with SD": "mean ± SD", "Mean with SEM": "mean ± SEM",
         "Mean with 95% CI": "mean with 95% CI", "Mean only": "mean", "Median only": "median",
         "Median with interquartile range": "median with interquartile range",
         "SD": "mean ± SD", "SEM": "mean ± SEM", "95% CI": "mean with 95% CI", "None": "mean"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def finite(values):
    """Return a float array with NaN and inf removed."""
    arr = np.asarray(values, dtype=float)
    return arr[np.isfinite(arr)]


def error_halfwidth(values, kind):
    """Half-width of the error bar for SD, SEM, or 95% CI of the mean."""
    v = finite(values)
    n = v.size
    if n < 2 or kind == "None":
        return 0.0
    sd = float(np.std(v, ddof=1))
    if kind == "SD":
        return sd
    sem = sd / math.sqrt(n)
    if kind == "SEM":
        return sem
    return float(stats.t.ppf(0.975, n - 1) * sem)


def summary_values(values, choice):
    """Center and error distances (below, above) for a Prism-style column plot choice."""
    v = finite(values)
    choice = LEGACY_SUMMARY.get(choice, choice)
    if v.size == 0:
        return NAN, 0.0, 0.0
    if choice.startswith("Median"):
        q1, med, q3 = (float(x) for x in np.percentile(v, [25, 50, 75]))
        if choice == "Median with interquartile range":
            return med, med - q1, q3 - med
        return med, 0.0, 0.0
    mean = float(np.mean(v))
    kind = {"Mean with SD": "SD", "Mean with SEM": "SEM", "Mean with 95% CI": "95% CI"}.get(choice)
    half = error_halfwidth(v, kind) if kind else 0.0
    return mean, half, half


def fmt(v, digits=4):
    """Compact number formatting for reports."""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "n/a"
    return f"{v:.{digits}g}"


@dataclass
class Descriptive:
    name: str
    n: int
    mean: float
    sd: float
    sem: float
    ci_low: float
    ci_high: float
    median: float
    q1: float
    q3: float
    minimum: float
    maximum: float


def describe(name, values):
    v = finite(values)
    n = v.size
    if n == 0:
        return Descriptive(name, 0, *([NAN] * 10))
    mean = float(np.mean(v))
    sd = float(np.std(v, ddof=1)) if n > 1 else NAN
    sem = sd / math.sqrt(n) if n > 1 else NAN
    half = error_halfwidth(v, "95% CI") if n > 1 else NAN
    q1, med, q3 = (float(x) for x in np.percentile(v, [25, 50, 75]))
    return Descriptive(name, n, mean, sd, sem, mean - half, mean + half,
                       med, q1, q3, float(v.min()), float(v.max()))


@dataclass
class Comparison:
    group1: str
    group2: str
    i: int
    j: int
    diff: float
    p: float
    ci_low: float = NAN
    ci_high: float = NAN
    diff_label: str = "Mean diff."
    context: str = ""
    cluster: int = -1
    mean1: float = NAN
    mean2: float = NAN
    se: float = NAN
    n1: int = 0
    n2: int = 0
    stat: float = NAN
    stat_name: str = ""
    df: float = NAN

    @property
    def summary(self):
        return star_label(self.p)


@dataclass
class StatsResult:
    test: str
    ok: bool = True
    message: str = ""
    omnibus: str = ""
    extra_lines: list = field(default_factory=list)
    posthoc: str = ""
    comparisons: list = field(default_factory=list)
    descriptives: list = field(default_factory=list)
    normality: list = field(default_factory=list)
    table: list = field(default_factory=list)     # (source, SS, DF, MS, F, DFn, DFd, P)
    summary: dict = field(default_factory=dict)   # F, P, R squared, variance tests, counts
    families: tuple = (1, 0)                      # (number of families, comparisons per family)
    conf: float = 0.95                            # confidence level for t tests


# ---------------------------------------------------------------------------
# Column statistics
# ---------------------------------------------------------------------------

T_TESTS = {"Unpaired t-test", "Welch's t-test", "Paired t-test"}


def conf_text(conf):
    """95 -> '95', 0.995 -> '99.5' (confidence level as a percentage)."""
    return format(round(conf * 100, 6), "g")


def alpha_text(conf):
    return format(round(1 - conf, 8), "g")


def run_column_stats(groups, test, mode="All pairs", gg=True, conf=0.95):
    """Run the selected test.

    groups: list of (name, values) where values may contain NaN. Row order is
    kept so paired tests can match rows.
    """
    result = StatsResult(test=test)
    result.conf = min(max(float(conf), 0.5), 0.99999)
    result.descriptives = [describe(n, v) for n, v in groups]
    result.normality = _normality(groups)

    if test == "None" or not groups:
        return result

    k = len(groups)
    names = [g[0] for g in groups]
    samples = [finite(g[1]) for g in groups]

    if test in TWO_GROUP_TESTS and k != 2:
        return _fail(result, f"{test} compares exactly two columns. "
                             f"You have {k}. Use one-way ANOVA or Kruskal-Wallis "
                             f"for three or more groups.")
    if test in MULTI_GROUP_TESTS and k < 2:
        return _fail(result, "Add at least two columns with data.")

    try:
        if test in RM_TESTS:
            return _rm_column(result, groups, test, mode, gg)
        if test in PAIRED_TESTS:
            return _paired(result, groups, test)
        if test in TWO_GROUP_TESTS:
            return _two_group(result, names, samples, test)
        if test == "One-way ANOVA":
            return _anova(result, names, samples, mode)
        if test == "Kruskal-Wallis test":
            return _kruskal(result, names, samples, mode)
    except (ValueError, ZeroDivisionError, FloatingPointError, np.linalg.LinAlgError) as exc:
        return _fail(result, f"{test} could not run on these data: {exc}")
    return _fail(result, f"Unknown test: {test}")


def _fail(result, message):
    result.ok = False
    result.message = message
    return result


def _normality(groups):
    out = []
    for name, values in groups:
        v = finite(values)
        if v.size >= 3 and np.ptp(v) > 0:
            w, p = stats.shapiro(v)
            out.append((name, float(w), float(p)))
        else:
            out.append((name, NAN, NAN))
    return out


def _two_group(result, names, samples, test):
    a, b = samples
    n1, n2 = a.size, b.size
    minimum = 1 if test == "Mann-Whitney test" else 2
    if n1 < minimum or n2 < minimum:
        return _fail(result, f"{test} needs at least {minimum} values in each column.")

    if test == "Mann-Whitney test":
        res = stats.mannwhitneyu(a, b, alternative="two-sided")
        u = float(res.statistic)
        result.omnibus = f"Mann-Whitney U = {fmt(u)}, {format_p(res.pvalue)} (two-tailed)"
        result.summary["P"] = float(res.pvalue)
        diff = float(np.median(b) - np.median(a))
        result.comparisons = [Comparison(names[0], names[1], 0, 1, diff, float(res.pvalue),
                                         diff_label="Median diff. (B - A)")]
        return result

    m1, m2 = float(np.mean(a)), float(np.mean(b))
    v1, v2 = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    if test == "Unpaired t-test":
        df = n1 + n2 - 2
        sp2 = ((n1 - 1) * v1 + (n2 - 1) * v2) / df
        se = math.sqrt(sp2 * (1 / n1 + 1 / n2))
        res = stats.ttest_ind(a, b, equal_var=True)
    else:  # Welch
        se = math.sqrt(v1 / n1 + v2 / n2)
        num = (v1 / n1 + v2 / n2) ** 2
        den = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
        df = num / den if den > 0 else NAN
        res = stats.ttest_ind(a, b, equal_var=False)
    diff = m2 - m1   # Prism reports the difference between means as B - A
    tcrit = stats.t.ppf(0.5 + result.conf / 2, df) if math.isfinite(df) else NAN
    lo, hi = diff - tcrit * se, diff + tcrit * se
    result.omnibus = (f"t = {fmt(abs(float(res.statistic)))}, df = {fmt(df)}, "
                      f"{format_p(res.pvalue)} (two-tailed)")
    result.summary["P"] = float(res.pvalue)
    result.extra_lines.append(
        f"Significantly different (P < {alpha_text(result.conf)})? "
        f"{'Yes' if res.pvalue < 1 - result.conf else 'No'}  "
        f"(confidence level {conf_text(result.conf)}%)")
    if test == "Unpaired t-test" and min(v1, v2) > 0:
        f_ratio = max(v1, v2) / min(v1, v2)
        dfn = (n1 - 1) if v1 >= v2 else (n2 - 1)
        dfd = (n2 - 1) if v1 >= v2 else (n1 - 1)
        p_f = min(1.0, 2 * stats.f.sf(f_ratio, dfn, dfd))
        result.summary["F test"] = (f_ratio, dfn, dfd, p_f)
        result.extra_lines.append(
            f"F test to compare variances: F = {fmt(f_ratio)}, {format_p(p_f)}"
            + ("  (variances differ; consider Welch's t-test)" if p_f < 0.05 else ""))
    result.comparisons = [Comparison(names[0], names[1], 0, 1, diff, float(res.pvalue), lo, hi,
                                     diff_label="Mean diff. (B - A)", mean1=m1, mean2=m2, se=se,
                                     n1=n1, n2=n2, stat=abs(float(res.statistic)), stat_name="t",
                                     df=df)]
    return result


def _paired(result, groups, test):
    (n1, v1), (n2, v2) = groups
    x, y = np.asarray(v1, float), np.asarray(v2, float)
    rows = min(x.size, y.size)
    x, y = x[:rows], y[:rows]
    keep = np.isfinite(x) & np.isfinite(y)
    dropped = int(np.sum(np.isfinite(x) | np.isfinite(y)) - np.sum(keep))
    x, y = x[keep], y[keep]
    n = x.size
    if n < 2:
        return _fail(result, "Paired tests need at least two rows with values in both columns.")
    result.summary["dropped"] = dropped
    if dropped:
        result.extra_lines.append(f"{dropped} row(s) without a partner value were excluded.")
    d = y - x   # Prism: mean of differences (B - A)
    if test == "Paired t-test":
        res = stats.ttest_rel(x, y)
        mean_d = float(np.mean(d))
        se = float(np.std(d, ddof=1)) / math.sqrt(n)
        tcrit = stats.t.ppf(0.5 + result.conf / 2, n - 1)
        result.omnibus = (f"t = {fmt(abs(float(res.statistic)))}, df = {n - 1}, "
                          f"{format_p(res.pvalue)} (two-tailed), pairs = {n}")
        result.summary["P"] = float(res.pvalue)
        result.extra_lines.append(
            f"Significantly different (P < {alpha_text(result.conf)})? "
            f"{'Yes' if res.pvalue < 1 - result.conf else 'No'}  "
            f"(confidence level {conf_text(result.conf)}%)")
        result.comparisons = [Comparison(n1, n2, 0, 1, mean_d, float(res.pvalue),
                                         mean_d - tcrit * se, mean_d + tcrit * se,
                                         diff_label="Mean of differences (B - A)")]
    else:
        if np.all(d == 0):
            return _fail(result, "All paired differences are zero.")
        res = stats.wilcoxon(x, y)
        result.omnibus = (f"Wilcoxon W = {fmt(float(res.statistic))}, "
                          f"{format_p(res.pvalue)} (two-tailed), pairs = {n}")
        result.summary["P"] = float(res.pvalue)
        result.comparisons = [Comparison(n1, n2, 0, 1, float(np.median(d)), float(res.pvalue),
                                         diff_label="Median of differences (B - A)")]
    return result


def _pairs(k, mode):
    if mode == "Each vs. first column":
        return [(0, j) for j in range(1, k)]
    return [(i, j) for i in range(k) for j in range(i + 1, k)]


def _anova(result, names, samples, mode):
    if any(s.size < 2 for s in samples):
        return _fail(result, "One-way ANOVA needs at least two values in every column.")
    k = len(samples)
    n_total = sum(s.size for s in samples)
    f_val, p_val = stats.f_oneway(*samples)
    grand = np.mean(np.concatenate(samples))
    ss_between = float(sum(s.size * (np.mean(s) - grand) ** 2 for s in samples))
    ss_total = float(np.sum((np.concatenate(samples) - grand) ** 2))
    ss_within = ss_total - ss_between
    r2 = ss_between / ss_total if ss_total > 0 else NAN
    mse = ss_within / (n_total - k)
    result.table = [("Treatment (between columns)", ss_between, k - 1, ss_between / (k - 1),
                     float(f_val), k - 1, n_total - k, float(p_val)),
                    ("Residual (within columns)", ss_within, n_total - k, mse, NAN, NAN, NAN, NAN),
                    ("Total", ss_total, n_total - 1, NAN, NAN, NAN, NAN, NAN)]
    result.summary = {"F": float(f_val), "P": float(p_val), "R squared": r2,
                      "k": k, "n_total": n_total}
    result.omnibus = (f"F ({k - 1}, {n_total - k}) = {fmt(float(f_val))}, "
                      f"{format_p(float(p_val))}, R squared = {fmt(r2, 4)}")
    bf = stats.levene(*samples, center="median")
    result.summary["Brown-Forsythe"] = (float(bf.statistic), k - 1, n_total - k, float(bf.pvalue))
    result.extra_lines.append(
        f"Brown-Forsythe test for equal variances: F ({k - 1}, {n_total - k}) = "
        f"{fmt(float(bf.statistic))}, {format_p(float(bf.pvalue))}")
    if all(np.ptp(x) > 0 for x in samples):
        bt = stats.bartlett(*samples)
        result.summary["Bartlett"] = (float(bt.statistic), float(bt.pvalue))
        result.extra_lines.append(
            f"Bartlett's test for equal variances: corrected statistic = "
            f"{fmt(float(bt.statistic))}, {format_p(float(bt.pvalue))}")
    if k < 3:
        return result

    if mode == "Each vs. first column":
        result.posthoc = "Dunnett's multiple comparisons test (each vs. first column)"
        kwargs = {}
        params = inspect.signature(stats.dunnett).parameters
        if "rng" in params:
            kwargs["rng"] = 0
        elif "random_state" in params:
            kwargs["random_state"] = 0
        res = stats.dunnett(*samples[1:], control=samples[0], **kwargs)
        ci = res.confidence_interval(confidence_level=0.95)
        for idx in range(k - 1):
            j = idx + 1
            # SciPy reports treatment minus control; report control vs. treatment
            diff = -float(np.mean(samples[j]) - np.mean(samples[0]))
            se = math.sqrt(mse * (1 / samples[0].size + 1 / samples[j].size))
            result.comparisons.append(Comparison(
                names[0], names[j], 0, j, diff, float(res.pvalue[idx]),
                -float(ci.high[idx]), -float(ci.low[idx]),
                mean1=float(np.mean(samples[0])), mean2=float(np.mean(samples[j])), se=se,
                n1=samples[0].size, n2=samples[j].size, stat=abs(diff) / se, stat_name="q",
                df=n_total - k))
        result.families = (1, k - 1)
    else:
        result.posthoc = "Tukey's multiple comparisons test (all pairs)"
        res = stats.tukey_hsd(*samples)
        ci = res.confidence_interval(confidence_level=0.95)
        for i, j in _pairs(k, mode):
            se = math.sqrt(mse * (1 / samples[i].size + 1 / samples[j].size))
            diff = float(res.statistic[i, j])
            result.comparisons.append(Comparison(
                names[i], names[j], i, j, diff, float(res.pvalue[i, j]),
                float(ci.low[i, j]), float(ci.high[i, j]),
                mean1=float(np.mean(samples[i])), mean2=float(np.mean(samples[j])), se=se,
                n1=samples[i].size, n2=samples[j].size, stat=abs(diff) / se * math.sqrt(2),
                stat_name="q", df=n_total - k))
        result.families = (1, len(result.comparisons))
    return result


def dunn_test(samples, pairs):
    """Dunn's test with tie correction and Bonferroni adjustment.

    Returns a list of (i, j, mean rank difference, z, adjusted p).
    """
    sizes = [s.size for s in samples]
    pooled = np.concatenate(samples)
    n_total = pooled.size
    ranks = stats.rankdata(pooled)
    edges = np.cumsum([0] + sizes)
    mean_ranks = [float(np.mean(ranks[edges[g]:edges[g + 1]])) for g in range(len(samples))]
    _, counts = np.unique(pooled, return_counts=True)
    ties = float(np.sum(counts ** 3 - counts))
    sigma2 = n_total * (n_total + 1) / 12.0 - ties / (12.0 * (n_total - 1))
    m = len(pairs)
    out = []
    for i, j in pairs:
        se = math.sqrt(sigma2 * (1.0 / sizes[i] + 1.0 / sizes[j]))
        diff = mean_ranks[i] - mean_ranks[j]
        z = diff / se if se > 0 else NAN
        p_raw = 2.0 * stats.norm.sf(abs(z)) if math.isfinite(z) else NAN
        out.append((i, j, diff, z, min(1.0, p_raw * m)))
    return out


def _kruskal(result, names, samples, mode):
    if any(s.size < 1 for s in samples):
        return _fail(result, "Kruskal-Wallis needs at least one value in every column.")
    if np.ptp(np.concatenate(samples)) == 0:
        return _fail(result, "All values are identical, so ranks cannot be compared.")
    h, p = stats.kruskal(*samples)
    result.omnibus = f"Kruskal-Wallis statistic = {fmt(float(h))}, {format_p(float(p))}"
    result.summary["P"] = float(p)
    k = len(samples)
    if k < 3:
        return result
    label = "each vs. first column" if mode == "Each vs. first column" else "all pairs"
    result.posthoc = f"Dunn's multiple comparisons test ({label}, Bonferroni adjusted)"
    for i, j, diff, _z, p_adj in dunn_test(samples, _pairs(k, mode)):
        result.comparisons.append(Comparison(names[i], names[j], i, j, diff, p_adj,
                                             diff_label="Mean rank diff."))
    return result


def _rm_column(result, groups, test, mode, gg):
    from . import anova  # imported here to avoid a circular import

    names = [g[0] for g in groups]
    k = len(groups)
    Y, excluded = anova.complete_rows(groups)
    n = Y.shape[0]
    if k < 2:
        return _fail(result, "Add at least two columns with data.")
    if test == "Friedman test" and k < 3:
        return _fail(result, "The Friedman test needs three or more columns. "
                             "For two matched columns, use the Wilcoxon signed-rank test.")
    if n < 2:
        return _fail(result, "Repeated-measures tests need at least two rows with a value "
                             "in every column. Each row is one subject.")
    result.extra_lines.append(f"Each row is one subject. Subjects with complete data: {n}.")
    if excluded:
        result.summary["rm_excluded"] = int(excluded)
        result.extra_lines.append(f"{excluded} row(s) with missing values were excluded. Prism "
                                  "would fit a mixed-effects model instead; results may differ.")
    pairs = _pairs(k, mode)
    if test == "Repeated-measures one-way ANOVA":
        rows, eps, applied = anova.rm_oneway(Y, gg)
        treat, indiv, resid = rows
        result.summary.update({"P": float(treat.p), "epsilon": float(eps), "gg_applied": bool(applied),
                               "matching_p": float(indiv.p)})
        # Like Prism, show epsilon-corrected degrees of freedom when the correction is applied
        df1, df2 = (eps * treat.df, eps * treat.df_den) if applied else (treat.df, treat.df_den)
        result.omnibus = (f"F ({fmt(df1)}, {fmt(df2)}) = {fmt(treat.f)}, "
                          f"{format_p(treat.p)}" + (" (Geisser-Greenhouse corrected)" if applied else ""))
        if k > 2:
            result.extra_lines.append(
                f"Geisser-Greenhouse epsilon = {fmt(eps, 4)}"
                + ("" if applied else " (not applied; sphericity assumed)"))
        result.extra_lines.append(
            f"Was the matching effective? F ({fmt(indiv.df)}, {fmt(indiv.df_den)}) = "
            f"{fmt(indiv.f)}, {format_p(indiv.p)}")
        ss_total = treat.ss + indiv.ss + resid.ss
        result.extra_lines.append(
            f"R squared = {fmt(treat.ss / (treat.ss + resid.ss), 4)}; matching R squared = "
            f"{fmt(indiv.ss / ss_total, 4)}")
        if k > 2:
            pooled = None if applied else (resid.ms, resid.df)
            basis = ("paired differences, separate error per comparison" if applied
                     else "pooled residual error")
            if mode == "Each vs. first column":
                result.posthoc = f"Šídák's multiple comparisons test (each vs. first column; {basis})"
                result.comparisons = anova.rm_posthoc_columns(names, Y, pairs, pooled)
            else:
                result.posthoc = f"Tukey's multiple comparisons test (all pairs; {basis})"
                result.comparisons = anova.rm_tukey_columns(names, Y, pooled)
            result.families = (1, len(result.comparisons))
        else:
            d = Y[:, 0] - Y[:, 1]
            se = float(np.std(d, ddof=1)) / math.sqrt(n)
            tcrit = stats.t.ppf(0.975, n - 1)
            result.comparisons = [Comparison(names[0], names[1], 0, 1, float(np.mean(d)),
                                             float(treat.p), float(np.mean(d)) - tcrit * se,
                                             float(np.mean(d)) + tcrit * se,
                                             diff_label="Mean of differences")]
    else:
        res = stats.friedmanchisquare(*Y.T)
        result.omnibus = f"Friedman statistic = {fmt(float(res.statistic))}, {format_p(float(res.pvalue))}"
        result.summary["P"] = float(res.pvalue)
        label = "each vs. first column" if mode == "Each vs. first column" else "all pairs"
        result.posthoc = f"Dunn's multiple comparisons test ({label}, Bonferroni adjusted)"
        result.comparisons = anova.friedman_dunn(names, Y, pairs)
    return result


# ---------------------------------------------------------------------------
# Curve fitting for XY data
# ---------------------------------------------------------------------------

def _linear(x, slope, intercept):
    return slope * x + intercept


def _four_pl(x, bottom, top, log_ec50, hill):
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        return bottom + (top - bottom) / (1.0 + 10.0 ** ((log_ec50 - np.log10(x)) * hill))


def _decay(x, y0, plateau, k):
    with np.errstate(over="ignore"):
        return (y0 - plateau) * np.exp(-k * x) + plateau


def _association(x, y0, plateau, k):
    with np.errstate(over="ignore"):
        return y0 + (plateau - y0) * (1.0 - np.exp(-k * x))


FIT_MODELS = {
    "None": None,
    "Linear regression": (_linear, ["Slope", "Y-intercept"]),
    "Dose-response, 4PL (variable slope)": (_four_pl, ["Bottom", "Top", "LogEC50", "Hill slope"]),
    "One-phase exponential decay": (_decay, ["Y0", "Plateau", "K"]),
    "One-phase association": (_association, ["Y0", "Plateau", "K"]),
}


@dataclass
class FitResult:
    series: str
    model: str
    ok: bool = True
    message: str = ""
    params: list = field(default_factory=list)   # (name, value, se, ci_low, ci_high)
    derived: list = field(default_factory=list)  # (name, text)
    r2: float = NAN
    syx: float = NAN
    n: int = 0
    func: object = None
    values: tuple = ()

    def predict(self, x):
        return self.func(np.asarray(x, float), *self.values)


def flatten_xy(x, y_matrix):
    """Use every replicate as its own point, as Prism does by default."""
    x = np.asarray(x, float)
    y = np.asarray(y_matrix, float)
    if y.ndim == 1:
        y = y[:, None]
    xs = np.repeat(x[:, None], y.shape[1], axis=1).ravel()
    ys = y.ravel()
    keep = np.isfinite(xs) & np.isfinite(ys)
    return xs[keep], ys[keep]


def _initial_guess(model, x, y):
    order = np.argsort(x)
    xs, ys = x[order], y[order]
    span = float(np.ptp(xs)) or 1.0
    if model == "Linear regression":
        slope, intercept = np.polyfit(xs, ys, 1)
        return [slope, intercept]
    if model.startswith("Dose-response"):
        lx = np.log10(xs)
        rising = np.corrcoef(lx, ys)[0, 1] >= 0 if np.ptp(ys) > 0 else True
        lo, hi = float(np.min(ys)), float(np.max(ys))
        bottom, top = (lo, hi) if rising else (hi, lo)
        return [bottom, top, float((lx.min() + lx.max()) / 2), 1.0]
    first = float(np.mean(ys[xs == xs[0]]))
    last = float(np.mean(ys[xs == xs[-1]]))
    return [first, last, 3.0 / span]


def fit_curve(series_name, x, y_matrix, model):
    result = FitResult(series=series_name, model=model)
    spec = FIT_MODELS.get(model)
    if spec is None:
        return _fit_fail(result, "No model selected.")
    func, names = spec
    xs, ys = flatten_xy(x, y_matrix)
    if model.startswith("Dose-response"):
        positive = xs > 0
        excluded = int(np.sum(~positive))
        xs, ys = xs[positive], ys[positive]
        if excluded:
            result.derived.append(("Note", f"{excluded} point(s) with X <= 0 excluded "
                                           "(X must be concentration, not log)."))
    n, p = xs.size, len(names)
    result.n = n
    if n <= p or np.unique(xs).size < p:
        return _fit_fail(result, f"Need more than {p} points at {p} or more X values.")
    try:
        p0 = _initial_guess(model, xs, ys)
        with warnings.catch_warnings():
            # Inestimable errors are reported in the results instead of on the console
            warnings.simplefilter("ignore", OptimizeWarning)
            values, pcov = curve_fit(func, xs, ys, p0=p0, maxfev=20000)
    except (RuntimeError, ValueError, TypeError) as exc:
        return _fit_fail(result, f"Fit did not converge: {exc}")

    df = n - p
    resid = ys - func(xs, *values)
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((ys - np.mean(ys)) ** 2))
    result.r2 = 1 - ss_res / ss_tot if ss_tot > 0 else NAN
    result.syx = math.sqrt(ss_res / df)
    tcrit = stats.t.ppf(0.975, df)
    diag = np.diag(pcov) if np.all(np.isfinite(pcov)) else np.full(p, np.inf)
    ses = np.sqrt(np.where(diag >= 0, diag, np.nan))
    if not np.all(np.isfinite(ses)):
        result.derived.append(("Warning", "Some parameter errors could not be estimated. "
                                          "Check the fit before reporting it."))
    for name, val, se in zip(names, values, ses):
        result.params.append((name, float(val), float(se),
                              float(val - tcrit * se), float(val + tcrit * se)))
    result.func = func
    result.values = tuple(float(v) for v in values)

    if model == "Linear regression":
        lr = stats.linregress(xs, ys)
        result.derived.append(("Slope different from zero", format_p(float(lr.pvalue))))
        if values[0] != 0:
            result.derived.append(("X-intercept", fmt(float(-values[1] / values[0]))))
    elif model.startswith("Dose-response"):
        _, val, se, lo, hi = result.params[2]
        result.derived.append(("EC50", f"{fmt(10 ** val)} (95% CI {fmt(10 ** lo)} to {fmt(10 ** hi)})"))
    else:
        k_val = values[2]
        if k_val > 0:
            result.derived.append(("Half-life", fmt(math.log(2) / k_val)))
            result.derived.append(("Tau", fmt(1 / k_val)))
    return result


def _fit_fail(result, message):
    result.ok = False
    result.message = message
    return result


# ---------------------------------------------------------------------------
# Reports and methods text
# ---------------------------------------------------------------------------

def _table(rows, header):
    widths = [max(len(str(r[c])) for r in [header] + rows) for c in range(len(header))]
    line = lambda r: "  ".join(str(v).ljust(w) for v, w in zip(r, widths)).rstrip()
    return "\n".join([line(header)] + [line(r) for r in rows])


def column_report(result, error_kind, table_title="Data table"):
    if result is None:
        return "Type or paste values into the grid. Each column is one group."
    out = []
    if result.ok and result.table:
        from . import prism_format as pf
        out.append("Ordinary one-way ANOVA")
        out.append(pf.rows_to_text(pf.one_way_rows(result, table_title)))
        out.extend(result.extra_lines[2:])
        if result.comparisons:
            out.append("")
            out.append(pf.rows_to_text(pf.comparison_rows(result.comparisons, result.posthoc,
                                                          result.families)))
            out.append(STAR_LEGEND)
        out.append("")
    elif result.test != "None":
        out.append(result.test)
        if not result.ok:
            out.append(result.message)
        else:
            out.append(result.omnibus)
            out.extend(result.extra_lines)
            if result.comparisons:
                out.append("")
                if result.posthoc:
                    out.append(result.posthoc)
                rows = []
                for c in result.comparisons:
                    ci = (f"{fmt(c.ci_low)} to {fmt(c.ci_high)}"
                          if math.isfinite(c.ci_low) else "")
                    rows.append([f"{c.group1} vs. {c.group2}", fmt(c.diff), ci,
                                 format_p(c.p), c.summary])
                diff_label = result.comparisons[0].diff_label
                p_label = "Adjusted p" if result.posthoc else "p"
                ci_head = (f"{conf_text(result.conf)}% CI of diff." if result.test in T_TESTS
                           else "95% CI of diff.")
                out.append(_table(rows, ["Comparison", diff_label, ci_head,
                                         p_label, "Summary"]))
                out.append(STAR_LEGEND)
        out.append("")

    out.append(f"Descriptive statistics (graph error bars: {error_kind})")
    rows = [[d.name, d.n, fmt(d.mean), fmt(d.sd), fmt(d.sem), fmt(d.median),
             f"{fmt(d.minimum)} to {fmt(d.maximum)}"] for d in result.descriptives]
    out.append(_table(rows, ["Group", "n", "Mean", "SD", "SEM", "Median", "Range"]))
    out.append("")
    out.append("Normality (Shapiro-Wilk)")
    rows = [[name, fmt(w), format_p(p) if math.isfinite(p) else "needs n >= 3",
             ("" if not math.isfinite(p) else ("Normal" if p >= 0.05 else "Not normal"))]
            for name, w, p in result.normality]
    out.append(_table(rows, ["Group", "W", "p", "Passed (alpha = 0.05)"]))
    out.append("Normality tests have low power with small n. Use them as a guide only.")
    return "\n".join(out)


def xy_report(fits, error_kind, series_counts):
    out = [f"XY data: points are means, error bars are {error_kind}."]
    for name, n_points in series_counts:
        out.append(f"  {name}: {n_points} X values with data")
    for fit in fits:
        out.append("")
        out.append(f"{fit.series}: {fit.model}")
        if not fit.ok:
            out.append(f"  {fit.message}")
            continue
        rows = [[name, fmt(v), fmt(se), f"{fmt(lo)} to {fmt(hi)}"]
                for name, v, se, lo, hi in fit.params]
        out.append(_table(rows, ["Parameter", "Best fit", "Std. error", "95% CI"]))
        for label, text in fit.derived:
            out.append(f"{label}: {text}")
        out.append(f"R squared = {fmt(fit.r2, 4)}, Sy.x = {fmt(fit.syx)}, n points = {fit.n}")
    return "\n".join(out)


def software_line():
    return (f"{APP_NAME} v{__version__} (SciPy v{scipy.__version__}, "
            f"Python v{platform.python_version()})")


METHOD_PHRASES = {
    "Unpaired t-test": "a two-tailed unpaired t-test",
    "Welch's t-test": "a two-tailed Welch's t-test",
    "Paired t-test": "a two-tailed paired t-test",
    "Mann-Whitney test": "a two-tailed Mann-Whitney test",
    "Wilcoxon signed-rank test": "a two-tailed Wilcoxon signed-rank test",
    "One-way ANOVA": "one-way ANOVA",
    "Kruskal-Wallis test": "the Kruskal-Wallis test",
    "Repeated-measures one-way ANOVA": "repeated-measures one-way ANOVA",
    "Friedman test": "the Friedman test",
}


def methods_text(result, error_kind, plot_type, show_points):
    """A draft Methods/legend sentence. Edit before use."""
    shown = SHOWN.get(error_kind, "mean")
    if plot_type == "Box plot":
        first = "Box plots show the median and interquartile range"
    elif plot_type == "Violin plot":
        first = "Violin plots show the data distribution with the median and interquartile range"
    else:
        first = f"Data are presented as {shown}"
    if plot_type == "Before-after (matched rows)":
        first = "Lines connect values from the same subject"
    elif show_points:
        first += " with individual data points"
    sentences = [first + "."]
    if result is not None and result.ok and result.test != "None":
        phrase = METHOD_PHRASES.get(result.test, result.test)
        if "Geisser-Greenhouse corrected" in result.omnibus:
            phrase += " with the Geisser-Greenhouse correction"
        if result.posthoc:
            post = result.posthoc.split(" (")[0]
            if post.startswith("Dunn's"):
                post += " with Bonferroni adjustment"
            phrase += f" followed by {post}"
        sentences.append(f"Statistical significance was determined by {phrase}.")
        sentences.append(STAR_LEGEND + ".")
    sentences.append(f"Analyses were performed in {software_line()}.")
    return " ".join(sentences)


def xy_methods_text(fits, error_kind):
    shown = SHOWN.get(error_kind, "mean")
    sentences = [f"Data are presented as {shown}."]
    models = sorted({f.model for f in fits if f.ok})
    if models:
        sentences.append("Curves were fit by nonlinear least squares using all replicate values ("
                         + "; ".join(models) + ").")
    sentences.append(f"Analyses were performed in {software_line()}.")
    return " ".join(sentences)


def write_column_csv(path, result, table_title="Data table"):
    """One-way ANOVA results use Prism's sheet layout; other tests use a plain layout."""
    from . import prism_format as pf
    if result.ok and result.table:
        rows = pf.one_way_rows(result, table_title)
        if result.comparisons:
            rows += [[], []] + pf.comparison_rows(result.comparisons, result.posthoc, result.families)
        rows += [[], [], ["Descriptive statistics", "n", "Mean", "SD", "SEM", "Median"]]
        rows += [[f"  {d.name}", str(d.n), pf.num(d.mean), pf.num(d.sd), pf.num(d.sem),
                  pf.num(d.median)] for d in result.descriptives]
        pf.write_csv(path, rows)
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Descriptive statistics"])
        w.writerow(["Group", "n", "Mean", "SD", "SEM", "95% CI low", "95% CI high",
                    "Median", "Q1", "Q3", "Min", "Max"])
        for d in result.descriptives:
            w.writerow([d.name, d.n, d.mean, d.sd, d.sem, d.ci_low, d.ci_high,
                        d.median, d.q1, d.q3, d.minimum, d.maximum])
        if result.test != "None" and result.ok:
            w.writerow([])
            w.writerow([result.test, result.omnibus])
            for line in result.extra_lines:
                w.writerow(["", line])
            if result.comparisons:
                w.writerow([result.posthoc or "Comparison"])
                w.writerow(["Group 1", "Group 2", result.comparisons[0].diff_label,
                            "95% CI low", "95% CI high", "p", "Summary"])
                for c in result.comparisons:
                    w.writerow([c.group1, c.group2, c.diff, c.ci_low, c.ci_high, c.p, c.summary])


def write_xy_csv(path, fits):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Series", "Model", "Parameter", "Best fit", "Std. error",
                    "95% CI low", "95% CI high", "R squared", "Sy.x", "n"])
        for f in fits:
            if not f.ok:
                w.writerow([f.series, f.model, f.message])
                continue
            for name, v, se, lo, hi in f.params:
                w.writerow([f.series, f.model, name, v, se, lo, hi, f.r2, f.syx, f.n])
            for label, text in f.derived:
                w.writerow([f.series, f.model, label, text])
