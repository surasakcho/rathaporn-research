# Slope Calculation Methodology

## Data Source

AW3D30 v3.x (JAXA EORC) — 30m resolution Digital Surface Model (DSM), WGS84 (EPSG:4326).
Four regional mosaics covering Thailand: N, NE, C, S.

Note: AW3D30 v3.x does not distribute a separate slope (SLP) product. Slope is derived from the DSM.

## Steps

### 1. Mosaic

The four regional DSM tiles are merged into a single raster using `rasterio.merge` (first-value strategy for overlapping pixels).

### 2. Reproject to UTM (meters)

The mosaic (WGS84, degrees) is reprojected to a metric CRS before computing gradients, so that pixel size is expressed in meters and slope is physically accurate:

- Provinces with EPSG:32647 shapefiles → DEM reprojected to **EPSG:32647** (UTM zone 47N)
- Provinces with EPSG:32648 shapefiles → DEM reprojected to **EPSG:32648** (UTM zone 48N)

The zone boundary is ~102°E. Using per-zone projection avoids the distortion of forcing all of Thailand into a single UTM zone.

Resampling method: **bilinear** (preserves smooth elevation transitions).

### 3. Slope Formula

Slope in degrees is computed per pixel using the **central difference** method:

$$
\text{slope} = \arctan\!\left(\sqrt{\left(\frac{\partial z}{\partial x}\right)^2 + \left(\frac{\partial z}{\partial y}\right)^2}\right) \times \frac{180}{\pi}
$$

Where:

$$
\frac{\partial z}{\partial x} = \frac{z_{i,j+1} - z_{i,j-1}}{2 \cdot \Delta x}, \quad
\frac{\partial z}{\partial y} = \frac{z_{i-1,j} - z_{i+1,j}}{2 \cdot \Delta y}
$$

- $\Delta x$, $\Delta y$ = pixel size in meters from the UTM transform
- Edge pixels use a one-sided (forward/backward) difference instead of central difference
- NoData pixels propagate as NoData in the slope raster
- Output dtype: float32

This is a **pure central difference** — simpler and computationally cheaper than Horn's 3×3 weighted kernel.

**Note on JAXA's methodology (verified July 2026):** JAXA's AW3D30 slope tiles use the **Horn (1981) 3×3 weighted kernel**, computed in WGS84 geographic space with pixel sizes converted to meters at mid-tile latitude. Their formula:

$$
\frac{\partial z}{\partial x} = \frac{(z_{NE} + 2z_E + z_{SE}) - (z_{NW} + 2z_W + z_{SW})}{8 \cdot \Delta x_m}
$$

Comparison of our computed slope vs JAXA tiles: RMSE = 0.04°. Differences arise from (1) kernel: our central diff vs Horn 3×3, and (2) CRS: our UTM reprojection vs JAXA's in-place degree→meter correction. **Decision pending** on whether to align with JAXA.

### 4. Memory-efficient computation

The projected DEM for zone 47 is ~58,000 × 32,000 pixels (~14 GB at float64). Slope is computed in **1,024 × 1,024 pixel windows** with a 1-pixel overlap on each side to maintain central-difference accuracy at tile boundaries. Output is written tile-by-tile in float32.

### 5. Slope classes

| Class    | Range        |
|----------|-------------|
| Flat     | 0° – < 3°   |
| Gentle   | 3° – < 8°   |
| Moderate | 8° – < 15°  |
| Steep    | ≥ 15°       |

### 6. Zonal statistics

`rasterstats.zonal_stats` is run against dissolved tambon polygons (multi-part island polygons dissolved to MultiPolygon before this step). Statistics computed per tambon:

- **Elevation**: mean, median, std, range (max − min)
- **Slope**: mean, median, std, and percentage of pixels in each slope class

## Output columns

| Column | Description |
|---|---|
| `avg_elev` | Mean elevation (m) |
| `median_elev` | Median elevation (m) |
| `sd_elev` | Std dev of elevation (m) |
| `elev_range` | Max − min elevation (m) |
| `avg_slope` | Mean slope (°) |
| `median_slope` | Median slope (°) |
| `sd_slope` | Std dev of slope (°) |
| `pct_flat` | % pixels with slope < 3° |
| `pct_gentle` | % pixels with slope 3–8° |
| `pct_moderate` | % pixels with slope 8–15° |
| `pct_steep` | % pixels with slope ≥ 15° |

## References

- JAXA EORC. AW3D30 Global Digital Surface Model. https://www.eorc.jaxa.jp/ALOS/en/aw3d30/
- Horn, B.K.P. (1981). Hill shading and the reflectance map. *Proceedings of the IEEE*, 69(1), 14–47.
