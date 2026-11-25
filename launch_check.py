"""First-launch check for STELplot. Run from the STELplot folder:

    python launch_check.py

It checks the installation, runs the test suites, then builds the interface
without showing it and exercises every tab. Results are printed and saved to
launch_check_report.txt. Send that file if anything fails.
"""

__author__ = "Daniel Shiwarski"

import contextlib
import io
import json
import os
import platform
import runpy
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
results = []


def step(name, fn):
    print(f"... {name}", flush=True)
    try:
        detail = fn()
        results.append((name, True, detail or ""))
        print(f"PASS  {name}" + (f": {detail}" if detail else ""), flush=True)
        return True
    except BaseException as exc:  # report everything, including SystemExit from tests
        if isinstance(exc, KeyboardInterrupt):
            raise
        results.append((name, False, traceback.format_exc()))
        print(f"FAIL  {name}\n{traceback.format_exc()}", flush=True)
        return False


def folder_check():
    """STELplot's code must be in a 'stelplot' folder next to this file."""
    needed = ["stelplot/__init__.py", "stelplot/gui.py", "stelplot/stats_engine.py",
              "stelplot/plotting.py", "tests/test_core.py"]
    missing = [p for p in needed if not os.path.exists(os.path.join(HERE, *p.split("/")))]
    protected = "program files" in HERE.lower()
    synced = "onedrive" in HERE.lower()
    if missing:
        if protected:
            how = ("This folder is inside Program Files, which Windows protects: copying or unzipping "
                   "there can skip folders without warning, and building STELplot.exe there usually fails. "
                   "Delete this STELplot folder, unzip STELplot.zip to C:\\STELplot instead, and run "
                   "the launch check from there (see INSTALL_WINDOWS.md, Step 2).")
        else:
            how = ("Unzip STELplot.zip again and keep the whole STELplot folder together, including the "
                   "stelplot and tests folders inside it.")
        raise RuntimeError(f"STELplot's program files are missing from {HERE}: {', '.join(missing)}. {how}")
    notes = []
    if protected:
        notes.append("note: STELplot is inside Program Files; move it to C:\\STELplot before building "
                     "STELplot.exe, because the build usually cannot write there")
    if synced:
        notes.append("note: STELplot is in a OneDrive folder; syncing can lock files during a build, so a "
                     "folder such as C:\\STELplot is safer")
    return HERE + ("; " + "; ".join(notes) if notes else "")


def environment():
    import numpy, scipy, matplotlib
    from stelplot import __version__
    return (f"STELplot {__version__}; Python {platform.python_version()} on {platform.system()} "
            f"{platform.release()} ({platform.machine()}); numpy {numpy.__version__}, "
            f"scipy {scipy.__version__}, matplotlib {matplotlib.__version__}")


def pyqt():
    from PyQt5 import QtCore
    return f"PyQt5 {QtCore.PYQT_VERSION_STR}, Qt {QtCore.QT_VERSION_STR}"


def fonts():
    from stelplot.lab_style import available_font, star_font
    font, star = available_font(), star_font()
    note = "" if font == "Arial" else " (Arial not found; exports will use this font instead)"
    return f"text font {font}{note}; significance star font {star}"


def run_suite(name):
    def fn():
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            runpy.run_module(f"tests.{name}", run_name="__main__")
        passed = buf.getvalue().count("PASS")
        return f"{passed} checks passed"
    return fn


