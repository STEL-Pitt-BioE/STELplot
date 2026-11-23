# Installing STELplot

Shiwarski Tissue Engineering Lab. Author: Daniel Shiwarski. For STELplot 1.5.

This guide assumes nothing is installed yet. Windows users can also follow **INSTALL_WINDOWS.md**, which covers Windows in more detail, including building STELplot.exe. It takes about 20 to 30 minutes, mostly waiting for downloads. You do not need administrator rights.

## What you need

- A Mac (macOS 11 or later) or a Windows 10 or 11 PC.
- An internet connection for the first installation.
- About 2 GB of free disk space (an estimate; most of it is the Python libraries).
- The file **STELplot.zip**, from the lab's shared folder or from Daniel.

STELplot has been tested on an Apple Silicon Mac. Windows uses the same software and should work the same way, but it has not yet been run on a lab PC; please report anything that differs.

Lab computers managed by Pitt IT may restrict installing software. If an installer is blocked, contact Health Sciences IT.

---

## Step 1. Unzip STELplot

1. Double-click **STELplot.zip**. A folder named **STELplot** appears.
2. Move the **STELplot** folder to your **Desktop**. (Any location works, but the commands below assume the Desktop.)
3. Open the folder and confirm it contains files such as `launch_check.py`, `stelplot_app.py`, and `environment.yml`.

## Step 2. Install Miniforge (the Python installer)

STELplot runs on Python. Miniforge installs Python and a tool called `conda` that downloads everything else STELplot needs. It uses the free conda-forge package source, which avoids Anaconda's licensing terms for large organizations.

If you already have Anaconda or Miniconda, you can skip to Step 3 and use it instead.

### On a Mac

1. Open **Terminal**: press Cmd+Space, type `Terminal`, and press Enter.
2. Copy and paste these three lines, one at a time, pressing Enter after each:

   ```
   cd ~
   curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
   bash Miniforge3-$(uname)-$(uname -m).sh
   ```

   The download command picks the right version for your Mac (Apple Silicon or Intel) automatically.

3. Answer the installer's questions:
   - Press **Enter** to read the license. Press the space bar to scroll to the end.
   - Type **yes** and press Enter to accept the license.
   - Press **Enter** to accept the default location (`~/miniforge3`).
   - When asked whether to initialize conda, type **yes** and press Enter.
4. **Quit Terminal completely** (Cmd+Q), then open it again. This step is required.
5. Check that it worked:

   ```
   conda --version
   ```

   You should see a version number such as `conda 25.x.x`. Your prompt may now start with `(base)`, which is normal.

### On Windows

1. Go to **https://github.com/conda-forge/miniforge/releases**. Under the most recent release, open **Assets** and download **Miniforge3-Windows-x86_64.exe**.
2. Double-click the downloaded file. If Windows shows a "Windows protected your PC" message, click **More info**, then **Run anyway**.
3. In the installer:
   - Click **Next** and **I Agree**.
   - Choose **Just Me (recommended)**.
   - Keep the default install location and the default options.
   - Click **Install**, then **Finish**.
4. Open the **Start** menu, type `Miniforge Prompt`, and open it. Use this window for all commands below (not the regular Command Prompt).
5. Check that it worked:

   ```
   conda --version
   ```

   You should see a version number.

## Step 3. Create the STELplot environment

This downloads the libraries STELplot uses (NumPy, SciPy, Matplotlib, and PyQt5) into a separate space called `stelplot`, so they cannot interfere with other software. You only do this once.

1. Go to the STELplot folder:
   - **Mac (Terminal):** type `cd ` (with a space after it), drag the **STELplot** folder from Finder into the Terminal window, and press Enter.
   - **Windows (Miniforge Prompt):** type:

     ```
     cd %USERPROFILE%\Desktop\STELplot
     ```

     If your Desktop is synced to OneDrive, use `cd %USERPROFILE%\OneDrive\Desktop\STELplot` instead.
2. Confirm you are in the right folder:
   - **Mac:** `ls` should list `environment.yml`.
   - **Windows:** `dir` should list `environment.yml`.
3. Create the environment (about 5 to 10 minutes):

   ```
   conda env create -f environment.yml
   ```

   When it finishes, you will see a message suggesting `conda activate stelplot`.
4. Activate it:

   ```
   conda activate stelplot
   ```

   Your prompt now starts with `(stelplot)`.

