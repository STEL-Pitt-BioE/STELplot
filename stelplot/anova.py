"""Two-way and repeated-measures ANOVA for STELplot.

Methods
-------
Ordinary two-way ANOVA uses a least-squares model with sum-to-zero (effect)
coding and Type III sums of squares, so unequal n per cell is handled.

Repeated-measures designs use the standard multivariate-to-univariate
approach: each subject's repeated values are transformed with orthonormal
contrasts, the between-subject design is fit by least squares, and the
sphericity-assumed F tests are traces of the hypothesis and error SSCP
matrices. The Geisser-Greenhouse epsilon is computed from the pooled
within-group covariance of those contrasts. Subjects with any missing value
are excluded (Prism would instead fit a mixed-effects model).
"""

__author__ = "Daniel Shiwarski"

import math
from dataclasses import dataclass, field

import numpy as np
from scipy import stats

from .stats_engine import Comparison, fmt, software_line

NAN = float("nan")

ANALYSES = ["Two-way ANOVA", "None"]
# Wording follows Prism's grouped-table matching options
ACROSS_ROW = "Matched values spread across a row"
IN_SUBCOLUMN = "Matched values stacked in a subcolumn"
DESIGNS = ["No matching", ACROSS_ROW, IN_SUBCOLUMN]
DESIGN_HELP = {
    "No matching": "Every value is an independent sample.",
    ACROSS_ROW: "Each subject is one replicate within a row, measured in every data set "
                "(for example, Before and After as data sets).",
    IN_SUBCOLUMN: "Each subject is one replicate subcolumn, measured at every row "
                  "(for example, time points down the rows).",
}
CELLS = "Compare cell means regardless of rows and columns"
GROUPED_COMPARISONS = ["None", "Compare columns within each row",
                       "Compare each column to the first, within each row",
                       "Compare rows within each column", CELLS]
FULL_MODEL = "Full model (with interaction)"
MAIN_EFFECTS = "Main effects only"
MODELS = [FULL_MODEL, MAIN_EFFECTS]
CORRECTIONS = ["Šídák", "Tukey"]


@dataclass
class AnovaRow:
    source: str
    ss: float
    df: float
    ms: float = NAN
    f: float = NAN
    df_den: float = NAN
    p: float = NAN
    pct: float = NAN
    gg: bool = False


@dataclass
class GroupedResult:
    title: str
    ok: bool = True
    message: str = ""
    design: str = "No matching"
    rows: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    posthoc: str = ""
    comparisons: list = field(default_factory=list)
    cells: list = field(default_factory=list)
    epsilon: float = NAN
    gg_applied: bool = False
    families: tuple = (1, 0)
    col_diff: dict = field(default_factory=dict)      # Prism "Difference between column means"
    data_summary: dict = field(default_factory=dict)
    model: str = FULL_MODEL


# ---------------------------------------------------------------------------
# Linear algebra helpers
# ---------------------------------------------------------------------------

def effect_code(levels, n_levels):
    """Sum-to-zero coding: n_levels - 1 columns, last level coded -1."""
    levels = np.asarray(levels)
    X = np.zeros((levels.size, max(n_levels - 1, 0)))
    for lv in range(n_levels - 1):
        X[levels == lv, lv] = 1.0
    if n_levels > 1:
        X[levels == n_levels - 1, :] = -1.0
    return X


def helmert(a):
    """a x (a - 1) orthonormal contrasts, each orthogonal to the unit vector."""
    M = np.zeros((a, a - 1))
    for j in range(1, a):
        v = np.zeros(a)
        v[:j] = 1.0
        v[j] = -float(j)
        M[:, j - 1] = v / np.linalg.norm(v)
    return M


def _sse(X, y):
    beta, _res, rank, _sv = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ beta
    return float(r @ r), int(rank)


def _hyp_ss(L, B, XtX_inv):
    """Trace of the hypothesis SSCP matrix for L B = 0."""
    LB = L @ B
    middle = np.linalg.pinv(L @ XtX_inv @ L.T)
    H = LB.T @ middle @ LB
    return float(np.trace(np.atleast_2d(H)))


