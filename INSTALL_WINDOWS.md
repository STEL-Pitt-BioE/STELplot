# Installing and building STELplot on Windows

Shiwarski Tissue Engineering Lab. Author: Daniel Shiwarski. For STELplot 1.8.1.

This guide covers two things: installing STELplot so you can run it, and compiling it into a standalone `STELplot.exe` that runs without Python. Allow about 30 to 45 minutes the first time, mostly for downloads.

STELplot has been tested on an Apple Silicon Mac. Windows uses the same code but has not yet been run on a lab PC, so please send `launch_check_report.txt` from your first Windows run (Step 5), even if everything passes.

## What you need

- A 64-bit Windows 10 or 11 PC.
- An internet connection for the first installation and the first build.
- About 3 GB of free disk space (an estimate: the environment plus the build files).
- The file **STELplot.zip**, from the lab's shared folder or from Daniel.

Pitt-managed PCs may restrict installing software. If an installer is blocked, contact Health Sciences IT.

---

## Part 1: Install and run STELplot

### Step 1. Install Miniforge (Python and conda)

1. Go to **https://github.com/conda-forge/miniforge/releases**. Under the most recent release, open **Assets** and download **Miniforge3-Windows-x86_64.exe**.
2. Run the downloaded file. If Windows shows "Windows protected your PC", click **More info**, then **Run anyway**.
3. In the installer, choose **Just Me (recommended)** and keep the default options. Administrator rights are not needed.
4. Open the **Start** menu, type `Miniforge Prompt`, and open it.

Use **Miniforge Prompt** for every command in this guide, not Command Prompt or PowerShell.

### Step 2. Unzip STELplot outside OneDrive

Unzip **STELplot.zip** into a plain folder such as `C:\STELplot`.

**Do not put STELplot in `C:\Program Files`.** Windows protects that folder: copying or unzipping into it asks for administrator permission and can skip folders without telling you, and the build in Part 2 usually cannot write there. (The finished STELplot.exe can go anywhere; see Step 9.)