def interface():
    os.environ.setdefault("QT_SCALE_FACTOR", "1")
    os.environ["STELPLOT_CONFIG_DIR"] = tempfile.mkdtemp(prefix="stelplot_styles_")
    import numpy as np
    from PyQt5 import QtCore, QtWidgets
    from stelplot import gui, prism_import
    from stelplot import lab_style as ls
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    for dark in (True, False):
        assets = gui.apply_theme(app, dark)
        missing = [k for k, path in assets.items() if not os.path.exists(path)]
        if missing:
            raise RuntimeError(f"Theme images were not created: {missing}")
    win = gui.MainWindow()
    out = tempfile.mkdtemp(prefix="stelplot_check_")
    done = []

    # Lay the window out without putting it on screen, and confirm the options panel fits
    win.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    win.show()
    for size in ((1280, 800), (1024, 700)):
        win.resize(*size)
        win.split.setSizes([int(size[0] * 0.3), int(size[0] * 0.46), int(size[0] * 0.24)])
        app.processEvents()
        inner = win.right_scroll.widget().width()
        view = win.right_scroll.viewport().width()
        if inner > view + 1:
            content = win.right_scroll.widget()
            widest = []
            for w in content.findChildren(QtWidgets.QWidget):
                if not w.isVisibleTo(content):
                    continue
                need = w.mapTo(content, QtCore.QPoint(0, 0)).x() + w.minimumSizeHint().width()
                text = getattr(w, "text", lambda: "")() if hasattr(w, "text") else ""
                widest.append((need, f"{type(w).__name__} {text!r}"[:60]))
            widest = ", ".join(f"{name} ({need} px)" for need, name in sorted(widest, reverse=True)[:4])
            raise RuntimeError(f"Options panel is wider than its area at {size[0]}x{size[1]}: "
                               f"{inner} px content in a {view} px panel. Widest: {widest}")
    done.append("options panel fits at 1280x800 and 1024x700")

    def settle():
        app.processEvents()
        win.refresh()
        win.canvas.draw()
        text = win.results.toPlainText()
        if text.startswith("The graph could not be drawn"):
            raise RuntimeError(text)
        return text

    def show(table):
        win.table_list.setCurrentRow(win.tables.index(table))
        app.processEvents()

    # A new project starts with one Column table
    col = win.current_table()
    if col.kind != "column" or win.table_list.count() != 1:
        raise RuntimeError("A new project should open with one Column table")

    # Table defaults and Enter navigation
    grid = col.panel.grid
    if grid.rowCount() < 1000 or grid.columnCount() != 10:
        raise RuntimeError(f"Column table has {grid.rowCount()} rows and {grid.columnCount()} "
                           "columns; expected 1000 and 10")
    try:
        from PyQt5.QtTest import QTest
    except ImportError:
        done.append("table defaults (Enter key not tested: PyQt5.QtTest unavailable)")
    else:
        grid.setCurrentCell(0, 0)
        QTest.keyClick(grid, QtCore.Qt.Key_Return)
        if grid.currentRow() != 1:
            raise RuntimeError(f"Enter moved to row {grid.currentRow() + 1}, expected row 2")
        QTest.keyClick(grid, QtCore.Qt.Key_Return, QtCore.Qt.ShiftModifier)
        if grid.currentRow() != 0:
            raise RuntimeError("Shift+Enter did not move back up")
        done.append("1000 rows, 10 columns, Enter moves down")

    # Undo and redo across a data change and a settings change
    col.panel.load_example()
    win._flush_history()
    col.opts.set("plot_type", "Box plot")
    col.opts.changed.emit()
    win._flush_history()
    win.undo()
    col = win.current_table()
    if col.opts.get("plot_type") != "Scatter dot plot":
        raise RuntimeError("Undo did not restore the previous plot type")
    win.undo()
    col = win.current_table()
    if col.panel.get_groups():
        raise RuntimeError("Undo did not remove the example data")
    if win.dirty:
        raise RuntimeError("Undoing back to the opening state should clear the unsaved marker")
    win.redo()
    win.redo()
    col = win.current_table()
    if len(col.panel.get_groups()) != 3 or col.opts.get("plot_type") != "Box plot":
        raise RuntimeError("Redo did not bring back the example data and plot type")
    col.opts.set("plot_type", "Scatter dot plot")
    col.opts.changed.emit()
    win._flush_history()
    done.append("undo and redo")

    # Several tables in one project: add, name, delete, undo the delete
    win.title_edit.setText("Migration")
    win._title_edited("Migration")
    if not win.table_list.item(0).text().startswith("Migration"):
        raise RuntimeError("Renaming did not update the tables list")
    grp = win.add_table("grouped")
    xy = win.add_table("xy")
    spare = win.add_table("column")
    if [t.kind for t in win.tables] != ["column", "grouped", "xy", "column"]:
        raise RuntimeError(f"Unexpected tables: {[t.kind for t in win.tables]}")
    win._flush_history()
    show(spare)
    win.delete_table()
    win._flush_history()
    if len(win.tables) != 3:
        raise RuntimeError("Delete did not remove the empty table")
    win.undo()
    if len(win.tables) != 4:
        raise RuntimeError("Undo did not bring back the deleted table")
    win.redo()
    col, grp, xy = win.tables
    if win.project_state()["tables"][0]["title"] != "Migration":
        raise RuntimeError("Table name was not saved in the project")
    if win.table_list.item(0).icon().isNull():
        raise RuntimeError("Tables list is missing the table-type badges")
    done.append("multiple tables, names, delete and undo")

    # Excluding a value by right-click (menu action tested directly)
    show(col)
    col.panel.load_example()
    before = int(np.isfinite(col.panel.get_groups()[0][1]).sum())
    col.panel.grid.setCurrentCell(0, 0)
    if col.panel.grid.set_selection_excluded(True) != 1:
        raise RuntimeError("Exclude did not change the selected value")
    after = int(np.isfinite(col.panel.get_groups()[0][1]).sum())
    if after != before - 1 or col.panel.state()["excluded"] != [[0, 0]]:
        raise RuntimeError("Excluded value was still used, or not saved")
    if "excluded value" not in settle():
        raise RuntimeError("Results did not mention the excluded value")
    win._flush_history()
    win.undo()
    if win.tables[0].panel.grid.excluded_cells():
        raise RuntimeError("Undo did not include the value again")
    win.redo()
    col, grp, xy = win.tables
    if col.panel.grid.excluded_cells() != [[0, 0]]:
        raise RuntimeError("Redo did not exclude the value again")
    done.append("exclude values")

    # Marker shapes and a custom style made with the style editor
    for shape in gui.pl.MARKER_CHOICES:
        col.opts.set("marker", shape)
        col.opts.set("marker_fill", "Open")
        settle()
    dlg = gui.StyleEditor(win, "Lab template", ls.preset("Lab template"), ls.PALETTES["Journal"])
    dlg.name_edit.setText("Launch check style")
    dlg.widgets["data_line"].setValue(1.5)
    dlg.widgets["tick_dir"].setCurrentIndex(1)
    dlg.n_colors.setValue(3)
    values = dlg.values()
    if values["data_line"] != 1.5 or values["tick_dir"] != "out" or len(values["palette"]) != 3:
        raise RuntimeError(f"Style editor returned unexpected values: {values}")
    if "Colorblind check" not in dlg.cvd_label.text():
        raise RuntimeError("Style editor did not show the colorblind check")
    ls.register_style("Launch check style", values)
    win._save_style_library()
    win._refresh_style_lists()
    for form in win._forms():
        if form.controls["style"].findText("Launch check style") < 0:
            raise RuntimeError("New style is missing from a table's Style menu")
    col.opts.set("style", "Launch check style")
    col.opts.apply_preset()
    settle()
    if "Launch check style" not in win.project_state()["styles"]:
        raise RuntimeError("Project does not carry the custom style")
    win.save_figure_to(os.path.join(out, "custom_style.svg"))
    dlg.deleteLater()
    col.opts.set("style", "Lab template")
    col.opts.apply_preset()
    ls.remove_style("Launch check style")
    win._refresh_style_lists()
    col.opts.set("marker", "Circle")
    col.opts.set("marker_fill", "Filled")
    done.append("marker shapes and style editor")

    # Column table: one-way ANOVA, every plot type, export
    col.opts.set("test", "One-way ANOVA")
    for plot_type in gui.pl.PLOT_TYPES:
        col.opts.set("plot_type", plot_type)
        text = settle()
    if "ANOVA summary" not in text:
        raise RuntimeError("Column results did not show the ANOVA summary:\n" + text[:1500])
    for ext in (".svg", ".pdf", ".png"):
        win.save_figure_to(os.path.join(out, "column" + ext))
    from PIL import Image
    if Image.open(os.path.join(out, "column.png")).convert("RGBA").getpixel((0, 0))[3] != 0:
        raise RuntimeError("PNG export kept a background with Transparent background on")
    if win.fig.patch.get_facecolor()[:3] == (1.0, 1.0, 1.0):
        raise RuntimeError("Preview figure still has a white background")
    win.save_results_to(os.path.join(out, "column_results.csv"))
    with open(os.path.join(out, "column_results.csv"), encoding="utf-8") as fh:
        if "Migration" not in fh.read():
            raise RuntimeError("Exported results do not name the table")
    done.append("column table")

    # Choosing and ordering the columns on the graph (and in the statistics)
    picker = col.opts.picker
    keys = [k for k, *_ in picker._items]
    heads = [col.panel.grid.header_text(k) for k in keys]
    if len(keys) != 3:
        raise RuntimeError(f"Data on graph should list the 3 example columns, found {len(keys)}")
    picker.set_checked(keys[1], False)
    settle()
    if [n for n, _ in win.last["groups"]] != [heads[0], heads[2]]:
        raise RuntimeError("Unchecking a column did not remove it from the graph")
    picker.move_key(keys[2], 0)
    settle()
    if [n for n, _ in win.last["groups"]] != [heads[2], heads[0]]:
        raise RuntimeError("Reordering did not change the graph order")
    if col.opts.state()["_series"] != {"order": [keys[2], keys[0], keys[1]], "hidden": [keys[1]]}:
        raise RuntimeError(f"Column choices were not saved: {col.opts.state()['_series']}")
    win._flush_history()
    win.undo()
    col = win.tables[0]
    if col.opts.picker.hidden or col.opts.picker.order != keys:
        raise RuntimeError("Undo did not restore the columns on the graph")
    win.redo()
    col = win.tables[0]
    for k in keys:
        col.opts.picker.set_checked(k, False)
    if "unchecked" not in settle() or win.last is not None:
        raise RuntimeError("Unchecking every column should leave an empty graph with a note")
    col.opts.picker.show_all()
    col.opts.picker.reset_order()
    settle()
    if [n for n, _ in win.last["groups"]] != heads:
        raise RuntimeError("All and Reset order did not restore every column in table order")
    done.append("choose and reorder columns")

    # Style preset switch
    col.opts.set("style", "Prism default")
    col.opts.apply_preset()
    settle()
    col.opts.set("style", "Lab template")
    col.opts.apply_preset()
    settle()
    done.append("style presets")

    # Grouped table: repeated-measures two-way ANOVA with comparisons
    show(grp)
    grp.panel.load_example()
    grp.opts.set("design", "Matched values stacked in a subcolumn")
    grp.opts.set("comparisons", "Compare columns within each row")
    for plot_type in gui.pl.GROUPED_PLOT_TYPES:
        grp.opts.set("plot_type", plot_type)
        text = settle()
    if "Two-way RM ANOVA" not in text:
        raise RuntimeError("Grouped results did not show the RM ANOVA table:\n" + text[:1500])
    win.save_figure_to(os.path.join(out, "grouped.svg"))
    win.save_results_to(os.path.join(out, "grouped_results.csv"))
    first = grp.opts.picker.order[0]
    grp.opts.picker.set_checked(first, False)
    if "at least two" not in settle():
        raise RuntimeError("Grouped table with one data set should explain that ANOVA needs two")
    grp.opts.picker.set_checked(first, True)
    settle()
    done.append("grouped table")

    # XY table: dose-response fit
    show(xy)
    xy.panel.load_example()
    xy.opts.set("fit_model", "Dose-response, 4PL (variable slope)")
    xy.opts.set("log_x", True)
    text = settle()
    if "LogEC50" not in text:
        raise RuntimeError("XY results did not show the 4PL fit:\n" + text[:1500])
    win.save_figure_to(os.path.join(out, "xy.svg"))
    done.append("XY table")

    # Prism import adds new tables; Prism-excluded values stay excluded
    fixtures = os.path.join("tests", "fixtures")
    tables = {t.title: t for t in prism_import.read_pzfx(os.path.join(fixtures, "PrismTemplates.pzfx"))}
    added = win.import_prism_tables([tables["Column Data Grouped: RM Two-way ANOVA (rows)"]])
    added[0].opts.set("design", "Matched values spread across a row")
    settle()
    sample = prism_import.read_pzfx(os.path.join(fixtures, "sample.pzfx"))
    added += win.import_prism_tables(sample[:1])
    if len(win.tables) != 5 or not added[1].panel.grid.excluded_cells():
        raise RuntimeError("Prism import did not add tables, or lost its excluded values")
    done.append("Prism import into new tables")

    # Project save and reopen, then a project saved by an earlier version
    path = os.path.join(out, "check.stelplot")
    titles = [t.title for t in win.tables]
    if not win.save_project_to(path) or not win.open_project_file(path):
        raise RuntimeError("Project save or reopen failed")
    if [t.title for t in win.tables] != titles or win.tables[0].panel.grid.excluded_cells() != [[0, 0]]:
        raise RuntimeError("Reopened project lost tables, names, or excluded values")
    settle()
    legacy = {"column": win.tables[0].state(), "grouped": win.tables[1].state(),
              "xy": win.tables[2].state(), "active_tab": 1}
    win.apply_state(legacy)
    if [t.kind for t in win.tables] != ["column", "grouped", "xy"]:
        raise RuntimeError("A project from an earlier version did not open as three tables")
    settle()
    done.append("project save and reopen, older projects")

    # Plain-language results, Interpret, confidence levels, dashed error bars, EPS
    import xml.etree.ElementTree as ET
    from stelplot import anova
    col, grp, xy = win.tables
    show(col)
    col.opts.set("test", "One-way ANOVA")
    settle()
    if not win.summary_label.text() or "Assumptions" not in win.interpret_text():
        raise RuntimeError("No plain-language summary or Interpret text for one-way ANOVA")
    keys = col.opts.picker.selected()
    col.opts.picker.set_checked(keys[2], False)
    col.opts.set("test", "Unpaired t-test")
    col.opts.set("conf", 99.5)
    if "P < 0.005" not in settle():
        raise RuntimeError("A 99.5% confidence level did not set the threshold to P < 0.005")
    col.opts.set("plot_type", "Bar with points")
    col.opts.set("error_style", "Dashed")
    settle()
    win.save_figure_to(os.path.join(out, "column.eps"))
    col.opts.picker.show_all()
    col.opts.set("conf", 95)
    col.opts.set("error_style", "Solid")
    done.append("plain-language results, Interpret, confidence levels, dashed error bars, EPS")

    # Cell-by-cell comparisons with the main-effects model
    show(grp)
    grp.opts.set("design", "No matching")
    grp.opts.set("model", anova.MAIN_EFFECTS)
    grp.opts.set("comparisons", anova.CELLS)
    if "regardless of rows and columns" not in settle():
        raise RuntimeError("Cell-by-cell comparisons did not run")
    done.append("cell-by-cell comparisons, main effects only")

    # Freezing a table
    show(col)
    win.set_frozen(col, True)
    before = col.panel.state()["cells"]
    col.panel.grid.setCurrentCell(0, 0)
    col.panel.grid.clear_selected()
    if col.panel.state()["cells"] != before or col.panel.grid.set_selection_excluded(True) != 0:
        raise RuntimeError("A frozen table was still edited")
    if not win.project_state()["tables"][0]["frozen"]:
        raise RuntimeError("Frozen state was not saved")
    win.set_frozen(col, False)
    done.append("freeze and unfreeze")

    # Transform, saved methods, copied settings, duplicate with empty data
    n = len(win.tables)
    new, _skipped = win.transform_table(col, "Y = log10(Y)")
    if len(win.tables) != n + 1 or new.kind != "column" or "log10" not in new.title or not new.has_data():
        raise RuntimeError("Transform did not create a new table")
    win.save_method(col, "Launch check method")
    win.apply_method(new, "Launch check method")
    win.clone_settings(col, new)
    show(col)
    empty = win.duplicate_empty()
    if empty.has_data() or empty.kind != "column":
        raise RuntimeError("Duplicate with empty data copied the data")
    settle()
    done.append("transform, methods, copied settings, duplicate with empty data")

    # Layout sheets, and moving between tables from the keyboard
    for ext in (".svg", ".png", ".tif"):
        win.export_layout([col, grp, xy], os.path.join(out, "layout" + ext), ncols=2)
    root = ET.parse(os.path.join(out, "layout.svg")).getroot()
    panels = [g for g in root if g.get("id", "").startswith("panel_")]
    if len(panels) != 3:
        raise RuntimeError(f"Layout sheet has {len(panels)} panels, expected 3")
    win.select_relative(1)
    win.select_relative(-1)
    settle()
    done.append("layout sheets, next and previous table")

    # Log Y axes, frequency distribution, heat map, and a custom transform
    show(col)
    for plot_type in ("Violin plot", "Bar with points"):
        col.opts.set("plot_type", plot_type)
        col.opts.set("log_y", True)
        settle()
    col.opts.set("log_y", False)
    col.opts.set("plot_type", gui.pl.HISTOGRAM)
    col.opts.set("hist_bin_width", "2")
    if "Frequency distribution" not in settle():
        raise RuntimeError("Histogram results did not include the frequency table")
    col.opts.set("hist_bin_width", "")
    col.opts.set("plot_type", "Scatter dot plot")
    show(grp)
    grp.opts.set("log_y", True)
    settle()
    grp.opts.set("log_y", False)
    grp.opts.set("plot_type", gui.pl.HEAT_MAP)
    grp.opts.set("heat_values", True)
    settle()
    win.save_figure_to(os.path.join(out, "heat_map.svg"))
    grp.opts.set("plot_type", "Grouped bars")
    show(xy)
    xy.opts.set("log_y", True)
    settle()
    xy.opts.set("log_y", False)
    new, _skipped = win.transform_table(col, gui.transforms.CUSTOM_Y, None, "log10(Y) * 100")
    if not new.has_data() or "Y = log10(Y) * 100" not in new.title:
        raise RuntimeError("Custom transform did not create a table")
    settle()
    done.append("log Y axes, frequency distribution, heat map, custom transform")

    # Identify outliers: flag with ROUT, exclude, and record it in the results and Methods text
    a = [10.1, 9.8, 10.3, 9.9, 10.0, 10.2, 9.7, 10.4, 9.6, 10.1, 9.9, 10.0, 10.2, 9.8, 10.3, 9.9,
         10.1, 10.0, 9.7, 30.0]
    cells = [[str(v), str(round(v + 1, 1)) if i < 19 else ""] for i, v in enumerate(a)]
    ot = win.add_table("column", "Outlier check", {"data": {"headers": ["A", "B"], "cells": cells}})
    win.identify_outliers(ot, gui.outliers.ROUT, 1.0, False)
    if ot.panel.grid.flagged_cells() != [[19, 0]]:
        raise RuntimeError(f"ROUT flagged {ot.panel.grid.flagged_cells()}, expected only row 20 of A")
    settle()
    if "flagged (amber)" not in win.flags_label.text():
        raise RuntimeError("The results did not mention the flagged value")
    if win.exclude_flagged(ot) != 1 or [19, 0] not in ot.panel.grid.excluded_cells():
        raise RuntimeError("Excluding the flagged value did not work")
    settle()
    if "Outliers: ROUT" not in win.summary_label.text():
        raise RuntimeError("The summary did not record the outlier test")
    if "ROUT" not in gui.outliers.methods_sentence(ot.outlier_record):
        raise RuntimeError("The Methods text did not record the outlier test")
    if win.project_state()["tables"][-1]["outliers"]["excluded"] != 1:
        raise RuntimeError("The project did not save the outlier record")
    done.append("identify outliers (ROUT), flag, exclude, and record")

    # Layout view with a live preview, back to the graph, and Export always in view
    win.set_layout_mode(True)
    app.processEvents()
    if win.center_stack.currentIndex() != 1 or not win.layout_action.isChecked():
        raise RuntimeError("Layout did not switch to the layout view")
    pix = win._render_layout_preview()
    if pix is None or pix.isNull():
        raise RuntimeError("The layout preview did not draw")
    win.set_layout_mode(False)
    if win.center_stack.currentIndex() != 0 or win.layout_action.isChecked():
        raise RuntimeError("Back to graph did not return to the graph")
    if win.right_scroll.isAncestorOf(win.export_section) or win.export_section.isHidden():
        raise RuntimeError("The Export section is not pinned below the settings")
    done.append("layout view with preview and back to graph, Export always in view")

    # Settings sections fold open and closed, in step across tables (your choices are restored)
    before = {sec: sec.expanded for sec in win.all_sections()}
    win.expand_all_sections(False)
    if any(sec.body.isVisibleTo(sec) for sec in win.all_sections()):
        raise RuntimeError("Collapse all left a settings section open")
    win.expand_all_sections(True)
    first = win.tables[0].opts.findChildren(gui.Section)[0]
    first.set_expanded(False)
    if any(s.expanded for s in win.all_sections() if s.title == first.title):
        raise RuntimeError("Collapsing a section did not collapse it for every table")
    for sec, on in before.items():
        sec.set_expanded(on, emit=False)
    done.append("collapsible settings sections")

    # The data panel narrows to two columns
    w2 = win.two_column_width()
    if win.left_split.minimumWidth() != w2:
        raise RuntimeError(f"Data panel minimum is {win.left_split.minimumWidth()} px, expected {w2}")
    if win.left_split.minimumSizeHint().width() > w2 + 1:
        raise RuntimeError(f"Data panel contents need {win.left_split.minimumSizeHint().width()} px; "
                           f"two columns are {w2} px")
    done.append(f"data panel narrows to two columns ({w2} px)")

    # Toolbar icons, README, and user guide
    toolbar = win.findChild(QtWidgets.QToolBar, "main_toolbar")
    plain = [a.text() for a in toolbar.actions() if a.text() and not a.isSeparator() and a.icon().isNull()]
    if plain:
        raise RuntimeError(f"Toolbar buttons without icons: {plain}")
    for doc in ("USER_GUIDE.md", "README.md"):
        hw = win.show_help(doc, doc)
        app.processEvents()
        if hw.toc.count() < 10 or not hw.view.toPlainText().strip():
            raise RuntimeError(f"{doc} did not open with its topics")
        hw.search.setText("ANOVA")
        app.processEvents()
        if all(hw.toc.item(i).isHidden() for i in range(hw.toc.count())):
            raise RuntimeError(f"Searching {doc} for ANOVA found nothing")
        hw.close()
    from stelplot import branding
    logo = win.findChild(QtWidgets.QLabel, "brand_logo")
    if win.windowIcon().isNull() or branding.tile_pixmap(28) is None:
        raise RuntimeError("The STELplot app icon was not found in stelplot/icons")
    if logo is None or logo.pixmap() is None or logo.pixmap().isNull():
        raise RuntimeError("The toolbar logo is missing")
    splash = branding.splash_screen()
    branding.splash_message(splash, "Launch check")
    if not isinstance(splash, branding.Splash) or splash.pixmap().isNull() or splash.message() != "Launch check":
        raise RuntimeError("The splash screen did not build")
    splash.close()
    lockup = "lockup" if branding.lockup_pixmap(200) is not None else "app tile (PyQt5.QtSvg unavailable)"
    done.append(f"toolbar icons, app icon, splash screen, {lockup} in About and help, README, and user guide")

    # Collapsible panels (each is toggled twice, so your own choice is restored)
    for name in gui.PANELS:
        before = win.panel_visible(name)
        win.toggle_panel(name)
        app.processEvents()
        if win.panel_visible(name) == before:
            raise RuntimeError(f"The {name} panel did not toggle")
        settle()
        win.toggle_panel(name)
        app.processEvents()
        if win.panel_visible(name) != before:
            raise RuntimeError(f"The {name} panel did not come back")
    done.append("collapsible panels")

    # Zoom to 500%
    zoom_before = win.zoom_combo.currentIndex()
    win.zoom_combo.setCurrentIndex(win.zoom_combo.findText("500%"))
    settle()
    w_in, _h = win.fig.get_size_inches()
    if abs(win.canvas.width() - round(w_in * 500)) > 2:
        raise RuntimeError(f"500% zoom drew {win.canvas.width()} px for a {w_in:.2f} in figure")
    win.zoom_combo.setCurrentIndex(zoom_before)

    # Dark mode on and off (restores your setting), methods text, and zoom levels
    original = win.dark_action.isChecked()
    win.dark_action.setChecked(not original)
    app.processEvents()
    win.dark_action.setChecked(original)
    win.copy_methods()
    zoom_saved = win.zoom_combo.currentIndex()   # STELplot remembers the zoom, so put it back
    for i in range(win.zoom_combo.count()):
        win.zoom_combo.setCurrentIndex(i)
        app.processEvents()
    win.zoom_combo.setCurrentIndex(zoom_saved)
    app.processEvents()
    done.append("dark mode, methods text, and preview zoom")

    # v1.9 graphs: volcano, grouped box, arrangements, orientation, right axis, circles, 3D, colors
    from stelplot import plotting as pl
    from stelplot import plot3d as p3

    def drawn(label):
        win.refresh()
        app.processEvents()
        text = win.results.toPlainText()
        if "could not be drawn" in text:
            raise RuntimeError(f"{label}: {text}")
        return text

    g = win.add_table("grouped", "Proteomics")
    g.panel.load_volcano_example()
    g.opts.set("plot_type", pl.VOLCANO)
    g.opts.update_enabled()
    if "Volcano plot:" not in drawn("grouped volcano") or win.last.get("volcano") is None:
        raise RuntimeError("The grouped volcano plot did not list its results")
    if g.opts.sections["Volcano plot"].isHidden():
        raise RuntimeError("Volcano settings are hidden for a volcano plot")
    if not (win.interpret_text().startswith("Volcano plot") and "higher in WT" not in
            win.summary_label.text() and "higher in KO" in win.summary_label.text()):
        raise RuntimeError("Interpret and the summary do not describe the volcano plot")
    win.save_results_to(os.path.join(out, "volcano.csv"))
    win.save_figure_to(os.path.join(out, "volcano.svg"))
    g2 = win.add_table("grouped", "Arrangements")
    g2.panel.load_example()
    for pt in (pl.GROUPED_BOX, pl.AREA, pl.BARS_3D):
        g2.opts.set("plot_type", pt)
        drawn(pt)
    g2.opts.set("plot_type", "Grouped bars")
    for arrangement in pl.ARRANGEMENTS:
        g2.opts.set("arrangement", arrangement)
        drawn(arrangement)
    g2.opts.set("arrangement", "Interleaved")
    g2.opts.set("orientation", "Horizontal")
    drawn("horizontal bars")
    g2.opts.set("orientation", "Vertical")
    g2.opts.set("plot_type", "Line plot (mean ± error)")
    drawn("line plot")
    g2.opts.set("right_series", ["Treated"])
    drawn("right axis")
    if win.last["opts"].right_series != ("Treated",) or len(win.fig.axes) != 2:
        raise RuntimeError("The right Y axis was not drawn")
    g2.opts.set("plot_type", pl.HEAT_MAP)
    g2.opts.set("heat_shape", "Circles")
    drawn("circle heat map")
    if "Table: Proteomics" not in [g2.opts.controls["circle_color"].itemText(i)
                                   for i in range(g2.opts.controls["circle_color"].count())]:
        raise RuntimeError("Other grouped tables are not offered as circle colors")
    xy = win.add_table("xy", "Volcano XY")
    xy.panel.load_volcano_example()
    xy.opts.set("plot_type", pl.VOLCANO)
    if "PROT" not in drawn("XY volcano"):
        raise RuntimeError("Row titles did not name the XY volcano points")
    xy.opts.set("plot_type", pl.AREA)
    drawn("XY area")
    d3 = win.add_table("xyz", "3D")
    d3.panel.load_example()
    for kind in p3.KINDS_3D:
        d3.opts.set("plot_type", kind)
        drawn(kind)
    d3.opts.set("color_by", p3.COLOR_BY[1])
    drawn("3D color column")
    win.save_figure_to(os.path.join(out, "surface.pdf"))
    col = win.tables[0]
    win.table_list.setCurrentRow(0)
    col.panel.load_example()
    col.opts.set("orientation", "Horizontal")
    drawn("horizontal column graph")
    ls.register_palette("Check scheme", ["#7A1F1F", "#E07B39", "#5B8E7D"])
    win._refresh_style_lists()
    col.opts.set("palette", "Check scheme")
    drawn("custom colors")
    path = os.path.join(out, "v19.stelplot")
    win.save_project_to(path)
    ls.remove_palette("Check scheme")
    win.open_project_file(path)
    if win.tables[0].opts.get("palette") != "Check scheme" or "Check scheme" not in ls.PALETTES:
        raise RuntimeError("A custom color scheme did not come back with the project")
    if [t.kind for t in win.tables][-1] != "xyz" or not win.tables[-2].panel.row_titles:
        raise RuntimeError("3D tables or XY row titles were not saved in the project")
    done.append("volcano plots (grouped and XY) with Interpret, grouped box plots, area plots, interleaved, "
                "separated, stacked, and superimposed bars, horizontal graphs, right Y axis, circle "
                "heat map, 3D tables (scatter, line, surface, wireframe, bars), custom color schemes")

    win.dirty = False
    win.close()
    return f"{', '.join(done)}; test files written to {out}"


