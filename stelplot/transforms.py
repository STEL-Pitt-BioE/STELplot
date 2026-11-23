"""Data transformations. Each makes a new table and leaves the original untouched.

Works on the saved state of a table, so it needs no Qt and can be tested directly.
"""

__author__ = "Daniel Shiwarski"

import ast
import math

import numpy as np

CUSTOM_Y = "Custom: Y = expression"
CUSTOM_X = "Custom: X = expression"
FUNCTIONS = {
    "log10": np.log10, "log": np.log, "ln": np.log, "log2": np.log2, "exp": np.exp,
    "sqrt": np.sqrt, "abs": np.abs, "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan, "sinh": np.sinh, "cosh": np.cosh,
    "tanh": np.tanh, "floor": np.floor, "ceil": np.ceil, "round": np.round, "sign": np.sign,
    "logit": lambda p: np.log(p / (1 - p)),
}
CONSTANTS = {"pi": math.pi, "e": math.e}
_BINARY = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide,
           ast.Pow: np.power, ast.Mod: np.mod}
_UNARY = {ast.UAdd: np.positive, ast.USub: np.negative}
EXPRESSION_HELP = ("Use Y (and X in XY tables), an optional constant K, numbers, + - * / ^, and "
                   "functions: " + ", ".join(sorted(FUNCTIONS)) + ". Constants: pi, e. "
                   "Example: log10(Y) * 100, or (Y - K) / K.")