Pitt PCs often sync the Desktop and Documents folders to OneDrive. Syncing can lock files while the build runs and slow it down, so a folder directly on `C:\` is the safer choice.

### Step 3. Go to the STELplot folder

In Miniforge Prompt:

```
cd C:\STELplot
dir
```

The list should include `environment.yml`, `launch_check.py`, and `build_windows.bat`.

### Step 4. Create the STELplot environment (once)

This downloads the libraries STELplot uses (about 5 to 10 minutes):

```
conda env create -f environment.yml
conda activate stelplot
```

Your prompt now starts with `(stelplot)`.

### Step 5. Run the launch check

```
python launch_check.py
```

It takes 1 to 2 minutes. Every line should say **PASS**, and the last line should say **Everything passed**.

On Windows, the **Fonts** line should show **Arial** for text and **Segoe UI Symbol** for the significance stars. Prism draws its stars with Zapf Dingbats, a Mac font; Segoe UI Symbol has the same heavy asterisk character, so the stars look very slightly different but mean the same thing.

The results are saved to `launch_check_report.txt` in the STELplot folder. Please send that file to Daniel after your first Windows run.

### Step 6. Start STELplot

```
python stelplot_app.py
```

After the first time, you can double-click **Start STELplot.bat** in the STELplot folder instead of typing commands. If Windows shows a SmartScreen warning, click **More info**, then **Run anyway**.

---

## Part 2: Compile the standalone app

### Step 7. Build STELplot.exe

In Miniforge Prompt, in `C:\STELplot`, with `(stelplot)` showing at the start of the prompt:

```
build_windows.bat
```

The first time, the script installs PyInstaller (the packaging tool). It then bundles Python, the libraries, the STEL Plot icons, the README, and the user guide into a single program. The build takes several minutes and prints many lines, including warnings; that is normal. It finishes with:

```
Done. The app is dist\STELplot.exe
```

Press any key to close the message.

### Step 8. Test the program

Open the `dist` folder inside `C:\STELplot` and double-click **STELplot.exe**.

- **The first time**, Windows will probably show "Windows protected your PC", because the program is not signed with a code-signing certificate. Click **More info**, then **Run anyway**.
- **Startup takes a few seconds.** The single-file program unpacks itself to a temporary folder each time it starts, before the splash screen appears.

### Step 9. Install it for everyday use

1. Make a folder for it, for example `C:\Users\<your name>\Apps\STELplot`.
2. Copy **STELplot.exe** into that folder.
3. Right-click **STELplot.exe** and choose **Pin to Start**, or choose **Show more options > Send to > Desktop (create shortcut)**.

You no longer need Miniforge Prompt or conda to run STELplot. Your styles, saved methods, and settings are stored separately in your Windows user profile, so they are kept when you update.

---

## Sharing STELplot with the lab

- **Send the program itself.** Lab members on 64-bit Windows 10 or 11 can run **STELplot.exe** (or a zip of it) without installing anything. They will see the same SmartScreen prompt the first time.
- **Antivirus.** Single-file programs built with PyInstaller are sometimes flagged by antivirus software even though they are safe. If Pitt's antivirus quarantines STELplot.exe, ask Health Sciences IT to allow it, or to sign it with a university code-signing certificate, which also removes the SmartScreen warning.

## Updating to a new version

1. Unzip the new **STELplot.zip** into a fresh folder, for example `C:\STELplot` (rename the old folder first).
2. In Miniforge Prompt:

   ```
   cd C:\STELplot
   conda activate stelplot
   python launch_check.py
   build_windows.bat
   ```

3. Replace the old **STELplot.exe** in your Apps folder with the new one from `dist`.

If the release notes say the requirements changed, run `conda env update -f environment.yml --prune` once before the launch check.

## Troubleshooting

**The launch check says "STELplot's program files are missing", or every step fails with "No module named 'stelplot'"**
The `stelplot` folder, which holds STELplot's program code, did not get copied. This usually happens when STELplot was unzipped into `C:\Program Files`. Delete that STELplot folder, unzip **STELplot.zip** again to `C:\STELplot`, then in Miniforge Prompt:

```
cd C:\STELplot
conda activate stelplot
python launch_check.py
```

Check that `C:\STELplot` contains a folder named `stelplot` (lowercase) next to `launch_check.py`. The conda environment from Step 4 does not need to be created again.

**"'conda' is not recognized as an internal or external command"**
You are in Command Prompt or PowerShell. Open **Miniforge Prompt** from the Start menu instead.

**"Could not find conda environment: stelplot"**
Step 4 did not finish. Go to the STELplot folder and run `conda env create -f environment.yml` again.

**"No module named PyQt5" or another missing module**
The environment is not active. Run `conda activate stelplot`; the prompt should start with `(stelplot)`.

**The launch check reports a FAIL**
Send `launch_check_report.txt` from the STELplot folder to Daniel.

**The build stops with an error**
Copy the last 20 or so lines from Miniforge Prompt and send them to Daniel.

**STELplot.exe opens and closes immediately, with no message**
The build hides the console window, so errors are not shown. To see them:

1. Open `build_windows.bat` in Notepad.
2. Delete `--windowed` from the `pyinstaller` line, then save.
3. Run `build_windows.bat` again, then run the new `dist\STELplot.exe`.

The rebuilt program opens with a console window that shows any error. Send that text to Daniel, then put `--windowed` back for normal use.

**The STELplot icon is hard to see on the taskbar**
The Windows build uses the transparent STEL Plot mark, whose black bars can be hard to see on a dark taskbar. Ask Daniel for a build that uses the white-tile icon instead.

## Removing STELplot

1. Delete **STELplot.exe** (and its shortcut) and the `C:\STELplot` folder. Keep any `.stelplot` project files you want.
2. In Miniforge Prompt, remove the environment:

   ```
   conda env remove -n stelplot
   ```

3. Optional: uninstall **Miniforge3** from **Settings > Apps**.
