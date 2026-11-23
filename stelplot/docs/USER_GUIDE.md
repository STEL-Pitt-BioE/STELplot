# STELplot user guide

Shiwarski Tissue Engineering Lab. Author: Daniel Shiwarski.

This guide walks through entering data, making graphs, choosing and reading statistics, and graphing each kind of data well. Use the list on the left to jump between topics, or type in the search box to find a word.

## Quick start

1. Click **+ New table** and choose **Column table** (each column is one group), **Grouped table** (two factors), or **XY table** (X values with Y measurements).
2. Type the table's name in the large title field above the grid.
3. Enter values: type in a cell and press **Enter** to move down or **Tab** to move right, or paste a block from Excel with **Cmd+V** (Ctrl+V on Windows).
4. In the graph settings on the right, choose a graph **Type** and, under **Statistics**, a **Test**.
5. Read the plain-language summary above the results. Click **Interpret** for what the test means and how to read it.
6. Click **Export figure** for an SVG or PDF you can edit in Illustrator, or **Layout** to combine several graphs into one figure.
7. Save the project (**Cmd+S**). It keeps every table, its data, and its settings.

## Choosing a table type

**Column table.** Use when each group is a single list of values: for example, cell counts for Control, Drug A, and Drug B. Each column is one group. Rows are not linked unless you choose a paired or repeated-measures test, which treats each row as one subject.

**Grouped table.** Use when there are two factors: for example, treatment (data sets) measured at several time points (rows). Each data set can hold several replicate subcolumns side by side. This is the table for two-way ANOVA.

**XY table.** Use when X is a number on a scale, such as concentration, time, or distance, and you want to see how Y changes with X. Each data set can hold replicate Y columns. This is the table for curve fitting.

**3D table.** Use when each point has three coordinates (X, Y, and Z), such as a response measured across two conditions, or principal component scores. A fourth column, optional, colors each point or surface patch on a color scale.

A quick test: if the X axis would show category names, use a Column or Grouped table. If it would show numbers on a scale, use an XY table.

## Entering and managing data

**Typing and pasting.** Enter moves down and Shift+Enter moves up; Tab moves right. Pasting a block that starts with a header row into the first row of a Column table turns the headers into column titles. Quotation marks that Excel or Prism add around names are removed.

**Several tables.** A project can hold any number of tables. Each keeps its own data and graph settings. Right-click a table in the list to rename, duplicate, freeze, or delete it. **Duplicate with empty data** keeps the layout and settings for a new experiment.

**Excluding values.** Right-click one or more cells and choose **Exclude**. Excluded values stay in the table in blue italic but are left out of graphs and statistics, and the results say how many were excluded. Choose **Include** to bring them back. Exclude a value only for a reason you would report, such as a documented technical failure, not because it looks inconvenient.

**Freezing.** **Freeze** (Cmd+L) locks a table so values cannot be typed over, pasted, cleared, or excluded. Use it once data are final.

**Transforming.** **Analysis > Transform data** makes a new table from log10, ln, square root, reciprocal, a constant, normalization (0 to 100%), percent of the first data set's mean, or fraction of total. XY tables can also transform X. **Custom: Y = expression** applies your own formula, for example `log10(Y) * 100` or `(Y - K) / K`; it can use Y, X (in XY tables), a constant K, + - * / ^, and functions such as log10, ln, exp, sqrt, abs, and logit. Only arithmetic and these functions are accepted. The original table is never changed.

**Importing from Prism.** **Import Prism** reads .prism (Prism 10 and 11) and .pzfx files. Each imported table becomes a new table. Values excluded in a .pzfx file stay excluded.

**Choosing what to graph.** **Data on graph**, at the top of the settings, lists every column with data. Uncheck a column to leave it off the graph and out of the statistics, and drag columns to reorder them. With "Each vs. first column" comparisons, the first column in this order is the control.

## Graphs for column data

**Scatter dot plot.** Shows every value with a line at the mean or median. The best default for small and medium samples, because readers see the actual data.

**Bar with points.** A bar at the mean with every value on top. Use when bars are expected, but always keep the points visible for small samples. Bar graphs should start at zero.

