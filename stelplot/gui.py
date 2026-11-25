"""STELplot desktop interface (PyQt5)."""

__author__ = "Daniel Shiwarski"

import json
import math
import os
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from matplotlib.figure import Figure
try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
except ImportError:  # older matplotlib
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from . import APP_NAME, ORG_NAME, __version__
from . import anova
from . import plotting as pl
from . import prism_import
from .clipboard import parse_clipboard
from . import stats_engine as se
from . import branding, help_docs, interpret, layout, outliers, transforms, workflow
from . import plot3d as p3
from . import volcano
from . import lab_style as ls
from .color_check import worst_pair
from .lab_style import PALETTES, STAR_LEGEND, format_p

NAVY = "#1F3864"
NAVY_HOVER = "#2E4A7D"
INVALID_CELL = QtGui.QColor("#F8D7DA")
PROJECT_EXT = ".stelplot"
DEFAULT_AUTHOR = "Daniel Shiwarski"
ZOOMS = {f"{z}%": z for z in (50, 75, 100, 125, 150, 200, 250, 300, 400, 500)}   # preview dots per inch
PANELS = {"tables": ("tables", "Ctrl+1"), "results": ("results", "Ctrl+2"),
          "settings": ("graph settings", "Ctrl+3")}
DEFAULT_ROWS = 1000          # rows available in every data table
DEFAULT_GROUPS = 10          # columns shown in a Column table
MAX_UNDO = 100               # undo steps kept per session
UNDO_SETTLE_MS = 350         # changes this close together become one undo step

EXCLUDED_ROLE = Qt.UserRole + 1
FLAG_ROLE = Qt.UserRole + 3
FLAG_BRUSH = QtGui.QBrush(QtGui.QColor(255, 170, 0, 110))   # possible outlier, either theme
EXCLUDED_COLOR = QtGui.QColor("#1f5cb8")   # set for the current theme by apply_theme

from .theme import DARK, EXCLUDED, LIGHT, QSS  # noqa: E402




def _theme_assets(name, theme):
    """Draw the check mark and arrow images the stylesheet uses; return their paths."""
    folder = os.path.join(tempfile.gettempdir(), "stelplot_theme")
    os.makedirs(folder, exist_ok=True)

    def save(fname, draw):
        path = os.path.join(folder, f"{name}_{fname}.png")
        img = QtGui.QImage(32, 32, QtGui.QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        painter = QtGui.QPainter(img)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        draw(painter)
        painter.end()
        img.save(path, "PNG")
        return path.replace("\\", "/")

    def check(p):
        p.setPen(QtGui.QPen(QtGui.QColor(theme["accent_text"]), 4.2, Qt.SolidLine, Qt.RoundCap,
                            Qt.RoundJoin))
        path = QtGui.QPainterPath()
        path.moveTo(7.5, 16.5)
        path.lineTo(13.5, 22.5)
        path.lineTo(24.5, 9.5)
        p.drawPath(path)

    def arrow(up):
        def draw(p):
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(theme["subtext"]))
            pts = ([(7, 21), (25, 21), (16, 10)] if up else [(7, 11), (25, 11), (16, 22)])
            p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in pts]))
        return draw

    return {"check": save("check", check), "arrow_up": save("up", arrow(True)),
            "arrow_down": save("down", arrow(False))}


def apply_theme(app, dark=False):
    EXCLUDED_COLOR.setNamedColor(EXCLUDED["dark" if dark else "light"])
    theme = DARK if dark else LIGHT
    assets = _theme_assets("dark" if dark else "light", theme)
    app.setStyleSheet(QSS.format(**theme, **assets))
    return assets


KIND_BADGES = {"column": ("C", "#1f6feb"), "grouped": ("G", "#13ADA6"), "xy": ("XY", "#AE9122"),
               "xyz": ("3D", "#773E55")}
_BADGE_CACHE = {}


def kind_icon(kind):
    """Small rounded badge marking a table's type in the tables list."""
    if kind not in _BADGE_CACHE:
        text, color = KIND_BADGES[kind]
        size = 44
        pix = QtGui.QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(color))
        p.drawRoundedRect(QtCore.QRectF(2, 2, size - 4, size - 4), 10, 10)
        font = QtGui.QFont()
        font.setBold(True)
        font.setPixelSize(19 if len(text) == 1 else 16)
        p.setFont(font)
        p.setPen(QtGui.QColor("#ffffff"))
        p.drawText(QtCore.QRectF(0, 0, size, size), Qt.AlignCenter, text)
        p.end()
        _BADGE_CACHE[kind] = QtGui.QIcon(pix)
    return _BADGE_CACHE[kind]


def parse_number(text):
    """Return (value, is_valid). Blank cells are valid and become NaN."""
    t = text.strip()
    if not t:
        return math.nan, True
    try:
        return float(t), True
    except ValueError:
        return math.nan, False


# ---------------------------------------------------------------------------
# Data grid
# ---------------------------------------------------------------------------

class DataGrid(QtWidgets.QTableWidget):
    """Spreadsheet-style grid with Excel copy and paste."""

    dataEdited = QtCore.pyqtSignal()
    message = QtCore.pyqtSignal(str)

    def __init__(self, rows, headers, grow_columns=True, header_paste=True, text_columns=(),
                 excludable_from=0, parent=None):
        super().__init__(rows, len(headers), parent)
        self._suspend = False
        self.grow_columns = grow_columns
        self.header_paste = header_paste
        self.text_columns = set(text_columns)
        self.excludable_from = excludable_from
        self.locked = False
        self._edit_triggers = self.editTriggers()
        self.setAccessibleName("Data table")
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.setHorizontalHeaderLabels(headers)
        hh = self.horizontalHeader()
        hh.setDefaultSectionSize(92)
        hh.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        hh.setHighlightSections(False)
        self.verticalHeader().setDefaultSectionSize(22)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.itemChanged.connect(self._on_item_changed)

    # ----- cell helpers
    def _on_item_changed(self, item):
        if self._suspend:
            return
        if self.is_flagged(item):   # a new value is no longer the one that was flagged
            self.set_flagged(item, False)
        self._validate(item)
        self.dataEdited.emit()

    def _validate(self, item):
        _, ok = parse_number(item.text())
        if item.column() in self.text_columns:
            ok = True
        was = self._suspend
        self._suspend = True
        if self.is_flagged(item):
            item.setBackground(FLAG_BRUSH)
        else:
            item.setBackground(QtGui.QBrush() if ok else QtGui.QBrush(INVALID_CELL))
        if self.is_excluded(item):
            item.setToolTip("Excluded: kept in the table but left out of graphs and statistics. "
                            "Right-click to include it again.")
        else:
            item.setToolTip(item.data(FLAG_ROLE) if self.is_flagged(item)
                            else ("" if ok else "Not a number. This cell is ignored."))
        self._suspend = was

    # ----- possible outliers (amber), from Analysis > Identify outliers
    @staticmethod
    def is_flagged(item):
        return item is not None and bool(item.data(FLAG_ROLE))

    def set_flagged(self, item, flag, tip=""):
        was = self._suspend
        self._suspend = True
        item.setData(FLAG_ROLE, (tip or "Possible outlier") if flag else None)
        self._suspend = was
        self._validate(item)

    def flagged_cells(self):
        return [[r, c] for r in range(self.rowCount()) for c in range(self.columnCount())
                if self.is_flagged(self.item(r, c))]

    def clear_flags(self):
        for r, c in self.flagged_cells():
            self.set_flagged(self.item(r, c), False)

    # ----- excluded values (shown blue italic, as in Prism)
    @staticmethod
    def is_excluded(item):
        return item is not None and bool(item.data(EXCLUDED_ROLE))

    def _set_excluded(self, item, flag):
        was = self._suspend
        self._suspend = True
        item.setData(EXCLUDED_ROLE, bool(flag))
        font = item.font()
        font.setItalic(bool(flag))
        item.setFont(font)
        if flag:
            item.setForeground(QtGui.QBrush(EXCLUDED_COLOR))
        else:
            item.setData(Qt.ForegroundRole, None)   # back to the theme's text color
        self._suspend = was
        self._validate(item)

    def set_locked(self, flag):
        """Freeze the table: values can be read and copied but not changed."""
        self.locked = bool(flag)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers if flag else self._edit_triggers)

    def _refuse_if_locked(self):
        if self.locked:
            self.message.emit("This table is frozen. Unfreeze it (Analysis menu or Cmd+L) to edit.")
        return self.locked

    def recolor_excluded(self):
        for r, c in self.excluded_cells():
            self.item(r, c).setForeground(QtGui.QBrush(EXCLUDED_COLOR))

    def excluded_cells(self):
        out = []
        for r in range(self.rowCount()):
            for c in range(self.columnCount()):
                if self.is_excluded(self.item(r, c)):
                    out.append([r, c])
        return out

    def set_selection_excluded(self, flag):
        """Exclude or include the selected values. Returns how many cells changed."""
        if self._refuse_if_locked():
            return 0
        changed = 0
        self._suspend = True
        try:
            for item in self.selectedItems():
                if (item.column() >= self.excludable_from and item.text().strip()
                        and self.is_excluded(item) != bool(flag)):
                    self._set_excluded(item, flag)
                    changed += 1
        finally:
            self._suspend = False
        if changed:
            verb = "Excluded" if flag else "Included"
            self.message.emit(f"{verb} {changed} value(s). Excluded values stay in the table but are "
                              "left out of graphs and statistics.")
            self.dataEdited.emit()
        return changed

    def _context_menu(self, pos):
        index = self.indexAt(pos)
        if index.isValid() and not self.selectionModel().isSelected(index):
            self.setCurrentCell(index.row(), index.column())
        items = [i for i in self.selectedItems()
                 if i.column() >= self.excludable_from and i.text().strip()]
        menu = QtWidgets.QMenu(self)
        exclude = menu.addAction("Exclude")
        include = menu.addAction("Include")
        exclude.setEnabled(not self.locked and any(not self.is_excluded(i) for i in items))
        include.setEnabled(not self.locked and any(self.is_excluded(i) for i in items))
        menu.addSeparator()
        clear_flags = None
        if self.flagged_cells():
            clear_flags = menu.addAction("Clear outlier flags")
        menu.addSeparator()
        copy = menu.addAction("Copy")
        paste = menu.addAction("Paste")
        clear = menu.addAction("Clear")
        paste.setEnabled(not self.locked)
        clear.setEnabled(not self.locked)
        chosen = menu.exec_(self.viewport().mapToGlobal(pos))
        if chosen is not None and chosen is clear_flags:
            self.clear_flags()
            self.message.emit("Outlier flags cleared. The values are unchanged.")
            self.dataEdited.emit()
        elif chosen is exclude:
            self.set_selection_excluded(True)
        elif chosen is include:
            self.set_selection_excluded(False)
        elif chosen is copy:
            self.copy_selection()
        elif chosen is paste:
            self.paste_clipboard()
        elif chosen is clear:
            self.clear_selected()

    def header_text(self, c):
        item = self.horizontalHeaderItem(c)
        return item.text() if item is not None else str(c + 1)

    def set_header_text(self, c, text):
        item = self.horizontalHeaderItem(c)
        if item is None:
            self.setHorizontalHeaderItem(c, QtWidgets.QTableWidgetItem(text))
        else:
            item.setText(text)

    def cell_text(self, r, c):
        item = self.item(r, c)
        return item.text() if item is not None else ""

    def set_cell_text(self, r, c, text):
        """Set a cell's text; new values (pasted or loaded) start out included."""
        item = self.item(r, c)
        if item is None:
            item = QtWidgets.QTableWidgetItem(text)
            self.setItem(r, c, item)
        else:
            item.setText(text)
        if self.is_excluded(item):
            self._set_excluded(item, False)
        if self.is_flagged(item):
            item.setData(FLAG_ROLE, None)
        self._validate(item)

    def column_values(self, c):
        out = np.full(self.rowCount(), np.nan)
        for r in range(self.rowCount()):
            item = self.item(r, c)
            if item is not None and not self.is_excluded(item):
                out[r] = parse_number(item.text())[0]
        return out

    def column_has_text(self, c):
        return any(self.cell_text(r, c).strip() for r in range(self.rowCount()))

    def to_matrix(self):
        rows = [[self.cell_text(r, c) for c in range(self.columnCount())]
                for r in range(self.rowCount())]
        while rows and not any(t.strip() for t in rows[-1]):
            rows.pop()
        return rows

    def load_matrix(self, matrix, min_rows=DEFAULT_ROWS, excluded=None, flagged=None):
        self._suspend = True
        try:
            self.clearContents()
            self.setRowCount(max(min_rows, len(matrix) + 5))
            for r, row in enumerate(matrix):
                for c, text in enumerate(row):
                    if c < self.columnCount() and text:
                        self.set_cell_text(r, c, text)
            for r, c in excluded or []:
                item = self.item(r, c)
                if item is not None and item.text().strip():
                    self._set_excluded(item, True)
            for entry in flagged or []:
                r, c = entry[0], entry[1]
                tip = entry[2] if len(entry) > 2 else ""
                item = self.item(r, c)
                if item is not None and item.text().strip():
                    self.set_flagged(item, True, tip)
        finally:
            self._suspend = False

    # ----- keyboard: copy, paste, delete
    def _step_row(self, step):
        row = self.currentRow() + step
        col = max(self.currentColumn(), 0)
        if row >= self.rowCount():
            self.setRowCount(self.rowCount() + 100)
        if row >= 0:
            self.setCurrentCell(row, col)

    def closeEditor(self, editor, hint):
        """After Enter commits an edit, move down like Excel (Shift+Enter moves up)."""
        super().closeEditor(editor, hint)
        if hint == QtWidgets.QAbstractItemDelegate.SubmitModelCache:
            shift = QtWidgets.QApplication.keyboardModifiers() & Qt.ShiftModifier
            self._step_row(-1 if shift else 1)

    def keyPressEvent(self, event):
        if self.locked and (event.matches(QtGui.QKeySequence.Paste)
                            or event.key() in (Qt.Key_Delete, Qt.Key_Backspace)):
            self._refuse_if_locked()
            return
        if (event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and self.state() != QtWidgets.QAbstractItemView.EditingState):
            self._step_row(-1 if event.modifiers() & Qt.ShiftModifier else 1)
            return
        if event.matches(QtGui.QKeySequence.Copy):
            self.copy_selection()
            return
        if event.matches(QtGui.QKeySequence.Paste):
            self.paste_clipboard()
            return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.clear_selected()
            return
        super().keyPressEvent(event)

    def copy_selection(self):
        ranges = self.selectedRanges()
        if not ranges:
            return
        r = ranges[0]
        lines = []
        for row in range(r.topRow(), r.bottomRow() + 1):
            cells = [self.cell_text(row, col) for col in range(r.leftColumn(), r.rightColumn() + 1)]
            lines.append("\t".join(cells))
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))

    def paste_clipboard(self):
        text = QtWidgets.QApplication.clipboard().text()
        if not text.strip():
            return
        if self._refuse_if_locked():
            return
        rows = parse_clipboard(text)
        if not rows:
            return
        r0, c0 = max(self.currentRow(), 0), max(self.currentColumn(), 0)
        headers = None
        if (self.header_paste and r0 == 0 and rows
                and any(t.strip() and not parse_number(t)[1] for t in rows[0])):
            headers = rows.pop(0)
        width = max([len(r) for r in rows] + [len(headers) if headers else 0])
        clipped = 0
        self._suspend = True
        try:
            if r0 + len(rows) > self.rowCount():
                self.setRowCount(r0 + len(rows) + 5)
            if c0 + width > self.columnCount():
                if self.grow_columns:
                    for c in range(self.columnCount(), c0 + width):
                        self.insertColumn(c)
                        self.set_header_text(c, f"Group {c + 1}")
                else:
                    clipped = c0 + width - self.columnCount()
            if headers:
                for k, h in enumerate(headers):
                    c = c0 + k
                    if c < self.columnCount() and h.strip():
                        self.set_header_text(c, h.strip())
            for dr, cells in enumerate(rows):
                for dc, t in enumerate(cells):
                    c = c0 + dc
                    if c < self.columnCount():
                        self.set_cell_text(r0 + dr, c, t.strip())
        finally:
            self._suspend = False
        if clipped:
            self.message.emit(f"{clipped} pasted column(s) did not fit. "
                              "Add series or replicates, then paste again.")
        self.dataEdited.emit()

    def clear_selected(self):
        if self._refuse_if_locked():
            return
        self._suspend = True
        try:
            for item in self.selectedItems():
                item.setText("")
                if self.is_excluded(item):
                    self._set_excluded(item, False)
                if self.is_flagged(item):
                    item.setData(FLAG_ROLE, None)
                self._validate(item)
        finally:
            self._suspend = False
        self.dataEdited.emit()


class FlowLayout(QtWidgets.QLayout):
    """Lays widgets out left to right and wraps onto new lines when the panel is narrow."""

    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self._gap = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QtCore.QSize(m.left() + m.right(), m.top() + m.bottom())

    def _arrange(self, rect, measure_only):
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line = area.x(), area.y(), 0
        for item in self._items:
            if item.widget() is not None and item.widget().isHidden():
                continue
            hint = item.sizeHint()
            if x > area.x() and x + hint.width() > area.right() + 1:
                x, y, line = area.x(), y + line + self._gap, 0
            if not measure_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))
            x += hint.width() + self._gap
            line = max(line, hint.height())
        return y + line - rect.y() + m.bottom()


class Section(QtWidgets.QFrame):
    """A settings group that folds open and closed when its title is clicked."""
    toggled = QtCore.pyqtSignal(str, bool)

    def __init__(self, title, form=True, parent=None):
        super().__init__(parent)
        self.setObjectName("section")
        self.title = title
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(3, 2, 3, 3)
        lay.setSpacing(0)
        self.header = QtWidgets.QPushButton()
        self.header.setObjectName("section_header")
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setAccessibleName(f"{title} settings")
        self.header.clicked.connect(lambda _checked=False: self.set_expanded(not self.expanded))
        self.body = QtWidgets.QWidget()
        self.body.setObjectName("section_body")
        if form:
            self.form = QtWidgets.QFormLayout(self.body)
            self.body_layout = self.form
        else:
            self.form = None
            self.body_layout = QtWidgets.QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(8, 2, 8, 8)
        lay.addWidget(self.header)
        lay.addWidget(self.body)
        self.expanded = True
        saved = QtCore.QSettings(ORG_NAME, APP_NAME).value(f"sections/{title}", True, type=bool)
        self.set_expanded(saved, emit=False, save=False)

    def setting_count(self):
        return self.form.rowCount() if self.form is not None else 0

    def update_header(self):
        n = self.setting_count()
        arrow = "\u25be" if self.expanded else "\u25b8"
        self.header.setText(f"{arrow}   {self.title}" + (f"   ({n})" if n else ""))
        self.header.setToolTip(f"{'Collapse' if self.expanded else 'Expand'} {self.title}")

    def set_expanded(self, on, emit=True, save=True):
        self.expanded = bool(on)
        self.body.setVisible(self.expanded)
        self.update_header()
        if save:
            QtCore.QSettings(ORG_NAME, APP_NAME).setValue(f"sections/{self.title}", self.expanded)
        if emit:
            self.toggled.emit(self.title, self.expanded)


class PageStack(QtWidgets.QWidget):
    """Shows one page at a time and takes the height of that page only.

    Qt's QStackedWidget sizes itself to its tallest page, so collapsing settings sections
    on the page shown did not shorten the panel; this keeps the panel as short as the page.
    """
    currentChanged = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages, self._current = [], -1
        self._lay = QtWidgets.QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

    def addWidget(self, w):
        self._pages.append(w)
        self._lay.addWidget(w)
        w.setVisible(False)
        if self._current < 0:
            self.setCurrentIndex(0)
        return len(self._pages) - 1

    def removeWidget(self, w):
        if w not in self._pages:
            return
        i = self._pages.index(w)
        self._pages.pop(i)
        self._lay.removeWidget(w)
        w.setVisible(False)
        if i == self._current:
            self._current = -1
            if self._pages:
                self.setCurrentIndex(min(i, len(self._pages) - 1))
        elif i < self._current:
            self._current -= 1

    def count(self):
        return len(self._pages)

    def widget(self, i):
        return self._pages[i] if 0 <= i < len(self._pages) else None

    def indexOf(self, w):
        return self._pages.index(w) if w in self._pages else -1

    def currentIndex(self):
        return self._current

    def currentWidget(self):
        return self.widget(self._current)

    def setCurrentIndex(self, i):
        if not 0 <= i < len(self._pages) or i == self._current:
            return
        if 0 <= self._current < len(self._pages):
            self._pages[self._current].setVisible(False)
        self._current = i
        self._pages[i].setVisible(True)
        self.currentChanged.emit(i)

    def setCurrentWidget(self, w):
        self.setCurrentIndex(self.indexOf(w))


_ICON_CACHE = {}