def gg_epsilon(error_sscp, df_error):
    """Geisser-Greenhouse epsilon from the contrast error SSCP matrix."""
    k = error_sscp.shape[0]
    if k < 2 or df_error <= 0:
        return 1.0
    S = error_sscp / df_error
    tr = np.trace(S)
    tr2 = np.trace(S @ S)
    if tr2 <= 0:
        return 1.0
    eps = tr * tr / (k * tr2)
    return float(min(1.0, max(1.0 / k, eps)))


def sidak(p, m):
    """Šídák multiplicity-adjusted p value for a family of m comparisons."""
    if not math.isfinite(p):
        return NAN
    p = min(max(p, 0.0), 1.0)
    if p >= 1.0:
        return 1.0
    return float(min(1.0, -math.expm1(m * math.log1p(-p))))


def _sidak_tcrit(m, df):
    alpha = -math.expm1(math.log1p(-0.05) / m)
    return float(stats.t.ppf(1 - alpha / 2, df))


# ---------------------------------------------------------------------------
# Repeated-measures core (one-way RM and mixed designs)
# ---------------------------------------------------------------------------

def rm_core(Y, groups, n_groups):
    """Y: subjects x within levels (complete). groups: between-group index per subject."""
    n_s, a = Y.shape
    b = n_groups
    cols = [np.ones(n_s)]
    if b > 1:
        cols.append(effect_code(groups, b))
    X = np.column_stack(cols)
    XtX_inv = np.linalg.pinv(X.T @ X)
    df_subj = n_s - b
    out = {"a": a, "b": b, "n_s": n_s, "df_subj": df_subj}

    # Between subjects: subject totals scaled to original units
    z0 = Y.sum(axis=1) / math.sqrt(a)
    beta0 = XtX_inv @ X.T @ z0
    r0 = z0 - X @ beta0
    out["ss_subj"] = float(r0 @ r0)
    if b > 1:
        L = np.zeros((b - 1, X.shape[1]))
        L[:, 1:b] = np.eye(b - 1)
        out["ss_between"] = _hyp_ss(L, beta0[:, None], XtX_inv)

    # Within subjects
    M = helmert(a)
    Z = Y @ M
    B = XtX_inv @ X.T @ Z
    E = Z - X @ B
    E_sscp = E.T @ E
    out["ss_error"] = float(np.trace(E_sscp))
    out["df_error"] = (a - 1) * df_subj
    L0 = np.zeros((1, X.shape[1]))
    L0[0, 0] = 1.0
    out["ss_within"] = _hyp_ss(L0, B, XtX_inv)
    if b > 1:
        out["ss_interaction"] = _hyp_ss(L, B, XtX_inv)
    out["epsilon"] = gg_epsilon(E_sscp, df_subj)
    out["ss_total"] = float(np.sum((Y - Y.mean()) ** 2))
    return out


def _f_row(source, ss, df, ms_den, df_den, ss_total, eps=1.0, gg=False):
    ms = ss / df
    f = ms / ms_den if ms_den > 0 else NAN
    e = eps if gg else 1.0
    p = float(stats.f.sf(f, e * df, e * df_den)) if math.isfinite(f) else NAN
    return AnovaRow(source, ss, df, ms, f, df_den, p, 100 * ss / ss_total if ss_total else NAN, gg)


def rm_oneway(Y, gg=True):
    """Repeated-measures one-way ANOVA on complete rows (subjects x conditions)."""
    c = rm_core(Y, np.zeros(Y.shape[0], int), 1)
    a, n_s = c["a"], c["n_s"]
    ms_err = c["ss_error"] / c["df_error"]
    apply = gg and a > 2
    rows = [
        _f_row("Treatment (between columns)", c["ss_within"], a - 1, ms_err, c["df_error"],
               c["ss_total"], c["epsilon"], apply),
        _f_row("Individual (between rows)", c["ss_subj"], n_s - 1, ms_err, c["df_error"],
               c["ss_total"]),
        AnovaRow("Residual", c["ss_error"], c["df_error"], ms_err,
                 pct=100 * c["ss_error"] / c["ss_total"] if c["ss_total"] else NAN),
    ]
    return rows, c["epsilon"], apply


# ---------------------------------------------------------------------------
# Data handling for grouped tables
# ---------------------------------------------------------------------------