**Box plot.** Shows the median, quartiles, and range or whiskers. Good for larger samples and skewed data.

**Violin plot.** Shows the shape of the distribution, with the median (dashed) and quartiles (dotted). Good for large samples, such as hundreds of cells per group. Points follow the violin's shape.

**Before-after.** Draws a line for each matched row. Use for paired data, so readers see each subject's change.

**Frequency distribution.** A histogram of each column's values, with bins shared by every column. Set **Bin width** and **First bin starts at** (leave them blank for a round width chosen automatically), and choose whether the bars show counts, percents, or fractions, as filled bars or outlines. Each bin includes its lower edge and excludes its upper edge; the last bin includes both. The frequency table appears at the top of the results. Use **Reference line at X** to mark a threshold.

**What the error bar shows.** Choose under **Plot**:

- **SD** describes the spread of the values. Use it to show variability.
- **SEM** describes how precisely the mean is known. It shrinks as n grows, so it can make variable data look tidy. Show it only with the individual points.
- **95% CI** shows the range likely to contain the true mean. Useful when the comparison of means is the point.
- **Median with IQR** suits skewed data and nonparametric tests.

Always say in the figure legend which one is shown and what n is.

## Graphs for grouped and XY data

**Grouped graphs.** Grouped bars or grouped scatter plots compare data sets within each row; line plots show trends across rows (for example, over time). Brackets for comparisons within each row are drawn on the graph; comparisons between rows and cell-by-cell comparisons are listed in the results.

**Grouped box plots and area plots.** **Grouped box plot** draws a box for each data set in each row (median, quartiles, and min-to-max or Tukey whiskers), with the points on top if you like. **Area plot** fills under each data set's means across the rows; choose Stacked to pile them up or Superimposed to overlap them.

**Arrangement.** For grouped bars: **Interleaved** puts data sets side by side within each row (the only arrangement that draws comparison brackets); **Separated** gives each data set its own block of bars; **Stacked** piles the data sets in each row, each segment with its upward error bar; **Superimposed** overlaps them at one position, the shorter bar in front.

**Orientation.** **Horizontal** turns column and grouped graphs on their side: group names run down the Y axis and values along X. Long group names often read better this way.

**Right Y axis.** To compare data on different scales, such as force and temperature, check the data sets to draw against a second axis under **Right Y axis**, and give it a title. Use it sparingly: two Y axes invite readers to compare heights that are not on the same scale.

**Volcano plots.** For proteomics and other omics data with many rows. In a Grouped table, put one protein (or gene, or site) per row with its name in the first column, and the replicates of two conditions in two data sets; the second data set is compared with the first. Each row gets a t test and a log2 fold change. Check **Values are already log2** when the intensities are log-transformed, so the fold change becomes the difference of means. In an XY table, enter fold changes as X and P values as Y, and turn on **Row titles** to name the points. With thousands of rows, hundreds of P values fall below 0.05 by chance alone, so consider **Use adjusted P (Benjamini-Hochberg FDR)**, which keeps the expected share of false discoveries below the cutoff. Points pass only if they clear both the fold change and the P cutoff. The **Volcano example** buttons load simulated data to try.

**Circle heat maps.** Set **Cells drawn as** to Circles to show two values at once: circle area shows each cell's mean, and color shows the value chosen under **Circle color shows** (the mean again, SD, SEM, n, coefficient of variation, or the means of another grouped table with the same row and data set names).

**3D graphs.** In a 3D table, choose 3D scatter, line, surface, wireframe, or bars. **Color by** uses Z, the fourth column, or a single color. Turn the view with **Elevation** and **Rotation**. 3D graphs are hard to read exactly, because perspective distorts heights; for publication, check that a 2D graph (a heat map or circle heat map, for example) would not show the same thing more clearly. Grouped tables can draw **3D bars** too.

**Custom color schemes.** **Edit colors...** under Style and size makes a named scheme of up to 12 colors, used in order by the data sets. The colorblind check scores the most similar pair; aim for 10 or more. Schemes also appear as heat map and 3D color scales.