def toolbar_icon(name, color="#ffffff"):
    """Simple line icons for the toolbar, drawn at twice the size for sharp Retina display."""
    key = (name, color)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    P, R = QtCore.QPointF, QtCore.QRectF
    pix = QtGui.QPixmap(48, 48)
    pix.fill(Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.scale(2, 2)
    p.setPen(QtGui.QPen(QtGui.QColor(color), 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)

    def path(points, close=False):
        pp = QtGui.QPainterPath()
        pp.moveTo(*points[0])
        for pt in points[1:]:
            pp.lineTo(*pt)
        if close:
            pp.closeSubpath()
        p.drawPath(pp)

    def undo_arrow():
        path([(9, 13), (4, 8.5), (9, 4)])
        pp = QtGui.QPainterPath()
        pp.moveTo(4, 8.5)
        pp.lineTo(14.5, 8.5)
        pp.cubicTo(18.5, 8.5, 20.5, 11, 20.5, 14)
        pp.cubicTo(20.5, 17, 18.5, 19.5, 14.5, 19.5)
        pp.lineTo(10, 19.5)
        p.drawPath(pp)

    if name == "new_table":
        p.drawRoundedRect(R(3, 4, 14, 14), 2, 2)
        p.drawLine(P(3, 9), P(17, 9))
        p.drawLine(P(8.5, 4), P(8.5, 18))
        p.drawLine(P(19.5, 14), P(19.5, 22))
        p.drawLine(P(15.5, 18), P(23.5, 18))
    elif name == "open":
        path([(3, 7), (3, 19), (21, 19), (21, 9.5), (11.5, 9.5), (9.5, 7), (3, 7)])
    elif name == "save":
        path([(4, 4), (16, 4), (20, 8), (20, 20), (4, 20)], close=True)
        p.drawRect(R(8, 4, 7, 4.5))
        p.drawRect(R(7, 13, 10, 7))
    elif name == "import":
        p.drawLine(P(12, 3), P(12, 14))
        path([(8, 10), (12, 14), (16, 10)])
        path([(4, 14), (4, 20), (20, 20), (20, 14)])
    elif name == "undo":
        undo_arrow()
    elif name == "redo":
        p.translate(24, 0)
        p.scale(-1, 1)
        undo_arrow()
    elif name == "figure":
        p.drawRoundedRect(R(3, 5, 18, 14), 2, 2)
        p.drawEllipse(P(8.5, 10), 1.6, 1.6)
        p.drawPolyline(QtGui.QPolygonF([P(3.5, 17.5), P(9, 12.5), P(13, 16), P(16, 13), P(20.5, 17)]))
    elif name == "results":
        path([(6, 3), (14, 3), (19, 8), (19, 21), (6, 21)], close=True)
        path([(14, 3), (14, 8), (19, 8)])
        for y, x2 in ((12, 16), (15, 16), (18, 13)):
            p.drawLine(P(9, y), P(x2, y))
    elif name == "layout":
        for x, y in ((3.5, 3.5), (13, 3.5), (3.5, 13), (13, 13)):
            p.drawRoundedRect(R(x, y, 7.5, 7.5), 1.5, 1.5)
    elif name == "transform":
        path([(4, 3), (4, 20), (21, 20)])
        pp = QtGui.QPainterPath()
        pp.moveTo(5.5, 17.5)
        pp.cubicTo(10.5, 17.5, 11, 6, 20, 5)
        p.drawPath(pp)
    elif name == "dark":
        moon = QtGui.QPainterPath()
        moon.addEllipse(P(11.5, 12.5), 8, 8)
        cut = QtGui.QPainterPath()
        cut.addEllipse(P(16, 8), 6.5, 6.5)
        p.drawPath(moon.subtracted(cut))
    elif name == "readme":
        for side in (1, -1):
            pp = QtGui.QPainterPath()
            pp.moveTo(12, 7)
            pp.cubicTo(12 - side * 2.5, 5, 12 - side * 6, 5, 12 - side * 9, 6)
            pp.lineTo(12 - side * 9, 19)
            pp.cubicTo(12 - side * 6, 18, 12 - side * 2.5, 18, 12, 20)
            p.drawPath(pp)
        p.drawLine(P(12, 7), P(12, 20))
    elif name == "guide":
        p.drawEllipse(P(12, 12), 9, 9)
        pp = QtGui.QPainterPath()
        pp.moveTo(9.3, 9.6)
        pp.cubicTo(9.3, 7.6, 10.7, 6.6, 12.2, 6.6)
        pp.cubicTo(14, 6.6, 15.2, 7.8, 15.2, 9.3)
        pp.cubicTo(15.2, 11.6, 12.2, 11.8, 12.2, 14)
        p.drawPath(pp)
        p.setBrush(QtGui.QColor(color))
        p.drawEllipse(P(12.2, 17.3), 0.7, 0.7)
    p.end()
    pix.setDevicePixelRatio(2)
    _ICON_CACHE[key] = QtGui.QIcon(pix)
    return _ICON_CACHE[key]


def brand_pixmap():
    """STELplot logo for the toolbar: a small rounded tile with a bar-and-points chart."""
    pix = QtGui.QPixmap(56, 56)
    pix.fill(Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QtGui.QColor("#3d8bff"))
    p.drawRoundedRect(QtCore.QRectF(2, 2, 52, 52), 12, 12)
    p.setBrush(QtGui.QColor("#ffffff"))
    for x, h in ((13, 16), (24, 28), (35, 22)):
        p.drawRoundedRect(QtCore.QRectF(x, 44 - h, 8, h), 2, 2)
    p.setBrush(QtGui.QColor("#ffd479"))
    for x, y in ((17, 22), (28, 10), (39, 16)):
        p.drawEllipse(QtCore.QPointF(x, y), 3, 3)
    p.end()
    pix.setDevicePixelRatio(2)
    return pix


class HelpWindow(QtWidgets.QDialog):
    """README or user guide: a searchable list of topics beside the text."""

    def __init__(self, parent, title, doc_name, dark=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)
        self.sections = help_docs.load_sections(doc_name)
        lay = QtWidgets.QHBoxLayout(self)
        side = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        logo = QtWidgets.QLabel()
        logo.setAccessibleName("STEL Plot logo")
        pix = branding.lockup_pixmap(190, dark=dark) or branding.tile_pixmap(36)
        if pix is not None:
            logo.setPixmap(pix)
        sl.addWidget(logo)
        name = QtWidgets.QLabel(title)
        name.setProperty("role", "heading")
        name.setWordWrap(True)
        sl.addWidget(name)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search")
        self.search.setAccessibleName("Search help")
        self.search.textChanged.connect(self._filter)
        self.toc = QtWidgets.QListWidget()
        self.toc.setObjectName("tables")
        self.toc.setAccessibleName("Help topics")
        for i, (heading, _text) in enumerate(self.sections):
            item = QtWidgets.QListWidgetItem(heading)
            item.setData(Qt.UserRole, i)
            self.toc.addItem(item)
        self.toc.currentItemChanged.connect(self._show)
        sl.addWidget(self.search)
        sl.addWidget(self.toc, 1)
        side.setFixedWidth(250)
        self.view = QtWidgets.QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.view.setAccessibleName("Help text")
        lay.addWidget(side)
        lay.addWidget(self.view, 1)
        self.toc.setCurrentRow(0)
        self.resize(940, 680)

    def _show(self, item, _previous=None):
        if item is None:
            return
        heading, text = self.sections[item.data(Qt.UserRole)]
        doc = f"## {heading}\n\n{text}"
        if hasattr(self.view, "setMarkdown"):
            self.view.setMarkdown(doc)
        else:
            self.view.setPlainText(doc)
        if self.search.text().strip():
            self.view.find(self.search.text().strip())

    def _filter(self, text):
        needle = text.strip().lower()
        first = None
        for i in range(self.toc.count()):
            item = self.toc.item(i)
            heading, body = self.sections[item.data(Qt.UserRole)]
            hit = not needle or needle in heading.lower() or needle in body.lower()
            item.setHidden(not hit)
            if hit and first is None:
                first = item
        if first is not None and (self.toc.currentItem() is None or self.toc.currentItem().isHidden()):
            self.toc.setCurrentItem(first)
        elif self.toc.currentItem() is not None:
            self._show(self.toc.currentItem())


def stats_shapiro_p(values):
    from scipy import stats
    try:
        return float(stats.shapiro(values).pvalue)
    except ValueError:
        return 1.0


def lock_panel(panel, flag):
    """Freeze or unfreeze a data panel: the grid and its editing buttons."""
    panel.grid.set_locked(flag)
    for kind in (QtWidgets.QPushButton, QtWidgets.QAbstractSpinBox):
        for w in panel.findChildren(kind):
            w.setEnabled(not flag)


def _button(text, slot, tooltip=""):
    b = QtWidgets.QPushButton(text)
    b.clicked.connect(slot)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def _hint(text):
    label = QtWidgets.QLabel(text)
    label.setProperty("role", "hint")
    label.setWordWrap(True)
    return label


# ---------------------------------------------------------------------------
# Column data tab
# ---------------------------------------------------------------------------

class ColumnPanel(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid = DataGrid(DEFAULT_ROWS, [f"Group {c + 1}" for c in range(DEFAULT_GROUPS)],
                             grow_columns=True, header_paste=True)
        self.grid.dataEdited.connect(self.changed)
        self.grid.horizontalHeader().sectionDoubleClicked.connect(self.rename)

        bar = FlowLayout()
        bar.addWidget(_button("Add group", self.add_group))
        bar.addWidget(_button("Remove group", self.remove_group,
                              "Removes the selected column, or the last one"))
        bar.addWidget(_button("Add 100 rows", self.add_rows))
        bar.addWidget(_button("Example data", self.load_example))
        bar.addWidget(_button("Clear", self.clear))

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(bar)
        lay.addWidget(self.grid, 1)
        lay.addWidget(_hint("Each column is one group. Enter moves down, Tab moves right. "
                            "Double-click a column title to rename it. Paste from Excel with Ctrl+V "
                            "(Cmd+V on Mac); a header row pasted into the first row becomes the "
                            "column titles."))

    def rename(self, c):
        if self.grid.locked:
            return
        text, ok = QtWidgets.QInputDialog.getText(self, "Rename column", "Column name:",
                                                  QtWidgets.QLineEdit.Normal,
                                                  self.grid.header_text(c))
        if ok and text.strip():
            self.grid.set_header_text(c, text.strip())
            self.changed.emit()

    def add_group(self):
        c = self.grid.columnCount()
        self.grid.insertColumn(c)
        self.grid.set_header_text(c, f"Group {c + 1}")
        self.changed.emit()

    def remove_group(self):
        if self.grid.columnCount() <= 1:
            return
        c = self.grid.currentColumn()
        if c < 0:
            c = self.grid.columnCount() - 1
        if self.grid.column_has_text(c):
            answer = QtWidgets.QMessageBox.question(
                self, "Remove group", f"Remove \"{self.grid.header_text(c)}\" and its data?")
            if answer != QtWidgets.QMessageBox.Yes:
                return
        self.grid.removeColumn(c)
        self.changed.emit()

    def add_rows(self):
        self.grid.setRowCount(self.grid.rowCount() + 100)

    def clear(self):
        answer = QtWidgets.QMessageBox.question(self, "Clear data", "Clear all values in this table?")
        if answer == QtWidgets.QMessageBox.Yes:
            self.grid.load_matrix([])
            self.changed.emit()

    def load_example(self):
        headers = ["Control", "Drug A", "Drug B"] + [f"Group {c}" for c in range(4, DEFAULT_GROUPS + 1)]
        values = [[9.8, 12.1, 15.2], [10.6, 13.4, 14.1], [8.9, 11.8, 16.3], [11.2, 12.9, 15.8],
                  [9.5, 14.0, 14.9], [10.1, 12.6, 17.0]]
        self.grid.setColumnCount(len(headers))
        self.grid.setHorizontalHeaderLabels(headers)
        self.grid.load_matrix([[str(v) for v in row] for row in values])
        self.changed.emit()

    def series_keys(self):
        """[(column index, title)] for columns that contain data."""
        return [(c, self.grid.header_text(c)) for c in range(self.grid.columnCount())
                if np.isfinite(self.grid.column_values(c)).any()]

    def get_groups(self, keys=None):
        """(title, values) for each column with data; `keys` picks columns and their order."""
        cols = range(self.grid.columnCount()) if keys is None else keys
        groups = []
        for c in cols:
            if 0 <= c < self.grid.columnCount():
                vals = self.grid.column_values(c)
                if np.isfinite(vals).any():
                    groups.append((self.grid.header_text(c), vals))
        return groups

    def state(self):
        flagged = [[r, c, self.grid.item(r, c).data(FLAG_ROLE)] for r, c in self.grid.flagged_cells()]
        return {"headers": [self.grid.header_text(c) for c in range(self.grid.columnCount())],
                "cells": self.grid.to_matrix(), "excluded": self.grid.excluded_cells(),
                "flagged": flagged}

    def load_state(self, st):
        headers = list(st.get("headers") or [])
        headers += [f"Group {c + 1}" for c in range(len(headers), DEFAULT_GROUPS)]
        self.grid.setColumnCount(len(headers))
        self.grid.setHorizontalHeaderLabels(headers)
        self.grid.load_matrix(st.get("cells", []), excluded=st.get("excluded"), flagged=st.get("flagged"))


# ---------------------------------------------------------------------------
# Replicate tables: XY data and grouped data share one layout
# ---------------------------------------------------------------------------

class SeriesPanel(QtWidgets.QWidget):
    """First column plus data sets, each with one column per replicate."""

    changed = QtCore.pyqtSignal()
    first_default = "X"
    series_word = "Series"
    first_is_text = False
    hint_text = ""
    allow_titles = False    # XY tables can add a Row title column at the right

    def __init__(self, parent=None):
        super().__init__(parent)
        self.x_name = self.first_default
        self.series_names = [f"{self.series_word} A", f"{self.series_word} B"]
        self.reps = 3
        self.row_titles = False
        self.grid = DataGrid(DEFAULT_ROWS, self._headers(), grow_columns=False, header_paste=False,
                             text_columns={0} if self.first_is_text else (), excludable_from=1)
        self.grid.dataEdited.connect(self.changed)
        self.grid.horizontalHeader().sectionDoubleClicked.connect(self.rename)

        self.reps_spin = QtWidgets.QSpinBox()
        self.reps_spin.setRange(1, 24)
        self.reps_spin.setValue(self.reps)
        self.reps_spin.valueChanged.connect(self._reps_changed)

        word = self.series_word.lower()
        bar = FlowLayout()
        bar.addWidget(_button(f"Add {word}", self.add_series))
        bar.addWidget(_button(f"Remove {word}", self.remove_series,
                              f"Removes the {word} of the selected column, or the last one"))
        reps_box = QtWidgets.QWidget()
        rb = QtWidgets.QHBoxLayout(reps_box)
        rb.setContentsMargins(0, 0, 0, 0)
        rb.addWidget(QtWidgets.QLabel("Replicates"))
        rb.addWidget(self.reps_spin)
        bar.addWidget(reps_box)
        if self.allow_titles:
            self.titles_check = QtWidgets.QCheckBox("Row titles")
            self.titles_check.setToolTip("Adds a text column at the right that names each row, for "
                                         "example the protein or gene on a volcano plot.")
            self.titles_check.toggled.connect(self._titles_toggled)
            bar.addWidget(self.titles_check)
        bar.addWidget(_button("Add 100 rows", self.add_rows))
        bar.addWidget(_button("Example data", self.load_example))
        if hasattr(self, "load_volcano_example"):
            bar.addWidget(_button("Volcano example", self.load_volcano_example,
                                  "Simulated proteomics data for a volcano plot"))
        bar.addWidget(_button("Clear", self.clear))

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(bar)
        lay.addWidget(self.grid, 1)
        lay.addWidget(_hint(self.hint_text))

    def _headers(self, names=None, reps=None):
        names = self.series_names if names is None else names
        reps = self.reps if reps is None else reps
        headers = [self.x_name]
        for name in names:
            headers += [name] if reps == 1 else [f"{name} ({k + 1})" for k in range(reps)]
        if self.row_titles:
            headers.append("Row title")
        return headers

    def title_column(self):
        """Grid column of the row titles, or None."""
        return 1 + len(self.series_names) * self.reps if self.row_titles else None

    def _sync_text_columns(self):
        cols = {0} if self.first_is_text else set()
        if self.row_titles:
            cols.add(self.title_column())
        self.grid.text_columns = cols

    def _titles_toggled(self, on):
        if on == self.row_titles:
            return
        if not on and any(t.strip() for t in self.row_title_list()):
            answer = QtWidgets.QMessageBox.question(self, "Remove row titles",
                                                    "Remove the row titles column and its text?")
            if answer != QtWidgets.QMessageBox.Yes:
                self.titles_check.blockSignals(True)
                self.titles_check.setChecked(True)
                self.titles_check.blockSignals(False)
                return
        old_titles = self.row_title_list()
        self.row_titles = on
        self._rebuild(self.series_names, self.reps, list(range(len(self.series_names))),
                      titles=old_titles if on else None)

    def row_title_list(self):
        c = self.title_column()
        if c is None:
            return []
        return [self.grid.cell_text(r, c).strip() for r in range(self.grid.rowCount())]

    def _rebuild(self, new_names, new_reps, source_index, titles=None):
        """Rebuild columns. source_index[s] is the old series index for new series s, or None."""
        old = self.grid.to_matrix()
        old_excluded = {tuple(rc) for rc in self.grid.excluded_cells()}
        old_reps = self.reps
        old_title_col = (1 + len(self.series_names) * old_reps) if self.row_titles else None
        if titles is None and old_title_col is not None:
            titles = [row[old_title_col] if old_title_col < len(row) else "" for row in old]
        self.series_names, self.reps = list(new_names), new_reps
        headers = self._headers()
        new_matrix, new_excluded = [], []
        for r_i, row in enumerate(old):
            new_row = [""] * len(headers)
            new_row[0] = row[0] if row else ""
            if self.row_titles and titles and r_i < len(titles):
                new_row[-1] = titles[r_i]
            for s_new, src in enumerate(source_index):
                if src is None:
                    continue
                for k in range(min(old_reps, new_reps)):
                    old_c = 1 + src * old_reps + k
                    if old_c < len(row):
                        new_row[1 + s_new * new_reps + k] = row[old_c]
                        if (len(new_matrix), old_c) in old_excluded:
                            new_excluded.append([len(new_matrix), 1 + s_new * new_reps + k])
            new_matrix.append(new_row)
        self.grid.setColumnCount(len(headers))
        self.grid.setHorizontalHeaderLabels(headers)
        self._sync_text_columns()
        self.grid.load_matrix(new_matrix, excluded=new_excluded)
        self.changed.emit()

    def _set_reps_quietly(self, value):
        self.reps_spin.blockSignals(True)
        self.reps_spin.setValue(value)
        self.reps_spin.blockSignals(False)

    def _reps_changed(self, value):
        lost = value < self.reps and any(
            self.grid.column_has_text(1 + s_i * self.reps + k)
            for s_i in range(len(self.series_names)) for k in range(value, self.reps))
        if lost:
            answer = QtWidgets.QMessageBox.question(
                self, "Fewer replicates",
                "Some replicate columns have data that will be removed. Continue?")
            if answer != QtWidgets.QMessageBox.Yes:
                self._set_reps_quietly(self.reps)
                return
        self._rebuild(self.series_names, value, list(range(len(self.series_names))))

    def add_series(self):
        letter = chr(ord("A") + len(self.series_names) % 26)
        names = self.series_names + [f"{self.series_word} {letter}"]
        self._rebuild(names, self.reps, list(range(len(self.series_names))) + [None])

    def remove_series(self):
        if len(self.series_names) <= 1:
            return
        c = self.grid.currentColumn()
        s_i = (c - 1) // self.reps if c >= 1 else len(self.series_names) - 1
        s_i = min(s_i, len(self.series_names) - 1)   # the row titles column picks the last one
        answer = QtWidgets.QMessageBox.question(
            self, f"Remove {self.series_word.lower()}",
            f"Remove \"{self.series_names[s_i]}\" and its data?")
        if answer != QtWidgets.QMessageBox.Yes:
            return
        keep = [i for i in range(len(self.series_names)) if i != s_i]
        self._rebuild([self.series_names[i] for i in keep], self.reps, keep)

    def rename(self, c):
        if self.grid.locked:
            return
        if c == self.title_column():
            return
        if c == 0:
            current, title = self.x_name, "Rename first column"
        else:
            current, title = self.series_names[(c - 1) // self.reps], f"Rename {self.series_word.lower()}"
        text, ok = QtWidgets.QInputDialog.getText(self, title, "Name:",
                                                  QtWidgets.QLineEdit.Normal, current)
        if not (ok and text.strip()):
            return
        if c == 0:
            self.x_name = text.strip()
        else:
            self.series_names[(c - 1) // self.reps] = text.strip()
        self.grid.setHorizontalHeaderLabels(self._headers())
        self.changed.emit()

    def add_rows(self):
        self.grid.setRowCount(self.grid.rowCount() + 100)

    def clear(self):
        answer = QtWidgets.QMessageBox.question(self, "Clear data", "Clear all values in this table?")
        if answer == QtWidgets.QMessageBox.Yes:
            self.grid.load_matrix([])
            self.changed.emit()

    def _load(self, first_name, names, reps, rows, titles=False):
        self.x_name, self.series_names, self.reps = first_name, list(names), reps
        self._set_reps_quietly(reps)
        if self.allow_titles:
            self.row_titles = titles
            self.titles_check.blockSignals(True)
            self.titles_check.setChecked(titles)
            self.titles_check.blockSignals(False)
        self._sync_text_columns()
        self.grid.setColumnCount(len(self._headers()))
        self.grid.setHorizontalHeaderLabels(self._headers())
        self.grid.load_matrix([[str(v) for v in row] for row in rows])
        self.changed.emit()

    def series_keys(self):
        """[(data set index, name)] for data sets that contain values."""
        block = self.replicate_block()
        return [(j, name) for j, name in enumerate(self.series_names)
                if np.isfinite(block[:, j, :]).any()]

    def replicate_block(self):
        """Values as rows x series x replicates."""
        n_rows = self.grid.rowCount()
        block = np.full((n_rows, len(self.series_names), self.reps), np.nan)
        for s_i in range(len(self.series_names)):
            for k in range(self.reps):
                block[:, s_i, k] = self.grid.column_values(1 + s_i * self.reps + k)
        return block

    def state(self):
        st = {"x_name": self.x_name, "series_names": self.series_names,
              "reps": self.reps, "cells": self.grid.to_matrix(),
              "excluded": self.grid.excluded_cells()}
        if self.row_titles:
            st["row_titles"] = True
        return st

    def load_state(self, st):
        self.x_name = st.get("x_name", self.first_default)
        self.series_names = list(st.get("series_names") or [f"{self.series_word} A"])
        self.reps = int(st.get("reps", 1))
        self._set_reps_quietly(self.reps)
        if self.allow_titles:
            self.row_titles = bool(st.get("row_titles", False))
            self.titles_check.blockSignals(True)
            self.titles_check.setChecked(self.row_titles)
            self.titles_check.blockSignals(False)
        self._sync_text_columns()
        self.grid.setColumnCount(len(self._headers()))
        self.grid.setHorizontalHeaderLabels(self._headers())
        self.grid.load_matrix(st.get("cells", []), excluded=st.get("excluded"))


class XYPanel(SeriesPanel):
    first_default = "X"
    series_word = "Series"
    allow_titles = True
    hint_text = ("The first column is X. Each series has one column per replicate. "
                 "Double-click a column title to rename its series. Leave cells blank "
                 "for missing replicates. Row titles (optional) name the points on a volcano plot.")

    def load_volcano_example(self):
        """Simulated proteomics results: log2 fold change, P value, and protein names."""
        rng = np.random.default_rng(7)
        n = 600
        fc = rng.normal(0, 0.8, n)
        fc[:40] += rng.choice([-2.2, 2.2], 40)
        p = np.clip(10 ** -(np.abs(fc) * rng.uniform(0.6, 2.4, n)), 1e-12, 1)
        rows = [[f"{fc[i]:.4f}", f"{p[i]:.4g}", f"PROT{i + 1}"] for i in range(n)]
        self._load("log2 fold change", ["P value"], 1, rows, titles=True)

    def load_example(self):
        rows = [[0.01, 2, 4, 1, 1, 0, 2], [0.1, 9, 12, 8, 3, 2, 4], [1, 48, 52, 45, 9, 12, 8],
                [10, 88, 91, 86, 41, 38, 45], [100, 99, 97, 101, 72, 75, 70]]
        self._load("Concentration", ["Vehicle", "Drug"], 3, rows)

    def get_xy(self, keys=None):
        x = self.grid.column_values(0)
        block = self.replicate_block()
        idx = range(len(self.series_names)) if keys is None else [k for k in keys
                                                                    if k < len(self.series_names)]
        series = [(self.series_names[s_i], block[:, s_i, :]) for s_i in idx
                  if np.isfinite(block[:, s_i, :]).any()]
        return x, series


class GroupedPanel(SeriesPanel):
    first_default = "Row"
    series_word = "Data set"
    first_is_text = True
    hint_text = ("Each row is one level of the row factor (for example, a time point); type its "
                 "name in the first column. Each data set has one column per replicate. For "
                 "repeated measures, keep each subject in the same replicate column.")

    def load_example(self):
        rows = [["Day 1", 9.6, 10.4, 8.9, 9.8, 9.9, 10.8, 8.7, 9.5],
                ["Day 7", 10.2, 11.5, 9.4, 10.6, 12.1, 13.2, 10.9, 12.0],
                ["Day 14", 11.4, 12.6, 10.8, 11.9, 13.9, 15.1, 12.6, 13.8],
                ["Day 21", 12.3, 13.4, 11.6, 12.7, 15.8, 17.0, 14.6, 16.1]]
        self._load("Time point", ["Control", "Treated"], 4, rows)

    def load_volcano_example(self):
        """Simulated proteomics intensities: 500 proteins, wild type and knockout, 4 replicates."""
        rng = np.random.default_rng(11)
        n, reps = 500, 4
        base = rng.normal(22, 2, (n, 1))
        wt = base + rng.normal(0, 0.45, (n, reps))
        shift = np.zeros((n, 1))
        shift[:25], shift[25:50] = 1.8, -1.6
        ko = base + shift + rng.normal(0, 0.45, (n, reps))
        rows = [[f"PROT{i + 1}"] + [f"{2 ** v:.5g}" for v in wt[i]] + [f"{2 ** v:.5g}" for v in ko[i]]
                for i in range(n)]
        self._load("Protein", ["WT", "KO"], reps, rows)

    def get_grouped(self, keys=None):
        labels = []
        for r in range(self.grid.rowCount()):
            text = self.grid.cell_text(r, 0).strip()
            labels.append(text or f"Row {r + 1}")
        block = self.replicate_block()
        if keys is None:
            return labels, list(self.series_names), block
        keys = [k for k in keys if k < len(self.series_names)]
        return labels, [self.series_names[k] for k in keys], block[:, keys, :]


class XYZPanel(QtWidgets.QWidget):
    """3D table: one row per point, with X, Y, Z, and an optional color value."""

    changed = QtCore.pyqtSignal()
    HEADERS = ["X", "Y", "Z", "Color (optional)"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid = DataGrid(DEFAULT_ROWS, self.HEADERS, grow_columns=False, header_paste=True)
        self.grid.dataEdited.connect(self.changed)
        self.grid.horizontalHeader().sectionDoubleClicked.connect(self.rename)
        bar = FlowLayout()
        bar.addWidget(_button("Add 100 rows", self.add_rows))
        bar.addWidget(_button("Example surface", self.load_example,
                              "A grid of X and Y values with a smooth Z, colored by a 4th value"))
        bar.addWidget(_button("Example scatter", self.load_scatter_example))
        bar.addWidget(_button("Clear", self.clear))
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(bar)
        lay.addWidget(self.grid, 1)
        lay.addWidget(_hint("Each row is one point: X, Y, and Z, plus an optional fourth value that "
                            "sets its color. For a smooth surface or wireframe, give Z for every "
                            "combination of X and Y. Double-click a column title to rename it."))

    def rename(self, c):
        if self.grid.locked:
            return
        text, ok = QtWidgets.QInputDialog.getText(self, "Rename column", "Column name:",
                                                  QtWidgets.QLineEdit.Normal, self.grid.header_text(c))
        if ok and text.strip():
            self.grid.set_header_text(c, text.strip())
            self.changed.emit()

    def add_rows(self):
        self.grid.setRowCount(self.grid.rowCount() + 100)

    def clear(self):
        answer = QtWidgets.QMessageBox.question(self, "Clear data", "Clear all values in this table?")
        if answer == QtWidgets.QMessageBox.Yes:
            self.grid.load_matrix([])
            self.changed.emit()

    def _load(self, rows, headers):
        self.grid.setHorizontalHeaderLabels(headers)
        self.grid.load_matrix([[format(v, ".5g") for v in row] for row in rows])
        self.changed.emit()

    def load_example(self):
        xs = np.linspace(0, 10, 11)
        ys = np.linspace(0, 40, 9)
        rows = [[x, y, 20 * np.exp(-((x - 5) ** 2) / 8 - ((y - 20) ** 2) / 200), 0.5 * x + 0.05 * y]
                for y in ys for x in xs]
        self._load(rows, ["Stiffness (kPa)", "Time (h)", "Expression", "Viability (%)"])

    def load_scatter_example(self):
        rng = np.random.default_rng(3)
        x = rng.normal(0, 1, 150)
        y = 0.6 * x + rng.normal(0, 0.8, 150)
        z = 0.4 * x - 0.5 * y + rng.normal(0, 0.5, 150)
        self._load(np.column_stack([x, y, z, x + y + z]), ["PC1", "PC2", "PC3", "Score"])

    def headers(self):
        return [self.grid.header_text(c) for c in range(4)]

    def get_xyz(self):
        return tuple(self.grid.column_values(c) for c in range(4))

    def series_keys(self):
        return []

    def state(self):
        return {"headers": self.headers(), "cells": self.grid.to_matrix(),
                "excluded": self.grid.excluded_cells()}

    def load_state(self, st):
        headers = list(st.get("headers") or self.HEADERS)[:4]
        headers += self.HEADERS[len(headers):]
        self.grid.setHorizontalHeaderLabels(headers)
        self.grid.load_matrix(st.get("cells", []), excluded=st.get("excluded"))


# ---------------------------------------------------------------------------
# Choosing and ordering the columns on a graph
# ---------------------------------------------------------------------------

class _ReorderList(QtWidgets.QListWidget):
    dropped = QtCore.pyqtSignal()

    def dropEvent(self, event):
        super().dropEvent(event)
        self.dropped.emit()


class SeriesPicker(QtWidgets.QWidget):
    """Choose which columns (groups, data sets, or series) are graphed, and in what order.

    Columns are tracked by their position in the table, so renaming keeps their settings.
    Only columns that contain data are listed.
    """
    changed = QtCore.pyqtSignal()
    KEY = Qt.UserRole + 2

    def __init__(self, noun, plural, parent=None):
        super().__init__(parent)
        self.noun, self.plural = noun, plural
        self.order, self.hidden, self._items = [], set(), None
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        self.list = _ReorderList()
        self.list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.list.setMaximumHeight(150)
        self.list.setToolTip(f"Check the {plural} to graph. Drag to change their order.")
        self.list.itemChanged.connect(self._checked)
        self.list.dropped.connect(self._reordered)
        lay.addWidget(self.list)
        row = QtWidgets.QHBoxLayout()
        for text, slot, tip, width in (("\u25b2", lambda: self._move(-1), "Move up", 34),
                                       ("\u25bc", lambda: self._move(1), "Move down", 34),
                                       ("All", self.show_all, f"Graph every {noun}", 0),
                                       ("Reset order", self.reset_order, "Use the table's order", 0)):
            b = _button(text, slot, tip)
            b.setAccessibleName(tip)
            if width:
                b.setFixedWidth(width)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.empty_hint = _hint(f"{plural.capitalize()} with data are listed here.")
        lay.addWidget(self.empty_hint)

    # ----- keeping the list in step with the table
    def sync(self, items):
        """items: [(key, name)] for columns with data, in table order."""
        names = dict(items)
        order = [k for k in self.order if k in names] + [k for k, _ in items if k not in self.order]
        self.order = order
        rows = [(k, names[k], k not in self.hidden) for k in order]
        if rows != self._items:
            self._items = rows
            self._rebuild()
        self.empty_hint.setVisible(not rows)

    def _rebuild(self):
        self.list.blockSignals(True)
        try:
            current = self.list.currentItem().data(self.KEY) if self.list.currentItem() else None
            self.list.clear()
            for k, name, shown in self._items or []:
                item = QtWidgets.QListWidgetItem(name or f"{self.noun.capitalize()} {k + 1}")
                item.setData(self.KEY, k)
                # no ItemIsDropEnabled, so dropping moves an item instead of replacing one
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
                              | Qt.ItemIsDragEnabled)
                item.setCheckState(Qt.Checked if shown else Qt.Unchecked)
                self.list.addItem(item)
                if k == current:
                    self.list.setCurrentItem(item)
        finally:
            self.list.blockSignals(False)

    def has_items(self):
        return bool(self._items)

    def selected(self):
        return [k for k in self.order if k not in self.hidden]

    # ----- user actions
    def _changed(self):
        self._items = [(k, n, k not in self.hidden) for k, n, _ in (self._items or [])]
        self.changed.emit()

    def _checked(self, item):
        k = item.data(self.KEY)
        if item.checkState() == Qt.Checked:
            self.hidden.discard(k)
        else:
            self.hidden.add(k)
        self._changed()

    def _reordered(self):
        shown = [self.list.item(i).data(self.KEY) for i in range(self.list.count())]
        self.order = shown + [k for k in self.order if k not in shown]
        names = {k: n for k, n, _ in (self._items or [])}
        self._items = [(k, names.get(k, ""), k not in self.hidden) for k in shown]
        self.changed.emit()

    def _move(self, step):
        row = self.list.currentRow()
        new = row + step
        if row < 0 or not (0 <= new < self.list.count()):
            return
        self.list.blockSignals(True)
        item = self.list.takeItem(row)
        self.list.insertItem(new, item)
        self.list.setCurrentRow(new)
        self.list.blockSignals(False)
        self._reordered()

    def set_checked(self, key, shown):
        (self.hidden.discard if shown else self.hidden.add)(key)
        self._items = [(k, n, k not in self.hidden) for k, n, _ in (self._items or [])]
        self._rebuild()
        self.changed.emit()

    def move_key(self, key, position):
        order = [k for k in self.order if k != key]
        order.insert(position, key)
        self.order = order
        names = {k: n for k, n, _ in (self._items or [])}
        self._items = [(k, names[k], k not in self.hidden) for k in order if k in names]
        self._rebuild()
        self.changed.emit()

    def show_all(self, *_):
        self.hidden.clear()
        self._items = [(k, n, True) for k, n, _ in (self._items or [])]
        self._rebuild()
        self.changed.emit()

    def reset_order(self, *_):
        self.order = sorted(self.order)
        names = {k: n for k, n, _ in (self._items or [])}
        self._items = [(k, names[k], k not in self.hidden) for k in self.order if k in names]
        self._rebuild()
        self.changed.emit()

    # ----- saving
    def state(self):
        return {"order": list(self.order), "hidden": sorted(self.hidden)}

    def load_state(self, st):
        st = st or {}
        self.order = [int(k) for k in st.get("order", [])]
        self.hidden = {int(k) for k in st.get("hidden", [])}
        self._items = None   # rebuilt on the next sync, when the names are known


# ---------------------------------------------------------------------------
# Option forms
# ---------------------------------------------------------------------------

class ColorButton(QtWidgets.QPushButton):
    """Shows a color; click to choose another."""
    colorChanged = QtCore.pyqtSignal()

    def __init__(self, color="#000000", parent=None):
        super().__init__(parent)
        self.setAccessibleName("Choose color")
        self.setFixedHeight(22)
        self.clicked.connect(self._choose)
        self.set_value(color)

    def value(self):
        return self._color

    def set_value(self, color):
        self._color = QtGui.QColor(str(color)).name() if QtGui.QColor(str(color)).isValid() else "#000000"
        self.setText(self._color.upper())
        light = QtGui.QColor(self._color).lightnessF() > 0.55
        self.setStyleSheet(f"background-color: {self._color}; color: {'#000000' if light else '#ffffff'}; "
                           "border: 1px solid #888888; border-radius: 3px;")

    def _choose(self):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(self._color), self, "Choose a color")
        if c.isValid() and c.name() != self._color:
            self.set_value(c.name())
            self.colorChanged.emit()


class CheckList(QtWidgets.QListWidget):
    """A short list of names with check boxes; value() is the checked names in order."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumHeight(84)
        self._checked = []
        self.itemChanged.connect(self._item_changed)   # runs before the form's own handler

    def value(self):
        return list(self._checked)

    def set_value(self, names):
        self._checked = [str(n) for n in (names or [])]
        self._sync_checks()

    def set_items(self, names):
        names = list(names)
        if [self.item(i).text() for i in range(self.count())] == names:
            return
        self.blockSignals(True)
        self.clear()
        for name in names:
            item = QtWidgets.QListWidgetItem(name)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            self.addItem(item)
        self.blockSignals(False)
        self._sync_checks()

    def _sync_checks(self):
        self.blockSignals(True)
        for i in range(self.count()):
            item = self.item(i)
            item.setCheckState(Qt.Checked if item.text() in self._checked else Qt.Unchecked)
        self.blockSignals(False)

    def _item_changed(self, _item):
        shown = {self.item(i).text() for i in range(self.count())}
        self._checked = ([self.item(i).text() for i in range(self.count())
                          if self.item(i).checkState() == Qt.Checked]
                         + [n for n in self._checked if n not in shown])   # keep hidden choices


class OptionsForm(QtWidgets.QWidget):
    changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.controls = {}
        self.sections = {}
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

    def group(self, title):
        box = Section(title)
        form = box.form
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        # When the panel is narrow, a long label moves above its field instead of widening the panel
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        self._layout.addWidget(box)
        self.sections[title] = box
        return form

    def _emit(self, *_):
        self.changed.emit()

    def combo(self, form, key, label, items, value):
        w = QtWidgets.QComboBox()
        w.addItems(items)
        # Let the menu shrink with the panel; the drop-down list still shows full names
        w.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        w.setMinimumContentsLength(8)
        w.view().setMinimumWidth(w.view().sizeHintForColumn(0) + 28)
        w.setCurrentIndex(max(0, w.findText(value)))
        w.currentIndexChanged.connect(self._emit)
        form.addRow(label, w)
        self.controls[key] = w

    def check(self, form, key, label, value):
        w = QtWidgets.QCheckBox(label)
        w.setChecked(value)
        w.toggled.connect(self._emit)
        form.addRow(w)
        self.controls[key] = w

    def number(self, form, key, label, lo, hi, step, value, decimals=2, suffix=""):
        w = QtWidgets.QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setDecimals(decimals)
        w.setValue(value)
        if suffix:
            w.setSuffix(suffix)
        w.valueChanged.connect(self._emit)
        form.addRow(label, w)
        self.controls[key] = w

    def color(self, form, key, label, value):
        """A swatch button that opens a color chooser."""
        w = ColorButton(value)
        w.colorChanged.connect(self._emit)
        form.addRow(label, w)
        self.controls[key] = w

    def checklist(self, form, key, label, hint=""):
        """Checkable names (for example, the data sets drawn on the right Y axis)."""
        w = CheckList()
        w.itemChanged.connect(self._emit)
        if hint:
            w.setToolTip(hint)
        form.addRow(label, w)
        self.controls[key] = w

    def text(self, form, key, label, value="", placeholder=""):
        w = QtWidgets.QLineEdit(value)
        if placeholder:
            w.setPlaceholderText(placeholder)
        w.textChanged.connect(self._emit)
        form.addRow(label, w)
        self.controls[key] = w

    def get(self, key):
        w = self.controls[key]
        if isinstance(w, (ColorButton, CheckList)):
            return w.value()
        if isinstance(w, QtWidgets.QComboBox):
            return w.currentText()
        if isinstance(w, QtWidgets.QCheckBox):
            return w.isChecked()
        if isinstance(w, QtWidgets.QDoubleSpinBox):
            return w.value()
        return w.text()

    def set(self, key, value):
        w = self.controls[key]
        w.blockSignals(True)
        try:
            if isinstance(w, (ColorButton, CheckList)):
                w.set_value(value)
            elif isinstance(w, QtWidgets.QComboBox):
                from .lab_style import PALETTE_ALIASES
                if str(value).startswith("Table: ") and w.findText(str(value)) < 0:
                    w.addItem(str(value))   # another table, listed once the project has loaded
                idx = w.findText(str(value))
                if idx < 0:
                    idx = w.findText(PALETTE_ALIASES.get(str(value), ""))
                if idx >= 0:
                    w.setCurrentIndex(idx)
            elif isinstance(w, QtWidgets.QCheckBox):
                w.setChecked(bool(value))
            elif isinstance(w, QtWidgets.QDoubleSpinBox):
                w.setValue(float(value))
            else:
                w.setText(str(value))
        finally:
            w.blockSignals(False)

    def set_items(self, key, items):
        """Replace a menu's choices, keeping the current choice when it still exists."""
        w = self.controls[key]
        if isinstance(w, CheckList):
            w.set_items(items)
            return
        current = w.currentText()
        w.blockSignals(True)
        try:
            w.clear()
            w.addItems(list(items))
            w.setCurrentIndex(max(0, w.findText(current)))
            w.view().setMinimumWidth(w.view().sizeHintForColumn(0) + 28)
        finally:
            w.blockSignals(False)

    def optional(self, key):
        """Blank text means automatic."""
        value, ok = parse_number(self.get(key))
        return value if ok and math.isfinite(value) else None

    def state(self):
        return {k: self.get(k) for k in self.controls}

    def load_state(self, st):
        for k, v in st.items():
            if k in self.controls:
                self.set(k, v)
        self.changed.emit()


def _style_group(form_owner, d, include_frame=True):
    """Shared "Style and size" controls. Choosing a style preset loads its text settings."""
    f = form_owner.group("Style and size")
    form_owner.combo(f, "style", "Style", ls.style_names(), d.style)
    f.addRow("", _button("Edit style...", form_owner.edit_style,
                         "Tune line weights, ticks, text, markers, and colors, and save as a style"))
    if include_frame:
        form_owner.combo(f, "frame", "Frame", pl.FRAMES, d.frame)
    form_owner.text(f, "y_min", "Y minimum", "", "Auto")
    form_owner.text(f, "y_max", "Y maximum", "", "Auto")
    form_owner.check(f, "log_y", "Log scale Y axis", False)
    form_owner.controls["log_y"].setToolTip("Display only: statistics use the original values. Values at "
                                            "or below zero cannot be shown on a log axis.")
    form_owner.number(f, "width_in", "X axis length", 0.5, 12, 0.1, d.width_in, 2, " in")
    form_owner.number(f, "height_in", "Y axis length", 0.5, 12, 0.1, d.height_in, 2, " in")
    form_owner.number(f, "font_size", "Numbering size", 4, 24, 0.5, d.font_size, 1, " pt")
    form_owner.check(f, "bold", "Bold text", d.bold)
    form_owner.combo(f, "palette", "Colors", list(PALETTES), d.palette)
    f.addRow("", _button("Edit colors...", form_owner.edit_colors,
                         "Make your own color scheme: pick each data set's color, save it under a "
                         "name, and use it on any graph"))
    form_owner.text(f, "ref_y", "Reference line at Y", "", "e.g. 1 or 0, 100")
    f.addRow(_hint("Axis titles and legends are 1 pt larger than the numbering. "
                   "Lab template matches the lab's Prism exports."))
    form_owner.controls["style"].currentIndexChanged.connect(form_owner.apply_preset)
    return f


class _StyledForm(OptionsForm):
    on_edit_style = None   # set by the main window
    picker = None

    def add_picker(self, noun, plural, analysis_word):
        box = Section("Data on graph", form=False)
        lay = box.body_layout
        self.picker = SeriesPicker(noun, plural)
        self.picker.changed.connect(self._emit)
        lay.addWidget(self.picker)
        lay.addWidget(_hint(f"Drag to reorder. Unchecked {plural} are left off the graph and out "
                            f"of the {analysis_word}."))
        self._layout.addWidget(box)

    def state(self):
        st = super().state()
        if self.picker is not None:
            st["_series"] = self.picker.state()
        return st

    def load_state(self, st):
        if self.picker is not None and "_series" in st:
            self.picker.load_state(st.get("_series"))
        super().load_state(st)

    def apply_preset(self, *_):
        name = self.get("style")
        st = ls.preset(name)
        self.set("font_size", st["font_size"])
        self.set("bold", st["bold"])
        if st.get("palette") and name in ls.PALETTES:
            self.set("palette", name)
        self.changed.emit()

    def edit_style(self, *_):
        if self.on_edit_style is not None:
            self.on_edit_style(self)

    on_edit_colors = None   # set by the main window

    def edit_colors(self, *_):
        if self.on_edit_colors is not None:
            self.on_edit_colors(self)

    def show_section(self, title, on):
        box = self.sections.get(title)
        if box is not None and box.isVisibleTo(self) != on:
            box.setVisible(on)


def _volcano_group(form_owner, grouped):
    """Settings shared by grouped and XY volcano plots."""
    d = pl.VolcanoOptions()
    f = form_owner.group("Volcano plot")
    form_owner.number(f, "v_fc", "Fold change cutoff (|log2|)", 0, 20, 0.1, d.fc_cutoff, 2)
    form_owner.number(f, "v_p", "P value cutoff", 0.000001, 1, 0.01, d.p_cutoff, 6)
    form_owner.check(f, "v_fdr", "Use adjusted P (Benjamini-Hochberg FDR)", d.use_fdr)
    form_owner.controls["v_fdr"].setToolTip("Thresholds and plots the false discovery rate adjusted "
                                            "P values (Benjamini and Hochberg, 1995) instead of P.")
    if grouped:
        form_owner.combo(f, "v_test", "Test on each row", volcano.TESTS, d.test)
        form_owner.check(f, "v_log", "Values are already log2", d.already_log)
        f.addRow(_hint("Each row is one protein, gene, or site. The second data set on the graph is "
                       "compared with the first (fold change = second / first)."))
    else:
        form_owner.combo(f, "v_pinput", "Y values are", volcano.P_INPUTS, d.p_input)
        f.addRow(_hint("X is the log2 fold change and the first Y column the P value. Turn on Row "
                       "titles above the table to name the points."))
    form_owner.number(f, "v_top", "Label the most significant", 0, 500, 1, d.label_top, 0, " rows")
    form_owner.text(f, "v_names", "Also label", "", "names, separated by commas")
    form_owner.color(f, "v_up", "Up color", d.up_color)
    form_owner.color(f, "v_down", "Down color", d.down_color)
    form_owner.color(f, "v_ns", "Not significant color", d.ns_color)
    form_owner.check(f, "v_counts", "Show counts in the legend", d.show_counts)


def _volcano_options(form, grouped):
    g = form.get
    return pl.VolcanoOptions(
        fc_cutoff=g("v_fc"), p_cutoff=g("v_p"), use_fdr=g("v_fdr"),
        test=g("v_test") if grouped else volcano.TESTS[0],
        already_log=g("v_log") if grouped else False,
        p_input=volcano.P_INPUTS[0] if grouped else g("v_pinput"),
        label_top=int(round(g("v_top"))), label_names=g("v_names"), up_color=g("v_up"),
        down_color=g("v_down"), ns_color=g("v_ns"), show_counts=g("v_counts"))


def _right_axis_group(form_owner, plural):
    f = form_owner.group("Right Y axis")
    form_owner.checklist(f, "right_series", f"{plural.capitalize()} on the right axis",
                         f"Checked {plural} are drawn against a second Y axis on the right.")
    form_owner.text(f, "right_label", "Right Y-axis title", "", "Names of the checked " + plural)
    form_owner.text(f, "right_min", "Right Y minimum", "", "Auto")
    form_owner.text(f, "right_max", "Right Y maximum", "", "Auto")
    f.addRow(_hint("For data on different scales, such as a measurement and a temperature."))


def _view3d_group(form_owner, color_choices, default_color_by, z_label=True):
    d = p3.View3DOptions()
    f = form_owner.group("3D view")
    form_owner.combo(f, "color_by", "Color by", color_choices, default_color_by)
    form_owner.combo(f, "cmap3d", "Color scale", pl.heat_map_names(), d.cmap)
    form_owner.text(f, "color_label", "Color bar title", "", "Auto")
    form_owner.check(f, "colorbar", "Show color bar", d.colorbar)
    form_owner.number(f, "elev", "Elevation", -90, 90, 5, d.elev, 0, "\u00b0")
    form_owner.number(f, "azim", "Rotation", -180, 180, 5, d.azim, 0, "\u00b0")
    form_owner.combo(f, "projection", "Projection", p3.PROJECTIONS, d.projection)
    form_owner.number(f, "bar_width", "Bar width", 0.1, 1.0, 0.05, d.bar_width, 2)
    if z_label:
        form_owner.text(f, "z_label", "Z-axis title", d.z_label)
    form_owner.text(f, "z_min", "Z minimum", "", "Auto")
    form_owner.text(f, "z_max", "Z maximum", "", "Auto")


def _view3d_options(form, z_label=None):
    g = form.get
    return p3.View3DOptions(
        elev=g("elev"), azim=g("azim"), projection=g("projection"), color_by=g("color_by"),
        cmap=g("cmap3d"), color_label=g("color_label"),
        z_label=z_label if z_label is not None else g("z_label"), z_min=form.optional("z_min"),
        z_max=form.optional("z_max"), bar_width=g("bar_width"), colorbar=g("colorbar"))


class ColumnOptions(_StyledForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        d = pl.ColumnPlotOptions()
        self.add_picker("column", "columns", "statistics")
        f = self.group("Graph")
        self.combo(f, "plot_type", "Type", pl.PLOT_TYPES, d.plot_type)
        self.combo(f, "error", "Plot", se.COLUMN_SUMMARIES, d.error)
        self.check(f, "show_points", "Show individual points", d.show_points)
        self.combo(f, "point_layout", "Point layout", pl.POINT_LAYOUTS, d.point_layout)
        self.combo(f, "point_color", "Point color", pl.POINT_COLORS, d.point_color)
        self.number(f, "point_size", "Point size", 1, 15, 0.1, d.point_size, 1, " pt")
        self.combo(f, "marker", "Marker shape", pl.MARKER_CHOICES, d.marker)
        self.combo(f, "marker_fill", "Markers", pl.MARKER_FILLS, d.marker_fill)
        self.combo(f, "bar_style", "Bars", pl.BAR_STYLES, d.bar_style)
        self.combo(f, "whiskers", "Whiskers", pl.WHISKER_TYPES, d.whiskers)
        self.combo(f, "error_style", "Error bar lines", pl.ERROR_STYLES, d.error_style)
        self.combo(f, "orientation", "Orientation", pl.ORIENTATIONS, d.orientation)
        self.text(f, "hist_bin_width", "Bin width", "", "Auto")
        self.text(f, "hist_bin_start", "First bin starts at", "", "Auto")
        self.combo(f, "hist_values", "Histogram shows", pl.HIST_VALUES, d.hist_values)
        self.combo(f, "hist_style", "Histogram style", pl.HIST_STYLES, d.hist_style)
        self.text(f, "ref_x", "Reference line at X", "", "e.g. 10")
        for key in ("hist_bin_width", "hist_bin_start", "hist_values", "hist_style", "ref_x"):
            self.controls[key].setToolTip("For the Frequency distribution graph type")

        f = self.group("Statistics")
        self.combo(f, "test", "Test", se.COLUMN_TESTS, "None")
        self.combo(f, "comparisons", "Compare", se.COMPARISON_MODES, "All pairs")
        self.number(f, "conf", "Confidence level", 50, 99.999, 0.5, 95, 3, " %")
        self.controls["conf"].setToolTip("For t tests: sets the confidence interval and the significance "
                                         "threshold. For example, 99.5% means P < 0.005.")
        self.check(f, "gg", "Geisser-Greenhouse correction", True)
        self.combo(f, "annotation", "Show on graph", pl.ANNOTATIONS, d.annotation)
        self.check(f, "show_ns", "Show non-significant comparisons", d.show_ns)
        f.addRow(_hint("Repeated-measures tests treat each row as one subject."))

        f = self.group("Labels")
        self.text(f, "title", "Title", d.title)
        self.text(f, "y_label", "Y-axis title", d.y_label)
        self.text(f, "x_label", "X-axis title", d.x_label)
        self.check(f, "rotate_labels", "Angle group names", d.rotate_labels)

        _style_group(self, d)
        self._layout.addStretch(1)
        self.changed.connect(self.update_enabled)
        self.update_enabled()

    def update_enabled(self):
        pt = self.get("plot_type")
        self.controls["bar_style"].setEnabled(pt == "Bar with points")
        self.controls["whiskers"].setEnabled(pt == "Box plot")
        self.controls["show_points"].setEnabled(pt not in ("Scatter dot plot",
                                                           "Before-after (matched rows)"))
        self.controls["point_layout"].setEnabled(pt != "Before-after (matched rows)")
        self.controls["error"].setEnabled(pt in ("Scatter dot plot", "Bar with points"))
        hist = pt == pl.HISTOGRAM
        self.controls["orientation"].setEnabled(not hist)
        for key in ("hist_bin_width", "hist_bin_start", "hist_values", "hist_style", "ref_x"):
            self.controls[key].setEnabled(hist)
        if hist:
            for key in ("show_points", "point_layout", "point_color", "point_size", "marker",
                        "marker_fill", "error_style", "log_y"):
                self.controls[key].setEnabled(False)
        else:
            for key in ("point_color", "point_size", "marker", "marker_fill", "error_style", "log_y"):
                self.controls[key].setEnabled(True)
        test = self.get("test")
        self.controls["comparisons"].setEnabled(test in se.MULTI_GROUP_TESTS)
        self.controls["gg"].setEnabled(test == "Repeated-measures one-way ANOVA")
        self.controls["conf"].setEnabled(test in se.T_TESTS)
        self.controls["annotation"].setEnabled(test != "None")
        self.controls["show_ns"].setEnabled(test != "None")

    def options(self):
        g = self.get
        return pl.ColumnPlotOptions(
            plot_type=g("plot_type"), error=g("error"), title=g("title"),
            x_label=g("x_label"), y_label=g("y_label"),
            y_min=self.optional("y_min"), y_max=self.optional("y_max"),
            width_in=g("width_in"), height_in=g("height_in"), font_size=g("font_size"),
            bold=g("bold"), style=g("style"), palette=g("palette"), point_size=g("point_size"),
            marker=g("marker"), marker_fill=g("marker_fill"),
            show_points=g("show_points"), point_layout=g("point_layout"),
            point_color=g("point_color"), bar_style=g("bar_style"), whiskers=g("whiskers"),
            error_style=g("error_style"), log_y=g("log_y"), ref_x=g("ref_x"),
            hist_bin_width=self.optional("hist_bin_width"), hist_bin_start=self.optional("hist_bin_start"),
            hist_values=g("hist_values"), hist_style=g("hist_style"),
            annotation=g("annotation"), show_ns=g("show_ns"), rotate_labels=g("rotate_labels"),
            frame=g("frame"), ref_y=g("ref_y"), orientation=g("orientation"))


class GroupedOptions(_StyledForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        d = pl.GroupedPlotOptions()
        self.add_picker("data set", "data sets", "ANOVA")
        f = self.group("Graph")
        self.combo(f, "plot_type", "Type", pl.GROUPED_PLOT_TYPES, d.plot_type)
        self.combo(f, "arrangement", "Arrangement", pl.ARRANGEMENTS, d.arrangement)
        self.controls["arrangement"].setToolTip(
            "Interleaved: data sets side by side in each row. Separated: one block of bars per data "
            "set. Stacked: data sets piled on each other. Superimposed: data sets overlap, the "
            "shorter in front.")
        self.combo(f, "orientation", "Orientation", pl.ORIENTATIONS, d.orientation)
        self.combo(f, "error", "Error bars", se.ERROR_TYPES, d.error)
        self.check(f, "show_points", "Show individual points", d.show_points)
        self.number(f, "point_size", "Point size", 1, 15, 0.1, d.point_size, 1, " pt")
        self.combo(f, "marker", "Marker shape", pl.MARKER_CHOICES, d.marker)
        self.combo(f, "marker_fill", "Markers", pl.MARKER_FILLS, d.marker_fill)
        self.combo(f, "bar_style", "Bars", pl.BAR_STYLES, d.bar_style)
        self.combo(f, "whiskers", "Whiskers", pl.WHISKER_TYPES, d.whiskers)
        self.combo(f, "legend", "Legend", pl.LEGEND_POSITIONS, d.legend)
        self.combo(f, "error_style", "Error bar lines", pl.ERROR_STYLES, d.error_style)
        self.combo(f, "heat_cmap", "Heat map colors", pl.heat_map_names(), d.heat_cmap)
        self.check(f, "heat_values", "Show values in cells", d.heat_values)
        self.controls["heat_cmap"].setToolTip("Viridis, Cividis, and Magma read correctly in grayscale and "
                                              "with color-vision deficiency. Y minimum and maximum set "
                                              "the color range. Your own color schemes are listed too.")
        self.combo(f, "heat_shape", "Cells drawn as", pl.HEAT_SHAPES, d.heat_shape)
        self.combo(f, "circle_color", "Circle color shows", pl.CIRCLE_COLORS, d.circle_color)
        self.controls["circle_color"].setToolTip(
            "Circle size shows each cell's mean. Color can show the same mean, the cell's SD, SEM, "
            "number of values, or coefficient of variation, or the cell means of another grouped "
            "table (matched by row and data set names).")
        self.text(f, "circle_color_label", "Color bar title", "", "Auto")
        self._plot_type = d.plot_type

        f = self.group("Statistics")
        self.combo(f, "analysis", "Analysis", anova.ANALYSES, "Two-way ANOVA")
        self.combo(f, "design", "Matching", anova.DESIGNS, "No matching")
        self.design_hint = _hint(anova.DESIGN_HELP["No matching"])
        f.addRow(self.design_hint)
        self.check(f, "gg", "Geisser-Greenhouse correction", True)
        self.combo(f, "model", "Model", anova.MODELS, anova.FULL_MODEL)
        self.controls["model"].setToolTip("Main effects only assumes no interaction (designs without "
                                          "matching).")
        self.combo(f, "comparisons", "Compare", anova.GROUPED_COMPARISONS, "None")
        self.combo(f, "correction", "Correction", anova.CORRECTIONS, "Šídák")
        self.combo(f, "annotation", "Show on graph", pl.ANNOTATIONS, d.annotation)
        self.check(f, "show_ns", "Show non-significant comparisons", d.show_ns)
        self.text(f, "row_factor", "Row factor name", "Row Factor")
        self.text(f, "col_factor", "Column factor name", "Column Factor")

        f = self.group("Labels")
        self.text(f, "title", "Title", d.title)
        self.text(f, "y_label", "Y-axis title", d.y_label)
        self.text(f, "x_label", "X-axis title", d.x_label)
        self.check(f, "rotate_labels", "Angle row names", d.rotate_labels)

        _volcano_group(self, grouped=True)
        _view3d_group(self, p3.GROUPED_COLOR_BY, "Data set", z_label=False)
        _right_axis_group(self, "data sets")
        _style_group(self, d)
        self._layout.addStretch(1)
        self.changed.connect(self.update_enabled)
        self.update_enabled()

    def update_enabled(self):
        pt = self.get("plot_type")
        if pt != self._plot_type:
            if pt == pl.VOLCANO and self.get("legend") == "Inside upper left":
                self.set("legend", "Above plot")   # an inside legend would cover the points
            self._plot_type = pt
        line = pt.startswith("Line")
        special = pt in (pl.HEAT_MAP, pl.VOLCANO, pl.BARS_3D)
        self.controls["bar_style"].setEnabled(pt == "Grouped bars")
        self.controls["arrangement"].setEnabled(pt in ("Grouped bars", pl.AREA))
        self.controls["orientation"].setEnabled(not special)
        self.controls["whiskers"].setEnabled(pt == pl.GROUPED_BOX)
        self.controls["show_points"].setEnabled(
            pt not in ("Grouped scatter dot plot", pl.AREA) and not special
            and not (pt == "Grouped bars" and self.get("arrangement") == "Stacked"))
        circles = pt == pl.HEAT_MAP and self.get("heat_shape") == "Circles"
        self.controls["heat_shape"].setEnabled(pt == pl.HEAT_MAP)
        self.controls["circle_color"].setEnabled(circles)
        self.controls["circle_color_label"].setEnabled(circles)
        self.show_section("Volcano plot", pt == pl.VOLCANO)
        self.show_section("3D view", pt == pl.BARS_3D)
        self.show_section("Right Y axis", pt in pl.RIGHT_AXIS_TYPES)
        on = self.get("analysis") != "None"
        design = self.get("design")
        for key in ("design", "comparisons", "correction"):
            self.controls[key].setEnabled(on)
        self.controls["gg"].setEnabled(on and design != "No matching")
        self.controls["model"].setEnabled(on and design == "No matching")
        heat = pt == pl.HEAT_MAP
        self.controls["heat_cmap"].setEnabled(heat)
        self.controls["heat_values"].setEnabled(heat)
        for key in ("error", "point_size", "marker", "marker_fill", "legend", "error_style", "log_y"):
            self.controls[key].setEnabled(not heat)
        if pt in (pl.VOLCANO, pl.BARS_3D):
            for key in ("error", "marker", "marker_fill", "error_style", "log_y"):
                self.controls[key].setEnabled(False)
            self.controls["point_size"].setEnabled(pt == pl.VOLCANO)
            self.controls["legend"].setEnabled(pt == pl.VOLCANO)
        self.controls["error"].setEnabled(pt not in (pl.GROUPED_BOX, pl.AREA) and not special)
        brackets = (on and not line and pt not in (pl.AREA,) and not special)
        self.controls["annotation"].setEnabled(brackets)
        self.controls["show_ns"].setEnabled(brackets)
        self.design_hint.setText(anova.DESIGN_HELP.get(design, ""))

    def options(self):
        g = self.get
        return pl.GroupedPlotOptions(
            plot_type=g("plot_type"), error=g("error"), title=g("title"),
            x_label=g("x_label"), y_label=g("y_label"),
            y_min=self.optional("y_min"), y_max=self.optional("y_max"),
            width_in=g("width_in"), height_in=g("height_in"), font_size=g("font_size"),
            bold=g("bold"), style=g("style"), palette=g("palette"), point_size=g("point_size"),
            marker=g("marker"), marker_fill=g("marker_fill"),
            show_points=g("show_points"), bar_style=g("bar_style"), error_style=g("error_style"),
            annotation=g("annotation"), show_ns=g("show_ns"), rotate_labels=g("rotate_labels"),
            legend=g("legend"), frame=g("frame"), ref_y=g("ref_y"), log_y=g("log_y"),
            heat_cmap=g("heat_cmap"), heat_values=g("heat_values"), heat_shape=g("heat_shape"),
            circle_color=g("circle_color"), circle_color_label=g("circle_color_label"),
            arrangement=g("arrangement"), orientation=g("orientation"), whiskers=g("whiskers"),
            right_series=tuple(g("right_series")), right_label=g("right_label"),
            right_min=self.optional("right_min"), right_max=self.optional("right_max"),
            volcano=_volcano_options(self, grouped=True), view3d=_view3d_options(self, ""))


class XYOptions(_StyledForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        d = pl.XYPlotOptions()
        self.add_picker("data set", "data sets", "curve fits")
        f = self.group("Graph")
        self.combo(f, "plot_type", "Type", pl.XY_PLOT_TYPES, d.plot_type)
        self.combo(f, "error", "Error", se.ERROR_TYPES, d.error)
        self.combo(f, "error_display", "Show error as", pl.XY_ERROR_DISPLAYS, d.error_display)
        self.number(f, "point_size", "Point size", 0.5, 15, 0.1, d.point_size, 1, " pt")
        self.combo(f, "marker", "Marker shape", pl.MARKER_CHOICES, d.marker)
        self.combo(f, "marker_fill", "Markers", pl.MARKER_FILLS, d.marker_fill)
        self.combo(f, "error_style", "Error bar lines", pl.ERROR_STYLES, d.error_style)
        self.check(f, "connect", "Connect means (when no curve is fit)", d.connect)
        self.combo(f, "legend", "Legend", pl.LEGEND_POSITIONS, d.legend)
        self.check(f, "log_x", "Log scale X axis", d.log_x)

        f = self.group("Curve fit")
        self.combo(f, "fit_model", "Model", list(se.FIT_MODELS), d.fit_model)

        f = self.group("Labels")
        self.text(f, "title", "Title", d.title)
        self.text(f, "x_label", "X-axis title", d.x_label)
        self.text(f, "y_label", "Y-axis title", d.y_label)

        _volcano_group(self, grouped=False)
        _right_axis_group(self, "data sets")
        f = _style_group(self, d)
        self.text(f, "x_min", "X minimum", "", "Auto")
        self.text(f, "x_max", "X maximum", "", "Auto")
        self.text(f, "ref_x", "Reference line at X", "", "e.g. 24")
        self._layout.addStretch(1)
        self._plot_type = d.plot_type
        self.changed.connect(self.update_enabled)
        self.update_enabled()

    def update_enabled(self):
        pt = self.get("plot_type")
        if pt != self._plot_type:
            if pt == pl.VOLCANO and self.get("legend") == "Inside upper left":
                self.set("legend", "Above plot")
            self._plot_type = pt
        volc = pt == pl.VOLCANO
        for key in ("error", "error_display", "marker", "marker_fill", "error_style", "connect",
                    "log_x", "log_y", "fit_model"):
            self.controls[key].setEnabled(not volc)
        self.show_section("Volcano plot", volc)
        self.show_section("Curve fit", not volc)
        self.show_section("Right Y axis", pt in pl.RIGHT_AXIS_TYPES)

    def options(self):
        g = self.get
        return pl.XYPlotOptions(
            error=g("error"), error_display=g("error_display"), title=g("title"),
            x_label=g("x_label"), y_label=g("y_label"),
            x_min=self.optional("x_min"), x_max=self.optional("x_max"),
            y_min=self.optional("y_min"), y_max=self.optional("y_max"),
            width_in=g("width_in"), height_in=g("height_in"), font_size=g("font_size"),
            bold=g("bold"), style=g("style"), palette=g("palette"), point_size=g("point_size"),
            marker=g("marker"), marker_fill=g("marker_fill"), log_x=g("log_x"),
            connect=g("connect"), error_style=g("error_style"),
            legend=g("legend"), fit_model=g("fit_model") if g("plot_type") != pl.VOLCANO else "None",
            frame=g("frame"), ref_x=g("ref_x"), ref_y=g("ref_y"), log_y=g("log_y"),
            plot_type=g("plot_type"), right_series=tuple(g("right_series")),
            right_label=g("right_label"), right_min=self.optional("right_min"),
            right_max=self.optional("right_max"), volcano=_volcano_options(self, grouped=False))


class XYZOptions(_StyledForm):
    """Graph settings for 3D tables."""

    def __init__(self, parent=None):
        super().__init__(parent)
        d = p3.XYZPlotOptions()
        f = self.group("Graph")
        self.combo(f, "plot_type", "Type", p3.KINDS_3D, d.plot_type)
        self.number(f, "point_size", "Point size", 0.5, 15, 0.1, d.point_size, 1, " pt")
        self.check(f, "use_headers", "Use column titles as axis titles", True)
        _view3d_group(self, p3.COLOR_BY, d.view3d.color_by)
        f = self.group("Labels")
        self.text(f, "title", "Title", d.title)
        self.text(f, "x_label", "X-axis title", d.x_label)
        self.text(f, "y_label", "Y-axis title", d.y_label)
        f = _style_group(self, d, include_frame=False)
        for key in ("y_min", "y_max", "log_y", "ref_y"):
            self.controls[key].setEnabled(False)
            self.controls[key].setToolTip("Not used by 3D graphs; set Z limits under 3D view.")
        self.set("width_in", d.width_in)
        self.set("height_in", d.height_in)
        self._layout.addStretch(1)
        self.changed.connect(self.update_enabled)
        self.update_enabled()

    def update_enabled(self):
        pt = self.get("plot_type")
        heads = self.get("use_headers")
        for key in ("x_label", "y_label", "z_label"):
            self.controls[key].setEnabled(not heads)
        self.controls["bar_width"].setEnabled(pt == "3D bars")
        self.controls["point_size"].setEnabled(pt in ("3D scatter", "3D line", "Wireframe"))
        single = self.get("color_by") == p3.COLOR_BY[2]
        for key in ("cmap3d", "color_label", "colorbar"):
            self.controls[key].setEnabled(not single)

    def options(self, headers=None):
        g = self.get
        heads = g("use_headers") and headers
        v = _view3d_options(self, headers[2] if heads else None)
        if heads and not g("color_label") and v.color_by == p3.COLOR_BY[1]:
            v.color_label = headers[3]
        return p3.XYZPlotOptions(
            plot_type=g("plot_type"), title=g("title"),
            x_label=headers[0] if heads else g("x_label"),
            y_label=headers[1] if heads else g("y_label"),
            width_in=g("width_in"), height_in=g("height_in"), font_size=g("font_size"),
            bold=g("bold"), style=g("style"), palette=g("palette"), point_size=g("point_size"),
            view3d=v)


# ---------------------------------------------------------------------------
# Style editor
# ---------------------------------------------------------------------------

STYLE_GROUPS = {
    "Text": ["font_family", "font_size", "title_extra", "graph_title_extra", "bold"],
    "Line weights": ["axis_line", "data_line", "bracket_line", "thin", "ref_line_width"],
    "Ticks": ["tick_dir", "tick_len"],
    "Markers, bars, and fills": ["markers", "marker_edge", "square_scale", "fill_alpha",
                                 "bar_width", "heavy_stars"],
}
STYLE_FIELD_INFO = {key: (label, kind, spec) for key, label, kind, spec in ls.STYLE_FIELDS}
N_COLOR_SLOTS = 8


class StyleEditor(QtWidgets.QDialog):
    """Edit a style's line weights, ticks, text, markers, and colors; save it under a name."""

    def __init__(self, parent, name, values, palette_colors):
        super().__init__(parent)
        self.setWindowTitle("Edit style")
        self.original = name
        self.result = None
        self.deleted = False
        self.widgets = {}
        builtin = name in ls.STYLE_PRESETS
        colors = list(values.get("palette") or palette_colors or ls.PALETTES[ls.DEFAULT_PALETTE])
        self.n_used = max(1, min(N_COLOR_SLOTS, len(colors)))
        self.colors = (colors + ["#999999"] * N_COLOR_SLOTS)[:N_COLOR_SLOTS]

        outer = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QFormLayout()
        self.name_edit = QtWidgets.QLineEdit(f"{name} (custom)" if builtin else name)
        top.addRow("Style name", self.name_edit)
        outer.addLayout(top)
        outer.addWidget(_hint("Built-in styles stay unchanged; your edits are saved as a new style."
                              if builtin else "Saving replaces this style. Change the name to keep both."))

        body = QtWidgets.QWidget()
        bl = QtWidgets.QVBoxLayout(body)
        for title, keys in STYLE_GROUPS.items():
            box = QtWidgets.QGroupBox(title)
            form = QtWidgets.QFormLayout(box)
            form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
            for key in keys:
                label, kind, spec = STYLE_FIELD_INFO[key]
                w = self._make_widget(kind, spec)
                self.widgets[key] = w
                self._set_widget(key, values.get(key))
                form.addRow(label, w)
            bl.addWidget(box)

        box = QtWidgets.QGroupBox("Colors")
        vl = QtWidgets.QVBoxLayout(box)
        self.use_colors = QtWidgets.QCheckBox("Save these colors with the style")
        self.use_colors.setChecked(True)
        vl.addWidget(self.use_colors)
        grid = QtWidgets.QGridLayout()
        self.color_buttons = []
        for j in range(N_COLOR_SLOTS):
            b = QtWidgets.QPushButton()
            b.setFixedSize(52, 26)
            b.setToolTip("Click to choose a color")
            b.clicked.connect(lambda _checked=False, j=j: self._pick_color(j))
            grid.addWidget(b, j // 4, j % 4)
            self.color_buttons.append(b)
        vl.addLayout(grid)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Number of colors"))
        self.n_colors = QtWidgets.QSpinBox()
        self.n_colors.setRange(1, N_COLOR_SLOTS)
        self.n_colors.setValue(self.n_used)
        self.n_colors.valueChanged.connect(lambda *_: self._update_colors())
        row.addWidget(self.n_colors)
        row.addStretch(1)
        vl.addLayout(row)
        self.cvd_label = _hint("")
        vl.addWidget(self.cvd_label)
        bl.addWidget(box)
        bl.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(_button("Import style file...", self._import))
        row.addWidget(_button("Export style file...", self._export))
        delete = _button("Delete style", self._delete)
        delete.setEnabled(name in ls.CUSTOM_STYLES)
        row.addWidget(delete)
        row.addStretch(1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save
                                             | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        outer.addLayout(row)
        self._update_colors()
        self.resize(600, 760)

    # ----- widgets
    @staticmethod
    def _make_widget(kind, spec):
        if kind == "float":
            w = QtWidgets.QDoubleSpinBox()
            lo, hi, step = spec
            w.setRange(lo, hi)
            w.setSingleStep(step)
            w.setDecimals(2)
            return w
        if kind == "bool":
            return QtWidgets.QCheckBox()
        if kind == "choice":
            w = QtWidgets.QComboBox()
            w.addItems(spec)
            return w
        if kind == "font":
            return QtWidgets.QFontComboBox()
        if kind == "markers":
            w = QtWidgets.QWidget()
            hl = QtWidgets.QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            w.combos = []
            for _ in range(6):
                cb = QtWidgets.QComboBox()
                cb.addItems(list(ls.MARKER_CODES))
                cb.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
                cb.setMinimumContentsLength(4)
                hl.addWidget(cb)
                w.combos.append(cb)
            return w
        raise ValueError(kind)

    def _set_widget(self, key, value):
        w = self.widgets[key]
        kind = STYLE_FIELD_INFO[key][1]
        if value is None and kind not in ("font", "markers"):
            return
        if kind == "float":
            w.setValue(float(value))
        elif kind == "bool":
            w.setChecked(bool(value))
        elif kind == "choice":
            w.setCurrentIndex(max(0, w.findText(str(value))))
        elif kind == "font":
            w.setCurrentFont(QtGui.QFont(value or ls.available_font()))
        elif kind == "markers":
            seq = list(value or pl.XY_MARKERS)
            for i, cb in enumerate(w.combos):
                cb.setCurrentIndex(max(0, cb.findText(ls.MARKER_NAMES.get(seq[i % len(seq)], "Circle"))))

    def values(self):
        out = {}
        for key, w in self.widgets.items():
            kind = STYLE_FIELD_INFO[key][1]
            if kind == "float":
                out[key] = w.value()
            elif kind == "bool":
                out[key] = w.isChecked()
            elif kind == "choice":
                out[key] = w.currentText()
            elif kind == "font":
                out[key] = w.currentFont().family()
            elif kind == "markers":
                out[key] = [ls.MARKER_CODES[cb.currentText()] for cb in w.combos]
        out["palette"] = self.colors[:self.n_colors.value()] if self.use_colors.isChecked() else None
        return out

    # ----- colors
    def _pick_color(self, j):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.colors[j]), self, "Choose a color")
        if c.isValid():
            self.colors[j] = c.name()
            self._update_colors()

    def _update_colors(self):
        n = self.n_colors.value()
        for j, b in enumerate(self.color_buttons):
            used = j < n
            b.setEnabled(used)
            b.setText("" if used else "off")
            b.setStyleSheet(f"background-color: {self.colors[j] if used else '#f2f2f2'}; "
                            "border: 1px solid #888888; border-radius: 3px;")
        if n < 2:
            self.cvd_label.setText("Colorblind check needs at least two colors.")
            return
        d, kind, variant, c1, c2 = worst_pair(self.colors[:n])
        rating = "good" if d >= 10 else ("fair" if d >= 5 else "hard to tell apart")
        self.cvd_label.setText(
            f"Colorblind check: the most similar pair differs by {d:.1f} ({rating}); {c1} vs {c2} "
            f"under {kind}, {variant}. For reference, the Journal palette scores 9.9 and "
            "Okabe-Ito 5.2 on this test. Guide: 10 or more good, 5 to 10 fair.")

    # ----- buttons
    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.information(self, "Name needed", "Enter a name for this style.")
            return
        if name in ls.STYLE_PRESETS:
            QtWidgets.QMessageBox.information(
                self, "Built-in style", f"'{name}' is built in. Save your changes under a new name.")
            return
        if name in ls.CUSTOM_STYLES and name != self.original:
            answer = QtWidgets.QMessageBox.question(self, "Replace style",
                                                    f"A style named '{name}' exists. Replace it?")
            if answer != QtWidgets.QMessageBox.Yes:
                return
        self.result = (name, self.values())
        self.accept()

    def _delete(self):
        answer = QtWidgets.QMessageBox.question(
            self, "Delete style", f"Delete the style '{self.original}'? Graphs using it switch "
            "to the Lab template.")
        if answer == QtWidgets.QMessageBox.Yes:
            self.deleted = True
            self.accept()

    def _export(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export style", (self.name_edit.text().strip() or "style") + ".stelstyle",
            "STELplot style (*.stelstyle)")
        if not path:
            return
        if not path.endswith(".stelstyle"):
            path += ".stelstyle"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"stelplot_style": 1, "name": self.name_edit.text().strip(),
                           "values": self.values()}, fh, indent=1)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Export failed", str(exc))

    def _import(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import style", "", "STELplot style (*.stelstyle);;All files (*)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            values = ls.validate_style(data.get("values", {}))
        except (OSError, ValueError, AttributeError) as exc:
            QtWidgets.QMessageBox.warning(self, "Import failed", f"Not a STELplot style file.\n\n{exc}")
            return
        for key in self.widgets:
            if key in values:
                self._set_widget(key, values[key])
        if values.get("palette"):
            pal = values["palette"]
            self.colors = (pal + ["#999999"] * N_COLOR_SLOTS)[:N_COLOR_SLOTS]
            self.n_colors.setValue(max(1, min(N_COLOR_SLOTS, len(pal))))
        name = str(data.get("name") or "Imported style")
        self.name_edit.setText(f"{name} (imported)" if name in ls.STYLE_PRESETS else name)
        self._update_colors()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class PaletteEditor(QtWidgets.QDialog):
    """Make or change a color scheme: the colors data sets use, in order."""

    def __init__(self, parent, name, colors):
        super().__init__(parent)
        self.setWindowTitle("Edit colors")
        self.result = None
        self.deleted = False
        custom = name in ls.CUSTOM_PALETTES
        n_max = ls.MAX_PALETTE_COLORS
        colors = list(colors or ls.PALETTES[ls.DEFAULT_PALETTE])
        self.colors = (colors + ["#999999"] * n_max)[:n_max]
        outer = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QFormLayout()
        self.name_edit = QtWidgets.QLineEdit(name if custom else f"{name} (custom)")
        self.name_edit.setAccessibleName("Color scheme name")
        top.addRow("Color scheme name", self.name_edit)
        self.n_colors = QtWidgets.QSpinBox()
        self.n_colors.setRange(1, n_max)
        self.n_colors.setValue(max(1, min(n_max, len(colors))))
        self.n_colors.valueChanged.connect(lambda *_: self._update())
        top.addRow("Number of colors", self.n_colors)
        outer.addLayout(top)
        grid = QtWidgets.QGridLayout()
        self.buttons = []
        for j in range(n_max):
            b = QtWidgets.QPushButton()
            b.setFixedSize(58, 28)
            b.setAccessibleName(f"Color {j + 1}")
            b.setToolTip(f"Color {j + 1}: click to choose")
            b.clicked.connect(lambda _checked=False, j=j: self._pick(j))
            grid.addWidget(QtWidgets.QLabel(str(j + 1)), (j // 6) * 2, j % 6, Qt.AlignHCenter)
            grid.addWidget(b, (j // 6) * 2 + 1, j % 6)
            self.buttons.append(b)
        outer.addLayout(grid)
        outer.addWidget(_hint("Data sets take the colors in order: the first data set gets color 1. "
                              "Heat maps and 3D graphs can also use a scheme of two or more colors "
                              "as a gradient. Schemes are kept on this computer and saved inside "
                              "projects that use them."))
        self.cvd_label = _hint("")
        outer.addWidget(self.cvd_label)
        box = QtWidgets.QDialogButtonBox()
        save = box.addButton("Save", QtWidgets.QDialogButtonBox.AcceptRole)
        save.clicked.connect(self._save)
        if custom:
            delete = box.addButton("Delete scheme", QtWidgets.QDialogButtonBox.DestructiveRole)
            delete.clicked.connect(self._delete)
        box.addButton(QtWidgets.QDialogButtonBox.Cancel).clicked.connect(self.reject)
        outer.addWidget(box)
        self._update()

    def _pick(self, j):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.colors[j]), self, "Choose a color")
        if c.isValid():
            self.colors[j] = c.name().upper()
            self._update()

    def chosen(self):
        return self.colors[:self.n_colors.value()]

    def _update(self):
        n = self.n_colors.value()
        for j, b in enumerate(self.buttons):
            used = j < n
            b.setEnabled(used)
            b.setText("" if used else "off")
            b.setStyleSheet(f"background-color: {self.colors[j] if used else '#f2f2f2'}; "
                            "border: 1px solid #888888; border-radius: 3px;")
        if n < 2:
            self.cvd_label.setText("Colorblind check needs at least two colors.")
            return
        d, kind, variant, c1, c2 = worst_pair(self.chosen())
        rating = "good" if d >= 10 else ("fair" if d >= 5 else "hard to tell apart")
        self.cvd_label.setText(
            f"Colorblind check: the most similar pair differs by {d:.1f} ({rating}); {c1} vs {c2} "
            f"under {kind}, {variant}. Guide: 10 or more good, 5 to 10 fair (Journal scores 9.9).")

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.information(self, "Name needed", "Give the color scheme a name.")
            return
        if name in ls.BUILTIN_PALETTES or name in ls.STYLE_PRESETS:
            QtWidgets.QMessageBox.information(self, "Built-in name",
                                              f"'{name}' is built in. Save under a new name.")
            return
        self.result = (name, self.chosen())
        self.accept()

    def _delete(self):
        self.deleted = True
        self.accept()


TABLE_KINDS = {
    "column": ("Column table", ColumnPanel, ColumnOptions),
    "grouped": ("Grouped table", GroupedPanel, GroupedOptions),
    "xy": ("XY table", XYPanel, XYOptions),
    "xyz": ("3D table", XYZPanel, XYZOptions),
}
TABLE_HINTS = {
    "column": "Each column is one group.",
    "grouped": "Rows are one factor and data sets the other; replicates sit side by side.",
    "xy": "X values in the first column, Y replicates beside them.",
    "xyz": "X, Y, and Z for each point, plus an optional color value: 3D scatter, line, surface, "
           "wireframe, and bars.",
}


class DataTable:
    """One data table in a project: its type, title, data grid, and graph settings."""

    def __init__(self, kind, title):
        self.kind = kind
        self.title = title
        _label, panel_cls, opts_cls = TABLE_KINDS[kind]
        self.panel = panel_cls()
        self.opts = opts_cls()
        self.frozen = False
        self.outlier_record = None   # method, threshold, log scale, and how many were excluded

    def has_data(self):
        return bool(self.panel.grid.to_matrix())

    def state(self):
        return {"kind": self.kind, "title": self.title, "data": self.panel.state(),
                "options": self.opts.state(), "frozen": self.frozen, "outliers": self.outlier_record}


def _card():
    frame = QtWidgets.QFrame()
    frame.setObjectName("card")
    return frame


def _heading(text):
    label = QtWidgets.QLabel(text)
    label.setProperty("role", "heading")
    return label


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.project_path = None
        self.dirty = False
        self.preview_dpi = ZOOMS["150%"]
        self.last = None
        self.tables = []
        self.settings = QtCore.QSettings(ORG_NAME, APP_NAME)
        self.setWindowIcon(branding.app_icon())
        self.last_dir = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.DocumentsLocation) or os.path.expanduser("~")

        # Custom styles saved on this computer
        self._style_library = self._styles_path()
        self._style_error = ""
        if os.path.exists(self._style_library):
            try:
                ls.load_style_library(self._style_library)
            except (OSError, ValueError) as exc:
                self._style_error = str(exc)

        # Redraw and undo timers exist before any table is added
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh)
        self._restoring = False
        self._undo, self._redo = [], []
        self._current = None
        self._saved_key = None
        self.commit_timer = QtCore.QTimer(self)
        self.commit_timer.setSingleShot(True)
        self.commit_timer.setInterval(UNDO_SETTLE_MS)
        self.commit_timer.timeout.connect(self._commit_history)

        # ---- left: tables list, then the selected table
        nav = _card()
        nl = QtWidgets.QVBoxLayout(nav)
        nl.setContentsMargins(10, 10, 10, 10)
        head = QtWidgets.QHBoxLayout()
        head.addWidget(_heading("Data tables"))
        head.addStretch(1)
        self.new_table_btn = QtWidgets.QToolButton()
        self.new_table_btn.setText("+ New table  \u25be")
        self.new_table_btn.setProperty("cta", "1")
        self.new_table_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.new_table_btn.setMenu(self._new_table_menu())
        self.new_table_btn.setToolTip("Add a Column, Grouped, or XY table to this project")
        head.addWidget(self.new_table_btn)
        nl.addLayout(head)
        self.table_list = QtWidgets.QListWidget()
        self.table_list.setObjectName("tables")
        self.table_list.setAccessibleName("Data tables")
        self.table_list.setIconSize(QtCore.QSize(22, 22))
        self.table_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_list.customContextMenuRequested.connect(self._table_context_menu)
        self.table_list.currentRowChanged.connect(self._table_selected)
        nl.addWidget(self.table_list, 1)
        row = FlowLayout()
        row.addWidget(_button("Duplicate", self.duplicate_table, "Copy this table, data and settings"))
        row.addWidget(_button("Delete", self.delete_table, "Remove this table from the project"))
        self.freeze_btn = _button("Freeze", self.toggle_freeze, "Lock this table's data against edits")
        row.addWidget(self.freeze_btn)
        nl.addLayout(row)

        data_card = _card()
        dl = QtWidgets.QVBoxLayout(data_card)
        dl.setContentsMargins(10, 8, 10, 10)
        self.title_edit = QtWidgets.QLineEdit()
        self.title_edit.setObjectName("table_title")
        self.title_edit.setAccessibleName("Table name")
        self.title_edit.setPlaceholderText("Name this table")
        self.title_edit.setToolTip("Table name. Shown in the tables list and as 'Table Analyzed' "
                                   "in exported results.")
        self.title_edit.textEdited.connect(self._title_edited)
        self.kind_label = _hint("")
        self.panel_stack = QtWidgets.QStackedWidget()
        dl.addWidget(self.title_edit)
        dl.addWidget(self.kind_label)
        dl.addWidget(self.panel_stack, 1)

        left = QtWidgets.QSplitter(Qt.Vertical)
        left.addWidget(nav)
        left.addWidget(data_card)
        left.setStretchFactor(1, 1)
        left.setSizes([190, 700])
        self.left_split = left

        # ---- right: graph settings for the selected table, then export
        self.opt_stack = PageStack()
        self.export_section = Section("Export")
        export_box = self.export_section
        ef = export_box.form
        self.author_edit = QtWidgets.QLineEdit(DEFAULT_AUTHOR)
        self.author_edit.setToolTip("Written to the file's author metadata")
        self.trim_check = QtWidgets.QCheckBox("Trim white space around the figure")
        self.trim_check.setChecked(True)
        self.transparent_check = QtWidgets.QCheckBox("Transparent background")
        self.transparent_check.setChecked(True)
        self.transparent_check.setToolTip("SVG, PDF, and PNG: no white rectangle behind the graph, so it "
                                          "sits cleanly in Illustrator layouts. TIFF files stay white, as "
                                          "many journals require.")
        export_btn = _button("Export figure", self.export_figure,
                             "SVG or PDF keep text editable in Illustrator")
        export_btn.setProperty("cta", "1")
        ef.addRow("Author", self.author_edit)
        ef.addRow(self.trim_check)
        ef.addRow(self.transparent_check)
        ef.addRow(export_btn)
        ef.addRow(_button("Export results (CSV)", self.export_results))
        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 12, 8)   # room so fields never touch the scroll bar
        head_box = QtWidgets.QWidget()
        settings_head = FlowLayout(head_box)
        settings_head.setContentsMargins(4, 0, 18, 2)
        settings_head.addWidget(_heading("Settings"))
        settings_head.addWidget(_button("Expand all", lambda: self.expand_all_sections(True),
                                        "Open every settings section"))
        settings_head.addWidget(_button("Collapse all", lambda: self.expand_all_sections(False),
                                        "Fold every settings section to its title"))
        rl.addWidget(self.opt_stack)
        rl.addStretch(1)
        right_scroll = QtWidgets.QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setWidget(right)
        self.right_scroll = right_scroll
        export_holder = QtWidgets.QWidget()
        eh = QtWidgets.QVBoxLayout(export_holder)
        eh.setContentsMargins(4, 4, 18, 4)
        eh.addWidget(export_box)
        self.right_panel = QtWidgets.QWidget()
        rp = QtWidgets.QVBoxLayout(self.right_panel)
        rp.setContentsMargins(0, 0, 0, 0)
        rp.setSpacing(4)
        rp.addWidget(head_box)
        rp.addWidget(right_scroll, 1)
        rp.addWidget(export_holder)
        self.right_panel.setMinimumWidth(320)

        # ---- center: preview and results
        self.zoom_combo = QtWidgets.QComboBox()
        self.zoom_combo.setAccessibleName("Preview zoom")
        self.zoom_combo.addItems(list(ZOOMS))
        saved_zoom = str(self.settings.value("zoom", "150%"))
        self.zoom_combo.setCurrentIndex(list(ZOOMS).index(saved_zoom if saved_zoom in ZOOMS else "150%"))
        self.preview_dpi = ZOOMS[self.zoom_combo.currentText()]
        self.zoom_combo.currentIndexChanged.connect(self._zoom_changed)
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.addWidget(_heading("Graph"))
        top_bar.addSpacing(12)
        top_bar.addWidget(_hint("Zoom"))
        top_bar.addWidget(self.zoom_combo)
        top_bar.addStretch(1)
        top_bar.addWidget(_hint("Shown at export size. Axis lengths are exact."))
        self.plot_scroll = QtWidgets.QScrollArea()
        self.plot_scroll.setWidgetResizable(False)
        self.plot_scroll.setAlignment(Qt.AlignCenter)
        self.plot_scroll.setObjectName("preview")
        plot_area = _card()
        pl_lay = QtWidgets.QVBoxLayout(plot_area)
        pl_lay.setContentsMargins(10, 8, 10, 10)
        pl_lay.addLayout(top_bar)
        pl_lay.addWidget(self.plot_scroll, 1)

        self.results = QtWidgets.QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        self.results.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        res_bar = QtWidgets.QHBoxLayout()
        res_bar.addWidget(_heading("Results"))
        res_bar.addStretch(1)
        res_bar.addWidget(_button("Interpret", self.show_interpret,
                                  "What this analysis does and how to read it"))
        res_bar.addWidget(_button("Copy results", self.copy_results))
        res_bar.addWidget(_button("Copy methods text", self.copy_methods,
                                  "Draft legend and Methods sentence. Review before use."))
        res_area = _card()
        self.res_area = res_area
        rs_lay = QtWidgets.QVBoxLayout(res_area)
        rs_lay.setContentsMargins(10, 8, 10, 10)
        rs_lay.addLayout(res_bar)
        self.flags_label = QtWidgets.QLabel()
        self.flags_label.setProperty("role", "warn")
        self.summary_label = QtWidgets.QLabel()
        self.summary_label.setProperty("role", "summary")
        for lab, name in ((self.flags_label, "Warnings"), (self.summary_label, "Summary")):
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lab.setAccessibleName(name)
            lab.hide()
            rs_lay.addWidget(lab)
        self.results.setAccessibleName("Results")
        rs_lay.addWidget(self.results, 1)
        self._summary = ("", [])
        center = QtWidgets.QSplitter(Qt.Vertical)
        center.addWidget(plot_area)
        center.addWidget(res_area)
        center.setSizes([540, 250])
        self.center_split = center

        # Slim arrow tabs on the edges hide and show the side panels and the results
        self._panel_size = {}
        self.edges = {"tables": self._edge_button(True, "tables"),
                      "settings": self._edge_button(True, "settings"),
                      "results": self._edge_button(False, "results")}
        center_box = QtWidgets.QWidget()
        cb = QtWidgets.QVBoxLayout(center_box)
        cb.setContentsMargins(0, 0, 0, 0)
        cb.setSpacing(1)
        cb.addWidget(center, 1)
        cb.addWidget(self.edges["results"])

        split = QtWidgets.QSplitter(Qt.Horizontal)
        split.addWidget(left)
        self.center_stack = QtWidgets.QStackedWidget()
        self.center_stack.addWidget(center_box)
        self.center_stack.addWidget(self._build_layout_view())
        split.addWidget(self.center_stack)
        split.addWidget(self.right_panel)
        split.setStretchFactor(1, 1)
        split.setChildrenCollapsible(False)
        self.split = split
        holder = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(holder)
        hl.setContentsMargins(2, 8, 2, 4)
        hl.setSpacing(2)
        hl.addWidget(self.edges["tables"])
        hl.addWidget(split, 1)
        hl.addWidget(self.edges["settings"])
        self.setCentralWidget(holder)

        self.author_edit.textChanged.connect(self._mark_changed)
        self.trim_check.toggled.connect(self._mark_changed)
        self.transparent_check.toggled.connect(self._mark_changed)

        # First table, created without counting as a change (the canvas comes after it)
        self.canvas = None
        self._restoring = True
        self.add_table("column", "Data 1")
        self._restoring = False
        self.left_split.setMinimumWidth(self.two_column_width())
        self.export_section.update_header()
        self.export_section.toggled.connect(self._section_toggled)
        self._build_canvas()
        self._build_actions()
        self._defaults = self.project_state()
        self._reset_history()
        self._update_title()
        self._fit_to_screen()
        for name in PANELS:
            if not self.settings.value(f"show_{name}", True, type=bool):
                self.set_panel_visible(name, False)
        self._update_edges()
        self.refresh()

    # ----- tables
    def current_table(self):
        row = self.table_list.currentRow()
        return self.tables[row] if 0 <= row < len(self.tables) else self.tables[0]

    def _item_text(self, t):
        return f"{t.title}  \U0001F512" if t.frozen else t.title

    def _make_item(self, t):
        item = QtWidgets.QListWidgetItem(kind_icon(t.kind), self._item_text(t))
        item.setToolTip(f"{t.title}\n{TABLE_KINDS[t.kind][0]}")
        return item

    def _next_table_name(self):
        numbers = [int(t.title[5:]) for t in self.tables
                   if t.title.startswith("Data ") and t.title[5:].isdigit()]
        return f"Data {max(numbers + [len(self.tables)]) + 1}"

    def _new_table_menu(self):
        menu = QtWidgets.QMenu(self)
        for kind, (label, *_rest) in TABLE_KINDS.items():
            act = menu.addAction(label)
            act.setToolTip(TABLE_HINTS[kind])
            act.triggered.connect(lambda _checked=False, k=kind: self.add_table(k))
        return menu

    def add_table(self, kind, title=None, state=None, select=True):
        """Add a table to the project. `state` may hold "data" and "options"."""
        t = DataTable(kind, title or self._next_table_name())
        t.opts.on_edit_style = self.edit_style
        t.opts.on_edit_colors = self.edit_colors
        if state:
            was = self._restoring
            self._restoring = True
            try:
                if state.get("data"):
                    t.panel.load_state(state["data"])
                if state.get("options"):
                    t.opts.load_state(state["options"])
            finally:
                self._restoring = was
        if state and state.get("frozen"):
            t.frozen = True
            lock_panel(t.panel, True)
        if state and state.get("outliers"):
            t.outlier_record = dict(state["outliers"])
        for sec in t.opts.findChildren(Section):
            sec.update_header()
            sec.toggled.connect(self._section_toggled)
        t.panel.changed.connect(self._mark_changed)
        t.panel.grid.message.connect(lambda m: self.statusBar().showMessage(m, 8000))
        t.opts.changed.connect(self._mark_changed)
        self.tables.append(t)
        self.panel_stack.addWidget(t.panel)
        self.opt_stack.addWidget(t.opts)
        self.table_list.addItem(self._make_item(t))
        if select:
            self.table_list.setCurrentRow(len(self.tables) - 1)
        self._fit_stack(self.opt_stack.currentIndex())
        if not self._restoring and hasattr(self, "edges") and not self.panel_visible("tables"):
            self.set_panel_visible("tables", True)
        self._mark_changed()
        return t

    def _remove_table_widgets(self, t):
        self.panel_stack.removeWidget(t.panel)
        self.opt_stack.removeWidget(t.opts)
        t.panel.deleteLater()
        t.opts.deleteLater()

    def delete_table(self, *_):
        if len(self.tables) == 1:
            QtWidgets.QMessageBox.information(
                self, "Keep one table", "A project needs at least one table. Use Clear to empty it.")
            return
        row = self.table_list.currentRow()
        t = self.tables[row]
        if t.has_data():
            answer = QtWidgets.QMessageBox.question(
                self, "Delete table", f"Delete '{t.title}' and its data? You can undo this.")
            if answer != QtWidgets.QMessageBox.Yes:
                return
        self.tables.pop(row)
        self._remove_table_widgets(t)
        self.table_list.takeItem(row)
        self.table_list.setCurrentRow(max(0, row - 1))
        self._mark_changed()

    def duplicate_table(self, *_):
        t = self.current_table()
        self.add_table(t.kind, f"{t.title} copy",
                       {"data": t.panel.state(), "options": t.opts.state()})

    def _table_context_menu(self, pos):
        item = self.table_list.itemAt(pos)
        if item is None:
            return
        self.table_list.setCurrentItem(item)
        menu = QtWidgets.QMenu(self)
        rename = menu.addAction("Rename")
        dup = menu.addAction("Duplicate")
        dup_empty = menu.addAction("Duplicate with empty data")
        freeze = menu.addAction("Unfreeze" if self.current_table().frozen else "Freeze")
        delete = menu.addAction("Delete")
        chosen = menu.exec_(self.table_list.viewport().mapToGlobal(pos))
        if chosen is rename:
            self.title_edit.setFocus()
            self.title_edit.selectAll()
        elif chosen is dup:
            self.duplicate_table()
        elif chosen is dup_empty:
            self.duplicate_empty()
        elif chosen is freeze:
            self.toggle_freeze()
        elif chosen is delete:
            self.delete_table()

    def _table_selected(self, row):
        if not (0 <= row < len(self.tables)):
            return
        t = self.tables[row]
        self.panel_stack.setCurrentWidget(t.panel)
        self.opt_stack.setCurrentWidget(t.opts)
        self.title_edit.setText(t.title)
        self.kind_label.setText(f"{TABLE_KINDS[t.kind][0]}. " + (
            "Frozen: the data can be read and copied but not changed." if t.frozen
            else TABLE_HINTS[t.kind]))
        self.freeze_btn.setText("Unfreeze" if t.frozen else "Freeze")
        self.table_list.scrollToItem(self.table_list.item(row))
        if self.canvas is not None:
            self.refresh()

    def _title_edited(self, text):
        t = self.current_table()
        t.title = text.strip() or "Untitled"
        item = self.table_list.item(self.tables.index(t))
        item.setText(self._item_text(t))
        item.setToolTip(f"{t.title}\n{TABLE_KINDS[t.kind][0]}")
        self._mark_changed()

    # ----- panel sizes and settings sections
    def two_column_width(self):
        """Narrowest the data panel may go: row numbers plus two data columns."""
        grid = self.tables[0].panel.grid
        return (grid.verticalHeader().sizeHint().width() + 2 * grid.horizontalHeader().defaultSectionSize()
                + 2 * grid.frameWidth() + 14 + 2 * 10 + 2 * 6)

    def _fit_stack(self, index):
        """The settings holder already takes the height of the page shown."""
        self.opt_stack.updateGeometry()

    def all_sections(self):
        return [s for t in self.tables for s in t.opts.findChildren(Section)] + [self.export_section]

    def _section_toggled(self, title, on):
        """Keep the same section open or closed for every table."""
        for sec in self.all_sections():
            if sec.title == title and sec.expanded != on:
                sec.set_expanded(on, emit=False, save=False)

    def expand_all_sections(self, on):
        for sec in self.all_sections():
            sec.set_expanded(on, emit=False)

    def show_help(self, doc_name, title):
        windows = self.__dict__.setdefault("_help_windows", {})
        win = windows.get(doc_name)
        if win is None:
            win = windows[doc_name] = HelpWindow(self, title, doc_name, dark=self.is_dark())
        win.show()
        win.raise_()
        win.activateWindow()
        return win

    # ----- freezing, duplicates, and moving between tables
    def set_frozen(self, t, flag):
        t.frozen = bool(flag)
        lock_panel(t.panel, t.frozen)
        self.table_list.item(self.tables.index(t)).setText(self._item_text(t))
        if t is self.current_table():
            self._table_selected(self.tables.index(t))
        self.statusBar().showMessage(f"'{t.title}' is {'frozen' if t.frozen else 'unfrozen'}.", 5000)
        self._mark_changed()

    def toggle_freeze(self, *_):
        t = self.current_table()
        self.set_frozen(t, not t.frozen)

    def duplicate_empty(self, *_):
        """Same layout, analysis, and graph settings, ready for new data (like Duplicate Family)."""
        t = self.current_table()
        return self.add_table(t.kind, f"{t.title} (new data)",
                              {"data": workflow.empty_data(t.kind, t.panel.state()),
                               "options": t.opts.state()})

    def select_relative(self, step):
        row = (self.table_list.currentRow() + step) % len(self.tables)
        self.table_list.setCurrentRow(row)

    # ----- data transformations
    def transform_table(self, t, name, k=None, expression=None):
        """Make a new table holding the transformed data. Returns (new table, values skipped)."""
        new_state, skipped = transforms.transform_state(t.kind, t.panel.state(), name, k, expression)
        new = self.add_table(t.kind, f"{t.title} ({transforms.short_name(name, expression)})",
                             {"data": new_state, "options": t.opts.state()})
        note = (f" {skipped} value(s) could not be transformed (for example, the log of zero or a "
                "negative number) and were left blank." if skipped else "")
        self.statusBar().showMessage(f"Created '{new.title}'. The original table is unchanged.{note}", 12000)
        return new, skipped

    def transform_dialog(self, *_):
        t = self.current_table()
        if t.kind == "xyz":
            QtWidgets.QMessageBox.information(self, "Transform data", "Transforms work on Column, "
                                              "Grouped, and XY tables.")
            return
        if not t.has_data():
            QtWidgets.QMessageBox.information(self, "Transform data", "This table has no data yet.")
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Transform data")
        form = QtWidgets.QFormLayout(dlg)
        choice = QtWidgets.QComboBox()
        choice.addItems(transforms.available(t.kind))
        k_edit = QtWidgets.QLineEdit()
        k_edit.setPlaceholderText("Value of K")
        k_edit.setAccessibleName("K")
        expr_edit = QtWidgets.QLineEdit()
        expr_edit.setPlaceholderText("e.g. log10(Y) * 100, or (Y - K) / K")
        expr_edit.setAccessibleName("Expression")
        expr_help = _hint(transforms.EXPRESSION_HELP)

        def update(*_):
            custom = transforms.is_custom(choice.currentText())
            k_edit.setEnabled(custom or transforms.needs_k(choice.currentText()))
            k_edit.setPlaceholderText("Optional for expressions" if custom else "Value of K")
            expr_edit.setEnabled(custom)
            expr_help.setVisible(custom)
            dlg.adjustSize()
        choice.currentIndexChanged.connect(update)
        form.addRow("Transform", choice)
        form.addRow("Expression", expr_edit)
        form.addRow(expr_help)
        form.addRow("K", k_edit)
        update()
        form.addRow(_hint("Creates a new table with the transformed values and the same graph "
                          "settings. The original table is not changed."))
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)

        def current_k():
            k, ok = parse_number(k_edit.text())
            return k if ok and math.isfinite(k) else None

        def check_then_accept():
            try:   # check the expression and K before closing, so mistakes can be fixed in place
                transforms.transform_state(t.kind, t.panel.state(), choice.currentText(), current_k(),
                                           expr_edit.text())
            except ValueError as exc:
                QtWidgets.QMessageBox.information(dlg, "Transform data", str(exc))
                return
            dlg.accept()
        buttons.accepted.connect(check_then_accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        self.transform_table(t, choice.currentText(), current_k(), expr_edit.text())

    # ----- reusable settings: methods and copying from another table
    def _methods_path(self):
        return os.path.join(os.path.dirname(self._style_library), "methods.json")

    def clone_settings(self, source, target):
        """Give `target` the analysis and graph settings of `source` (like Clone a Graph)."""
        target.opts.load_state(workflow.method_settings(source.opts.state()))
        self.statusBar().showMessage(f"Applied the settings of '{source.title}' to '{target.title}'.", 6000)

    def clone_settings_dialog(self, *_):
        t = self.current_table()
        others = [o for o in self.tables if o is not t and o.kind == t.kind]
        if not others:
            QtWidgets.QMessageBox.information(
                self, "Apply settings", f"There is no other {TABLE_KINDS[t.kind][0].lower()} to copy from.")
            return
        names = [o.title for o in others]
        name, ok = QtWidgets.QInputDialog.getItem(self, "Apply settings from another table",
                                                  f"Copy the analysis and graph settings into '{t.title}' from:",
                                                  names, 0, False)
        if ok:
            self.clone_settings(others[names.index(name)], t)

    def save_method(self, t, name):
        methods = workflow.load_methods(self._methods_path())
        methods[name] = {"kind": t.kind, "options": workflow.method_settings(t.opts.state())}
        workflow.save_methods(self._methods_path(), methods)
        self.statusBar().showMessage(f"Saved method '{name}'. Apply it to any {TABLE_KINDS[t.kind][0].lower()}.", 6000)

    def apply_method(self, t, name):
        method = workflow.load_methods(self._methods_path())[name]
        t.opts.load_state(method["options"])
        self.statusBar().showMessage(f"Applied method '{name}' to '{t.title}'.", 6000)

    def save_method_dialog(self, *_):
        t = self.current_table()
        name, ok = QtWidgets.QInputDialog.getText(self, "Save settings as method",
                                                  "Name for this analysis and graph method:", text=t.title)
        if ok and name.strip():
            self.save_method(t, name.strip())

    def apply_method_dialog(self, *_):
        t = self.current_table()
        methods = {n: m for n, m in workflow.load_methods(self._methods_path()).items() if m["kind"] == t.kind}
        if not methods:
            QtWidgets.QMessageBox.information(self, "Apply method",
                                              f"No saved methods for a {TABLE_KINDS[t.kind][0].lower()} yet. "
                                              "Use Save settings as method first.")
            return
        name, ok = QtWidgets.QInputDialog.getItem(self, "Apply method", f"Apply to '{t.title}':",
                                                  sorted(methods), 0, False)
        if ok:
            self.apply_method(t, name)

    def delete_method_dialog(self, *_):
        methods = workflow.load_methods(self._methods_path())
        if not methods:
            QtWidgets.QMessageBox.information(self, "Delete method", "There are no saved methods.")
            return
        name, ok = QtWidgets.QInputDialog.getItem(self, "Delete method", "Delete:", sorted(methods), 0, False)
        if ok:
            methods.pop(name, None)
            workflow.save_methods(self._methods_path(), methods)
            self.statusBar().showMessage(f"Deleted method '{name}'.", 5000)

    # ----- outliers
    def identify_outliers(self, t, method=outliers.ROUT, threshold_pct=None, log_scale=False):
        """Flag possible outliers in each column of a Column table. Values are not changed."""
        grid = t.panel.grid
        grid.clear_flags()
        results = []
        for c, title in t.panel.series_keys():
            res = outliers.identify(grid.column_values(c), method, threshold_pct, log_scale)
            results.append((title, res))
            tip = (f"Possible outlier: {res.describe()}. Use Analysis > Identify outliers to exclude it, "
                   "or right-click to clear the flags.")
            for r in res.outliers:
                if grid.item(r, c) is not None:
                    grid.set_flagged(grid.item(r, c), True, tip)
        if results:
            first = results[0][1]
            old = t.outlier_record or {}
            t.outlier_record = {"method": method, "threshold": first.threshold, "log": bool(log_scale),
                                "flagged": sum(len(r.outliers) for _, r in results),
                                "excluded": old.get("excluded", 0) if old.get("method") == method else 0}
        self._mark_changed()
        return results

    def exclude_flagged(self, t):
        """Exclude every flagged value (blue italic, reversible). Returns how many."""
        grid = t.panel.grid
        if grid._refuse_if_locked():
            return 0
        cells = grid.flagged_cells()
        for r, c in cells:
            item = grid.item(r, c)
            grid.set_flagged(item, False)
            grid._set_excluded(item, True)
        if t.outlier_record is not None:
            t.outlier_record["excluded"] = t.outlier_record.get("excluded", 0) + len(cells)
            t.outlier_record["flagged"] = 0
        grid.dataEdited.emit()
        return len(cells)

    def outliers_dialog(self, *_):
        t = self.current_table()
        if t.kind != "column":
            QtWidgets.QMessageBox.information(
                self, "Identify outliers", "Identify outliers works on Column tables, testing each column "
                "separately. Grouped and XY tables usually have too few values per cell for these tests.")
            return
        if not t.has_data():
            QtWidgets.QMessageBox.information(self, "Identify outliers", "This table has no data yet.")
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Identify outliers")
        form = QtWidgets.QFormLayout(dlg)
        method = QtWidgets.QComboBox()
        method.addItems(outliers.METHODS)
        level = QtWidgets.QDoubleSpinBox()
        level.setRange(0.01, 20)
        level.setDecimals(2)
        level.setSuffix(" %")
        level_label = QtWidgets.QLabel("Q")
        log_check = QtWidgets.QCheckBox("Test on log scale")
        log_check.setToolTip("For log-normal data such as cell sizes, areas, and concentrations. "
                             "Values at or below zero are not tested.")

        def update(*_):
            m = method.currentText()
            level.setValue(outliers.DEFAULT_THRESHOLD[m])
            level_label.setText("Q (false discovery rate)" if m == outliers.ROUT else "Alpha")
        method.currentIndexChanged.connect(update)
        update()
        failing = []
        for c, title in t.panel.series_keys():
            v = t.panel.grid.column_values(c)
            v = v[np.isfinite(v)]
            if 3 <= v.size <= 5000 and stats_shapiro_p(v) < 0.05:
                failing.append(title)
        form.addRow("Method", method)
        form.addRow(level_label, level)
        form.addRow(log_check)
        form.addRow(_hint("Each column is tested separately. Flagged values are highlighted, not removed; "
                          "you decide whether to exclude them. ROUT (Q = 1%) can find several outliers. "
                          "Grubbs' test finds one at a time. Both assume Gaussian data apart from outliers."))
        if failing:
            form.addRow(_hint(f"\u26a0  {', '.join(failing)} fail the normality test. If the values are "
                              "log-normal (a long upper tail), test on the log scale; otherwise real "
                              "values in the tail will be flagged."))
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Find outliers")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        results = self.identify_outliers(t, method.currentText(), level.value(), log_check.isChecked())
        total = sum(len(r.outliers) for _, r in results)
        lines = []
        for title, r in results:
            if r.message:
                lines.append(f"{title}: not tested. {r.message}")
                continue
            found = ", ".join(f"row {pos + 1} ({value:g})" for pos, value, _s, _p in r.details[:8])
            more = f", and {len(r.details) - 8} more" if len(r.details) > 8 else ""
            skipped = f"; {r.skipped} value(s) at or below zero not tested" if r.skipped else ""
            lines.append(f"{title}: {len(r.outliers)} of {r.n_tested}" + (f": {found}{more}" if found else "")
                         + skipped)
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Identify outliers")
        box.setText(f"{results[0][1].describe()} flagged {total} value(s). They are highlighted in amber."
                    if results else "No columns with data.")
        box.setInformativeText("\n".join(lines))
        exclude_btn = box.addButton("Exclude flagged values", QtWidgets.QMessageBox.AcceptRole) if total else None
        box.addButton("Keep highlighted" if total else "Close", QtWidgets.QMessageBox.RejectRole)
        clear_btn = box.addButton("Clear flags", QtWidgets.QMessageBox.DestructiveRole) if total else None
        box.exec_()
        clicked = box.clickedButton()
        if exclude_btn is not None and clicked is exclude_btn:
            n = self.exclude_flagged(t)
            self.statusBar().showMessage(f"Excluded {n} value(s). They stay in the table in blue italic; "
                                         "right-click and choose Include to restore any of them.", 10000)
        elif clear_btn is not None and clicked is clear_btn:
            t.panel.grid.clear_flags()
            t.panel.grid.dataEdited.emit()

    # ----- layout sheets
    def figure_for_table(self, t):
        """Render a table's graph at export size without changing the window. None if empty."""
        if t.kind == "xyz":
            opts = t.opts.options(t.panel.headers())
            x, y, z, c = t.panel.get_xyz()
            if not np.isfinite(z).any():
                return None
            fig = Figure(figsize=(opts.width_in, opts.height_in))
            p3.render_xyz(fig, x, y, z, c, opts)
            return fig
        opts = t.opts.options()
        t.opts.picker.sync(t.panel.series_keys())
        keys = t.opts.picker.selected()
        fig = Figure(figsize=(opts.width_in, opts.height_in))
        if t.kind == "column":
            groups = t.panel.get_groups(keys)
            if not groups:
                return None
            result = se.run_column_stats(groups, t.opts.get("test"), t.opts.get("comparisons"),
                                         gg=t.opts.get("gg"), conf=t.opts.get("conf") / 100)
            pl.render_column(fig, groups, opts, result)
        elif t.kind == "grouped":
            labels, names, block = t.panel.get_grouped(keys)
            if not names or not np.isfinite(block).any():
                return None
            g = t.opts
            result = (anova.run_grouped(labels, names, block, design=g.get("design"),
                                        comparisons=g.get("comparisons"), correction=g.get("correction"),
                                        gg=g.get("gg"), model=g.get("model"))
                      if g.get("analysis") != "None" else None)
            pl.render_grouped(fig, labels, names, block, opts, result, self._color_source(t))
        else:
            x, series = t.panel.get_xy(keys)
            if not series:
                return None
            fits = ([se.fit_curve(name, x, y, opts.fit_model) for name, y in series]
                    if opts.fit_model != "None" else [])
            pl.render_xy(fig, x, series, opts, fits, t.panel.row_title_list())
        return fig

    def _color_source(self, t):
        """For circle heat maps colored by another grouped table: (row labels, names, values)."""
        choice = t.opts.get("circle_color")
        if not choice.startswith("Table: "):
            return None
        title = choice[len("Table: "):]
        other = next((o for o in self.tables if o.kind == "grouped" and o.title == title
                      and o is not t), None)
        return other.panel.get_grouped() if other is not None else None

    def _sync_choices(self, t):
        """Lists that depend on the table's data sets and on the other tables in the project."""
        if "right_series" in t.opts.controls:
            names = [n for _k, n in t.panel.series_keys()]
            t.opts.set_items("right_series", names)
        if t.kind == "grouped":
            others = [f"Table: {o.title}" for o in self.tables if o.kind == "grouped" and o is not t]
            t.opts.set_items("circle_color", pl.CIRCLE_COLORS + others)

    def export_layout(self, tables, path, ncols=2, gap_in=0.25, letters=True, letter_size=10.0):
        """Arrange the graphs of `tables` into one SVG, PNG, or TIFF file."""
        folder = tempfile.mkdtemp(prefix="stelplot_layout_")
        vector = path.lower().endswith(".svg")
        author = self.author_edit.text().strip() or DEFAULT_AUTHOR
        panels = []
        for i, t in enumerate(tables):
            fig = self.figure_for_table(t)
            if fig is None:
                continue
            panel = os.path.join(folder, f"panel_{i}{'.svg' if vector else '.png'}")
            pl.save_figure(fig, panel, author=author, trim=True, transparent=True)
            panels.append(panel)
        if not panels:
            raise ValueError("None of the chosen tables has data to graph.")
        if vector:
            return layout.compose_svg(panels, path, ncols, gap_in, letters, letter_size,
                                      font=ls.available_font(), author=author)
        return layout.compose_raster(panels, path, ncols, gap_in, letters, letter_size,
                                     white=path.lower().endswith((".tif", ".tiff")) or not self.transparent_check.isChecked())

    def _build_layout_view(self):
        """Layout sheet view: graphs to include on the left, a live preview on the right."""
        view = _card()
        lay = QtWidgets.QVBoxLayout(view)
        lay.setContentsMargins(10, 8, 10, 10)
        head = QtWidgets.QHBoxLayout()
        back = _button("\u2190  Back to graph", lambda: self.set_layout_mode(False),
                       "Return to the graph and results")
        back.setProperty("cta", "1")
        head.addWidget(back)
        head.addSpacing(12)
        head.addWidget(_heading("Layout sheet"))
        head.addStretch(1)
        head.addWidget(_button("Export layout...", self.export_layout_dialog,
                               "SVG (editable in Illustrator), PNG, or TIFF"))
        lay.addLayout(head)
        body = QtWidgets.QHBoxLayout()
        side = QtWidgets.QWidget()
        side.setFixedWidth(250)
        sl = QtWidgets.QVBoxLayout(side)
        sl.setContentsMargins(0, 4, 0, 0)
        sl.addWidget(QtWidgets.QLabel("Graphs on the sheet"))
        self.layout_picker = SeriesPicker("graph", "graphs")
        self.layout_picker.changed.connect(self._layout_changed)
        sl.addWidget(self.layout_picker)
        form = QtWidgets.QFormLayout()
        self.layout_cols = QtWidgets.QSpinBox()
        self.layout_cols.setRange(1, 6)
        self.layout_cols.setValue(2)
        self.layout_gap = QtWidgets.QDoubleSpinBox()
        self.layout_gap.setRange(0, 2)
        self.layout_gap.setSingleStep(0.05)
        self.layout_gap.setValue(0.25)
        self.layout_gap.setSuffix(" in")
        self.layout_letters = QtWidgets.QCheckBox("Panel letters (A, B, C)")
        self.layout_letters.setChecked(True)
        self.layout_letter_size = QtWidgets.QDoubleSpinBox()
        self.layout_letter_size.setRange(6, 24)
        self.layout_letter_size.setValue(10)
        self.layout_letter_size.setSuffix(" pt")
        for w in (self.layout_cols, self.layout_gap, self.layout_letter_size):
            w.valueChanged.connect(self._layout_changed)
        self.layout_letters.toggled.connect(self._layout_changed)
        form.addRow("Graphs per row", self.layout_cols)
        form.addRow("Space between", self.layout_gap)
        form.addRow(self.layout_letters)
        form.addRow("Letter size", self.layout_letter_size)
        sl.addLayout(form)
        sl.addWidget(_hint("Check the graphs to include and drag them into order; panels are lettered "
                           "in this order. Each graph uses its own table's settings and axis lengths."))
        sl.addStretch(1)
        self.layout_scroll = QtWidgets.QScrollArea()
        self.layout_scroll.setObjectName("preview")
        self.layout_scroll.setAlignment(Qt.AlignCenter)
        self.layout_scroll.setWidgetResizable(False)
        self.layout_label = QtWidgets.QLabel()
        self.layout_label.setAlignment(Qt.AlignCenter)
        self.layout_label.setAccessibleName("Layout sheet preview")
        self.layout_scroll.setWidget(self.layout_label)
        self.layout_status = _hint("")
        preview = QtWidgets.QVBoxLayout()
        preview.addWidget(self.layout_scroll, 1)
        preview.addWidget(self.layout_status)
        body.addWidget(side)
        body.addLayout(preview, 1)
        lay.addLayout(body, 1)
        self.layout_timer = QtCore.QTimer(self)
        self.layout_timer.setSingleShot(True)
        self.layout_timer.setInterval(250)
        self.layout_timer.timeout.connect(self._render_layout_preview)
        return view

    def layout_mode(self):
        return hasattr(self, "center_stack") and self.center_stack.currentIndex() == 1

    def set_layout_mode(self, on=True):
        on = bool(on)
        self.center_stack.setCurrentIndex(1 if on else 0)
        act = getattr(self, "layout_action", None)
        if act is not None and act.isChecked() != on:
            act.blockSignals(True)
            act.setChecked(on)
            act.blockSignals(False)
        if on:
            self._sync_layout_picker()
            self._render_layout_preview()
        else:
            self.refresh()

    def _sync_layout_picker(self):
        self.layout_picker.sync([(i, t.title) for i, t in enumerate(self.tables) if t.has_data()])

    def _layout_tables(self):
        return [self.tables[k] for k in self.layout_picker.selected() if k < len(self.tables)]

    def _layout_changed(self, *_):
        if not self._restoring:
            self._mark_changed()
        self.layout_timer.start()

    def layout_state(self):
        return {"graphs": self.layout_picker.state(), "per_row": self.layout_cols.value(),
                "gap": self.layout_gap.value(), "letters": self.layout_letters.isChecked(),
                "letter_size": self.layout_letter_size.value()}

    def _load_layout_state(self, st):
        st = st or {}
        widgets = (self.layout_cols, self.layout_gap, self.layout_letters, self.layout_letter_size)
        for w in widgets:
            w.blockSignals(True)
        try:
            self.layout_picker.load_state(st.get("graphs"))
            self.layout_cols.setValue(int(st.get("per_row", 2)))
            self.layout_gap.setValue(float(st.get("gap", 0.25)))
            self.layout_letters.setChecked(bool(st.get("letters", True)))
            self.layout_letter_size.setValue(float(st.get("letter_size", 10)))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self._sync_layout_picker()

    def _render_layout_preview(self):
        """Draw the sheet at the preview zoom (twice that resolution, for Retina screens)."""
        import shutil
        self._sync_layout_picker()
        chosen = self._layout_tables()
        if not chosen:
            self.layout_label.setPixmap(QtGui.QPixmap())
            self.layout_label.setText("Check at least one graph with data.")
            self.layout_label.adjustSize()
            self.layout_status.setText("")
            return None
        ratio = 2.0
        dpi = int(round(self.preview_dpi * ratio))
        folder = tempfile.mkdtemp(prefix="stelplot_preview_")
        try:
            panels = []
            for i, t in enumerate(chosen):
                fig = self.figure_for_table(t)
                if fig is None:
                    continue
                path = os.path.join(folder, f"panel_{i}.png")
                pl.save_figure(fig, path, trim=True, transparent=False, dpi=dpi)
                panels.append(path)
            if not panels:
                self.layout_label.setText("None of the checked tables has data to graph.")
                return None
            out = os.path.join(folder, "layout.png")
            _path, size = layout.compose_raster(panels, out, self.layout_cols.value(),
                                                self.layout_gap.value(), self.layout_letters.isChecked(),
                                                self.layout_letter_size.value(), dpi=dpi, white=True)
            pix = QtGui.QPixmap(out)
        except (OSError, ValueError) as exc:
            self.layout_status.setText(f"The preview could not be drawn: {exc}")
            return None
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        pix.setDevicePixelRatio(ratio)
        self.layout_label.setText("")
        self.layout_label.setPixmap(pix)
        self.layout_label.adjustSize()
        self.layout_status.setText(f"{len(panels)} graph(s). Sheet {size[0] / dpi:.2f} x {size[1] / dpi:.2f} "
                                   f"in, shown at the {self.zoom_combo.currentText()} preview zoom.")
        return pix

    def export_layout_dialog(self, *_):
        chosen = self._layout_tables()
        if not chosen:
            QtWidgets.QMessageBox.information(self, "Layout sheet", "Check at least one graph to export.")
            return
        filters = "SVG, editable in Illustrator (*.svg);;PNG, 600 dpi (*.png);;TIFF, 600 dpi (*.tif)"
        path, chosen_filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export layout sheet", os.path.join(self.last_dir, "layout.svg"), filters)
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".svg", ".png", ".tif", ".tiff"):
            ext = ".png" if "PNG" in chosen_filter else ".tif" if "TIFF" in chosen_filter else ".svg"
            path += ext
        try:
            self.export_layout(chosen, path, self.layout_cols.value(), self.layout_gap.value(),
                               self.layout_letters.isChecked(), self.layout_letter_size.value())
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(self, "Layout not saved", str(exc))
            return
        self.last_dir = os.path.dirname(path)
        self.statusBar().showMessage(f"Saved layout sheet with {len(chosen)} graph(s) to {path}", 8000)

    def layout_dialog(self, *_):
        """Open the layout sheet view (File > Export layout sheet and the toolbar's Layout)."""
        self.set_layout_mode(True)

    # ----- styles
    @staticmethod
    def _styles_path():
        base = (os.environ.get("STELPLOT_CONFIG_DIR")
                or QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.AppConfigLocation)
                or os.path.join(os.path.expanduser("~"), ".stelplot"))
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "styles.json")

    def _save_style_library(self):
        try:
            ls.save_style_library(self._style_library)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Style not saved",
                                          f"The style library could not be saved.\n\n{exc}")

    def _forms(self):
        return [t.opts for t in self.tables]

    def _refresh_style_lists(self):
        for form in self._forms():
            form.set_items("style", ls.style_names())
            form.set_items("palette", list(ls.PALETTES))
            for key in ("heat_cmap", "cmap3d"):
                if key in form.controls:
                    form.set_items(key, pl.heat_map_names())

    def edit_colors(self, form):
        name = ls.PALETTE_ALIASES.get(form.get("palette"), form.get("palette"))
        dlg = PaletteEditor(self, name, ls.PALETTES.get(name))
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        if dlg.deleted:
            ls.remove_palette(name)
            self._save_style_library()
            self._refresh_style_lists()
            for f in self._forms():
                if f.get("palette") not in ls.PALETTES:
                    f.set("palette", ls.DEFAULT_PALETTE)
                    f.changed.emit()
            self.statusBar().showMessage(f"Deleted color scheme '{name}'.", 5000)
            return
        new_name, colors = dlg.result
        try:
            ls.register_palette(new_name, colors)
        except ValueError as exc:
            QtWidgets.QMessageBox.information(self, "Colors not saved", str(exc))
            return
        self._save_style_library()
        self._refresh_style_lists()
        form.set("palette", new_name)
        form.changed.emit()
        for f in self._forms():
            if f is not form and new_name in (f.get("palette"), f.get("heat_cmap") if "heat_cmap" in
                                              f.controls else None):
                f.changed.emit()
        self.statusBar().showMessage(f"Saved color scheme '{new_name}'. It is available for every "
                                     "table.", 6000)

    def _palettes_in_use(self):
        names = set()
        for form in self._forms():
            for key in ("palette", "heat_cmap", "cmap3d"):
                if key in form.controls:
                    names.add(form.get(key))
        return {n: list(ls.CUSTOM_PALETTES[n]) for n in names if n in ls.CUSTOM_PALETTES}

    def edit_style(self, form):
        name = form.get("style")
        palette = ls.PALETTES.get(ls.PALETTE_ALIASES.get(form.get("palette"), form.get("palette")))
        dlg = StyleEditor(self, name, ls.preset(name), list(palette or [])[:N_COLOR_SLOTS])
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        if dlg.deleted:
            ls.remove_style(name)
            self._save_style_library()
            self._refresh_style_lists()
            for f in self._forms():
                if f.get("style") not in ls.style_names() or f.get("style") == name:
                    f.set("style", ls.DEFAULT_STYLE)
                    f.apply_preset()
            self.statusBar().showMessage(f"Deleted style '{name}'.", 5000)
            return
        new_name, values = dlg.result
        try:
            ls.register_style(new_name, values)
        except ValueError as exc:
            QtWidgets.QMessageBox.information(self, "Style not saved", str(exc))
            return
        self._save_style_library()
        self._refresh_style_lists()
        form.set("style", new_name)
        form.apply_preset()
        for f in self._forms():   # other tables already using this style pick up the changes
            if f is not form and f.get("style") == new_name:
                f.changed.emit()
        self.statusBar().showMessage(f"Saved style '{new_name}'. It is available for every table.", 6000)

    def _styles_in_use(self):
        names = set()
        for form in self._forms():
            names.update({form.get("style"), form.get("palette")})
        return {n: ls.style_definition(n) for n in names if n in ls.CUSTOM_STYLES}

    # ----- window and canvas
    def _fit_to_screen(self):
        """Open at about 92% of the available screen and split the panels proportionally."""
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            w, h, x, y = 1280, 800, 40, 40
        else:
            avail = screen.availableGeometry()
            w = min(1600, int(avail.width() * 0.92))
            h = min(1000, int(avail.height() * 0.92))
            x = avail.x() + (avail.width() - w) // 2
            y = avail.y() + (avail.height() - h) // 2
        self.resize(w, h)
        self.move(x, y)
        right = max(340, int(w * 0.24))
        left = int(w * 0.30)
        self.split.setSizes([left, max(300, w - left - right), right])
        nav = max(150, int(h * 0.24))
        self.left_split.setSizes([nav, max(300, h - nav)])

    def _active_kind(self):
        return self.current_table().kind

    def _active_size(self):
        opts = self.current_table().opts
        return opts.get("width_in"), opts.get("height_in")

    def _build_canvas(self):
        w, h = self._active_size()
        self.fig = Figure(figsize=(w, h), dpi=self.preview_dpi)
        canvas = FigureCanvas(self.fig)
        old = self.plot_scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.canvas = canvas
        self.canvas.setAccessibleName("Graph preview")
        self._fit_canvas(w, h)
        self.plot_scroll.setWidget(self.canvas)

    def _fit_canvas(self, w, h):
        self.fig.set_size_inches(w, h, forward=False)
        self.canvas.setFixedSize(int(round(w * self.preview_dpi)), int(round(h * self.preview_dpi)))

    def _zoom_changed(self, *_):
        self.preview_dpi = ZOOMS[self.zoom_combo.currentText()]
        self.settings.setValue("zoom", self.zoom_combo.currentText())
        self._build_canvas()
        self.refresh()

    def zoom_step(self, step):
        i = min(max(self.zoom_combo.currentIndex() + step, 0), self.zoom_combo.count() - 1)
        self.zoom_combo.setCurrentIndex(i)

    # ----- collapsible panels
    def _edge_button(self, vertical, name):
        b = QtWidgets.QToolButton()
        b.setObjectName("edge")
        b.setAutoRaise(True)
        b.setCursor(Qt.PointingHandCursor)
        if vertical:
            b.setFixedWidth(14)
            b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        else:
            b.setFixedHeight(14)
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        b.setAccessibleName(f"Hide or show the {PANELS[name][0]} panel")
        b.clicked.connect(lambda _checked=False, n=name: self.toggle_panel(n))
        return b

    def _panel(self, name):
        """(panel widget, splitter holding it, index of the neighbor that gives or takes space)."""
        if name == "results":
            return self.res_area, self.center_split, 0
        return ({"tables": self.left_split, "settings": self.right_panel}[name], self.split, 1)

    def panel_visible(self, name):
        return not self._panel(name)[0].isHidden()

    def set_panel_visible(self, name, visible):
        w, split, neighbor = self._panel(name)
        i = split.indexOf(w)
        if not visible and not w.isHidden():
            size = split.sizes()[i]
            if size > 0:
                self._panel_size[name] = size
            w.hide()
        elif visible and w.isHidden():
            w.show()
            sizes = split.sizes()
            total = sum(sizes)
            default = {"tables": int(0.3 * total), "settings": 340, "results": 250}[name]
            want = self._panel_size.get(name, default)
            sizes[i] = want
            sizes[neighbor] = max(220, total - sum(sz for j, sz in enumerate(sizes) if j != neighbor))
            split.setSizes(sizes)
        self.settings.setValue(f"show_{name}", bool(visible))
        self._update_edges()

    def toggle_panel(self, name):
        self.set_panel_visible(name, not self.panel_visible(name))

    def _update_edges(self):
        arrows = {"tables": ("\u25c2", "\u25b8"), "settings": ("\u25b8", "\u25c2"),
                  "results": ("\u25be", "\u25b4")}
        for name, button in self.edges.items():
            shown = self.panel_visible(name)
            button.setText(arrows[name][0 if shown else 1])
            label = PANELS[name][0]
            button.setToolTip(f"{'Hide' if shown else 'Show'} {label} ({PANELS[name][1].replace('Ctrl', 'Cmd' if sys.platform == 'darwin' else 'Ctrl')})")
            act = getattr(self, "panel_actions", {}).get(name)
            if act is not None and act.isChecked() != shown:
                act.blockSignals(True)
                act.setChecked(shown)
                act.blockSignals(False)

    def _set_dark(self, on):
        apply_theme(QtWidgets.QApplication.instance(), bool(on))
        self.settings.setValue("dark_mode", bool(on))
        for t in self.tables:
            t.panel.grid.recolor_excluded()
        self.refresh()

    def _paper(self):
        """Give the preview figure the backdrop color, so the graph appears without a box.
        Exports are unaffected (see the Transparent background option)."""
        dark = self.dark_action.isChecked() if hasattr(self, "dark_action") else False
        self.fig.patch.set_facecolor((DARK if dark else LIGHT)["preview_bg"])

    # ----- change tracking and undo
    def _set_dirty(self, value):
        self.dirty = value
        self._update_title()

    def _mark_changed(self, *_):
        self.timer.start()
        if self._restoring:
            return
        self._set_dirty(True)
        self.commit_timer.start()
        self._update_undo_actions()

    def _snapshot(self):
        """(full state JSON, comparison key). The key ignores which table is showing."""
        st = self.project_state()
        full = json.dumps(st, sort_keys=True)
        st.pop("active_table", None)
        return full, json.dumps(st, sort_keys=True)

    def _reset_history(self):
        self.commit_timer.stop()
        self._undo, self._redo = [], []
        self._current = self._snapshot()
        self._saved_key = self._current[1]
        self._update_undo_actions()

    def _commit_history(self):
        if self._restoring or self._current is None:
            return
        new = self._snapshot()
        if new[1] != self._current[1]:
            self._undo.append(self._current)
            del self._undo[:-MAX_UNDO]
            self._redo.clear()
            self._current = new
        self._set_dirty(self._current[1] != self._saved_key)
        self._update_undo_actions()

    def _flush_history(self):
        if self.commit_timer.isActive():
            self.commit_timer.stop()
            self._commit_history()

    def _restore(self, snapshot):
        self.apply_state(json.loads(snapshot[0]))
        self._current = self._snapshot()
        self._set_dirty(self._current[1] != self._saved_key)
        self._update_undo_actions()

    def undo(self, *_):
        self._flush_history()
        if not self._undo:
            return
        self._redo.append(self._current)
        self._restore(self._undo.pop())
        self.statusBar().showMessage(f"Undone. {len(self._undo)} more step(s) available.", 3000)

    def redo(self, *_):
        self._flush_history()
        if not self._redo:
            return
        self._undo.append(self._current)
        self._restore(self._redo.pop())
        self.statusBar().showMessage("Redone.", 3000)

    def _update_undo_actions(self):
        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(bool(self._undo) or self.commit_timer.isActive())
            self.redo_action.setEnabled(bool(self._redo))

    def _update_title(self):
        name = os.path.basename(self.project_path) if self.project_path else "Untitled"
        self.setWindowTitle(f"{name}{'*' if self.dirty else ''} - {APP_NAME}")

    # ----- drawing
    def refresh(self):
        if self.layout_mode():
            self.layout_timer.start()
        try:
            t = self.current_table()
            if t.kind != "xyz":
                self._sync_choices(t)
            {"column": self._refresh_column, "grouped": self._refresh_grouped,
             "xy": self._refresh_xy, "xyz": self._refresh_xyz}[t.kind](t)
        except Exception:  # keep the app running and show the details
            self.results.setPlainText("The graph could not be drawn.\n\n" + traceback.format_exc())
            self.statusBar().showMessage("Drawing failed. Details are in the results panel.", 8000)

    def _picked(self, t):
        """Update the table's Data on graph list; return the chosen keys (None: nothing picked)."""
        t.opts.picker.sync(t.panel.series_keys())
        keys = t.opts.picker.selected()
        if t.opts.picker.has_items() and not keys:
            self.fig.clear()
            self.fig.stel_notes = []
            self.fig.text(0.5, 0.5, "Every column is unchecked\nunder Data on graph.", ha="center",
                          va="center", fontsize=8, color="#5c6672")
            self._paper()
            self.canvas.draw_idle()
            self.last = None
            self._show_summary("", [], t)
            self.results.setPlainText("Every column is unchecked under Data on graph (top of the graph "
                                      "settings). Check at least one to graph and analyze it.")
            return None
        return keys

    def _refresh_column(self, t):
        opts = t.opts.options()
        keys = self._picked(t)
        if keys is None:
            return
        groups = t.panel.get_groups(keys)
        result = (se.run_column_stats(groups, t.opts.get("test"), t.opts.get("comparisons"),
                                      gg=t.opts.get("gg"), conf=t.opts.get("conf") / 100)
                  if groups else None)
        pl.render_column(self.fig, groups, opts, result)
        self._paper()
        self._fit_canvas(*self.fig.get_size_inches())
        self.canvas.draw_idle()
        self.last = {"kind": "column", "groups": groups, "opts": opts, "result": result,
                     "title": t.title,
                     "draw": lambda fig: pl.render_column(fig, groups, opts, result)}
        report = se.column_report(result, opts.error, t.title) + self._excluded_note(t)
        freq = getattr(self.fig, "stel_frequency", None) if opts.plot_type == pl.HISTOGRAM else None
        if freq:
            report = pl.frequency_text(freq) + "\n\n" + report
        self.results.setPlainText(report)
        self._show_summary(*(interpret.column_summary(result) if result else ("", [])), t)

    def _refresh_grouped(self, t):
        opts = t.opts.options()
        keys = self._picked(t)
        if keys is None:
            return
        labels, names, block = t.panel.get_grouped(keys)
        g = t.opts
        result = None
        if g.get("analysis") != "None":
            result = anova.run_grouped(labels, names, block, design=g.get("design"),
                                       comparisons=g.get("comparisons"),
                                       correction=g.get("correction"), gg=g.get("gg"),
                                       model=g.get("model"))
        source = self._color_source(t)
        pl.render_grouped(self.fig, labels, names, block, opts, result, source)
        self._paper()
        self._fit_canvas(*self.fig.get_size_inches())
        self.canvas.draw_idle()
        has = bool(np.isfinite(block).any())
        vtable = getattr(self.fig, "stel_volcano", None)
        self.last = {"kind": "grouped", "labels": labels, "names": names, "block": block,
                     "opts": opts, "result": result, "has": has, "title": t.title,
                     "volcano": vtable,
                     "draw": lambda fig: pl.render_grouped(fig, labels, names, block, opts, result,
                                                           source)}
        rf, cf = self._factor_names()
        if vtable is not None:
            self._show_summary(*interpret.volcano_summary(vtable), t)
            self.results.setPlainText(volcano.volcano_text(vtable) + self._excluded_note(t))
            return
        self._show_summary(*(interpret.grouped_summary(result, rf, cf) if (has and result) else ("", [])), t)
        if not has:
            self.results.setPlainText("Enter a label for each row and replicate values for each data set.")
        elif result is None:
            cells = anova.cell_table(*anova.clean_grouped(labels, names, block))
            rows = [[rl, cn, n, se.fmt(m), se.fmt(sd), se.fmt(sm)] for rl, cn, n, m, sd, sm in cells]
            self.results.setPlainText("Cell statistics\n" + anova._table(
                rows, ["Row", "Data set", "n", "Mean", "SD", "SEM"]) + self._excluded_note(t))
        else:
            if (result.ok and result.comparisons and opts.annotation != "None"
                    and g.get("comparisons") in ("Compare rows within each column", anova.CELLS)):
                result.notes.append("Comparisons between rows are listed here but not drawn "
                                    "on the graph.")
            rf, cf = self._factor_names()
            self.results.setPlainText(anova.grouped_report(result, opts.error, STAR_LEGEND, format_p,
                                                           t.title, rf, cf) + self._excluded_note(t))

    def _refresh_xy(self, t):
        opts = t.opts.options()
        keys = self._picked(t)
        if keys is None:
            return
        x, series = t.panel.get_xy(keys)
        fits = ([se.fit_curve(name, x, y, opts.fit_model) for name, y in series]
                if opts.fit_model != "None" else [])
        titles = t.panel.row_title_list()
        pl.render_xy(self.fig, x, series, opts, fits, titles)
        self._paper()
        self._fit_canvas(*self.fig.get_size_inches())
        self.canvas.draw_idle()
        vtable = getattr(self.fig, "stel_volcano", None)
        self.last = {"kind": "xy", "x": x, "series": series, "opts": opts, "fits": fits,
                     "title": t.title, "volcano": vtable,
                     "draw": lambda fig: pl.render_xy(fig, x, series, opts, fits, titles)}
        if vtable is not None:
            self.results.setPlainText(volcano.volcano_text(vtable) + self._excluded_note(t))
            self._show_summary(*interpret.volcano_summary(vtable), t)
            return
        if series:
            counts = [(name, int(pl.xy_summary(x, y, opts.error)[0].size)) for name, y in series]
            self.results.setPlainText(se.xy_report(fits, opts.error, counts) + self._excluded_note(t))
            self._show_summary(*interpret.xy_summary(fits, x), t)
        else:
            self.results.setPlainText("Enter X values in the first column and Y replicates beside them.")
            self._show_summary("", [], t)

    def _refresh_xyz(self, t):
        opts = t.opts.options(t.panel.headers())
        x, y, z, c = t.panel.get_xyz()
        p3.render_xyz(self.fig, x, y, z, c, opts)
        self._paper()
        self._fit_canvas(*self.fig.get_size_inches())
        self.canvas.draw_idle()
        ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        self.last = {"kind": "xyz", "opts": opts, "has": bool(ok.any()), "title": t.title,
                     "xyz": (x, y, z, c), "headers": t.panel.headers(),
                     "draw": lambda fig: p3.render_xyz(fig, x, y, z, c, opts)}
        if not ok.any():
            self.results.setPlainText("Enter X, Y, and Z values for each point.")
        else:
            heads = t.panel.headers()
            lines = [f"{int(ok.sum())} points with X, Y, and Z"]
            for name, v in zip(heads, (x, y, z, c)):
                v = v[ok & np.isfinite(v)]
                if v.size:
                    lines.append(f"{name}: {v.size} values, {se.fmt(float(v.min()))} to "
                                 f"{se.fmt(float(v.max()))}, mean {se.fmt(float(v.mean()))}")
            self.results.setPlainText("\n".join(lines) + self._excluded_note(t))
        self._show_summary("", [], t)

    def _show_summary(self, text, warnings, t=None):
        warnings = list(warnings) + list(getattr(self.fig, "stel_notes", None) or [])
        n_ex = len(t.panel.grid.excluded_cells()) if t is not None else 0
        if n_ex:
            warnings.append(f"{n_ex} excluded value(s) are left out of this graph and analysis.")
        record = t.outlier_record if t is not None else None
        n_flag = len(t.panel.grid.flagged_cells()) if t is not None else 0
        if n_flag:
            how = outliers.OutlierResult(record["method"], record["threshold"], record.get("log")).describe() \
                if record else "an outlier test"
            warnings.append(f"{n_flag} value(s) are flagged (amber) as possible outliers by {how} and are "
                            "still included. Use Analysis > Identify outliers to exclude them, or "
                            "right-click a cell.")
        if record and record.get("excluded"):
            how = outliers.OutlierResult(record["method"], record["threshold"], record.get("log")).describe()
            text = (text + "\n\n" if text else "") + (f"Outliers: {how} excluded {record['excluded']} "
                                                        "value(s) before this analysis.")
        self._summary = (text, warnings)
        self.summary_label.setText(text)
        self.summary_label.setVisible(bool(text))
        self.flags_label.setText("\n".join(f"\u26a0  {w}" for w in warnings))
        self.flags_label.setVisible(bool(warnings))

    def interpret_name(self, t=None):
        t = t or self.current_table()
        if t.kind in ("grouped", "xy") and t.opts.get("plot_type") == pl.VOLCANO:
            return "Volcano plot"
        if t.kind == "column":
            return t.opts.get("test")
        if t.kind == "grouped":
            return "Two-way ANOVA" if t.opts.get("analysis") != "None" else "None"
        if t.kind == "xyz":
            return "None"
        return t.opts.get("fit_model")

    def interpret_text(self):
        text, warnings = self._summary
        out = interpret.help_text(self.interpret_name())
        if text:
            out += "\n\nThese results\n" + text
        if warnings:
            out += "\n\nWorth a look\n" + "\n".join(f"- {w}" for w in warnings)
        return out

    def show_interpret(self, *_):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Interpret results")
        lay = QtWidgets.QVBoxLayout(dlg)
        view = QtWidgets.QPlainTextEdit(self.interpret_text())
        view.setReadOnly(True)
        view.setAccessibleName("Interpretation")
        lay.addWidget(view)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        dlg.resize(620, 520)
        dlg.exec_()

    @staticmethod
    def _excluded_note(t):
        n = len(t.panel.grid.excluded_cells())
        return (f"\n\n{n} excluded value(s) are left out of this graph and analysis "
                "(blue italic in the table)." if n else "")

    def _table_title(self, opts=None):
        return (self.last or {}).get("title") or self.current_table().title

    def _factor_names(self):
        g = self.current_table().opts
        return (g.get("row_factor").strip() or "Row Factor",
                g.get("col_factor").strip() or "Column Factor")

    def _has_data(self):
        if not self.last:
            return False
        kind = self.last["kind"]
        if kind in ("grouped", "xyz"):
            return self.last["has"]
        return bool(self.last["groups"] if kind == "column" else self.last["series"])

    # ----- export
    def export_figure(self):
        self.refresh()
        if not self._has_data():
            QtWidgets.QMessageBox.information(self, "Nothing to export", "Enter data to make a graph first.")
            return
        opts = self.last["opts"]
        base = (opts.title or self.last.get("title") or "figure").replace("/", "-")
        filters = ";;".join(pl.EXPORT_FORMATS.values())
        path, chosen = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export figure", os.path.join(self.last_dir, base + ".svg"), filters)
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in pl.EXPORT_FORMATS and ext != ".tiff":
            ext = next((e for e, label in pl.EXPORT_FORMATS.items() if label == chosen), ".svg")
            path += ext
        try:
            self.save_figure_to(path)
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(self, "Export failed", f"The figure was not saved.\n\n{exc}")
            return
        self.last_dir = os.path.dirname(path)
        self.statusBar().showMessage(f"Exported figure to {path}", 8000)

    def save_figure_to(self, path):
        """Render the current graph at export size and save it (no dialogs)."""
        opts = self.last["opts"]
        fig = Figure(figsize=(opts.width_in, opts.height_in))
        self.last["draw"](fig)
        pl.save_figure(fig, path, author=self.author_edit.text().strip() or DEFAULT_AUTHOR,
                       title=opts.title, trim=self.trim_check.isChecked(),
                       transparent=self.transparent_check.isChecked())
        return path

    def export_results(self):
        self.refresh()
        if not self._has_data():
            QtWidgets.QMessageBox.information(self, "Nothing to export", "Enter data first.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export results", os.path.join(self.last_dir, "results.csv"), "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            self.save_results_to(path)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Export failed", f"The results were not saved.\n\n{exc}")
            return
        self.last_dir = os.path.dirname(path)
        self.statusBar().showMessage(f"Exported results to {path}", 8000)

    def save_results_to(self, path):
        """Write the current results as CSV in Prism's layout where available (no dialogs)."""
        kind = self.last["kind"]
        title = self._table_title(self.last["opts"])
        if self.last.get("volcano") is not None:
            volcano.write_volcano_csv(path, self.last["volcano"])
        elif kind == "xyz":
            import csv
            x, y, z, c = self.last["xyz"]
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(self.last["headers"])
                for row in zip(x, y, z, c):
                    if all(np.isfinite(row[:3])):
                        w.writerow(["" if not np.isfinite(v) else format(v, ".6g") for v in row])
        elif kind == "column":
            se.write_column_csv(path, self.last["result"], title)
        elif kind == "grouped":
            rf, cf = self._factor_names()
            anova.write_grouped_csv(path, self.last["result"], self.last["labels"],
                                    self.last["names"], self.last["block"], title, rf, cf)
        else:
            se.write_xy_csv(path, self.last["fits"])
        return path

    def copy_results(self):
        text, warnings = self._summary
        head = (text + "\n\n" if text else "") + "".join(f"Note: {w}\n" for w in warnings)
        QtWidgets.QApplication.clipboard().setText((head + "\n" if head else "") + self.results.toPlainText())
        self.statusBar().showMessage("Results copied", 4000)

    def copy_methods(self):
        if not self._has_data():
            return
        opts = self.last["opts"]
        vt = self.last.get("volcano")
        if vt is not None:
            text = self._volcano_methods(vt, opts)
        elif self.last["kind"] == "xyz":
            text = (f"Data were plotted as a 3D {opts.plot_type.replace('3D ', '').lower()} graph "
                    f"in {APP_NAME} {__version__}.")
        elif self.last["kind"] == "column":
            text = se.methods_text(self.last["result"], opts.error, opts.plot_type,
                                   opts.show_points or opts.plot_type == "Scatter dot plot")
        elif self.last["kind"] == "grouped":
            text = anova.grouped_methods_text(
                self.last["result"], opts.error, opts.plot_type,
                opts.show_points or opts.plot_type == "Grouped scatter dot plot", STAR_LEGEND)
        else:
            text = se.xy_methods_text(self.last["fits"], opts.error)
        extra = outliers.methods_sentence(self.current_table().outlier_record)
        if extra:
            text = text.rstrip() + " " + extra
        QtWidgets.QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Methods text copied. Review it before use.", 6000)

    def _volcano_methods(self, vt, opts):
        v = opts.volcano
        which = ("Benjamini-Hochberg adjusted P values (false discovery rate)" if vt["use_fdr"]
                 else "P values")
        if self.last["kind"] == "grouped":
            names = self.last["names"]
            fc = ("the difference in mean log2 values" if v.already_log else
                  "log2 of the ratio of means")
            test = ("Welch's unpaired t test" if v.test == volcano.TESTS[0]
                    else "an unpaired t test assuming equal SDs")
            how = (f"For each row, the fold change of {names[1]} relative to {names[0]} was "
                   f"calculated as {fc}, and P values were from {test}. ")
        else:
            how = "Fold changes (log2) and P values were entered as computed. "
        return (how + f"Rows with |log2 fold change| of at least {vt['fc_cutoff']:g} and {which} "
                f"below {vt['p_cutoff']:g} were called changed ({vt['counts']['Up']} up, "
                f"{vt['counts']['Down']} down). Volcano plots were made in {APP_NAME} {__version__}.")

    # ----- projects
    def project_state(self):
        return {"app": APP_NAME, "version": __version__, "format": 2,
                "active_table": max(0, self.table_list.currentRow()),
                "tables": [t.state() for t in self.tables],
                "export": {"author": self.author_edit.text(), "trim": self.trim_check.isChecked(),
                           "transparent": self.transparent_check.isChecked()},
                "styles": self._styles_in_use(),
                "palettes": self._palettes_in_use(),
                "layout": self.layout_state() if hasattr(self, "layout_picker") else {}}

    @staticmethod
    def _legacy_tables(st):
        """Projects saved before v1.5 had one Column, Grouped, and XY table each."""
        tables = []
        for kind, title in (("column", "Column data"), ("grouped", "Grouped data"), ("xy", "XY data")):
            sec = st.get(kind)
            if sec and sec.get("data", {}).get("cells"):
                tables.append({"kind": kind, "title": title, "data": sec["data"],
                               "options": sec.get("options", {})})
        if not tables:
            sec = st.get("column") or {}
            tables.append({"kind": "column", "title": "Data 1", "data": sec.get("data", {}),
                           "options": sec.get("options", {})})
        return tables

    def apply_state(self, st):
        self._restoring = True
        try:
            self._apply_state(st)
        finally:
            self._restoring = False
            self.commit_timer.stop()

    def _apply_state(self, st):
        # Styles saved inside the project are added if this computer does not have them
        for name, values in (st.get("styles") or {}).items():
            if name not in ls.STYLE_PRESETS and name not in ls.CUSTOM_STYLES and isinstance(values, dict):
                try:
                    ls.register_style(name, values)
                except ValueError:
                    pass
        for name, colors in (st.get("palettes") or {}).items():
            if name not in ls.PALETTES and isinstance(colors, list):
                try:
                    ls.register_palette(name, colors)
                except ValueError:
                    pass
        self._refresh_style_lists()
        tables = st.get("tables") or self._legacy_tables(st)
        if [t.kind for t in self.tables] == [d["kind"] for d in tables]:
            # Same table layout: load in place (fast, keeps scroll positions)
            for i, (t, d) in enumerate(zip(self.tables, tables)):
                t.title = d.get("title") or t.title
                t.frozen = bool(d.get("frozen", False))
                lock_panel(t.panel, t.frozen)
                t.outlier_record = dict(d["outliers"]) if d.get("outliers") else None
                t.panel.load_state(d.get("data") or {})
                t.opts.load_state(d.get("options") or {})
                self.table_list.item(i).setText(self._item_text(t))
        else:
            self.table_list.blockSignals(True)
            for t in self.tables:
                self._remove_table_widgets(t)
            self.tables = []
            self.table_list.clear()
            self.table_list.blockSignals(False)
            for d in tables:
                self.add_table(d["kind"], d.get("title"), d, select=False)
        self._refresh_style_lists()
        self._load_layout_state(st.get("layout"))
        self.author_edit.setText(st.get("export", {}).get("author", DEFAULT_AUTHOR))
        self.trim_check.setChecked(st.get("export", {}).get("trim", True))
        self.transparent_check.setChecked(st.get("export", {}).get("transparent", True))
        active = int(st.get("active_table", 0)) if "tables" in st else 0
        active = min(max(active, 0), len(self.tables) - 1)
        self.table_list.setCurrentRow(active)
        self._table_selected(active)

    def _confirm_discard(self):
        if not self.dirty:
            return True
        answer = QtWidgets.QMessageBox.question(
            self, "Unsaved changes", "Save changes to this project first?",
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Save)
        if answer == QtWidgets.QMessageBox.Save:
            return self.save_project()
        return answer == QtWidgets.QMessageBox.Discard

    def new_project(self, *_):
        if not self._confirm_discard():
            return
        self.apply_state(json.loads(json.dumps(self._defaults)))
        self.project_path = None
        self._reset_history()
        self._set_dirty(False)

    def open_project(self, *_):
        if not self._confirm_discard():
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open project", self.last_dir,
            f"{APP_NAME} project (*{PROJECT_EXT});;All files (*)")
        if not path:
            return
        self.open_project_file(path)

    def open_project_file(self, path):
        try:
            with open(path, encoding="utf-8") as fh:
                st = json.load(fh)
            self.apply_state(st)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QtWidgets.QMessageBox.warning(self, "Could not open project",
                                          f"This file could not be read as a {APP_NAME} project.\n\n{exc}")
            return False
        self.project_path = path
        self.last_dir = os.path.dirname(path)
        self._reset_history()
        self._set_dirty(False)
        return True

    def save_project(self, save_as=False):
        path = self.project_path
        if save_as or not path:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save project", os.path.join(self.last_dir, "analysis" + PROJECT_EXT),
                f"{APP_NAME} project (*{PROJECT_EXT})")
            if not path:
                return False
            if not path.endswith(PROJECT_EXT):
                path += PROJECT_EXT
        return self.save_project_to(path)

    def save_project_to(self, path):
        self._flush_history()
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.project_state(), fh, indent=1)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Save failed", f"The project was not saved.\n\n{exc}")
            return False
        self.project_path = path
        self.last_dir = os.path.dirname(path)
        self._saved_key = self._current[1] if self._current else None
        self._set_dirty(False)
        self.statusBar().showMessage(f"Saved {path}", 5000)
        return True

    def import_prism(self, *_):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Prism table", self.last_dir,
            "Prism files (*.prism *.pzfx);;Prism 10 and 11 (*.prism);;Prism XML (*.pzfx)")
        if not path:
            return
        try:
            tables = prism_import.read_any(path)
        except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
            QtWidgets.QMessageBox.warning(self, "Import failed",
                                          f"The file could not be read as a Prism file.\n\n{exc}")
            return
        if not tables:
            QtWidgets.QMessageBox.information(self, "No data tables", "This file has no data tables.")
            return
        supported = [t for t in tables if t.kind != "unsupported"]
        items = [f"{t.title}  ({t.describe()})" for t in tables]
        all_label = f"All supported tables ({len(supported)})"
        if len(supported) > 1:
            items = [all_label] + items
        item, ok = QtWidgets.QInputDialog.getItem(self, "Import Prism table",
                                                  "Choose a data table. Each one becomes a new "
                                                  "table in this project:", items, 0, False)
        if not ok:
            return
        chosen = supported if item == all_label else [tables[items.index(item) - (len(items) - len(tables))]]
        if len(chosen) == 1 and chosen[0].kind == "unsupported":
            QtWidgets.QMessageBox.information(self, "Table not supported", chosen[0].message)
            return
        self.import_prism_tables(chosen)
        self.last_dir = os.path.dirname(path)

    def import_prism_tables(self, prism_tables):
        """Add each Prism table as a new table in this project. Returns the tables added."""
        added = []
        for pt in prism_tables:
            if pt.kind == "unsupported":
                continue
            added.append(self.add_table(pt.kind, pt.title, {"data": pt.to_state()}))
        excluded = sum(pt.excluded for pt in prism_tables if pt.kind != "unsupported")
        note = (f" {excluded} value(s) excluded in Prism are marked excluded (blue italic)."
                if excluded else "")
        grouped = any(pt.kind == "grouped" for pt in prism_tables)
        hint = " For grouped tables, choose the matching option before reading the ANOVA." if grouped else ""
        self.statusBar().showMessage(f"Imported {len(added)} table(s).{note}{hint}", 12000)
        return added

    def closeEvent(self, event):
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    # ----- menus and toolbar
    def _action(self, menu, text, slot, shortcut=None):
        act = QtWidgets.QAction(text, self)
        if shortcut is not None:
            act.setShortcut(QtGui.QKeySequence(shortcut))
        act.triggered.connect(slot)
        menu.addAction(act)
        return act

    def _build_actions(self):
        m = self.menuBar().addMenu("&File")
        self._action(m, "New project", self.new_project, QtGui.QKeySequence.New)
        self._action(m, "Open project...", self.open_project, QtGui.QKeySequence.Open)
        self._action(m, "Save project", lambda: self.save_project(), QtGui.QKeySequence.Save)
        self._action(m, "Save project as...", lambda: self.save_project(save_as=True),
                     QtGui.QKeySequence.SaveAs)
        m.addSeparator()
        sub = m.addMenu("New table")
        for kind, (label, *_rest) in TABLE_KINDS.items():
            self._action(sub, label, lambda _checked=False, k=kind: self.add_table(k))
        self._action(m, "Import Prism tables (.prism or .pzfx)...", self.import_prism)
        m.addSeparator()
        self._action(m, "Export figure...", self.export_figure, "Ctrl+E")
        self._action(m, "Export results (CSV)...", self.export_results)
        self._action(m, "Export layout sheet...", self.layout_dialog, "Ctrl+Shift+E")
        m.addSeparator()
        self._action(m, "Quit", self.close, QtGui.QKeySequence.Quit)
        e = self.menuBar().addMenu("&Edit")
        self.undo_action = self._action(e, "Undo", self.undo, QtGui.QKeySequence.Undo)
        self.redo_action = self._action(e, "Redo", self.redo, QtGui.QKeySequence.Redo)
        an = self.menuBar().addMenu("&Analysis")
        self._action(an, "Transform data...", self.transform_dialog, "Ctrl+T")
        self._action(an, "Identify outliers...", self.outliers_dialog, "Ctrl+Shift+O")
        an.addSeparator()
        self._action(an, "Apply settings from another table...", self.clone_settings_dialog)
        self._action(an, "Save settings as method...", self.save_method_dialog)
        self._action(an, "Apply method...", self.apply_method_dialog)
        self._action(an, "Delete method...", self.delete_method_dialog)
        an.addSeparator()
        self._action(an, "Duplicate table with empty data", self.duplicate_empty)
        self._action(an, "Freeze or unfreeze table", self.toggle_freeze, "Ctrl+L")
        v = self.menuBar().addMenu("&View")
        self.panel_actions = {}
        for name, (label, key) in PANELS.items():
            act = QtWidgets.QAction(f"Show {label}", self)
            act.setCheckable(True)
            act.setChecked(self.panel_visible(name))
            act.setShortcut(QtGui.QKeySequence(key))
            act.toggled.connect(lambda on, n=name: self.set_panel_visible(n, on))
            v.addAction(act)
            self.panel_actions[name] = act
        v.addSeparator()
        self._action(v, "Next table", lambda: self.select_relative(1), "Ctrl+]")
        self._action(v, "Previous table", lambda: self.select_relative(-1), "Ctrl+[")
        v.addSeparator()
        self._action(v, "Default zoom (150%)", lambda: self.zoom_combo.setCurrentIndex(
            list(ZOOMS).index("150%")), "Ctrl+0")
        self._action(v, "Zoom in", lambda: self.zoom_step(1), QtGui.QKeySequence.ZoomIn)
        self._action(v, "Zoom out", lambda: self.zoom_step(-1), QtGui.QKeySequence.ZoomOut)
        v.addSeparator()
        self.dark_action = QtWidgets.QAction("Dark mode", self)
        self.dark_action.setCheckable(True)
        self.dark_action.setChecked(self.settings.value("dark_mode", False, type=bool))
        self.dark_action.toggled.connect(self._set_dark)
        v.addAction(self.dark_action)
        h = self.menuBar().addMenu("&Help")
        self.guide_action = self._action(h, "User guide", lambda: self.show_help("USER_GUIDE.md", "STELplot user guide"),
                                         QtGui.QKeySequence.HelpContents)
        self.readme_action = self._action(h, "README", lambda: self.show_help("README.md", "STELplot README"))
        h.addSeparator()
        self._action(h, f"About {APP_NAME}", self.about)
        self._action(h, "Statistics notes", self.stats_notes)
        self._update_undo_actions()

        tb = QtWidgets.QToolBar("Main")
        tb.setObjectName("main_toolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(tb)
        logo = QtWidgets.QLabel()
        logo.setObjectName("brand_logo")
        logo.setPixmap(branding.tile_pixmap(28) or brand_pixmap())
        logo.setAccessibleName(f"{APP_NAME} logo")
        brand = QtWidgets.QLabel(APP_NAME)
        brand.setObjectName("brand")
        tb.addWidget(logo)
        tb.addWidget(brand)
        tb.addSeparator()
        new_btn = QtWidgets.QToolButton()
        new_btn.setText("New table  \u25be")
        new_btn.setIcon(toolbar_icon("new_table"))
        new_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        new_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        new_btn.setMenu(self._new_table_menu())
        new_btn.setToolTip("Add a Column, Grouped, or XY table")
        new_btn.setAccessibleName("New table")
        tb.addWidget(new_btn)
        tb.addSeparator()
        mod = "Cmd" if sys.platform == "darwin" else "Ctrl"

        def add(text, slot, icon, tip):
            act = QtWidgets.QAction(toolbar_icon(icon), text, self)
            act.triggered.connect(slot)
            act.setToolTip(tip)
            tb.addAction(act)
            return act

        add("Open", self.open_project, "open", f"Open a project ({mod}+O)")
        add("Save", lambda: self.save_project(), "save", f"Save this project ({mod}+S)")
        add("Import Prism", self.import_prism, "import", "Add tables from a .prism or .pzfx file")
        tb.addSeparator()
        self.undo_action.setIcon(toolbar_icon("undo"))
        self.undo_action.setToolTip(f"Undo ({mod}+Z)")
        self.redo_action.setIcon(toolbar_icon("redo"))
        self.redo_action.setToolTip("Redo")
        tb.addAction(self.undo_action)
        tb.addAction(self.redo_action)
        tb.addSeparator()
        add("Export figure", self.export_figure, "figure", f"SVG, PDF, EPS, PNG, or TIFF ({mod}+E)")
        add("Export results", self.export_results, "results", "Results as CSV")
        self.layout_action = add("Layout", lambda: self.set_layout_mode(not self.layout_mode()), "layout",
                                 "Layout sheet view: several graphs on one sheet, lettered A, B, C. "
                                 "Click again to return to the graph.")
        self.layout_action.setCheckable(True)
        add("Transform", self.transform_dialog, "transform", f"Transform data into a new table ({mod}+T)")
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.guide_action.setIcon(toolbar_icon("guide"))
        self.guide_action.setToolTip("How to use STELplot: plotting, statistics, and good graphing practice")
        self.readme_action.setIcon(toolbar_icon("readme"))
        self.readme_action.setToolTip("Features, installation, and file layout")
        tb.addAction(self.guide_action)
        tb.addAction(self.readme_action)
        tb.addSeparator()
        self.dark_action.setIcon(toolbar_icon("dark"))
        self.dark_action.setToolTip("Switch between light and dark themes")
        tb.addAction(self.dark_action)

    def is_dark(self):
        return self.dark_action.isChecked() if hasattr(self, "dark_action") else False

    def about(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"About {APP_NAME}")
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.setContentsMargins(28, 24, 28, 18)
        lay.setSpacing(10)
        logo = QtWidgets.QLabel()
        logo.setAccessibleName("STEL Plot logo")
        pix = branding.lockup_pixmap(260, dark=self.is_dark()) or branding.tile_pixmap(72)
        if pix is not None:
            logo.setPixmap(pix)
        lay.addWidget(logo, 0, Qt.AlignLeft)
        lay.addSpacing(6)
        lay.addWidget(QtWidgets.QLabel(f"Version {__version__}\n{ORG_NAME}\nAuthor: {DEFAULT_AUTHOR}"))
        lay.addWidget(_hint(f"Statistics: {se.software_line()}\nFigures use the lab style in "
                            "stelplot/lab_style.py."))
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        buttons.accepted.connect(dlg.accept)
        lay.addWidget(buttons)
        dlg.exec_()

    def stats_notes(self):
        QtWidgets.QMessageBox.information(
            self, "Statistics notes",
            "Two-group tests need exactly two columns. Paired tests match values by row.\n\n"
            "One-way ANOVA uses Tukey's test for all pairs or Dunnett's test for each vs. "
            "the first column (SciPy).\n\n"
            "Kruskal-Wallis uses Dunn's test with tie correction and Bonferroni adjustment.\n\n"
            "Repeated-measures tests treat each row (Column tables) or each replicate column "
            "(Grouped tables) as one subject. Subjects with missing values are excluded.\n\n"
            "Two-way ANOVA uses Type III sums of squares. Repeated-measures designs report "
            "the Geisser-Greenhouse epsilon and can apply its correction.\n\n"
            "Curve fits use every replicate value as a separate point.\n\n"
            "Choose the test before looking at the results, and report it in your Methods.")


def main(app=None, splash=None):
    """Start STELplot. stelplot_app.py passes in the application and splash it already showed."""
    if app is None:
        branding.name_mac_menu()
        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            QtWidgets.QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, "AA_UseHighDpiPixmaps"):
            QtWidgets.QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setWindowIcon(branding.app_icon())
    app.setStyle("Fusion")
    app.setPalette(app.style().standardPalette())
    dark = QtCore.QSettings(ORG_NAME, APP_NAME).value("dark_mode", False, type=bool)
    apply_theme(app, dark)
    if splash is not None:
        branding.splash_message(splash, "Opening the window...")
        app.processEvents()
    win = MainWindow()
    win.show()
    if splash is not None:
        splash.finish(win)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