def clean_grouped(row_labels, col_names, D):
    """Drop empty rows and data sets. D has shape rows x data sets x replicates."""
    D = np.asarray(D, float)
    has = np.isfinite(D)
    keep_r = has.any(axis=(1, 2))
    keep_c = has.any(axis=(0, 2))
    D = D[keep_r][:, keep_c]
    rl = [row_labels[i] for i in range(len(row_labels)) if keep_r[i]]
    cn = [col_names[j] for j in range(len(col_names)) if keep_c[j]]
    return rl, cn, D


def cell_table(row_labels, col_names, D):
    cells = []
    for r, rl in enumerate(row_labels):
        for c, cn in enumerate(col_names):
            v = D[r, c][np.isfinite(D[r, c])]
            n = v.size
            mean = float(np.mean(v)) if n else NAN
            sd = float(np.std(v, ddof=1)) if n > 1 else NAN
            sem = sd / math.sqrt(n) if n > 1 else NAN
            cells.append((rl, cn, n, mean, sd, sem))
    return cells


def _subjects(D, design):
    """Return (Y subjects x within levels, between index, excluded count, within axis)."""
    R, C, K = D.shape
    Ys, groups, excluded = [], [], 0
    if design == IN_SUBCOLUMN:
        for c in range(C):
            for k in range(K):
                y = D[:, c, k]
                if np.all(np.isfinite(y)):
                    Ys.append(y)
                    groups.append(c)
                elif np.any(np.isfinite(y)):
                    excluded += 1
    else:
        for r in range(R):
            for k in range(K):
                y = D[r, :, k]
                if np.all(np.isfinite(y)):
                    Ys.append(y)
                    groups.append(r)
                elif np.any(np.isfinite(y)):
                    excluded += 1
    if not Ys:
        return np.zeros((0, 0)), np.zeros(0, int), excluded
    return np.array(Ys), np.array(groups, int), excluded


# ---------------------------------------------------------------------------
# Two-way analyses
# ---------------------------------------------------------------------------

def run_grouped(row_labels, col_names, D, design="No matching", comparisons="None",
                correction="Šídák", gg=True, model=FULL_MODEL):
    row_labels, col_names, D = clean_grouped(row_labels, col_names, D)
    title = "Two-way ANOVA" if design == "No matching" else \
        f"Two-way repeated-measures ANOVA ({design.lower()})"
    res = GroupedResult(title=title, design=design)
    if design != "No matching":
        if comparisons == CELLS:
            res.notes.append("Cell-by-cell comparisons are available for designs without matching; "
                             "none were run.")
            comparisons = "None"
        if model == MAIN_EFFECTS:
            res.notes.append("Main effects only applies to designs without matching; the full "
                             "model was fit.")
            model = FULL_MODEL
    res.model = model
    res.comparison_mode = comparisons
    res.n_cols = len(col_names)
    R, C = len(row_labels), len(col_names)
    if R == 0:
        res.ok, res.message = False, "Enter data to run the analysis."
        return res
    res.cells = cell_table(row_labels, col_names, D)
    if R < 2 or C < 2:
        res.ok = False
        res.message = ("Two-way ANOVA needs at least two rows and two data sets with values. "
                       "For one factor, use a Column table.")
        return res
    try:
        if design == "No matching":
            _ordinary(res, row_labels, col_names, D, comparisons, correction, model)
        else:
            _mixed(res, row_labels, col_names, D, design, comparisons, correction, gg)
    except (ValueError, np.linalg.LinAlgError, ZeroDivisionError) as exc:
        res.ok, res.message = False, f"The analysis could not run on these data: {exc}"
    return res