def parse_expression(text, names):
    """Check an expression and return its syntax tree. Only arithmetic, the names given,
    pi and e, and the functions in FUNCTIONS are allowed: nothing else can run."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Enter an expression, for example log10(Y) * 100.")
    if len(text) > 300:
        raise ValueError("The expression is too long (300 characters at most).")
    try:
        tree = ast.parse(text.replace("^", "**"), mode="eval")
    except SyntaxError:
        raise ValueError(f"'{text}' is not a valid expression. {EXPRESSION_HELP}") from None
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Load, ast.operator, ast.unaryop)):
            continue
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            continue
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            continue
        if isinstance(node, ast.Name):
            if node.id in names or node.id in CONSTANTS or node.id in FUNCTIONS:
                continue
            hint = " K needs a value in the K box." if node.id == "K" else ""
            raise ValueError(f"Unknown name '{node.id}'.{hint} {EXPRESSION_HELP}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in FUNCTIONS and len(node.args) == 1 and not node.keywords:
            continue
        raise ValueError(f"Only arithmetic and math functions are allowed. {EXPRESSION_HELP}")
    return tree.body


def evaluate(node, env):
    """Evaluate a checked expression on arrays."""
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return env[node.id] if node.id in env else CONSTANTS[node.id]
    if isinstance(node, ast.BinOp):
        return _BINARY[type(node.op)](evaluate(node.left, env), evaluate(node.right, env))
    if isinstance(node, ast.UnaryOp):
        return _UNARY[type(node.op)](evaluate(node.operand, env))
    if isinstance(node, ast.Call):
        return FUNCTIONS[node.func.id](evaluate(node.args[0], env))
    raise ValueError("Unsupported expression.")

Y_FUNCTIONS = {
    "Y = log10(Y)": (lambda y, k: np.log10(y), False),
    "Y = ln(Y)": (lambda y, k: np.log(y), False),
    "Y = 10^Y": (lambda y, k: np.power(10.0, y), False),
    "Y = e^Y": (lambda y, k: np.exp(y), False),
    "Y = sqrt(Y)": (lambda y, k: np.sqrt(y), False),
    "Y = Y squared": (lambda y, k: y ** 2, False),
    "Y = 1/Y": (lambda y, k: 1.0 / y, False),
    "Y = |Y|": (lambda y, k: np.abs(y), False),
    "Y = Y * K": (lambda y, k: y * k, True),
    "Y = Y + K": (lambda y, k: y + k, True),
    "Y = Y ^ K": (lambda y, k: np.power(y, k), True),
}
PER_SET = {
    "Normalize: 0% = smallest, 100% = largest in each data set": "normalize",
    "Percent of the first data set's mean": "percent_first",
    "Fraction of total (each data set)": "fraction",
}
X_FUNCTIONS = {
    "X = log10(X)": (lambda x, k: np.log10(x), False),
    "X = ln(X)": (lambda x, k: np.log(x), False),
    "X = X * K": (lambda x, k: x * k, True),
}
SHORT = {"Y = log10(Y)": "log10", "Y = ln(Y)": "ln", "Y = 10^Y": "10^Y", "Y = e^Y": "e^Y",
         "Y = sqrt(Y)": "sqrt", "Y = Y squared": "squared", "Y = 1/Y": "reciprocal",
         "Y = |Y|": "absolute", "Y = Y * K": "x K", "Y = Y + K": "+ K", "Y = Y ^ K": "^ K",
         "X = log10(X)": "log10 X", "X = ln(X)": "ln X", "X = X * K": "X x K"}


def available(kind):
    names = list(Y_FUNCTIONS) + list(PER_SET)
    if kind == "column":
        names = [n.replace("data set", "column") for n in names]
    names.append(CUSTOM_Y)
    if kind == "xy":
        names += list(X_FUNCTIONS) + [CUSTOM_X]
    return names


def is_custom(name):
    return name in (CUSTOM_Y, CUSTOM_X)


def needs_k(name):
    for table in (Y_FUNCTIONS, X_FUNCTIONS):
        if name in table:
            return table[name][1]
    return False


def short_name(name, expression=""):
    if is_custom(name):
        side = "Y" if name == CUSTOM_Y else "X"
        text = " ".join((expression or "").split())
        return f"{side} = {text[:40]}{'...' if len(text) > 40 else ''}"
    if name in SHORT:
        return SHORT[name]
    return {"normalize": "normalized", "percent_first": "% of first", "fraction": "fraction of total"}[
        PER_SET[name.replace("column", "data set")]]


def _parse(text):
    t = (text or "").strip()
    if not t:
        return math.nan
    try:
        return float(t)
    except ValueError:
        return math.nan


def _fmt(v):
    return "" if not math.isfinite(v) else format(v, ".6g")


def transform_state(kind, state, name, k=None, expression=None):
    """Return (new_state, number of values that could not be transformed)."""
    cells = [list(r) for r in state.get("cells", [])]
    excluded = {tuple(rc) for rc in state.get("excluded", [])}
    if not cells:
        return dict(state), 0
    width = max(len(r) for r in cells)
    cells = [r + [""] * (width - len(r)) for r in cells]
    n_rows = len(cells)
    first_data = 0 if kind == "column" else 1
    if kind == "column":
        sets = [[c] for c in range(width)]
    else:
        reps = int(state.get("reps", 1))
        n_sets = len(state.get("series_names", [])) or max(0, (width - 1) // max(reps, 1))
        sets = [[1 + j * reps + r for r in range(reps)] for j in range(n_sets)]
        sets = [[c for c in s if c < width] for s in sets]
    values = np.array([[_parse(v) for v in row] for row in cells], dtype=float)
    out = values.copy()
    if needs_k(name) and (k is None or not math.isfinite(k)):
        raise ValueError("Enter a value for K.")
    if is_custom(name):
        names = {"Y"} if name == CUSTOM_Y else {"X"}
        if kind == "xy":
            names.add("X")
        if k is not None and math.isfinite(k):
            names.add("K")
        tree = parse_expression(expression, names)
    key = name.replace("column", "data set")
    with np.errstate(all="ignore"):
        if is_custom(name):
            env = {"K": np.float64(k)} if (k is not None and math.isfinite(k)) else {}
            if kind == "xy":
                env["X"] = values[:, 0]
            cols = [0] if name == CUSTOM_X else list(range(first_data, width))
            for c in cols:
                if name == CUSTOM_Y:
                    env["Y"] = values[:, c]
                result = np.asarray(evaluate(tree, env), dtype=float)
                out[:, c] = np.broadcast_to(result, values[:, c].shape)
        elif name in Y_FUNCTIONS or name in X_FUNCTIONS:
            func = (Y_FUNCTIONS.get(name) or X_FUNCTIONS[name])[0]
            cols = [0] if name in X_FUNCTIONS else list(range(first_data, width))
            for c in cols:
                out[:, c] = func(values[:, c], k)
        elif key in PER_SET:
            mode = PER_SET[key]
            usable = lambda s: np.array([values[r, c] for c in s for r in range(n_rows)
                                         if (r, c) not in excluded and math.isfinite(values[r, c])])
            ref = None
            if mode == "percent_first" and sets:
                first = usable(sets[0])
                ref = float(first.mean()) if first.size else math.nan
            for s in sets:
                v = usable(s)
                for c in s:
                    if mode == "normalize":
                        lo, hi = (float(v.min()), float(v.max())) if v.size else (math.nan, math.nan)
                        out[:, c] = (values[:, c] - lo) / (hi - lo) * 100 if hi > lo else math.nan
                    elif mode == "percent_first":
                        out[:, c] = values[:, c] / ref * 100 if ref else math.nan
                    else:
                        total = float(v.sum()) if v.size else math.nan
                        out[:, c] = values[:, c] / total if total else math.nan
        else:
            raise ValueError(f"Unknown transform: {name}")
    invalid = 0
    changed_cols = [0] if (name in X_FUNCTIONS or name == CUSTOM_X) else list(range(first_data, width))
    for r in range(n_rows):
        for c in changed_cols:
            if math.isfinite(values[r, c]):
                if not math.isfinite(out[r, c]):
                    invalid += 1
                cells[r][c] = _fmt(out[r, c])
    new = dict(state)
    new["cells"] = cells
    new["excluded"] = [list(rc) for rc in sorted(excluded)
                       if rc[0] < n_rows and rc[1] < width and cells[rc[0]][rc[1]]]
    return new, invalid
