# TODO — Demographic Structural Land Allocation

## Data Preparation

### Terrain variables (from AW3D30 DEM — 4 regional GeoTIFF tiles under `data/raw/elevation-slope/`)

Output: one row per tambon with columns:
`tambon_code, avg_slope, median_slope, sd_slope, avg_elev, median_elev, sd_elev, elev_range, pct_flat, pct_gentle, pct_moderate, pct_steep`

- Slope classes: flat < 3°, gentle 3–8°, moderate 8–15°, steep > 15°
- These serve as geographic control variables (Z_i) in the SDM to isolate demographic effects from physical land constraints

- [x] Calculate terrain variables per tambon (merge 4 DEM tiles → derive slope raster → zonal stats against LDD tambon polygons) — **done** (`terrain_vars.csv` + `terrain_vars.gpkg`, 7317 tambons). Slope: central difference on UTM-reprojected DEM. JAXA uses Horn (1981) kernel in WGS84 — RMSE diff 0.04°, negligible; **method decision pending**.
- [ ] **Gap: Province 34 (Ubon Ratchathani) is entirely missing from `terrain_vars.csv`** — 0 tambons out of ~198 expected. Likely cause: LDD boundary folder for province 34 absent or shapefile doesn't match `*[Tt]am*.shp` glob in `terrain_vars.py`. Check `data/raw/ldd-data/admin-boundary/` for the province-34 folder and re-run if missing. Identified by `validate_terrain.py`.
- [ ] Calculate flood risk proxy per tambon — definition TBD (candidate: flow accumulation from DEM + low-elevation threshold; or use existing flood hazard shapefile from DDPMor GISTDA)

### Accessibility variables

- [x] Calculate distance from each tambon's centroid to the nearest municipal city (เทศบาลเมือง / เทศบาลนคร) — **done** (`distance_to_city_vars.csv` + `distance_to_city_vars.gpkg`, 7589 tambons, 170 distinct city GPS points from DLA LAO registry)
- [ ] Calculate distance from each tambon's centroid to the nearest major road
- [ ] Road density per tambon

### Land & natural resources

- [ ] Soil condition & soil suitability — definition TBD (candidate: NECTEC AgriMap)
- [ ] Distance to nearest water source per tambon

### Socioeconomic

- [ ] Number of households per tambon
- [ ] Average revenue per tambon
