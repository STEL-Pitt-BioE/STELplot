"""Read data tables from Prism .pzfx files (Prism's XML project format).

Only the data tables are read. Prism stores graph formatting and analysis
settings in a compressed proprietary block, which is not decoded here.
Values that Prism marks as excluded come in marked as excluded, so they are also left
out of STELplot's analyses.
"""

__author__ = "Daniel Shiwarski"

import math
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

KIND_BY_TYPE = {"OneWay": "column", "TwoWay": "grouped", "XY": "xy"}
KIND_LABEL = {"column": "Column data", "grouped": "Grouped data", "xy": "XY data"}


def _text(elem):
    return "".join(elem.itertext()).strip() if elem is not None else ""


def _values(subcolumn):
    """Return (values, excluded {row: value}). Blank, text, and excluded cells are NaN in
    `values`, ready for analysis; excluded numbers are kept separately so they can be shown."""
    out, excluded = [], {}
    for row, d in enumerate(subcolumn.findall("d")):
        raw = (d.text or "").strip()
        try:
            value = float(raw)
        except ValueError:
            value = math.nan
        if d.get("Excluded") == "1":
            if raw:
                excluded[row] = value
            out.append(math.nan)
        else:
            out.append(value)
    return out, excluded


@dataclass
class PrismTable:
    title: str
    table_type: str
    kind: str
    replicates: int = 1
    message: str = ""
    row_titles: list = field(default_factory=list)
    x_title: str = "X"
    x_values: list = field(default_factory=list)
    columns: list = field(default_factory=list)   # (title, [subcolumn values])
    excluded: int = 0
    excluded_values: dict = field(default_factory=dict)   # (data set, subcolumn) -> {row: value}

    def describe(self):
        if self.kind == "unsupported":
            return f"{self.table_type} table, not supported"
        reps = f", {self.replicates} replicates" if self.replicates > 1 else ""
        return f"{KIND_LABEL[self.kind]}, {len(self.columns)} data sets{reps}"

    def n_rows(self):
        lengths = [len(v) for _, subs in self.columns for v in subs]
        lengths += [len(self.row_titles), len(self.x_values)]
        return max(lengths) if lengths else 0

    def to_state(self):
        """State dictionary for the matching STELplot data panel."""
        fmt = lambda v: "" if (v is None or not math.isfinite(v)) else format(v, ".10g")
        n = self.n_rows()

        def cell(values, r):
            return fmt(values[r]) if r < len(values) else ""

        def ycell(j, k, values, r):
            ex = self.excluded_values.get((j, k), {})
            return fmt(ex[r]) if r in ex else cell(values, r)

        excluded = []
        if self.kind == "column":
            cells = [[ycell(j, 0, subs[0] if subs else [], r) for j, (_, subs) in enumerate(self.columns)]
                     for r in range(n)]
            for (j, k), rows in self.excluded_values.items():
                excluded += [[r, j] for r in rows if k == 0]
            return {"headers": [t or f"Group {i + 1}" for i, (t, _) in enumerate(self.columns)],
                    "cells": cells, "excluded": sorted(excluded)}
        reps = self.replicates
        cells = []
        for r in range(n):
            if self.kind == "grouped":
                first = self.row_titles[r] if r < len(self.row_titles) else ""
            else:
                first = cell(self.x_values, r)
            row = [first]
            for j, (_, subs) in enumerate(self.columns):
                for k in range(reps):
                    row.append(ycell(j, k, subs[k], r) if k < len(subs) else "")
            cells.append(row)
        for (j, k), rows in self.excluded_values.items():
            excluded += [[r, 1 + j * reps + k] for r in rows if k < reps]
        names = [t or f"Data set {i + 1}" for i, (t, _) in enumerate(self.columns)]
        first_name = "Row" if self.kind == "grouped" else (self.x_title or "X")
        return {"x_name": first_name, "series_names": names, "reps": reps, "cells": cells,
                "excluded": sorted(excluded)}


