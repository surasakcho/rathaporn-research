# TODO — Demographic Structural Land Allocation

## Data Preparation

### Terrain variables (from AW3D30 DEM — 4 regional GeoTIFF tiles under `data/raw/elevation-slope/`)

Output: one row per tambon with columns:
`tambon_code, avg_slope, median_slope, sd_slope, avg_elev, median_elev, sd_elev, elev_range, pct_flat, pct_gentle, pct_moderate, pct_steep`

- Slope classes: flat < 3°, gentle 3–8°, moderate 8–15°, steep > 15°
- These serve as geographic control variables (Z_i) in the SDM to isolate demographic effects from physical land constraints

- [ ] Calculate terrain variables per tambon (merge 4 DEM tiles → derive slope raster → zonal stats against LDD tambon polygons)
- [ ] Calculate flood risk proxy per tambon — definition TBD (candidate: flow accumulation from DEM + low-elevation threshold; or use existing flood hazard shapefile from DDPMor GISTDA)

### Accessibility variables

- [ ] Calculate distance from each tambon's centroid to the nearest municipal city (เทศบาลเมือง / เทศบาลนคร)
- [ ] Calculate distance from each tambon's centroid to the nearest major road
- [ ] Road density per tambon

### Land & natural resources

- [ ] Soil condition & soil suitability — definition TBD (candidate: NECTEC AgriMap)
- [ ] Distance to nearest water source per tambon

### Socioeconomic

- [ ] Number of households per tambon
- [ ] Average revenue per tambon
