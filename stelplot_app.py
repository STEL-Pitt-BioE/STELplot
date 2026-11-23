"""Launch STELplot. This is also the entry point for PyInstaller builds.

The splash screen appears first; the plotting and statistics libraries load behind it.
"""

__author__ = "Daniel Shiwarski"

import sys


def run():
    from PyQt5 import QtCore, QtWidgets

    from stelplot import branding
    branding.name_mac_menu()
    for attr in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        if hasattr(QtCore.Qt, attr):
            QtWidgets.QApplication.setAttribute(getattr(QtCore.Qt, attr), True)
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(branding.app_icon())
    splash = branding.splash_screen()
    splash.show()
    branding.splash_message(splash, "Loading plotting and statistics libraries...")
    app.processEvents()
    from stelplot.gui import main   # matplotlib and SciPy load here, behind the splash
    main(app=app, splash=splash)


if __name__ == "__main__":
    run()
