"""Reusable workflows: saved methods, settings copied between tables, and empty-data copies."""

__author__ = "Daniel Shiwarski"

import json
import os


def method_settings(options_state):
    """Graph and analysis settings to reuse on other data (column choices are left out)."""
    return {k: v for k, v in options_state.items() if k != "_series"}


def empty_data(kind, data_state):
    """Same table layout (titles, data sets, replicates, row titles) with the values removed."""
    st = json.loads(json.dumps(data_state))
    if kind == "grouped":
        st["cells"] = [[row[0] if row else ""] for row in st.get("cells", []) if row and row[0]]
    else:
        st["cells"] = []
    st["excluded"] = []
    return st


def load_methods(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    methods = data.get("methods", {}) if isinstance(data, dict) else {}
    return {name: m for name, m in methods.items()
            if isinstance(m, dict) and m.get("kind") in ("column", "grouped", "xy", "xyz")}


def save_methods(path, methods):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"stelplot_methods": 1, "methods": methods}, fh, indent=1)
