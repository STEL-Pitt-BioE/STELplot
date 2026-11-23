"""STELplot icons and the startup splash screen.

Uses only PyQt5, so the splash can appear before the plotting and statistics libraries load.
Icon files are in stelplot/icons: the rounded app tile (macos/) and the transparent mark
(windows_linux_web/), plus STEL_Plot.icns and STEL_Plot.ico for built apps.
"""

__author__ = "Daniel Shiwarski"

import sys

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from . import APP_NAME, ORG_NAME, __version__
from .help_docs import icon_path

TILE_SIZES = (16, 32, 64, 128, 256, 512, 1024)
MARK_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
NAVY = "#163460"


def tile_file(size):
    return icon_path(f"macos/STEL_Plot_icon_{size}.png")


def mark_file(size):
    return icon_path(f"windows_linux_web/STEL_Plot_mark_{size}.png")


def app_icon():
    """Dock, taskbar, and window icon: the rounded tile on macOS, the mark elsewhere."""
    icon = QtGui.QIcon()
    files = ([tile_file(s) for s in TILE_SIZES] if sys.platform == "darwin"
             else [mark_file(s) for s in MARK_SIZES])
    for path in files:
        if path:
            icon.addFile(path)
    return icon


def tile_pixmap(points, ratio=2.0):
    """The app tile at `points` (logical size), sharp on Retina screens. None if not found."""
    px = int(round(points * ratio))
    size = next((s for s in TILE_SIZES if s >= px), TILE_SIZES[-1])
    path = tile_file(size)
    if not path:
        return None
    pix = QtGui.QPixmap(path).scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pix.setDevicePixelRatio(ratio)
    return pix


SPLASH_FILE = "splash/STEL_Plot_splash_1600x900.png"
LOCKUP_FILE = "STEL_Plot_lockup_horizontal.svg"
MESSAGE_GRAY = "#5c6672"
# Where the splash artwork sits, as fractions of its width and height (from the 1600 x 900 file):
# content runs from x = 126 to 1472 and ends at y = 772, leaving a white strip at the bottom.
SPLASH_LEFT, SPLASH_RIGHT, SPLASH_TEXT_Y = 126 / 1600, 1472 / 1600, 836 / 900


class Splash(QtWidgets.QSplashScreen):
    """Splash screen that writes its loading message into the design's bottom margin."""

    def __init__(self, pixmap, message_rect):
        super().__init__(pixmap)
        self._message_rect = message_rect

    def drawContents(self, painter):
        if not self.message():
            return
        font = QtGui.QFont()
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(MESSAGE_GRAY))
        painter.drawText(self._message_rect, Qt.AlignLeft | Qt.AlignVCenter, self.message())


def splash_message(splash, text):
    splash.showMessage(text)


def _splash_width():
    """800 points wide (the 1600 x 900 artwork at 2x), smaller on small screens."""
    screen = QtGui.QGuiApplication.primaryScreen()
    if screen is None:
        return 800
    return int(min(800, screen.availableGeometry().width() * 0.6))


def splash_screen():
    """The STEL Plot splash from the identity design, with the version and a loading message."""
    ratio = 2.0
    width = _splash_width()
    path = icon_path(SPLASH_FILE)
    if path:
        pix = QtGui.QPixmap(path).scaledToWidth(int(width * ratio), Qt.SmoothTransformation)
    else:   # fallback if the artwork is missing: the app tile and name on white
        pix = QtGui.QPixmap(int(width * ratio), int(width * ratio * 9 / 16))
        pix.fill(Qt.white)
    height = pix.height() / ratio
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.TextAntialiasing)
    p.scale(ratio, ratio)
    if not path:
        tile = tile_pixmap(width * 0.22, ratio)
        if tile is not None:
            p.drawPixmap(QtCore.QPointF(width * SPLASH_LEFT, height * 0.25), tile)
        font = QtGui.QFont()
        font.setPixelSize(int(width * 0.07))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QtGui.QColor(NAVY))
        p.drawText(QtCore.QRectF(width * 0.4, height * 0.3, width * 0.55, height * 0.25),
                   Qt.AlignLeft | Qt.AlignVCenter, APP_NAME)
    font = QtGui.QFont()
    font.setPixelSize(13)
    p.setFont(font)
    p.setPen(QtGui.QColor(MESSAGE_GRAY))
    row = QtCore.QRectF(width * SPLASH_LEFT, height * SPLASH_TEXT_Y - 12,
                        width * (SPLASH_RIGHT - SPLASH_LEFT), 24)
    p.drawText(row, Qt.AlignRight | Qt.AlignVCenter, f"Version {__version__}")
    p.end()
    pix.setDevicePixelRatio(ratio)
    splash = Splash(pix, QtCore.QRectF(row.x(), row.y(), row.width() * 0.75, row.height()))
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    return splash


def lockup_pixmap(width, dark=False, ratio=2.0):
    """The horizontal STEL PLOT lockup at `width` points. For dark backgrounds the black parts
    are drawn white. None if PyQt5.QtSvg or the file is not available."""
    path = icon_path(LOCKUP_FILE)
    if not path:
        return None
    try:
        from PyQt5 import QtSvg
    except ImportError:
        return None
    with open(path, encoding="utf-8") as fh:
        svg = fh.read()
    if dark:
        svg = svg.replace('fill="#000000"', 'fill="#FFFFFF"')
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg.encode("utf-8")))
    if not renderer.isValid():
        return None
    box = renderer.viewBoxF()
    height = width * box.height() / box.width()
    pix = QtGui.QPixmap(int(round(width * ratio)), int(round(height * ratio)))
    pix.fill(Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    renderer.render(p)
    p.end()
    pix.setDevicePixelRatio(ratio)
    return pix


def name_mac_menu():
    """Show 'STELplot' instead of 'python' in the macOS menu bar when running from source.

    Needs the optional pyobjc-framework-Cocoa package; without it nothing changes. Call before
    the QApplication is created. Built apps (build_mac.sh) are named STELplot automatically.
    """
    if sys.platform != "darwin":
        return False
    try:
        from Foundation import NSBundle
    except ImportError:
        return False
    bundle = NSBundle.mainBundle()
    info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
    if info is None:
        return False
    info["CFBundleName"] = APP_NAME
    return True
