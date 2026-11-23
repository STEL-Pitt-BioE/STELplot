@echo off
REM Double-click launcher for STELplot on Windows. Author: Daniel Shiwarski
cd /d "%~dp0"
set "CONDA_ACT="
for %%P in ("%USERPROFILE%\miniforge3" "%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3" "%LOCALAPPDATA%\miniforge3" "%ProgramData%\miniforge3") do (
    if exist "%%~P\Scripts\activate.bat" if not defined CONDA_ACT set "CONDA_ACT=%%~P\Scripts\activate.bat"
)
if not defined CONDA_ACT (
    echo Could not find conda. See INSTALL.md, Step 2.
    pause
    exit /b 1
)
call "%CONDA_ACT%" stelplot
if errorlevel 1 (
    echo The stelplot environment was not found. See INSTALL.md, Step 3.
    pause
    exit /b 1
)
python stelplot_app.py
if errorlevel 1 pause
