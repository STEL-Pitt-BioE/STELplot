"""Clipboard text parsing for the data grids (no Qt needed, so it can be tested)."""

__author__ = "Daniel Shiwarski"

import csv
import io

_QUOTE_PAIRS = {'"': '"', "\u201c": "\u201d", "'": "'"}


def _unquote(cell):
    cell = cell.strip()
    if len(cell) >= 2 and _QUOTE_PAIRS.get(cell[0]) == cell[-1]:
        cell = cell[1:-1].strip()
    return cell


def parse_clipboard(text):
    """Split tab-separated clipboard text into rows of cells.

    Excel and Prism wrap text containing spaces, tabs, or line breaks in quotes when
    copying; those quotes are removed so pasted titles read Casted ctrl, not "Casted ctrl".
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    if not text:
        return []
    rows = csv.reader(io.StringIO(text), delimiter="\t", quotechar='"')
    return [[_unquote(c) for c in row] for row in rows]
