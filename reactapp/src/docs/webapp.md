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