**XY graphs.** Points with error bars or error bands show the mean of the replicates at each X. Turn on **Log scale X axis** for concentrations that span several orders of magnitude. Choose a model under **Model** to draw a curve through the data (see "Curve fitting").

**Heat maps.** In a Grouped table, the **Heat map** graph type shows each cell's mean as a color, with rows down the side, data sets across the top, and a color bar. Viridis, Cividis, and Magma stay readable in grayscale and for color-blind readers; use the red-blue map only for data centered on a meaningful middle value. **Show values in cells** prints each mean. Y minimum and Y maximum set the color range.

**Log axes.** **Log scale Y axis** (under Style and size) is available for every graph type, and XY graphs also have **Log scale X axis**. A log axis changes only how the graph looks: means, error bars, and statistics are still computed from the original values. Values at or below zero cannot appear on a log axis, so they are left off the graph and noted above the results. On a log axis, bars start at the bottom of the axis, because a log axis has no zero.

**Markers and colors.** **Marker shape** picks circles, squares, triangles, diamonds, or hexagons; **Vary by group** gives each group its own shape, which helps in black-and-white printing and for color-blind readers. The default **Journal** palette was chosen to stay distinguishable under the common forms of color blindness.

## Statistics: choosing a test

Start from the design, not the result. Choose the test before looking at the P values.