if __name__ == "__main__":
    print("STELplot launch check\n")
    has_qt = True
    files_ok = step("STELplot files", folder_check)
    if files_ok:
        step("Python packages", environment)
        has_qt = step("PyQt5", pyqt)
        step("Fonts", fonts)
        for suite in ("test_core", "test_anova", "test_prism", "test_style", "test_palette",
                      "test_prism_bundle", "test_custom_style", "test_features",
                      "test_graph_types"):
            step(f"Test suite {suite}", run_suite(suite))
        if has_qt:
            step("Interface (built off screen, every table type exercised)", interface)
    failed = [r for r in results if not r[1]]
    lines = [f"{'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if ok and detail else "")
             for name, ok, detail in results]
    for name, ok, detail in failed:
        lines += ["", f"----- {name} -----", detail]
    with open("launch_check_report.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n" + "=" * 60)
    if not files_ok:
        print("STELplot's program files are missing, so nothing else was checked.\n" + results[0][2].splitlines()[-1])
    elif failed:
        print(f"{len(failed)} step(s) failed. Please send launch_check_report.txt.")
        if not has_qt:
            print("PyQt5 is missing: run 'conda activate stelplot' first, or "
                  "'pip install PyQt5' in this environment.")
    else:
        print("Everything passed. Start STELplot with:  python stelplot_app.py")
    print("Report saved to launch_check_report.txt")