def read_pzfx(path):
    """Return a list of PrismTable objects in the order Prism lists them."""
    root = ET.parse(path).getroot()
    tables = []
    for elem in list(root.iter("Table")) + list(root.iter("HugeTable")):
        ttype = elem.get("TableType", "")
        kind = KIND_BY_TYPE.get(ttype, "unsupported")
        t = PrismTable(title=_text(elem.find("Title")) or "Untitled", table_type=ttype, kind=kind)
        y_format = elem.get("YFormat", "replicates")
        if kind != "unsupported" and y_format != "replicates":
            t.kind = "unsupported"
            t.message = ("This table holds summary values (for example mean, SD, and N) rather "
                         "than individual replicates. STELplot needs the raw values.")
        elif kind == "unsupported":
            t.message = f"{ttype or 'This'} tables are not supported yet."
        try:
            t.replicates = max(1, int(elem.get("Replicates", "1")))
        except ValueError:
            t.replicates = 1
        rt = elem.find("RowTitlesColumn")
        if rt is not None and rt.find("Subcolumn") is not None:
            t.row_titles = [(d.text or "").strip() for d in rt.find("Subcolumn").findall("d")]
        xc = elem.find("XColumn")
        if xc is not None:
            t.x_title = _text(xc.find("Title")) or "X"
            sub = xc.find("Subcolumn")
            if sub is not None:
                t.x_values, ex = _values(sub)
                t.excluded += len(ex)
        for yc in elem.findall("YColumn"):
            subs = []
            for sub in yc.findall("Subcolumn"):
                vals, ex = _values(sub)
                if ex:
                    t.excluded_values[(len(t.columns), len(subs))] = ex
                subs.append(vals)
                t.excluded += len(ex)
            t.columns.append((_text(yc.find("Title")), subs))
        if t.kind == "column":
            t.replicates = 1
        tables.append(t)
    return tables


# ---------------------------------------------------------------------------
# Prism 10/11 .prism bundles
# ---------------------------------------------------------------------------
# Layout verified on a Prism 11.1 file (format 1-6-1):
#   document.json                     sheets.data lists the user's data tables
#   data/sheets/<sheet>/sheet.json    title; table.format, table.dataFormat, table.dataSets,
#                                     table.rowTitlesDataSet, table.replicatesCount
#   data/sets/<set>.json              data set title and its list of replicate subcolumns
#   data/tables/<table uid>/data.csv  values: row titles first (if present), then each data
#                                     set's subcolumns in order; blank cells are empty
# Not yet verified on a real file: XY tables and how excluded values are marked.

PRISM_KIND = {"column": "column", "grouped": "grouped"}
RAW_FORMATS = {"y_single", "y_replicates"}


def _float(v):
    v = (v or "").strip()
    try:
        return float(v)
    except ValueError:
        return math.nan


def read_prism(path):
    """Return PrismTable objects for the data tables in a Prism 10/11 .prism file."""
    import csv
    import io
    import json
    import zipfile

    tables = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())

        def load(name):
            return json.loads(z.read(name).decode("utf-8"))

        doc = load("document.json")
        for sheet_uid in doc.get("sheets", {}).get("data", []):
            sheet_path = f"data/sheets/{sheet_uid}/sheet.json"
            if sheet_path not in names:
                continue
            sheet = load(sheet_path)
            table = sheet.get("table", {})
            fmt, data_fmt = table.get("format", ""), table.get("dataFormat", "")
            title = sheet.get("title") or "Untitled"
            kind = PRISM_KIND.get(fmt, "unsupported")
            t = PrismTable(title=title, table_type=f"{fmt} ({data_fmt})", kind=kind)
            if fmt == "xy":
                t.kind = "unsupported"
                t.message = ("XY tables in .prism files are not supported yet. In Prism, save a "
                             "copy as .pzfx and import that.")
                tables.append(t)
                continue
            if kind == "unsupported":
                t.message = f"{fmt or 'This'} tables are not supported yet."
                tables.append(t)
                continue
            if data_fmt not in RAW_FORMATS:
                t.kind = "unsupported"
                t.message = ("This table holds summary values (for example mean, SD, and N) rather "
                             "than individual replicates. STELplot needs the raw values.")
                tables.append(t)
                continue
            sets = []
            for set_uid in table.get("dataSets", []):
                name = f"data/sets/{set_uid}.json"
                info = load(name) if name in names else {}
                sets.append((info.get("title", ""), max(1, len(info.get("replicates", [])) or 1)))
            csv_name = f"data/tables/{table.get('uid')}/data.csv"
            rows = []
            if csv_name in names:
                rows = list(csv.reader(io.StringIO(z.read(csv_name).decode("utf-8"))))
            col = 0
            if table.get("rowTitlesDataSet"):
                t.row_titles = [(r[0].strip() if r else "") for r in rows]
                col = 1
            reps = max([n for _, n in sets] + [int(table.get("replicatesCount", 1) or 1)])
            t.replicates = reps if kind == "grouped" else 1
            for set_title, n_sub in sets:
                subs = []
                for k in range(n_sub):
                    subs.append([_float(r[col + k]) if col + k < len(r) else math.nan for r in rows])
                col += n_sub
                t.columns.append((set_title, subs))
            tables.append(t)
    return tables


def read_any(path):
    """Read data tables from a .pzfx or .prism file, chosen by file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".prism":
        return read_prism(path)
    return read_pzfx(path)
