"""Checks for two-way and repeated-measures ANOVA. Run from the STELplot folder:

    python -m tests.test_anova

Each check compares STELplot against an independent textbook formula.
"""

__author__ = "Daniel Shiwarski"

import math

import numpy as np
from scipy import stats

from stelplot import anova
from stelplot import stats_engine as se

RNG = np.random.default_rng(11)


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print(f"PASS  {name}")


def close(a, b, tol=1e-8):
    return math.isclose(a, b, rel_tol=tol, abs_tol=1e-10)


def row(res, source):
    return next(r for r in res.rows if r.source == source)


def test_sidak():
    check("Šídák adjustment formula", close(anova.sidak(0.01, 3), 1 - 0.99 ** 3))
    check("Šídák p stays at 1", anova.sidak(1.0, 5) == 1.0)


def test_rm_oneway():
    n, k = 8, 4
    Y = RNG.normal(10, 2, (n, 1)) + np.array([0, 1, 2.5, 1.5]) + RNG.normal(0, 1, (n, k))
    rows, eps, _ = anova.rm_oneway(Y, gg=False)
    grand = Y.mean()
    ss_cond = n * np.sum((Y.mean(0) - grand) ** 2)
    ss_subj = k * np.sum((Y.mean(1) - grand) ** 2)
    ss_err = np.sum((Y - grand) ** 2) - ss_cond - ss_subj
    f_ref = (ss_cond / (k - 1)) / (ss_err / ((k - 1) * (n - 1)))
    check("RM one-way SS treatment matches classic formula", close(rows[0].ss, ss_cond))
    check("RM one-way SS residual matches classic formula", close(rows[2].ss, ss_err))
    check("RM one-way F matches classic formula", close(rows[0].f, f_ref))

    # Box's epsilon from the double-centered covariance matrix
    S = np.cov(Y, rowvar=False)
    sbar, sdiag, srow = S.mean(), np.mean(np.diag(S)), S.mean(axis=1)
    box = (k ** 2 * (sdiag - sbar) ** 2) / ((k - 1) * (np.sum(S ** 2) - 2 * k * np.sum(srow ** 2)
                                                         + k ** 2 * sbar ** 2))
    check("Geisser-Greenhouse epsilon matches Box's formula", close(eps, box, 1e-9))

    rows_gg, _, applied = anova.rm_oneway(Y, gg=True)
    p_ref = stats.f.sf(f_ref, eps * (k - 1), eps * (k - 1) * (n - 1))
    check("GG-corrected p uses epsilon-scaled df", applied and close(rows_gg[0].p, p_ref))

    Y2 = Y[:, :2]
    rows2, _, _ = anova.rm_oneway(Y2, gg=True)
    t = stats.ttest_rel(Y2[:, 0], Y2[:, 1])
    check("RM ANOVA with two columns gives F = t^2 of the paired t-test",
          close(rows2[0].f, float(t.statistic) ** 2))


def test_rm_column_interface():
    Y = RNG.normal(10, 2, (6, 1)) + np.array([0, 2, 4.0]) + RNG.normal(0, 1, (6, 3))
    groups = [("Day 1", Y[:, 0]), ("Day 7", Y[:, 1]), ("Day 14", Y[:, 2].copy())]
    groups[2][1][3] = np.nan
    r = se.run_column_stats(groups, "Repeated-measures one-way ANOVA")
    check("RM ANOVA excludes incomplete rows", r.ok and any("1 row(s)" in s for s in r.extra_lines))
    check("RM ANOVA runs Šídák comparisons", len(r.comparisons) == 3)
    r = se.run_column_stats(groups, "Friedman test")
    ref = stats.friedmanchisquare(*np.delete(Y, 3, axis=0).T)
    check("Friedman statistic matches SciPy", se.fmt(float(ref.statistic)) in r.omnibus)
    r = se.run_column_stats(groups[:2], "Friedman test")
    check("Friedman refuses two columns", not r.ok)


