@echo off
REM Build STELplot.exe on Windows. Author: Daniel Shiwarski
REM Run from the STELplot folder inside the activated stelplot environment.
python -m pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --onefile --name STELplot ^
    --icon stelplot\icons\STEL_Plot.ico --add-data "stelplot\icons;stelplot\icons" ^
    --add-data "stelplot\docs;stelplot\docs" --add-data "README.md;." stelplot_app.py
echo.
echo Done. The app is dist\STELplot.exe
pause
