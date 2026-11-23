# STELplot

Plotting and statistics for the Shiwarski Tissue Engineering Lab.
Author: Daniel Shiwarski. Version 1.4.0.

STELplot covers the everyday Prism workflow: type, paste, or import data; pick a graph and a test; and export a lab-formatted figure that opens cleanly in Adobe Illustrator.

## Features

**Column data.** Scatter dot plots, bars with points, box plots, violin plots, and before-after plots. Prism's "Plot" choices: mean with SD, SEM, or 95% CI; mean only; median only; median with interquartile range.

**Column statistics.** Unpaired, Welch's, and paired t-tests; Mann-Whitney and Wilcoxon tests; one-way ANOVA with Tukey or Dunnett; Kruskal-Wallis with Dunn's test; repeated-measures one-way ANOVA (Geisser-Greenhouse correction, Šídák comparisons); Friedman test with Dunn's test. Brown-Forsythe and Bartlett's tests accompany one-way ANOVA.

**Grouped data (two-way).** Prism-style grouped table. Ordinary two-way ANOVA (Type III) and two-way repeated-measures ANOVA with Prism's matching layouts ("matched values spread across a row" or "stacked in a subcolumn"). Comparisons within rows, against the first column, or within columns, with Šídák or Tukey correction.

**XY data.** Replicates per series, shaded error bands or error bars, filled or open markers, and curve fits (linear, 4PL dose-response, one-phase decay, one-phase association).

**Prism-style results.** One-way and two-way ANOVA results, multiple comparisons, and test details use Prism's sheet layout on screen and in CSV export.

**Prism import.** File > Import Prism tables adds each chosen table as a new table in the project (or all supported tables at once). It reads data tables from Prism 10/11 .prism files and from .pzfx files: column and grouped tables from both, and XY tables from .pzfx. Values excluded in a .pzfx stay excluded. Not yet verified for .prism files: XY tables (save a .pzfx copy for now) and how excluded values are marked, since the test file had none.

**Plain-language results.** Above the results, a summary explains the outcome in words (direction and size of the difference, its confidence interval, and what the P value means), and a yellow banner flags problems worth checking: very small groups, data that fail the Shapiro-Wilk normality test, unequal SDs, rows dropped from paired or repeated-measures tests, a low Geisser-Greenhouse epsilon without the correction, conflicting overall and pairwise results, poorly fitting or poorly determined curves, and excluded values. Interpret explains what the chosen test does, its assumptions, and how to read it. The help is written into STELplot rather than linked to GraphPad's website.

**More statistics.** t tests take a confidence level with decimals (for example 99.5%, which sets the threshold to P < 0.005). Two-way ANOVA adds cell-by-cell comparisons (compare cell means regardless of rows and columns) and a main-effects-only model; both match Prism 11 on a lab data file.

**Outliers.** Analysis > Identify outliers tests each column of a Column table with ROUT (Q = 1% by default; Motulsky and Brown, BMC Bioinformatics 2006;7:123, doi:10.1186/1471-2105-7-123) or Grubbs' test, single or iterative (alpha = 5%; Grubbs, Technometrics 1969;11:1-21, doi:10.1080/00401706.1969.10490657), optionally on the log scale. Possible outliers are highlighted in amber, never removed automatically; Exclude flagged values excludes them (reversible), and the results and Methods text record the method and count. Checked against the paper's reported false-outlier rate (1 to 3% of experiments with Gaussian data) and GraphPad's published Grubbs critical values; not yet compared with Prism's own outlier output.

**Data transformations.** Analysis > Transform data makes a new table from log10, ln, 10^Y, e^Y, square root, square, reciprocal, absolute value, Y times, plus, or to the power K, normalization (0 to 100%), percent of the first data set's mean, or fraction of total; XY tables can also transform X. Custom: Y = expression applies your own formula (for example log10(Y) * 100) using Y, X, K, arithmetic, and math functions; nothing else is accepted. The original table is unchanged and excluded values stay excluded.