def _balanced(R=3, C=2, K=4):
    eff_r = np.array([0, 2, 3.0])[:R]
    eff_c = np.array([0, 1.5, 0.5])[:C]
    D = 10 + eff_r[:, None, None] + eff_c[None, :, None] + RNG.normal(0, 1, (R, C, K))
    D[1, 1] += 1.0  # interaction
    return D


def test_two_way_balanced():
    D = _balanced()
    R, C, K = D.shape
    res = anova.run_grouped(["R1", "R2", "R3"], ["A", "B"], D)
    grand = D.mean()
    cell = D.mean(axis=2)
    ra, cb = D.mean(axis=(1, 2)), D.mean(axis=(0, 2))
    ss_r = C * K * np.sum((ra - grand) ** 2)
    ss_c = R * K * np.sum((cb - grand) ** 2)
    ss_rc = K * np.sum((cell - ra[:, None] - cb[None, :] + grand) ** 2)
    sse = np.sum((D - cell[:, :, None]) ** 2)
    check("two-way row SS matches classic formula", close(row(res, "Row factor").ss, ss_r))
    check("two-way column SS matches classic formula", close(row(res, "Column factor").ss, ss_c))
    check("two-way interaction SS matches classic formula", close(row(res, "Interaction").ss, ss_rc))
    check("two-way residual SS matches classic formula", close(row(res, "Residual").ss, sse))


def _type3_cell_means(D):
    """Independent Type III check using the cell-means model and contrast matrices."""
    R, C, _ = D.shape
    mu = np.array([np.nanmean(D[r, c]) for r in range(R) for c in range(C)])
    n = np.array([np.sum(np.isfinite(D[r, c])) for r in range(R) for c in range(C)])
    V = np.diag(1.0 / n)
    cr = np.hstack([np.eye(R - 1), -np.ones((R - 1, 1))])
    cc = np.hstack([np.eye(C - 1), -np.ones((C - 1, 1))])
    hyps = {"Row factor": np.kron(cr, np.ones((1, C)) / C),
            "Column factor": np.kron(np.ones((1, R)) / R, cc),
            "Interaction": np.kron(cr, cc)}
    return {k: float((L @ mu) @ np.linalg.solve(L @ V @ L.T, L @ mu)) for k, L in hyps.items()}


def test_two_way_unbalanced():
    D = _balanced(R=3, C=3, K=5)
    D[0, 0, 3:] = np.nan
    D[2, 1, 4] = np.nan
    D[1, 2, 2:] = np.nan
    res = anova.run_grouped(["R1", "R2", "R3"], ["A", "B", "C"], D)
    ref = _type3_cell_means(D)
    for name, ss in ref.items():
        check(f"unbalanced Type III {name.lower()} SS matches cell-means method",
              close(row(res, name).ss, ss, 1e-8))
    check("unbalanced data are flagged", any("Type III" in n for n in res.notes))


def test_two_way_posthoc():
    D = _balanced()
    res = anova.run_grouped(["R1", "R2", "R3"], ["A", "B"], D,
                            comparisons="Compare columns within each row", correction="Šídák")
    mse = row(res, "Residual").ms
    dfe = row(res, "Residual").df
    c = res.comparisons[0]
    diff = D[0, 0].mean() - D[0, 1].mean()
    t = diff / math.sqrt(mse * 2 / D.shape[2])
    p_ref = anova.sidak(2 * stats.t.sf(abs(t), dfe), 3)
    check("two-way Šídák comparison uses pooled residual error", close(c.p, p_ref))
    check("two-way comparisons keep their row context", c.context == "R1" and c.cluster == 0)
    res = anova.run_grouped(["R1", "R2", "R3"], ["A", "B"], D,
                            comparisons="Compare rows within each column", correction="Tukey")
    check("Tukey comparisons of rows run", len(res.comparisons) == 6 and "Tukey" in res.posthoc)


def _mixed_data(C=3, R=4, K=5):
    subj = RNG.normal(0, 2, (1, C, K))
    time = np.linspace(0, 3, R)[:, None, None]
    group = np.array([0, 1, 2.5])[:C][None, :, None]
    return 10 + subj + time + group + 0.4 * time * group + RNG.normal(0, 1, (R, C, K))


