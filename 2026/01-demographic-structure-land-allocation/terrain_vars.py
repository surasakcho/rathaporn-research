"""
Compute tambon-level terrain variables from AW3D30 DEM tiles.

Steps:
  1. Collect all tambon shapefiles from LDD admin-boundary folders, split by UTM zone.
  2. Merge 4 DEM tiles into a mosaic (WGS84).
  3. For each zone (EPSG:32647, EPSG:32648):
       - Reproject mosaic to that zone (meters → accurate slope).
       - Compute slope raster (degrees).
       - Run zonal stats for elevation and slope per tambon polygon.
  4. Write output/terrain_vars.csv + output/terrain_vars.gpkg.

Output columns:
  tambon_code, avg_slope, median_slope, sd_slope,
  avg_elev, median_elev, sd_elev, elev_range,
  pct_flat, pct_gentle, pct_moderate, pct_steep

Slope classes: flat < 3°, gentle 3–8°, moderate 8–15°, steep ≥ 15°
Tambon code: 6-digit string = PROV_CODE(2) + AMP_CODE(2) + TAM_CODE(2)
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.merge import merge as rio_merge
from rasterio.warp import reproject, Resampling, calculate_default_transform
import rasterio.crs
import numpy.ma as ma
from rasterstats import zonal_stats

BASE = Path(__file__).parent
DEM_DIR = BASE / "data" / "raw" / "elevation-slope"
BOUNDARY_DIR = BASE / "data" / "raw" / "ldd-data" / "admin-boundary"
OUT_DIR = BASE / "data" / "processed"
INTERMEDIATE_DIR = OUT_DIR / "_terrain_intermediate"

OUT_DIR.mkdir(parents=True, exist_ok=True)
INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)

SLOPE_CLASSES = [("flat", 0, 3), ("gentle", 3, 8), ("moderate", 8, 15), ("steep", 15, 9999)]


def find_tambon_shp(province_dir: Path) -> Path | None:
    candidates = list(province_dir.glob("*[Tt]am*.shp"))
    return candidates[0] if candidates else None


def build_tambon_code(gdf: gpd.GeoDataFrame) -> pd.Series:
    return (
        gdf["PROV_CODE"].astype(int).astype(str).str.zfill(2)
        + gdf["AMP_CODE"].astype(int).astype(str).str.zfill(2)
        + gdf["TAM_CODE"].astype(int).astype(str).str.zfill(2)
    )


def compute_slope_windowed(src_path: Path, dst_path: Path, block_size: int = 1024) -> None:
    """Compute slope in degrees using windowed reads to avoid loading the full DEM into memory."""
    SLOPE_NODATA = -9999.0
    with rasterio.open(src_path) as src:
        res_x = abs(src.transform.a)
        res_y = abs(src.transform.e)
        dem_nodata = src.nodata if src.nodata is not None else -9999.0
        height, width = src.height, src.width
        meta = src.meta.copy()
        meta.update({"dtype": "float32", "nodata": SLOPE_NODATA, "count": 1})

        with rasterio.open(dst_path, "w", **meta) as dst:
            total_blocks = ((height + block_size - 1) // block_size) * ((width + block_size - 1) // block_size)
            done = 0
            for row_off in range(0, height, block_size):
                for col_off in range(0, width, block_size):
                    # Read with 1-pixel overlap on each side for central-difference gradient
                    r0 = max(0, row_off - 1)
                    c0 = max(0, col_off - 1)
                    r1 = min(height, row_off + block_size + 1)
                    c1 = min(width, col_off + block_size + 1)

                    win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
                    block = src.read(1, window=win).astype(np.float32)
                    block[block == dem_nodata] = np.nan

                    dz_dx = np.full_like(block, np.nan)
                    dz_dy = np.full_like(block, np.nan)

                    dz_dx[:, 1:-1] = (block[:, 2:] - block[:, :-2]) / (2 * res_x)
                    dz_dy[1:-1, :] = (block[:-2, :] - block[2:, :]) / (2 * res_y)
                    dz_dx[:, 0] = (block[:, 1] - block[:, 0]) / res_x
                    dz_dx[:, -1] = (block[:, -1] - block[:, -2]) / res_x
                    dz_dy[0, :] = (block[0, :] - block[1, :]) / res_y
                    dz_dy[-1, :] = (block[-2, :] - block[-1, :]) / res_y

                    slope_block = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))
                    slope_block[np.isnan(block)] = np.nan

                    # Trim overlap back to the actual output tile
                    rs = row_off - r0
                    cs = col_off - c0
                    re = rs + min(block_size, height - row_off)
                    ce = cs + min(block_size, width - col_off)
                    tile = slope_block[rs:re, cs:ce]

                    out_win = rasterio.windows.Window(col_off, row_off, ce - cs, re - rs)
                    tile_out = np.where(np.isnan(tile), SLOPE_NODATA, tile)
                    dst.write(tile_out.astype("float32"), 1, window=out_win)

                    done += 1
                    if done % 50 == 0:
                        print(f"    slope blocks: {done}/{total_blocks}", flush=True)



def make_slope_class_fn(lo: float, hi: float):
    def fn(masked_arr):
        valid = ~masked_arr.mask if ma.is_masked(masked_arr) else np.ones(masked_arr.shape, bool)
        total = int(valid.sum())
        if total == 0:
            return None
        data = masked_arr.data if ma.is_masked(masked_arr) else np.asarray(masked_arr)
        count = int(((data >= lo) & (data < hi) & valid).sum())
        return round(count / total * 100.0, 4)
    return fn


def process_zone(tambons: gpd.GeoDataFrame, epsg: int, mosaic_path: Path) -> pd.DataFrame:
    print(f"\n--- Zone EPSG:{epsg} | {len(tambons)} tambons ---")
    target_crs = rasterio.crs.CRS.from_epsg(epsg)

    # Reproject DEM mosaic to this zone
    proj_dem_path = INTERMEDIATE_DIR / f"dem_{epsg}.tif"
    if not proj_dem_path.exists():
        print(f"  Reprojecting DEM → EPSG:{epsg} ...")
        with rasterio.open(mosaic_path) as src:
            transform, width, height = calculate_default_transform(
                src.crs, target_crs, src.width, src.height, *src.bounds
            )
            meta = src.meta.copy()
            meta.update({"crs": target_crs, "transform": transform, "width": width, "height": height})
            with rasterio.open(proj_dem_path, "w", **meta) as dst:
                reproject(
                    source=rasterio.band(src, 1),
                    destination=rasterio.band(dst, 1),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=target_crs,
                    resampling=Resampling.bilinear,
                )
        print(f"  Saved: {proj_dem_path.name}")
    else:
        print(f"  Using cached: {proj_dem_path.name}")

    # Compute slope raster
    slope_path = INTERMEDIATE_DIR / f"slope_{epsg}.tif"
    if not slope_path.exists():
        print("  Computing slope (windowed) ...")
        compute_slope_windowed(proj_dem_path, slope_path)
        print(f"  Saved: {slope_path.name}")
    else:
        print(f"  Using cached: {slope_path.name}")

    # Zonal stats — elevation
    print("  Running elevation zonal stats ...")
    with rasterio.open(proj_dem_path) as src:
        dem_nodata_val = src.nodata if src.nodata is not None else -9999.0

    elev_stats = zonal_stats(
        tambons,
        str(proj_dem_path),
        stats=["mean", "median", "std", "min", "max"],
        nodata=dem_nodata_val,
        all_touched=False,
    )

    # Zonal stats — slope (with class percentages in one pass)
    print("  Running slope zonal stats ...")
    add_stats = {
        f"pct_{name}": make_slope_class_fn(lo, hi)
        for name, lo, hi in SLOPE_CLASSES
    }
    slope_stats = zonal_stats(
        tambons,
        str(slope_path),
        stats=["mean", "median", "std"],
        nodata=-9999.0,
        all_touched=False,
        add_stats=add_stats,
    )

    # Assemble rows
    rows = []
    for i, row_gdf in enumerate(tambons.itertuples()):
        e = elev_stats[i]
        s = slope_stats[i]
        emin = e.get("min") or 0
        emax = e.get("max") or 0
        rows.append({
            "tambon_code": row_gdf.tambon_code,
            "avg_elev":     e.get("mean"),
            "median_elev":  e.get("median"),
            "sd_elev":      e.get("std"),
            "elev_range":   (emax - emin) if (e.get("min") is not None and e.get("max") is not None) else None,
            "avg_slope":    s.get("mean"),
            "median_slope": s.get("median"),
            "sd_slope":     s.get("std"),
            "pct_flat":     s.get("pct_flat"),
            "pct_gentle":   s.get("pct_gentle"),
            "pct_moderate": s.get("pct_moderate"),
            "pct_steep":    s.get("pct_steep"),
        })

    stats_df = pd.DataFrame(rows)
    tambons_with_stats = tambons.copy().reset_index(drop=True)
    for col in stats_df.columns:
        tambons_with_stats[col] = stats_df[col].values

    return tambons_with_stats


def main():
    # --- Step 1: Collect tambon shapefiles, split by UTM zone ---
    print("Loading tambon shapefiles ...")
    zone_gdfs = {32647: [], 32648: []}
    missing, unexpected_crs = [], []

    for prov_dir in sorted(BOUNDARY_DIR.iterdir()):
        if not prov_dir.is_dir():
            continue
        shp = find_tambon_shp(prov_dir)
        if shp is None:
            missing.append(prov_dir.name)
            continue
        gdf = gpd.read_file(shp)
        gdf["tambon_code"] = build_tambon_code(gdf)
        epsg = gdf.crs.to_epsg()
        if epsg in zone_gdfs:
            zone_gdfs[epsg].append(gdf)
        else:
            unexpected_crs.append((prov_dir.name, epsg))

    if missing:
        print(f"WARNING: no tambon shp in: {missing}")
    if unexpected_crs:
        print(f"WARNING: unexpected CRS: {unexpected_crs}")

    raw_47 = gpd.GeoDataFrame(pd.concat(zone_gdfs[32647], ignore_index=True), crs="EPSG:32647")
    raw_48 = gpd.GeoDataFrame(pd.concat(zone_gdfs[32648], ignore_index=True), crs="EPSG:32648")
    # Dissolve multi-part polygons (islands etc.) stored as separate rows into single MultiPolygon per tambon
    tambons_47 = raw_47.dissolve(by="tambon_code").reset_index()[["tambon_code", "geometry"]]
    tambons_47 = gpd.GeoDataFrame(tambons_47, crs="EPSG:32647")
    tambons_48 = raw_48.dissolve(by="tambon_code").reset_index()[["tambon_code", "geometry"]]
    tambons_48 = gpd.GeoDataFrame(tambons_48, crs="EPSG:32648")
    print(f"Zone 47: {len(tambons_47)} tambons | Zone 48: {len(tambons_48)} tambons")

    # --- Step 2: Merge DEM tiles ---
    mosaic_path = INTERMEDIATE_DIR / "dem_mosaic.tif"
    if not mosaic_path.exists():
        print("\nMerging DEM tiles ...")
        dem_tiles = sorted(DEM_DIR.glob("AW3D30-Thailand-*.tif"))
        if not dem_tiles:
            raise FileNotFoundError(f"No DEM tiles found in {DEM_DIR}")
        print(f"  Tiles: {[t.name for t in dem_tiles]}")
        srcs = [rasterio.open(t) for t in dem_tiles]
        mosaic, mosaic_transform = rio_merge(srcs)
        meta = srcs[0].meta.copy()
        meta.update({"height": mosaic.shape[1], "width": mosaic.shape[2], "transform": mosaic_transform})
        for s in srcs:
            s.close()
        with rasterio.open(mosaic_path, "w", **meta) as dst:
            dst.write(mosaic)
        print(f"  Saved mosaic: {mosaic_path.name}")
    else:
        print(f"\nUsing cached mosaic: {mosaic_path.name}")

    # --- Step 3: Process each zone ---
    result_47 = process_zone(tambons_47, 32647, mosaic_path)
    result_48 = process_zone(tambons_48, 32648, mosaic_path)

    # --- Step 4: Combine and save ---
    print("\nSaving outputs ...")
    # Reproject zone 48 to WGS84 for a unified GeoPackage (QGIS handles mixed CRS but one layer is cleaner)
    result_47_wgs = result_47.to_crs("EPSG:4326")
    result_48_wgs = result_48.to_crs("EPSG:4326")
    combined_geo = gpd.GeoDataFrame(
        pd.concat([result_47_wgs, result_48_wgs], ignore_index=True),
        crs="EPSG:4326",
    )

    output_cols = [
        "tambon_code", "avg_slope", "median_slope", "sd_slope",
        "avg_elev", "median_elev", "sd_elev", "elev_range",
        "pct_flat", "pct_gentle", "pct_moderate", "pct_steep",
    ]

    csv_path = OUT_DIR / "terrain_vars.csv"
    combined_geo[output_cols].to_csv(csv_path, index=False)
    print(f"  CSV: {csv_path}")

    gpkg_path = OUT_DIR / "terrain_vars.gpkg"
    combined_geo[output_cols + ["geometry"]].to_file(gpkg_path, driver="GPKG", layer="terrain_vars")
    print(f"  GeoPackage: {gpkg_path}")

    print(f"\nDone. {len(combined_geo)} tambons written.")
    dupe = combined_geo["tambon_code"].duplicated().sum()
    if dupe:
        print(f"WARNING: {dupe} duplicate tambon_code values — check for overlapping province folders.")


if __name__ == "__main__":
    main()