| Your data | Test in STELplot |
|---|---|
| Two independent groups, roughly Gaussian | Unpaired t test (Welch's t test if SDs may differ) |
| Two independent groups, skewed or ranked | Mann-Whitney test |
| Two matched measurements (before and after, same sample) | Paired t test |
| Two matched measurements, differences clearly not Gaussian | Wilcoxon signed-rank test |
| Three or more independent groups, roughly Gaussian | One-way ANOVA with Tukey (all pairs) or Dunnett (vs. control) |
| Three or more independent groups, skewed | Kruskal-Wallis test with Dunn's comparisons |
| Three or more matched measurements per subject | Repeated-measures one-way ANOVA (Friedman test if not Gaussian) |
| Two factors (for example, treatment and time) | Two-way ANOVA in a Grouped table |
| Y changing with a numeric X | Curve fit in an XY table |

**Independent or matched?** Values are matched when each row is the same subject, culture, donor, or experiment measured under each condition. Matching removes subject-to-subject variation and usually adds power. Never treat technical replicates (several wells from one culture) as independent biological replicates; average them first or use them as replicate subcolumns.

**Gaussian or not?** STELplot runs a Shapiro-Wilk normality test and warns when data fail it. With small samples this test has little power, and with large samples it flags trivial departures, so also consider what you know about the measurement. Ratios, concentrations, and sizes are often log-normal: a log transformation can make them suitable for t tests and ANOVA.

**Multiple comparisons.** Comparing many pairs increases the chance of a false positive. Tukey's test (all pairs), Dunnett's test (each vs. control), Šídák's correction, and Dunn's test (after Kruskal-Wallis) adjust P values for the number of comparisons. Ask only the comparisons you need: comparing each group to a control has more power than comparing all pairs.

## Statistics: reading the results

**P value.** The P value asks: if there were truly no difference, how often would random sampling give a difference this large or larger? A small P value says chance is an unlikely explanation. It does not measure how big or important the effect is, and P > 0.05 does not show that groups are the same.

**Confidence interval.** The confidence interval of a difference shows the range of effect sizes consistent with the data. It is often more informative than the P value: a narrow interval near zero suggests little effect, while a wide interval means the experiment could not tell.

**Significance threshold.** By convention P < 0.05 is called significant. For t tests you can set a stricter confidence level under **Statistics** (for example 99.5% for P < 0.005).

**Stars on the graph.** ns P ≥ 0.05; * P < 0.05; ** P < 0.01; *** P < 0.001; **** P < 0.0001. State this in the figure legend, along with the test used.

**Warnings.** The yellow banner above the results flags things worth checking: very small groups, data that fail the normality test, unequal SDs, rows dropped from paired or repeated-measures tests, a low Geisser-Greenhouse epsilon, an overall test that disagrees with the pairwise comparisons, poor curve fits, and excluded values. A warning is a prompt to think, not an error.

**Interpret.** The **Interpret** button explains the chosen test, its assumptions, and how to read its output, followed by the summary of these results.

## Outliers

**What it does.** **Analysis > Identify outliers** (Cmd+Shift+O) tests each column of a Column table and highlights possible outliers in amber. Nothing is removed until you choose **Exclude flagged values**; excluded values then stay in the table in blue italic, can be included again, and are covered by undo. The summary above the results and **Copy methods text** record the method, its threshold, and how many values were excluded.

**Methods.**

- **ROUT** (recommended, Q = 1%) fits the data robustly and then uses the false discovery rate to decide which points are too far from the fit, so it can find several outliers at once. With Gaussian data its authors report false outliers in about 1 to 3% of experiments, and it never flags a value when a column has only 2 or 3 values. Motulsky HJ, Brown RE. BMC Bioinformatics 2006;7:123. doi:10.1186/1471-2105-7-123. PMID 16526949.
- **Grubbs' test** (alpha = 5%) tests the single most extreme value. **Iterative Grubbs** repeats it after each outlier is removed, but a second outlier can hide the first (masking). Grubbs FE. Technometrics 1969;11(1):1-21. doi:10.1080/00401706.1969.10490657.

**Before you exclude anything.**

- **Decide the rule before you look at the results**, and apply it the same way to every group.
- **Check that the data are roughly Gaussian.** Both tests assume it. Sizes, areas, and concentrations are often log-normal, with a long upper tail of real values; turn on **Test on log scale** for such data, or real values in the tail will be flagged. The dialog warns when a column fails the normality test.
- **Look at each flagged value.** Exclude values with a reason, such as a technical failure, not only because they are far from the rest; an extreme value can be real biological variation and the most interesting result.
- **Run the test once.** Re-running it after excluding values finds new "outliers" each time.
- **Report it.** State the method, Q or alpha, and how many values were excluded from each group.

## Two-way ANOVA

**Layout.** Put one factor in rows (for example, time or dose) and the other in data sets (for example, treatment). Replicates go in the subcolumns of each data set.

**Matching.** Choose **No matching** for independent values. Choose **Matched values spread across a row** when each row holds the same subject across data sets, or **Matched values stacked in a subcolumn** when each subcolumn is one subject measured at every row (the usual layout for time courses). Keep the **Geisser-Greenhouse correction** on for repeated measures.

**Reading it.** Each factor's P value asks whether that factor shifts the means overall. A significant **interaction** means the effect of one factor depends on the level of the other; then the main effects alone can mislead, and comparisons within each row or column are more informative.

**Model.** **Main effects only** assumes there is no interaction and adds its variation to the residual. Use it only when there is a reason to expect no interaction.

**Comparisons.** Compare data sets within each row, each data set to the first within each row, rows within each data set, or every cell with every other cell. Cell-by-cell comparisons test many pairs, so each one has less power.

## Curve fitting

**Choosing a model.** Use **Linear regression** for straight-line relationships, **Dose-response, 4PL** for sigmoidal concentration-response data (enter X as concentrations; STELplot takes the logarithm), **One-phase exponential decay** for values falling to a plateau, and **One-phase association** for values rising to a plateau.

**Reading the fit.** Look at the best-fit values with their confidence intervals, and at R squared, the fraction of variation the curve explains. For dose-response curves the EC50 is the concentration giving a response halfway between the bottom and top plateaus.

**When to worry.** Very wide confidence intervals usually mean the data do not define a parameter, often because the concentrations do not reach both plateaus. STELplot warns when R squared is low, when intervals are very wide, when the EC50 lies outside the concentrations tested, and when there are few points for the number of parameters.

## Good graphing practice

- **Show the data.** For n below about 20 per group, show every point. Bars alone hide the distribution and the sample size.
- **Match the graph to the data.** Use before-after lines for paired data, XY graphs for numeric X, and box or violin plots for large or skewed samples.
- **Say what the error bars are.** Write "mean ± SD, n = 6 biological replicates" or similar in the legend. Avoid SEM bars without the points.
- **Start bars at zero.** Bar length encodes the value, so a truncated axis exaggerates differences. Scatter, box, and violin plots may use a tighter range.
- **Use a log axis for concentrations** and other values that span orders of magnitude.
- **Keep scales consistent** across panels that readers will compare, and use the same colors for the same groups throughout a paper.
- **Use color-blind-safe colors** (the Journal palette) and, where it helps, marker shapes that vary by group.
- **Export at final size.** Axis lengths in STELplot are exact, so set them to the printed size (for example 2 in) and place the SVG in Illustrator at 100% without scaling. Text then stays at the chosen point size (journals often ask for 5 to 8 pt in the final figure; check the journal's instructions).
- **Report fully.** Give the test, whether it was paired, the multiple comparisons method, exact P values where possible, n and what it counts, and any excluded values and why.

## Reporting and methods text

**Copy methods text** drafts a figure legend and a Methods sentence from the current analysis. Review and edit it before use, and add the software line from the README's citation section. **Copy results** copies the summary, any warnings, and the full results.

A complete statistics description usually states: the test (and whether paired or repeated measures), the multiple comparisons test, the significance threshold, what n counts (biological versus technical replicates), how values are shown (mean ± SD, median and IQR), and any exclusions.

## Figures and layout sheets

**Export figure** saves SVG, PDF, or EPS (vector, editable text) or PNG or TIFF at 600 dpi. **Transparent background** leaves out the white rectangle in SVG, PDF, and PNG; TIFF files stay white.

**Layout** switches the center of the window to the layout sheet view: a live preview of several tables' graphs arranged in one figure with panel letters A, B, C. Check and order the graphs, choose how many per row and the spacing, then click **Export layout...** for editable SVG or 600 dpi PNG or TIFF. The preview updates as you change data or settings. Click **Back to graph** (or Layout again) to return. For a PDF layout, open the SVG in Illustrator and save as PDF.

**Styles.** **Edit style...** under Style and size tunes line weights, ticks, fonts, markers, fill opacity, bar width, and colors, and saves them as a named style. Export a .stelstyle file to share a lab style.

## Reusable workflows

**Save settings as method** stores a table's analysis and graph settings under a name. **Apply method** uses them on another table of the same type. **Apply settings from another table** copies settings directly between tables. **Duplicate with empty data** keeps a table's layout and settings for new data. Together these let you rerun the same analysis-and-graph chain on each new experiment.

## Keyboard shortcuts

| Action | Mac | Windows |
|---|---|---|
| New, open, save project | Cmd+N, Cmd+O, Cmd+S | Ctrl+N, Ctrl+O, Ctrl+S |
| Undo, redo | Cmd+Z, Shift+Cmd+Z | Ctrl+Z, Ctrl+Y |
| Export figure, layout sheet | Cmd+E, Shift+Cmd+E | Ctrl+E, Shift+Ctrl+E |
| Transform data | Cmd+T | Ctrl+T |
| Freeze or unfreeze table | Cmd+L | Ctrl+L |
| Next, previous table | Cmd+], Cmd+[ | Ctrl+], Ctrl+[ |
| Show tables, results, settings | Cmd+1, Cmd+2, Cmd+3 | Ctrl+1, Ctrl+2, Ctrl+3 |
| Zoom in, out | Cmd+Plus, Cmd+Minus | Ctrl+Plus, Ctrl+Minus |
| Default zoom (150%) | Cmd+0 | Ctrl+0 |
| User guide | Cmd+? | F1 |

## Troubleshooting

**The graph is empty.** Check that the table has numbers (not text), that at least one column is checked under Data on graph, and that values are not all excluded.

**A test will not run.** The results explain why: for example, a t test needs exactly two columns, and two-way ANOVA needs at least two rows and two data sets.

**Fonts look different in Illustrator.** STELplot uses Arial when it is installed. Check the Fonts line of `python launch_check.py`.

**Something else.** Run `python launch_check.py` and send `launch_check_report.txt` to Daniel.