def test_mixed_design():
    D = _mixed_data()
    R, C, K = D.shape
    res = anova.run_grouped([f"T{i}" for i in range(R)], ["A", "B", "C"], D,
                            design=anova.IN_SUBCOLUMN, gg=False)
    grand = D.mean()
    subj_means = D.mean(axis=0)          # C x K
    group_means = D.mean(axis=(0, 2))    # C
    time_means = D.mean(axis=(1, 2))     # R
    cell = D.mean(axis=2)                # R x C
    ss_between = R * K * np.sum((group_means - grand) ** 2)
    ss_subj = R * np.sum((subj_means - group_means[:, None]) ** 2)
    ss_time = C * K * np.sum((time_means - grand) ** 2)
    ss_int = K * np.sum((cell - grand) ** 2) - ss_between - ss_time
    ss_err = np.sum((D - grand) ** 2) - ss_between - ss_subj - ss_time - ss_int
    check("mixed design between-groups SS matches split-plot formula",
          close(row(res, "Column factor").ss, ss_between))
    check("mixed design subject SS matches split-plot formula", close(row(res, "Subject").ss, ss_subj))
    check("mixed design within-factor SS matches split-plot formula",
          close(row(res, "Row factor").ss, ss_time))
    check("mixed design interaction SS matches split-plot formula",
          close(row(res, "Interaction").ss, ss_int))
    check("mixed design residual SS matches split-plot formula", close(row(res, "Residual").ss, ss_err))
    f_between = (ss_between / (C - 1)) / (ss_subj / (C * K - C))
    check("between-groups F uses the subject error term", close(row(res, "Column factor").f, f_between))

    Dt = np.transpose(D, (1, 0, 2))
    res_t = anova.run_grouped(["A", "B", "C"], [f"T{i}" for i in range(R)], Dt,
                              design=anova.ACROSS_ROW, gg=False)
    check("matched-across-columns layout equals the transposed matched-across-rows result",
          close(row(res_t, "Interaction").f, row(res, "Interaction").f)
          and close(row(res_t, "Column factor").f, row(res, "Row factor").f))

    D2 = D.copy()
    D2[2, 1, 0] = np.nan
    res2 = anova.run_grouped([f"T{i}" for i in range(R)], ["A", "B", "C"], D2,
                             design=anova.IN_SUBCOLUMN,
                             comparisons="Compare columns within each row")
    check("incomplete subjects are excluded and reported",
          res2.ok and any("1 subject(s)" in n for n in res2.notes))
    check("between-group comparisons at each row run", len(res2.comparisons) == 3 * R)
    res3 = anova.run_grouped([f"T{i}" for i in range(R)], ["A", "B", "C"], D,
                             design=anova.IN_SUBCOLUMN,
                             comparisons="Compare rows within each column", correction="Tukey")
    sel = D[0, 0] - D[1, 0]
    t = sel.mean() / (sel.std(ddof=1) / math.sqrt(K))
    p_ref = anova.sidak(2 * stats.t.sf(abs(t), K - 1), len(res3.comparisons))
    check("within-subject comparisons are paired with Šídák adjustment",
          close(res3.comparisons[0].p, p_ref) and "Šídák" in res3.posthoc)
    check("Tukey request falls back to Šídák for paired comparisons, with a note",
          any("Šídák's correction was used" in n for n in res3.notes))


def test_guards():
    D = np.full((2, 2, 3), np.nan)
    D[0, 0] = [1, 2, 3]
    D[1, 1] = [2, 3, 4]
    D[0, 1] = [2, 2, 3]
    res = anova.run_grouped(["R1", "R2"], ["A", "B"], D)
    check("empty cell is refused with a clear message", not res.ok and "Empty" in res.message)
    res = anova.run_grouped(["R1"], ["A", "B"], np.ones((1, 2, 3)))
    check("single row is refused", not res.ok)


if __name__ == "__main__":
    test_sidak()
    test_rm_oneway()
    test_rm_column_interface()
    test_two_way_balanced()
    test_two_way_unbalanced()
    test_two_way_posthoc()
    test_mixed_design()
    test_guards()
    print("\nAll ANOVA checks passed.")