def _ordinary(res, row_labels, col_names, D, comparisons, correction, model=FULL_MODEL):
    R, C, _ = D.shape
    rr, cc, kk = np.nonzero(np.isfinite(D))
    y = D[rr, cc, kk]
    n_obs = y.size
    counts = np.zeros((R, C), int)
    np.add.at(counts, (rr, cc), 1)
    if (counts == 0).any():
        empty = [f"{row_labels[r]} / {col_names[c]}" for r, c in zip(*np.nonzero(counts == 0))]
        res.ok = False
        res.message = "Every row and data set combination needs at least one value. Empty: " + \
            ", ".join(empty[:6])
        return
    A = effect_code(rr, R)
    B = effect_code(cc, C)
    replicated = n_obs > R * C
    fit_interaction = replicated and model != MAIN_EFFECTS
    terms = {}
    if fit_interaction:
        terms["Interaction"] = np.column_stack([A[:, i] * B[:, j]
                                                for i in range(R - 1) for j in range(C - 1)])
    terms["Row factor"] = A
    terms["Column factor"] = B
    ones = np.ones(n_obs)
    sse_full, rank = _sse(np.column_stack([ones] + list(terms.values())), y)
    df_err = n_obs - rank
    if df_err <= 0:
        res.ok, res.message = False, "Not enough values to estimate the residual error."
        return
    mse = sse_full / df_err
    ss_total = float(np.sum((y - y.mean()) ** 2))
    for name, cols in terms.items():
        others = [ones] + [v for key, v in terms.items() if key != name]
        sse_red, _ = _sse(np.column_stack(others), y)
        res.rows.append(_f_row(name, sse_red - sse_full, cols.shape[1], mse, df_err, ss_total))
    res.rows.append(AnovaRow("Residual", sse_full, df_err, mse,
                             pct=100 * sse_full / ss_total if ss_total else NAN))
    res.rows.append(AnovaRow("Total", ss_total, n_obs - 1))
    res.data_summary = {"columns": C, "rows": R, "values": int(n_obs),
                        "missing": int(np.sum(~np.isfinite(D)))}
    if C == 2:
        v1, v2 = y[cc == 0], y[cc == 1]
        se = math.sqrt(mse * (1 / v1.size + 1 / v2.size))
        diff = float(v1.mean() - v2.mean())
        half = float(stats.t.ppf(0.975, df_err)) * se
        res.col_diff = {"names": (col_names[0], col_names[1]), "means": (float(v1.mean()), float(v2.mean())),
                        "diff": diff, "se": se, "ci": (diff - half, diff + half), "checked": False}
    if not replicated:
        res.notes.append("Only one value per cell, so the interaction cannot be tested. "
                         "The model includes main effects only.")
    elif not fit_interaction:
        res.notes.append("Main effects only: the interaction was not fit, so its variation is part "
                         "of the residual.")
    if len(np.unique(counts)) > 1:
        res.notes.append("Cell sizes differ; Type III sums of squares are reported.")
    if comparisons == CELLS:
        _cells_posthoc(res, row_labels, col_names, rr, cc, y, counts, correction, mse, df_err,
                       fit_interaction)
    elif comparisons != "None":
        _posthoc_pooled(res, row_labels, col_names, D, comparisons, correction, mse, df_err)


def _cell_design(r_idx, c_idx, R, C, interaction):
    A = effect_code(r_idx, R)
    B = effect_code(c_idx, C)
    cols = [np.ones(len(r_idx)), A, B]
    if interaction:
        cols.append(np.column_stack([A[:, i] * B[:, j] for i in range(R - 1) for j in range(C - 1)]))
    return np.column_stack(cols)


def _cells_posthoc(res, row_labels, col_names, rr, cc, y, counts, correction, mse, df_err,
                   interaction):
    """Compare every cell mean with every other, using the model's predicted (LS) means.

    With the full model the predicted means are the cell means. With main effects only
    they come from the additive fit, as in Prism.
    """
    R, C = len(row_labels), len(col_names)
    X = _cell_design(rr, cc, R, C, interaction)
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    cells = [(r, c) for r in range(R) for c in range(C)]
    Xc = _cell_design(np.array([r for r, _ in cells]), np.array([c for _, c in cells]), R, C,
                      interaction)
    pred = Xc @ beta
    items = []
    for a in range(len(cells)):
        for b in range(a + 1, len(cells)):
            L = Xc[a] - Xc[b]
            se = math.sqrt(max(mse * float(L @ XtX_inv @ L), 0.0))
            (r1, c1), (r2, c2) = cells[a], cells[b]
            comp = Comparison(f"{row_labels[r1]}:{col_names[c1]}", f"{row_labels[r2]}:{col_names[c2]}",
                              a, b, float(pred[a] - pred[b]), NAN,
                              diff_label="Predicted (LS) mean diff.")
            comp.context, comp.cluster = "", -1
            comp.mean1, comp.mean2 = float(pred[a]), float(pred[b])
            comp.n1, comp.n2 = int(counts[r1, c1]), int(counts[r2, c2])
            items.append((comp, comp.diff / se if se > 0 else NAN, df_err, se))
    name = _adjust(res, items, correction, True, len(cells))
    res.posthoc = (f"{name} multiple comparisons test (compare cell means regardless of rows and "
                   f"columns; predicted means; pooled residual error)")


