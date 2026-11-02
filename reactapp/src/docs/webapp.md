### Bootstrap: Advanced parameters

When the **Bootstrap** method is selected, the wizard shows an **Advanced parameters** panel. The defaults are fimeval's own and work for most case studies; change them only when you have a reason to.

- **Iterations** (default **100**, max 1,000): how many times pixels are resampled. More iterations give smoother box-plots and take proportionally longer.
- **Points per iteration** (default **500**, max 50,000): the sample size for the Random and Stratified approaches. Larger samples narrow the spread of each metric.
- **Grid spacing min / max** (default **100–1,000 m**): for the Systematic approach only, the range from which each iteration's grid spacing is drawn.
- **Random seed** (default blank): leave blank for a different random sample each run. Enter any whole number to make the run **reproducible**: two runs with the same inputs, approach and seed produce identical sampling CSVs and box-plots.

The parameters used are recorded on the run's detail page and in the downloaded outputs, so a result can always be traced back to its settings.

### FAQs & Known Limitations

This is a **lightweight (alpha) build**, tuned for quick, moderate-sized evaluations on shared infrastructure, so a few limits apply:

- **Input size:** up to **2&nbsp;GB per raster**, and the area of interest is capped (~**1,000&nbsp;km²**). Very large or high-resolution case studies may be offered a coarser run or declined.
- **Larger case studies:** the **Desktop Application** (see above) is expected to support **larger rasters, finer resolutions, and the full set of options**. For anything beyond the web app's limits, use the desktop version or the [full fimeval package](https://github.com/sdmlua/fimeval).
- **Processing:** inputs are aligned to the coarsest resolution and reprojected to a common CRS (**EPSG:5070**) before evaluation — mixed resolutions and projections are fine.
- **Alpha status:** features and limits may change as the app matures.

### Contact & Attribution

This FIMeval web app is built to evaluate candidate flood-inundation maps against trusted benchmarks, and is integrated with the open-source [fimeval](https://github.com/sdmlua/fimeval) framework by SDML. For installation, documentation, and contribution details, see the [FIMeval GitHub repository](https://github.com/sdmlua/fimeval).

**Research & Data Science**<br>
Sagy Cohen · Supath Dhital · Dipsikha Devi

**Architecture & Engineering**<br>
Nathan Swain — Lead Engineer & Architect · Reshma Raghavan — Software Developer