## Step 4. Run the launch check

The launch check confirms everything installed correctly. It runs all of STELplot's automated checks (statistics compared with Prism, figure styles, and file import), then builds the interface out of sight and tries every tab.

```
python launch_check.py
```

It takes 1 to 2 minutes. Each step prints **PASS** or **FAIL**, and the last lines say either **Everything passed** or how many steps failed. On a Mac, a Python icon may appear briefly in the Dock; that is normal.

Also check the **Fonts** line. It should say `text font Arial`. If it names a different font, exported figures will use that font instead.

The results are saved to `launch_check_report.txt` in the STELplot folder. If anything fails, send that file to Daniel.

## Step 5. Start STELplot

```
python stelplot_app.py
```

The STELplot window opens. To make a first graph, click **Example data** in the Data 1 table, then set **Test** to "One-way ANOVA". Use **+ New table** to add Grouped or XY tables.

---

## Starting STELplot after the first time

You do not repeat Steps 1 to 4. Each time you want to use STELplot:

1. Open **Terminal** (Mac) or **Miniforge Prompt** (Windows).
2. Activate the environment and go to the folder:

   ```
   conda activate stelplot
   ```

   Then use the same `cd` command as in Step 3.
3. Start the app:

   ```
   python stelplot_app.py
   ```

### Optional: double-click launchers

The STELplot folder includes two shortcuts that do the three steps above for you. They look for Miniforge, Miniconda, or Anaconda in their usual locations. If a launcher does not work on your computer, use the Terminal steps instead.

- **Mac: `Start STELplot.command`.** The first time, right-click it and choose **Open**, then click **Open** again, because macOS blocks scripts downloaded from the internet. If macOS says it is not allowed to run, open Terminal in the STELplot folder and run `chmod +x "Start STELplot.command"`.
- **Windows: `Start STELplot.bat`.** Double-click it. If Windows shows a SmartScreen warning, click **More info**, then **Run anyway**.

A Terminal or command window stays open while STELplot runs. Closing that window also closes STELplot.

## Updating to a new version

1. Rename your current folder (for example, to `STELplot_old`) so the new one does not unzip as "STELplot 2".
2. Unzip the new **STELplot.zip** onto your Desktop.
3. Your `stelplot` environment carries over. If the release notes say the requirements changed, run this once in the new folder:

   ```
   conda activate stelplot
   conda env update -f environment.yml --prune
   ```

4. Run `python launch_check.py`, then `python stelplot_app.py`.
5. Your saved `.stelplot` projects open in the new version. Once everything works, you can delete the old folder.

## Troubleshooting

**"conda: command not found" (Mac) or "'conda' is not recognized" (Windows)**
- Mac: quit Terminal completely (Cmd+Q) and reopen it. If that does not help, run `~/miniforge3/bin/conda init zsh`, then quit and reopen Terminal.
- Windows: make sure you are using **Miniforge Prompt**, not Command Prompt or PowerShell.

**"can't open file ... launch_check.py: No such file or directory"**
You are in the wrong folder or have an older copy of STELplot. Repeat the `cd` step, then list the files (`ls` on Mac, `dir` on Windows) and confirm `launch_check.py` is there. If it is missing, download the latest STELplot.zip.

**"Could not find conda environment: stelplot"**
Step 3 did not finish. Go to the STELplot folder and run `conda env create -f environment.yml` again.

**"No module named PyQt5" or another missing module**
The environment is not active. Run `conda activate stelplot`; your prompt should start with `(stelplot)`.

**`conda env create` stops with a network or download error**
Check your internet connection and run the command again. On some university networks, downloads can be blocked; try another network or contact IT. If the error says the environment already exists, run `conda env update -f environment.yml --prune` instead.

**The launch check reports a FAIL**
Send `launch_check_report.txt` from the STELplot folder to Daniel.

**The window is too large or cut off**
STELplot sizes itself to your screen when it opens. If the window was moved to a different monitor, close it and start STELplot again.

## Removing STELplot

1. Delete the **STELplot** folder. Keep any `.stelplot` project files you want.
2. Remove the environment:

   ```
   conda env remove -n stelplot
   ```

3. Optional, to remove Miniforge entirely on a Mac: delete the `miniforge3` folder in your home folder, and remove the block of lines marked `conda initialize` from the file `~/.zshrc`. On Windows, uninstall **Miniforge3** from **Settings > Apps**.