def _mixed(res, row_labels, col_names, D, design, comparisons, correction, gg):
    Y, groups, excluded = _subjects(D, design)
    if design == IN_SUBCOLUMN:
        within_name, between_name = "Row factor", "Column factor"
        b = len(col_names)
    else:
        within_name, between_name = "Column factor", "Row factor"
        b = len(row_labels)
    if Y.shape[0] == 0:
        res.ok, res.message = False, "No subject has a value at every level. Check the layout."
        return
    present = np.unique(groups)
    if present.size < b:
        res.ok, res.message = False, "Every group needs at least one complete subject."
        return
    if Y.shape[0] - b < 1:
        res.ok, res.message = False, "Need more subjects than groups to estimate error."
        return
    c = rm_core(Y, groups, b)
    a = c["a"]
    apply = gg and a > 2
    ms_subj = c["ss_subj"] / c["df_subj"]
    ms_err = c["ss_error"] / c["df_error"]
    tot = c["ss_total"]
    res.rows = [
        _f_row("Interaction", c["ss_interaction"], (a - 1) * (b - 1), ms_err, c["df_error"],
               tot, c["epsilon"], apply),
        _f_row(within_name, c["ss_within"], a - 1, ms_err, c["df_error"], tot, c["epsilon"], apply),
        _f_row(between_name, c["ss_between"], b - 1, ms_subj, c["df_subj"], tot),
        _f_row("Subject", c["ss_subj"], c["df_subj"], ms_err, c["df_error"], tot),
        AnovaRow("Residual", c["ss_error"], c["df_error"], ms_err, pct=100 * c["ss_error"] / tot),
    ]
    order = {"Interaction": 0, "Row factor": 1, "Column factor": 2, "Subject": 3, "Residual": 4}
    res.rows.sort(key=lambda r: order.get(r.source, 9))   # Prism's row order
    res.epsilon = c["epsilon"]
    res.gg_applied = apply
    res.data_summary = {"columns": len(col_names), "rows": len(row_labels), "subjects": int(Y.shape[0]),
                        "missing": int(np.sum(~np.isfinite(D)))}
    if design == ACROSS_ROW and a == 2:
        m1, m2 = float(Y[:, 0].mean()), float(Y[:, 1].mean())
        se = math.sqrt(2.0 * ms_err / Y.shape[0])
        half = float(stats.t.ppf(0.975, c["df_error"])) * se
        res.col_diff = {"names": (col_names[0], col_names[1]), "means": (m1, m2), "diff": m1 - m2,
                        "se": se, "ci": (m1 - m2 - half, m1 - m2 + half), "checked": True}
    res.notes.append(f"Subjects with complete data: {Y.shape[0]}.")
    if excluded:
        res.notes.append(f"{excluded} subject(s) with missing values were excluded. Prism would "
                         "fit a mixed-effects model instead; results may differ.")
    if a > 2:
        res.notes.append(f"Geisser-Greenhouse epsilon = {fmt(c['epsilon'], 3)}"
                         + (f" (applied to {within_name.lower()} and interaction)." if apply
                            else " (not applied; sphericity assumed)."))
    if comparisons != "None":
        pooled = None if apply else (ms_err, c["df_error"])
        _posthoc_rm(res, row_labels, col_names, Y, groups, design, comparisons, correction, pooled)


# ---------------------------------------------------------------------------
# Multiple comparisons
# ---------------------------------------------------------------------------

def _plan(comparisons, n_rows, n_cols):
    """List of (context index, level i, level j, within_rows flag)."""
    plan = []
    if comparisons == "Compare columns within each row":
        for r in range(n_rows):
            plan += [(r, i, j, True) for i in range(n_cols) for j in range(i + 1, n_cols)]
    elif comparisons == "Compare each column to the first, within each row":
        for r in range(n_rows):
            plan += [(r, 0, j, True) for j in range(1, n_cols)]
    elif comparisons == "Compare rows within each column":
        for c in range(n_cols):
            plan += [(c, i, j, False) for i in range(n_rows) for j in range(i + 1, n_rows)]
    return plan


