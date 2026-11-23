"""Outlier identification: ROUT and Grubbs' test, one column at a time.

ROUT follows Motulsky HJ, Brown RE. Detecting outliers when fitting data with nonlinear
regression - a new method based on robust nonlinear regression and the false discovery rate.
BMC Bioinformatics 2006;7:123. doi:10.1186/1471-2105-7-123. PMID 16526949. Here the model is
the column mean (K = 1 parameter):
  1. Robust fit minimizing sum(ln(1 + (residual / RSDR)^2)), the Lorentzian merit function,
     with RSDR recomputed every iteration (the adaptive method).
  2. RSDR = P68 * N / (N - K), where P68 is the 68.27th percentile of |residuals|.
  3. Rank |residuals| from smallest (1) to largest (N); for i = int(0.7 N) .. N compare the
     two-tailed P of t = |residual_i| / RSDR (df N - K) with Q (N - (i - 1)) / N. The first
     point with P below its threshold, and every point further out, are outliers.

Grubbs' test follows Grubbs FE. Procedures for detecting outlying observations in samples.
Technometrics 1969;11(1):1-21. doi:10.1080/00401706.1969.10490657. Two-sided: G is the
largest |value - mean| / SD; it is an outlier when G exceeds the critical value for alpha.
Iterative Grubbs repeats the test after removing each outlier (masking can hide outliers).

Both assume the values, apart from outliers, come from a Gaussian distribution. For log-normal
data (common for sizes, areas, and concentrations) test on the log scale.
"""

__author__ = "Daniel Shiwarski"

import math
from dataclasses import dataclass, field

import numpy as np
from scipy import stats

ROUT = "ROUT"
GRUBBS = "Grubbs (most extreme value)"
ITERATIVE_GRUBBS = "Iterative Grubbs"
METHODS = [ROUT, GRUBBS, ITERATIVE_GRUBBS]
DEFAULT_THRESHOLD = {ROUT: 1.0, GRUBBS: 5.0, ITERATIVE_GRUBBS: 5.0}   # Q or alpha, in percent
THRESHOLD_NAME = {ROUT: "Q", GRUBBS: "alpha", ITERATIVE_GRUBBS: "alpha"}


@dataclass
class OutlierResult:
    method: str
    threshold: float            # Q or alpha as a fraction
    log_scale: bool
    n_tested: int = 0
    outliers: list = field(default_factory=list)   # positions in the original values
    details: list = field(default_factory=list)    # (position, value, statistic, P) per outlier
    skipped: int = 0            # values at or below zero, not tested on the log scale
    message: str = ""

    def describe(self):
        name = THRESHOLD_NAME[self.method]
        scale = ", log scale" if self.log_scale else ""
        return f"{self.method} ({name} = {format(round(self.threshold * 100, 6), 'g')}%{scale})"


def p68(abs_residuals):
    """68.27th percentile of |residuals|, interpolating between the values that bracket it."""
    return float(np.percentile(abs_residuals, 68.27))


def rsdr(residuals, k=1):
    n = len(residuals)
    return p68(np.abs(residuals)) * n / (n - k) if n > k else math.nan


def _merit(r, scale):
    return float(np.sum(np.log1p((r / scale) ** 2)))


def robust_mean(y, max_iter=500):
    """Location that minimizes the Lorentzian merit function, adaptively (Motulsky & Brown).

    Starts from the least-squares mean. Each step is the Gauss-Newton step for the merit
    function (weights 1 / (1 + RR^2)); after each step the previous merit is recomputed with
    the new RSDR so the two can be compared, and the step is halved if it made things worse.
    """
    y = np.asarray(y, float)
    mu = float(np.mean(y))
    for _ in range(max_iter):
        scale = rsdr(y - mu)
        if not (scale > 0):
            return mu
        w = 1.0 / (1.0 + ((y - mu) / scale) ** 2)
        step = float(np.sum(w * (y - mu)) / np.sum(w))
        new = mu + step
        new_scale = rsdr(y - new)
        if not (new_scale > 0):
            return new
        while _merit(y - new, new_scale) > _merit(y - mu, new_scale) and abs(step) > 1e-15:
            step /= 2.0
            new = mu + step
            new_scale = rsdr(y - new)
            if not (new_scale > 0):
                return new
        if abs(new - mu) <= 1e-12 * max(1.0, abs(mu), scale):
            return new
        mu = new
    return mu


