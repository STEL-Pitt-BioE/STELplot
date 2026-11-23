#!/bin/bash
# Build STELplot.app on macOS. Author: Daniel Shiwarski
# Run from the STELplot folder inside the activated stelplot environment.
set -e
cd "$(dirname "$0")"
python3 -m pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name STELplot \
    --osx-bundle-identifier edu.pitt.shiwarskilab.stelplot \
    --icon stelplot/icons/STEL_Plot.icns --add-data "stelplot/icons:stelplot/icons" \
    --add-data "stelplot/docs:stelplot/docs" --add-data "README.md:." stelplot_app.py
echo "Done. The app is dist/STELplot.app"