**Reusable workflows.** Save settings as method stores a table's analysis and graph settings; Apply method uses them on another table of the same type. Apply settings from another table copies them directly (like Prism's Clone a Graph). Duplicate with empty data keeps a table's layout and settings for a new experiment (like Duplicate Family). Freeze (Cmd+L) locks a table's data against edits.

**Graph types.** Column tables: scatter dot, bar with points, box, violin, before-after, and frequency distribution (histogram with a chosen bin width and first bin; counts, percents, or fractions; frequency table in the results). Grouped tables: grouped bars, grouped scatter, line, and heat map (cell means with a color bar; Viridis, Cividis, Magma, Blues, or red-blue). XY tables: points, error bars or bands, and curve fits. Log scale Y axis is available for every graph and log scale X for XY graphs; log axes change only the display, never the statistics. Reference lines at Y on every graph, and at X on XY graphs and histograms.

**Figures.** Export as SVG, PDF, EPS, PNG, or TIFF. EPS has no transparency, so partly transparent fills are blended with white. Layout (toolbar or File > Export layout sheet) switches to the layout sheet view, a live preview of several graphs arranged with panel letters; export it as editable SVG or 600 dpi PNG or TIFF, and click Back to graph to return. Error bars can be dashed.

**Accessibility.** Keyboard focus is outlined, arrow-only buttons have names for screen readers, Cmd+] and Cmd+[ move between tables, and theme colors meet WCAG contrast (4.5:1 for text, 3:1 for controls), checked by the test suite.

**Several tables per project.** The Data tables list at the top left works like Prism's navigator. Click + New table (or File > New table) and choose a Column, Grouped, or XY table. Each table keeps its own data and graph settings. Name a table in the title field above its grid; the name appears in the list and as "Table Analyzed" in exported results. Right-click a table to rename, duplicate, or delete it. Projects saved by earlier versions open with each of their old tabs as a table.

**Excluding values.** Right-click one or more cells and choose Exclude. Excluded values stay in the table in blue italic, as in Prism, and are left out of graphs and statistics; the results note how many were excluded. Choose Include to bring them back. Exclusions are saved in the project, can be undone, and values excluded in a Prism .pzfx file import as excluded.

**Professional layout.** A navy toolbar with the STELplot logo and line icons for each command. The STEL Plot app icon appears in the Dock or taskbar, the toolbar, and the window title. The startup splash (the 1600 x 900 design from the STEL Plot identity) shows while the plotting libraries load, and the horizontal STEL PLOT lockup heads the About box and help windows (drawn white where it sits on a dark background). Brand colors: STEL Black #000000, STEL Blue #1D75BD, STEL Red #ED1B24. The standalone apps use STEL_Plot.icns (Mac) and STEL_Plot.ico (Windows). When running from source on a Mac, the menu bar says "python"; installing the optional pyobjc-framework-Cocoa package (`pip install pyobjc-framework-Cocoa` in the stelplot environment) usually makes it say STELplot, and the built app always does. README and User guide buttons (Help menu, Cmd+? on a Mac, F1 on Windows) open a searchable help window; the user guide covers the table types, plotting, choosing and reading statistics, two-way ANOVA, curve fitting, and good graphing practice. Settings sections (Data on graph, Graph, Statistics, Labels, Style and size) fold open and closed by clicking their titles, with Expand all and Collapse all; STELplot remembers which are open. The Settings header and the Export section stay in view while the settings scroll. Button rows wrap, so the data panel can be narrowed to two columns.

**Panels and zoom.** The slim arrow tabs on the left and right edges hide and show the tables panel and the graph settings panel; the tab under the results hides the results. View > Show tables, Show results, and Show graph settings do the same (Cmd+1, Cmd+2, Cmd+3 on a Mac; Ctrl on Windows). Hidden panels stay hidden the next time STELplot opens, and adding or importing a table reopens the tables panel. The preview zooms from 50% to 500% (View > Zoom in and Zoom out, Cmd+= and Cmd+-; View > Default zoom, Cmd+0, returns to 150%; the last zoom is remembered); zoom changes only the preview, never the exported size.

**Look.** STELplot uses the same light theme as the lab's calcium pipeline app, with a toolbar and card layout. View > Dark mode (or the toolbar button) switches themes; figures and exports are not affected.

**Marker shapes.** Each tab has a Marker shape setting (circle, square, triangle, inverted triangle, diamond, or hexagon) and a Markers setting (filled or open). Vary by group gives each group or data set the next shape in the style's marker order. Shapes are sized for equal visual weight; squares follow the style's square size (Prism's 1.414x by default).

**Custom styles.** Click Edit style... under Style and size to tune text, line weights (axes, error bars and mean lines, brackets, outlines, reference lines), tick length and direction, marker order, open-marker outline, square size, fill opacity, bar width, asterisk style, and up to eight colors. A colorblind check scores the colors as you choose them. Save under a name and the style appears on every tab. Styles are kept on this computer, travel inside project files, and can be exported as a .stelstyle file to share with the lab. Built-in styles cannot be overwritten.

**Undo and redo.** Edit > Undo (Cmd+Z) and Edit > Redo (Shift+Cmd+Z) cover table edits, pastes, added or removed columns, renames, imports, example data, and every graph, statistics, and style setting. Rapid changes count as one step; up to 100 steps are kept, and the history starts fresh when a project is opened. While typing in a text field, Cmd+Z undoes typing in that field.

**Export.** SVG and PDF keep text editable in Illustrator. PNG and TIFF export at 600 dpi. The plotting area is exactly the X and Y axis lengths you set; the figure grows to fit labels.

## Style presets

**Lab template** (default) is measured from the lab's Prism SVG exports: Arial 7 pt numbering and labels, 8 pt axis titles and legends, 0.72 pt axes and data lines, 0.36 pt outlines, 1.8 pt inward ticks, 50% fills, Prism's heavy asterisk, Prism-style brackets, dashed violin medians with dotted quartiles, and dotted 1.44 pt reference lines. Measured values match the exports within Prism's 0.4% export scaling; axis title spacing is within 0.7 pt.

**Prism default** follows Prism's Format Axes defaults for a new graph: Arial Bold 11, 12, and 14 pt, 1 pt axes, and outward ticks. Prism lists tick length only as "Normal," so 4 pt is an estimate.

Not measured from an export: the graph title size in the Lab template (9 pt; no export had a title) and error-band colors for colored series (the black band matches the export exactly).

## Color palettes

**Journal** (default): black #000000, cobalt #1355AA, ochre #AE9122, teal #13ADA6, muted red #C55C55, plum #773E55. Muted tones in the style of Nature, Cell, and Science figures, selected for colorblind robustness.

How it was chosen: an exhaustive search over moderate-chroma, mid-lightness colors in the blue, coral, teal, gold, and plum families. The score is the smallest CIEDE2000 difference between any two colors, as solid colors and as 50% bar fills, under normal vision and simulated deuteranopia, protanopia, and tritanopia. Scores on that test:

| Palette (first 6 colors) | Weakest pair |
|---|---|
| Journal | 9.9 (first 2-3 colors: 20.8; first 4: 11.1) |
| Lab template (black, pink, teal, purple) | 8.3 |
| Tol muted | 6.3 |
| Okabe-Ito | 5.2 |

The comparison palettes are colorblind safe as solid colors; their lower scores come mostly from 50% fills, which compress differences. Use the colors in order, since the first ones are the most distinct. The Journal colors are not separated by lightness alone, so for grayscale printing rely on labels and symbols or use the Grayscale palette. The simulation is a model and is not a substitute for feedback from colorblind readers.

Other palettes: Lab template, Okabe-Ito, Tol muted, Tol bright, Lab navy/blue, and Grayscale. `stelplot/color_check.py` scores any palette with the same test.

## Testing status

Automated checks pass in eight scripts (run `python launch_check.py` for the current count):

- `tests/test_core.py` (66): column statistics against SciPy, curve fits, export formats, exact axis lengths and preset text settings, Prism-like axis ranges.
- `tests/test_anova.py` (36): two-way, mixed, and repeated-measures ANOVA against independent textbook formulas.
- `tests/test_prism.py` (31): STELplot against Prism 9.4.1 results stored in the lab template. The three Prism results sheets (two one-way ANOVAs, one two-way RM ANOVA) are reproduced line for line; Tukey and Šídák test details, adjusted P values, and the difference between column means also match.
- `tests/test_style.py` (18): exported SVG line widths, tick lengths, font sizes, fills, dashes, and legend swatches against the Prism exports.
- `tests/test_prism_bundle.py`: reads a synthetic .prism file built with the layout found in a Prism 11.1 file, and compares with Prism 11 results when the lab file is present.
- `tests/test_custom_style.py`: marker shapes on every graph type, custom style validation, export of custom line widths and colors, and saving and reloading the style library.
- `tests/test_features.py`: confidence levels, cell-by-cell comparisons, the main-effects model, Prism-style rounding, dashed error bars, EPS, transformations, plain-language summaries and warnings, layout sheets, theme contrast, and saved methods.
- `tests/test_palette.py` (6): CIEDE2000 against published test pairs, and the Journal palette scores above.

Also checked against Prism 11 results stored in a lab .prism file (not shipped; place it in `tests/fixtures/private/` to rerun): Welch's t test (difference B - A, CI, SE), ordinary one-way ANOVA with Tukey for unequal n (540 to 3,241), ordinary two-way ANOVA including the difference between column means, and RM one-way ANOVA with the Geisser-Greenhouse correction followed by Tukey's test.

Not yet checked against Prism: between-group comparisons at one level of a repeated factor; Dunnett's "q" label. Not yet available: Prism-layout sheets for t tests and RM one-way ANOVA (results are shown in STELplot's own layout).

The PyQt5 interface has been statically checked but **not yet launched**. The first run on a lab computer is the real test; please send any error text.

## First launch

New users: follow **INSTALL.md** for step-by-step instructions starting from a computer with nothing installed. The short version for anyone with conda already set up:

1. Unzip STELplot. Open Terminal (Mac) or Anaconda Prompt (Windows) and change to the STELplot folder.
2. Create the environment once: `conda env create -f environment.yml` (a few minutes), then `conda activate stelplot`.
3. Run `python launch_check.py`. It checks the installation, runs all automated checks, then builds the interface off screen and exercises every tab (drawing, statistics, export, project save and reopen, Prism import, style presets). It writes `launch_check_report.txt`.
4. If everything passes, start the app with `python stelplot_app.py`. If anything fails, send `launch_check_report.txt`.

## Install and run

```
conda env create -f environment.yml
conda activate stelplot
python stelplot_app.py
```

Or with pip: `pip install -r requirements.txt`, then `python stelplot_app.py`. Run the checks with `python -m tests.test_core` (and likewise test_anova, test_prism, test_style, and test_palette).

## Build standalone apps

PyInstaller cannot cross-compile. On Windows run `build_windows.bat` (output `dist\STELplot.exe`); on a Mac run `bash build_mac.sh` (output `dist/STELplot.app`). Apple Silicon builds run only on Apple Silicon; an Intel build should also run on Apple Silicon through Rosetta 2, but confirm on one machine. The apps are unsigned, so the first launch needs right-click > Open on a Mac or More info > Run anyway on Windows.

## Statistics notes

All tests are two-tailed with alpha = 0.05. Two-way ANOVA uses Type III sums of squares. Repeated-measures designs report the Geisser-Greenhouse epsilon and apply it by default. **Subjects with missing values are excluded**; Prism would fit a mixed-effects model instead, so results differ when values are missing. After RM ANOVA with sphericity assumed, within-subject comparisons use the pooled residual error, which matches Prism; with the correction applied, they use paired differences with separate error terms, and after RM one-way ANOVA Tukey's test uses DF = n - 1, as Prism 11 does. Two-group tests report differences as B - A, like Prism. Šídák's correction treats all listed comparisons as one family; Tukey's test uses the studentized range within each row or column. Dunn's tests use a Bonferroni adjustment.

Not yet included: two-way ANOVA with both factors repeated, mixed-effects models, three-way ANOVA, Welch's ANOVA, survival curves, outlier tests, contingency tables, and data transforms.

## Customizing

Most changes can be made in the app with Edit style... (see Custom styles). `stelplot/lab_style.py` holds the built-in presets, palettes, and column geometry; edits there change every figure. Custom styles are stored in `styles.json` in STELplot's settings folder (on a Mac, under ~/Library/Preferences/STELplot).

## Citing

SciPy: Virtanen P, Gommers R, Oliphant TE, et al. SciPy 1.0: fundamental algorithms for scientific computing in Python. *Nat Methods*. 2020;17(3):261-272. DOI: 10.1038/s41592-019-0686-2. PMID: 32015543. PMCID: PMC7056644. (Verified in PubMed.)

Matplotlib: Hunter JD. Matplotlib: A 2D graphics environment. *Comput Sci Eng*. 2007;9(3):90-95. DOI: 10.1109/MCSE.2007.55. (From the official matplotlib.org citation file.)

Color vision simulation: Machado GM, Oliveira MM, Fernandes LAF. A physiologically-based model for simulation of color vision deficiency. *IEEE Trans Vis Comput Graph*. 2009;15(6):1291-1298. DOI: 10.1109/TVCG.2009.113. (Matrices checked against the authors' published table.)

Tol palettes: Tol P. Colour Schemes. SRON Technical Note SRON/EPS/TN/09-002, issue 3.2, 2021. https://personal.sron.nl/~pault/data/colourschemes.pdf

Okabe-Ito palette: [REF needed]. CIEDE2000 test pairs: [REF needed].

## Licensing

PyQt5 is available under GPL v3 or a commercial license. Internal lab use is fine; check with Pitt before distributing outside the lab. `tests/fixtures` contains the lab's Prism template and results sheets; remove them before sharing STELplot outside the lab.

## Files

```
stelplot_app.py            Launcher and PyInstaller entry point
stelplot/gui.py            PyQt5 interface
stelplot/plotting.py       Figure rendering and export
stelplot/lab_style.py      Style presets, palettes, geometry
stelplot/color_check.py    Colorblind-safety scoring for palettes
stelplot/stats_engine.py   Column tests, curve fits, reports
stelplot/anova.py          Two-way, repeated-measures, and Friedman analyses
stelplot/prism_format.py   Prism-layout results and CSV export
stelplot/prism_import.py   Reads data tables from Prism .prism and .pzfx files
stelplot/interpret.py      Plain-language summaries, warnings, and Interpret help
stelplot/transforms.py     Data transformations (each makes a new table)
stelplot/layout.py         Layout sheets (several graphs on one figure)
stelplot/workflow.py       Saved methods and empty-data duplicates
stelplot/outliers.py       ROUT and Grubbs outlier tests
stelplot/theme.py          Light and dark themes, contrast checks
stelplot/clipboard.py      Pasting from Excel and Prism
stelplot/help_docs.py      Finds the README, user guide, and icons
stelplot/branding.py       App icon, toolbar logo, and splash screen
stelplot/icons/            STEL Plot icon set, splash, lockup, and identity overview
stelplot/docs/USER_GUIDE.md  User guide shown in the Help window
tests/                     Eight test scripts and fixtures
launch_check.py            First-launch check; writes launch_check_report.txt
INSTALL.md                 Installation guide for new users (Mac and Windows)
INSTALL_WINDOWS.md         Windows installation and building STELplot.exe
Start STELplot.command     Double-click launcher (Mac)
Start STELplot.bat         Double-click launcher (Windows)
build_windows.bat, build_mac.sh, environment.yml, requirements.txt
```