def rout(y, q=0.01, k=1):
    """Positions of outliers in y (finite values), with (position, t, P) for each."""
    y = np.asarray(y, float)
    n = y.size
    if n - k < 1:
        return [], []
    mu = robust_mean(y)
    resid = y - mu
    scale = rsdr(resid, k)
    if not (scale > 0):
        return [], []
    order = np.argsort(np.abs(resid), kind="stable")   # rank 1 = closest, rank N = furthest
    for i in range(max(1, int(0.70 * n)), n + 1):
        pos = order[i - 1]
        alpha_i = q * (n - (i - 1)) / n
        t = abs(resid[pos]) / scale
        p = float(2 * stats.t.sf(t, n - k))
        if p < alpha_i:
            out = [int(order[j - 1]) for j in range(i, n + 1)]
            det = [(int(order[j - 1]), abs(resid[order[j - 1]]) / scale,
                    float(2 * stats.t.sf(abs(resid[order[j - 1]]) / scale, n - k))) for j in range(i, n + 1)]
            return out, det
    return [], []


def grubbs_critical(n, alpha=0.05):
    """Two-sided Grubbs critical value of G for n values."""
    t = stats.t.isf(alpha / (2 * n), n - 2)
    return (n - 1) / math.sqrt(n) * math.sqrt(t * t / (n - 2 + t * t))


def grubbs_p(g, n):
    """Approximate two-sided P value for G (as GraphPad computes it): N times the two-tailed P
    of the equivalent t, capped at 1."""
    denom = (n - 1) ** 2 - n * g * g
    if denom <= 0:
        return 0.0
    t = math.sqrt(n * (n - 2) * g * g / denom)
    return min(1.0, n * 2 * float(stats.t.sf(t, n - 2)))


def grubbs(y, alpha=0.05, iterative=False):
    """Positions of outliers in y, with (position, G, P) for each."""
    y = np.asarray(y, float)
    keep = list(range(y.size))
    out, det = [], []
    while len(keep) >= 3:
        v = y[keep]
        sd = float(np.std(v, ddof=1))
        if not (sd > 0):
            break
        dev = np.abs(v - v.mean())
        j = int(np.argmax(dev))
        g = float(dev[j] / sd)
        if g <= grubbs_critical(len(keep), alpha):
            break
        pos = keep.pop(j)
        out.append(pos)
        det.append((pos, g, grubbs_p(g, len(v))))
        if not iterative:
            break
    return out, det


def identify(values, method=ROUT, threshold_pct=None, log_scale=False):
    """Test one column. values may contain NaN (blank or excluded cells are skipped)."""
    pct = DEFAULT_THRESHOLD[method] if threshold_pct is None else float(threshold_pct)
    res = OutlierResult(method=method, threshold=pct / 100.0, log_scale=bool(log_scale))
    v = np.asarray(values, float)
    idx = np.flatnonzero(np.isfinite(v))
    data = v[idx]
    if log_scale:
        pos = data > 0
        res.skipped = int(np.sum(~pos))
        idx, data = idx[pos], np.log10(data[pos])
    res.n_tested = int(data.size)
    if method == ROUT:
        if data.size < 3:
            res.message = "ROUT needs at least 3 values."
            return res
        found, det = rout(data, res.threshold)
    else:
        if data.size < 3:
            res.message = "Grubbs' test needs at least 3 values."
            return res
        found, det = grubbs(data, res.threshold, iterative=(method == ITERATIVE_GRUBBS))
    res.outliers = sorted(int(idx[p]) for p in found)
    res.details = sorted((int(idx[p]), float(v[idx[p]]), float(s), float(pv)) for p, s, pv in det)
    return res


def methods_sentence(record):
    """Sentence for the Methods text from a saved outlier record (see the main window)."""
    if not record or not record.get("excluded"):
        return ""
    ref = ("Motulsky and Brown, BMC Bioinformatics 2006" if record["method"] == ROUT
           else "Grubbs, Technometrics 1969")
    name = THRESHOLD_NAME[record["method"]]
    scale = " on log-transformed values" if record.get("log") else ""
    return (f"Outliers were identified in each group with the {record['method']} method "
            f"({name} = {format(round(record['threshold'] * 100, 6), 'g')}%{scale}; {ref}), and "
            f"{record['excluded']} value(s) were excluded from the analysis.")