def _adjust(res, items, correction, all_pairs, k_means):
    """items: list of (Comparison stub, t, df, se). Applies Tukey or Šídák."""
    m = len(items)
    use_tukey = correction == "Tukey" and all_pairs and k_means > 2
    if correction == "Tukey" and not use_tukey:
        res.notes.append("Tukey's test applies to all-pairs comparisons with pooled error; "
                         "Šídák's correction was used instead.")
    contexts = len({comp.context for comp, *_ in items}) or 1
    for comp, t, df, se in items:
        comp.se, comp.df = se, df
        if use_tukey:
            q = abs(t) * math.sqrt(2)
            comp.p = float(stats.studentized_range.sf(q, k_means, df))
            half = float(stats.studentized_range.ppf(0.95, k_means, df)) / math.sqrt(2) * se
            comp.stat, comp.stat_name = q, "q"
        else:
            comp.p = sidak(2 * float(stats.t.sf(abs(t), df)), m)
            half = _sidak_tcrit(m, df) * se
            comp.stat, comp.stat_name = abs(t), "t"
        comp.ci_low, comp.ci_high = comp.diff - half, comp.diff + half
        res.comparisons.append(comp)
    res.families = (contexts, m // contexts) if use_tukey else (1, m)
    return "Tukey's" if use_tukey else "Šídák's"


def _posthoc_pooled(res, row_labels, col_names, D, comparisons, correction, mse, df_err):
    R, C, _ = D.shape
    plan = _plan(comparisons, R, C)
    means = np.nanmean(D, axis=2)
    counts = np.sum(np.isfinite(D), axis=2)
    items = []
    for ctx, i, j, within_rows in plan:
        if within_rows:
            m1, m2, n1, n2 = means[ctx, i], means[ctx, j], counts[ctx, i], counts[ctx, j]
            comp = Comparison(col_names[i], col_names[j], i, j, float(m1 - m2), NAN)
            comp.context, comp.cluster = row_labels[ctx], ctx
        else:
            m1, m2, n1, n2 = means[i, ctx], means[j, ctx], counts[i, ctx], counts[j, ctx]
            comp = Comparison(row_labels[i], row_labels[j], i, j, float(m1 - m2), NAN)
            comp.context, comp.cluster = col_names[ctx], -1
        se = math.sqrt(mse * (1 / n1 + 1 / n2))
        comp.mean1, comp.mean2, comp.n1, comp.n2 = float(m1), float(m2), int(n1), int(n2)
        items.append((comp, comp.diff / se, df_err, se))
    all_pairs = comparisons != "Compare each column to the first, within each row"
    k = C if plan and plan[0][3] else R
    name = _adjust(res, items, correction, all_pairs, k)
    res.posthoc = f"{name} multiple comparisons test ({comparisons.lower()}; pooled residual error)"


def _posthoc_rm(res, row_labels, col_names, Y, groups, design, comparisons, correction,
                pooled=None):
    """Within-subject pairs use the pooled residual error when sphericity is assumed
    (this matches Prism), or paired differences with a separate error per comparison
    when the Geisser-Greenhouse correction is applied. Between-subject pairs at one
    level use the pooled SD at that level."""
    R, C = len(row_labels), len(col_names)
    plan = _plan(comparisons, R, C)
    rows_within = design == IN_SUBCOLUMN
    n_s, a = Y.shape
    b = len(np.unique(groups))
    items, kinds = [], set()
    for ctx, i, j, within_rows in plan:
        if within_rows:
            g1, g2 = col_names[i], col_names[j]
            context, cluster = row_labels[ctx], ctx
        else:
            g1, g2 = row_labels[i], row_labels[j]
            context, cluster = col_names[ctx], -1
        # Is this comparison between levels of the within factor?
        is_within = (not within_rows) if rows_within else within_rows
        if is_within:
            sel = groups == ctx
            d = Y[sel, i] - Y[sel, j]
            n = d.size
            if n < 2:
                continue
            diff = float(np.mean(d))
            means_n = (float(Y[sel, i].mean()), float(Y[sel, j].mean()), n, n)
            if pooled is not None:
                ms_err, df = pooled
                se = math.sqrt(2.0 * ms_err / n)
                kinds.add("within_pooled")
            else:
                se = float(np.std(d, ddof=1)) / math.sqrt(n)
                df = n - 1
                kinds.add("paired")
            t = diff / se if se > 0 else NAN
        else:
            level = ctx
            vals = Y[:, level]
            resid = sum(float(np.sum((vals[groups == g] - vals[groups == g].mean()) ** 2))
                        for g in np.unique(groups))
            df = n_s - b
            s2 = resid / df
            v1, v2 = vals[groups == i], vals[groups == j]
            se = math.sqrt(s2 * (1 / v1.size + 1 / v2.size))
            diff = float(v1.mean() - v2.mean())
            t = diff / se if se > 0 else NAN
            means_n = (float(v1.mean()), float(v2.mean()), v1.size, v2.size)
            kinds.add("pooled")
        comp = Comparison(g1, g2, i, j, diff, NAN,
                          diff_label="Mean diff." if not is_within else "Mean of differences")
        comp.context, comp.cluster = context, cluster
        comp.mean1, comp.mean2, comp.n1, comp.n2 = means_n
        items.append((comp, t, df, se))
    paired_only = kinds == {"paired"}
    all_pairs = comparisons != "Compare each column to the first, within each row"
    k = C if plan and plan[0][3] else R
    name = _adjust(res, items, correction, all_pairs and not paired_only, k)
    basis = {"paired": "paired differences, separate error per comparison",
             "within_pooled": "pooled residual error",
             "pooled": "pooled SD at each level"}[next(iter(kinds))] if kinds else ""
    res.posthoc = f"{name} multiple comparisons test ({comparisons.lower()}; {basis})"


# ---------------------------------------------------------------------------
# Column-table repeated measures (one-way RM ANOVA, Friedman)
# ---------------------------------------------------------------------------

def complete_rows(groups):
    """Stack columns by row and keep rows with a value in every column."""
    arrays = [np.asarray(v, float) for _, v in groups]
    n = max(a.size for a in arrays)
    Y = np.full((n, len(arrays)), np.nan)
    for j, a in enumerate(arrays):
        Y[:a.size, j] = a
    any_val = np.isfinite(Y).any(axis=1)
    keep = np.isfinite(Y).all(axis=1)
    return Y[keep], int(np.sum(any_val & ~keep))


def rm_posthoc_columns(names, Y, pairs, pooled=None):
    """Šídák-adjusted comparisons. pooled=(MS residual, df) uses the pooled residual
    error (sphericity assumed, as Prism does); otherwise paired differences."""
    m = len(pairs)
    out = []
    for i, j in pairs:
        d = Y[:, i] - Y[:, j]
        n = d.size
        diff = float(np.mean(d))
        if pooled is not None:
            se, df = math.sqrt(2.0 * pooled[0] / n), pooled[1]
        else:
            se, df = float(np.std(d, ddof=1)) / math.sqrt(n), n - 1
        t = diff / se if se > 0 else NAN
        p = sidak(2 * float(stats.t.sf(abs(t), df)), m) if math.isfinite(t) else NAN
        half = _sidak_tcrit(m, df) * se
        out.append(Comparison(names[i], names[j], i, j, diff, p, diff - half, diff + half,
                              diff_label="Mean of differences"))
    return out


def rm_tukey_columns(names, Y, pooled=None):
    """Tukey comparisons after RM one-way ANOVA.

    With the Geisser-Greenhouse correction (pooled=None), each pair uses its own paired
    error and DF = n - 1; this matches Prism 11. With sphericity assumed, the pooled
    residual error and its DF are used.
    """
    n, k = Y.shape
    out = []
    for i in range(k):
        for j in range(i + 1, k):
            d = Y[:, i] - Y[:, j]
            diff = float(np.mean(d))
            if pooled is not None:
                se, df = math.sqrt(2.0 * pooled[0] / n), pooled[1]
            else:
                se, df = float(np.std(d, ddof=1)) / math.sqrt(n), n - 1
            q = abs(diff) / se * math.sqrt(2) if se > 0 else NAN
            p = float(stats.studentized_range.sf(q, k, df)) if math.isfinite(q) else NAN
            half = float(stats.studentized_range.ppf(0.95, k, df)) / math.sqrt(2) * se
            out.append(Comparison(names[i], names[j], i, j, diff, p, diff - half, diff + half,
                                  mean1=float(Y[:, i].mean()), mean2=float(Y[:, j].mean()), se=se,
                                  n1=n, n2=n, stat=q, stat_name="q", df=df))
    return out


def friedman_dunn(names, Y, pairs):
    """Dunn-type comparisons of mean ranks after Friedman, Bonferroni adjusted."""
    n, k = Y.shape
    ranks = np.apply_along_axis(stats.rankdata, 1, Y)
    mean_ranks = ranks.mean(axis=0)
    se = math.sqrt(k * (k + 1) / (6.0 * n))
    m = len(pairs)
    out = []
    for i, j in pairs:
        diff = float(mean_ranks[i] - mean_ranks[j])
        z = diff / se
        p = min(1.0, 2 * float(stats.norm.sf(abs(z))) * m)
        out.append(Comparison(names[i], names[j], i, j, diff, p, diff_label="Mean rank diff."))
    return out


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def _table(rows, header):
    widths = [max(len(str(r[c])) for r in [header] + rows) for c in range(len(header))]
    return "\n".join("  ".join(str(v).ljust(w) for v, w in zip(r, widths)).rstrip()
                     for r in [header] + rows)


def grouped_report(res, error_kind, star_legend, format_p, table_title="Data table",
                   row_factor="Row Factor", col_factor="Column Factor"):
    from . import prism_format as pf
    out = [res.title]
    if res.ok and res.rows:
        out.append(pf.rows_to_text(pf.two_way_rows(res, table_title, row_factor, col_factor)))
        out.extend(n for n in res.notes if not n.startswith("Subjects with complete data"))
        if res.comparisons:
            out.append("")
            note = pf.grouped_comparison_note(getattr(res, "comparison_mode", "None"),
                                              getattr(res, "n_cols", 2))
            out.append(pf.rows_to_text(pf.comparison_rows(res.comparisons, res.posthoc, res.families,
                                                          header_note=note, grouped=True)))
            out.append(star_legend)
    elif not res.ok:
        out.append(res.message)
    out.append("")
    out.append(f"Cell statistics (graph error bars: {error_kind})")
    rows = [[rl, cn, n, fmt(m), fmt(sd), fmt(se)] for rl, cn, n, m, sd, se in res.cells]
    out.append(_table(rows, ["Row", "Data set", "n", "Mean", "SD", "SEM"]))
    return "\n".join(out)


def grouped_methods_text(res, error_kind, plot_type, show_points, star_legend):
    """A draft legend and Methods sentence for grouped data. Edit before use."""
    from .stats_engine import SHOWN
    shown = SHOWN.get(error_kind, "mean")
    first = f"Data are presented as {shown}"
    if show_points:
        first += " with individual data points"
    sentences = [first + "."]
    if res is not None and res.ok:
        if res.design == "No matching":
            phrase = "two-way ANOVA"
        else:
            phrase = f"two-way repeated-measures ANOVA ({res.design.lower()})"
            if res.gg_applied:
                phrase += " with the Geisser-Greenhouse correction"
        if res.posthoc:
            phrase += f" followed by {res.posthoc.split(' (')[0]}"
        sentences.append(f"Statistical significance was determined by {phrase}.")
        if res.comparisons:
            sentences.append(star_legend + ".")
    sentences.append(f"Analyses were performed in {software_line()}.")
    return " ".join(sentences)


def write_grouped_csv(path, res, row_labels, col_names, D, table_title="Data table",
                      row_factor="Row Factor", col_factor="Column Factor"):
    """Two-way results in Prism's sheet layout, followed by cell statistics."""
    from . import prism_format as pf
    labels, names, block = clean_grouped(row_labels, col_names, D)
    cells = res.cells if res is not None else cell_table(labels, names, block)
    rows = []
    if res is not None and res.ok and res.rows:
        rows += pf.two_way_rows(res, table_title, row_factor, col_factor)
        if res.comparisons:
            note = pf.grouped_comparison_note(getattr(res, "comparison_mode", "None"),
                                              getattr(res, "n_cols", 2))
            rows += [[], []] + pf.comparison_rows(res.comparisons, res.posthoc, res.families,
                                                  header_note=note, grouped=True)
        rows += [[], []]
    elif res is not None and not res.ok:
        rows += [[res.title], [res.message], []]
    rows.append(["Cell statistics", "n", "Mean", "SD", "SEM"])
    rows += [[f"  {rl} / {cn}", str(n), pf.num(m), pf.num(sd), pf.num(sem)]
             for rl, cn, n, m, sd, sem in cells]
    pf.write_csv(path, rows)
