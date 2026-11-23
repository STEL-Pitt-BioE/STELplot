"""Light and dark themes for the STELplot window, shared with the lab's calcium pipeline.

No Qt here, so the colors can be checked by tests (for example, text contrast).
"""

__author__ = "Daniel Shiwarski"

# Look and feel shared with the lab's calcium transient pipeline GUI
LIGHT = {
    "bg": "#f4f5f7", "panel": "#ffffff", "text": "#1d2129", "subtext": "#5c6672",
    "line": "#d5d9de", "accent": "#1f6feb", "accent_text": "#ffffff", "alt_row": "#fafbfc",
    "preview_bg": "#eef0f3", "hover": "#eef3fe", "indicator": "#7f8893", "scroll": "#c3c8cf",
    "warn": "#7a4f00", "warn_bg": "#fff4d6",
    "toolbar_top": "#1f4677", "toolbar_bottom": "#163460", "toolbar_text": "#ffffff",
    "toolbar_edge": "#0f2647", "toolbar_hover": "rgba(255, 255, 255, 0.15)",
    "toolbar_line": "rgba(255, 255, 255, 0.30)", "toolbar_dim": "rgba(255, 255, 255, 0.45)",
}
DARK = {
    "bg": "#22262b", "panel": "#2b3037", "text": "#e6e8ea", "subtext": "#a6adb5",
    "line": "#3b4149", "accent": "#5b9bff", "accent_text": "#0f1216", "alt_row": "#30353c",
    "preview_bg": "#dcdfe4", "hover": "#333a44", "indicator": "#7d8590", "scroll": "#4a515a",
    "warn": "#ffd479", "warn_bg": "#4a3a12",
    "toolbar_top": "#1b222c", "toolbar_bottom": "#141a22", "toolbar_text": "#e6e8ea",
    "toolbar_edge": "#0c1015", "toolbar_hover": "rgba(255, 255, 255, 0.10)",
    "toolbar_line": "rgba(255, 255, 255, 0.22)", "toolbar_dim": "rgba(230, 232, 234, 0.45)",
}
QSS = """
* {{ outline: none; }}
QPushButton:focus, QToolButton:focus, QComboBox:focus, QListWidget:focus, QTableView:focus,
QPlainTextEdit:focus {{ border: 1px solid {accent}; }}
QCheckBox:focus {{ color: {accent}; }}
QLabel[role="warn"], QFrame#card QLabel[role="warn"] {{ background: {warn_bg}; color: {warn}; border: 1px solid {warn};
                      border-radius: 6px; padding: 6px 9px; }}
QLabel[role="summary"], QFrame#card QLabel[role="summary"] {{ background: {bg}; color: {text}; border: 1px solid {line};
                         border-radius: 6px; padding: 7px 9px; }}
QWidget {{ background: {bg}; color: {text}; font-size: 13px; }}
QFrame#card {{ background: {panel}; border: 1px solid {line}; border-radius: 8px; }}
QFrame#card QWidget {{ background: transparent; }}
QFrame#card QLineEdit, QFrame#card QAbstractSpinBox, QFrame#card QComboBox,
QFrame#card QPlainTextEdit, QFrame#card QAbstractItemView, QFrame#card QMenu,
QFrame#card QPushButton, QFrame#card QToolButton {{ background: {panel}; }}
QFrame#card QScrollArea#preview {{ background: {preview_bg}; border-radius: 6px; }}
QFrame#card QPushButton[cta="1"], QFrame#card QToolButton[cta="1"] {{ background: {accent};
    color: {accent_text}; }}
QLabel[role="heading"] {{ font-size: 15px; font-weight: 600; background: transparent; }}
QLabel[role="hint"] {{ color: {subtext}; background: transparent; }}
QLineEdit#table_title {{ font-size: 18px; font-weight: 600; background: transparent;
                         border: 1px solid transparent; border-radius: 5px; padding: 3px 4px; }}
QLineEdit#table_title:hover {{ border-color: {line}; }}
QLineEdit#table_title:focus {{ border-color: {accent}; background: {panel}; }}
QGroupBox {{ background: {panel}; border: 1px solid {line}; border-radius: 8px;
             margin-top: 14px; padding: 12px 8px 8px 8px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px;
                    color: {subtext}; font-weight: 600; }}
QGroupBox QLabel, QGroupBox QCheckBox {{ background: transparent; font-weight: normal; }}
QPushButton, QToolButton {{ background: {panel}; border: 1px solid {line}; border-radius: 5px;
               padding: 5px 12px; }}
QPushButton:hover, QToolButton:hover {{ border-color: {accent}; }}
QPushButton:disabled {{ color: {subtext}; border-color: {line}; }}
QPushButton[cta="1"], QToolButton[cta="1"] {{ background: {accent}; color: {accent_text};
                        border: none; font-weight: 600; padding: 6px 16px; }}
QToolButton::menu-indicator {{ image: none; width: 0px; }}
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTableWidget, QTableView,
QListWidget, QTextEdit {{
    background: {panel}; border: 1px solid {line}; border-radius: 5px;
    selection-background-color: {accent}; selection-color: {accent_text}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ padding: 3px 6px; min-height: 22px; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {accent}; }}
QComboBox QAbstractItemView {{ background: {panel}; border: 1px solid {line}; }}
QHeaderView::section {{ background: {bg}; color: {subtext}; border: none;
                        border-bottom: 1px solid {line}; border-right: 1px solid {line};
                        padding: 4px 6px; font-weight: 600; }}
QTableWidget, QTableView {{ gridline-color: {line}; alternate-background-color: {alt_row}; }}
QTableView QTableCornerButton::section {{ background: {bg}; border: none;
    border-bottom: 1px solid {line}; border-right: 1px solid {line}; }}
QListWidget#tables {{ padding: 4px; }}
QListWidget#tables::item {{ padding: 4px 6px; border-radius: 6px; margin: 1px 0px; }}
QListWidget#tables::item:hover {{ background: {hover}; }}
QListWidget#tables::item:selected {{ background: {accent}; color: {accent_text}; }}
QToolBar {{ background: {panel}; border-bottom: 1px solid {line}; spacing: 4px; padding: 5px; }}
QToolBar QToolButton {{ padding: 5px 10px; border: 1px solid {line}; border-radius: 5px; }}
QToolBar QToolButton:hover {{ border-color: {accent}; background: {hover}; }}
QToolBar QToolButton:checked {{ border-color: {accent}; color: {accent}; }}
QToolBar::separator {{ background: {line}; width: 1px; margin: 4px 6px; }}
QMenu {{ background: {panel}; border: 1px solid {line}; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {accent}; color: {accent_text}; }}
QToolTip {{ background: {panel}; color: {text}; border: 1px solid {line}; padding: 4px; }}
QStatusBar {{ background: {panel}; border-top: 1px solid {line}; color: {subtext}; }}
QToolBar#main_toolbar {{ background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
        stop: 0 {toolbar_top}, stop: 1 {toolbar_bottom});
    border: none; border-bottom: 1px solid {toolbar_edge}; padding: 6px 10px; spacing: 3px; }}
QToolBar#main_toolbar QWidget {{ background: transparent; color: {toolbar_text}; }}
QToolBar#main_toolbar QToolButton {{ background: transparent; color: {toolbar_text};
    border: 1px solid transparent; border-radius: 6px; padding: 5px 9px; }}
QToolBar#main_toolbar QToolButton:hover {{ background: {toolbar_hover}; border-color: {toolbar_line}; }}
QToolBar#main_toolbar QToolButton:pressed, QToolBar#main_toolbar QToolButton:checked {{
    background: {toolbar_hover}; border-color: {toolbar_text}; }}
QToolBar#main_toolbar QToolButton:disabled {{ color: {toolbar_dim}; }}
QToolBar#main_toolbar QToolButton:focus {{ border-color: {toolbar_text}; }}
QToolBar#main_toolbar::separator {{ background: {toolbar_line}; width: 1px; margin: 7px 8px; }}
QToolBar#main_toolbar QLabel#brand {{ font-size: 16px; font-weight: 700; padding: 0px 8px 0px 2px; }}
QFrame#section {{ background: {panel}; border: 1px solid {line}; border-radius: 8px; }}
QFrame#section QWidget {{ background: transparent; }}
QFrame#section QLineEdit, QFrame#section QAbstractSpinBox, QFrame#section QComboBox,
QFrame#section QAbstractItemView, QFrame#section QPushButton, QFrame#section QToolButton {{
    background: {panel}; }}
QFrame#section QPushButton[cta="1"] {{ background: {accent}; color: {accent_text}; }}
QFrame#section QPushButton#section_header {{ background: transparent; border: 1px solid transparent;
    border-radius: 7px; text-align: left; padding: 8px 10px; font-weight: 600; color: {text}; }}
QFrame#section QPushButton#section_header:hover {{ background: {hover}; }}
QFrame#section QPushButton#section_header:focus {{ border-color: {accent}; }}
QToolButton#edge {{ border: none; background: transparent; color: {subtext}; padding: 0px;
                    font-size: 11px; border-radius: 4px; }}
QToolButton#edge:hover {{ background: {hover}; color: {accent}; }}
QScrollArea {{ border: none; background: {bg}; }}
QCheckBox {{ spacing: 7px; }}
QCheckBox:disabled {{ color: {subtext}; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {indicator};
                       border-radius: 4px; background: {panel}; }}
QCheckBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url("{check}"); }}
QCheckBox::indicator:disabled {{ background: {bg}; border-color: {line}; }}
QCheckBox::indicator:checked:disabled {{ background: {line}; border-color: {line}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{ image: url("{arrow_down}"); width: 10px; height: 10px; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 20px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border;
    width: 18px; border: none; background: transparent; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {hover}; }}
QAbstractSpinBox::up-arrow {{ image: url("{arrow_up}"); width: 9px; height: 9px; }}
QAbstractSpinBox::down-arrow {{ image: url("{arrow_down}"); width: 9px; height: 9px; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {scroll}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:horizontal {{ background: {scroll}; border-radius: 3px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {indicator}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QAbstractScrollArea::corner {{ background: transparent; }}
QSplitter::handle {{ background: {bg}; }}
QSplitter::handle:horizontal {{ width: 6px; }}
QSplitter::handle:vertical {{ height: 6px; }}
"""


# Excluded values are shown in blue italic; each theme has a shade with enough contrast
EXCLUDED = {"light": "#1f5cb8", "dark": "#8cb6ff"}


def luminance(hex_color):
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    """WCAG 2 contrast ratio between two colors (1 to 21)."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)
