"""
Compute accessibility variables for each tambon:
  - dist_city_km: distance (km) to nearest เทศบาลเมือง or เทศบาลนคร

City locations come from the DLA LAO registry (re01_9112566tambon.csv).
Each LAO has one GPS office location; rows with the same LAT/LONG are the
same physical city — deduplicated before distance calculation.

Tambon centroids are derived from terrain_vars.gpkg (which covers all 7589 tambons).
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import geopandas as gpd
from pathlib import Path
from scipy.spatial import cKDTree

BASE   = Path(__file__).parent
DLA    = BASE / "data/raw/DLA/re01_9112566tambon.csv"
GPKG   = BASE / "data/processed/terrain/terrain_vars.gpkg"
OUT_DIR = BASE / "data/processed/access"
OUT_CSV  = OUT_DIR / "access_vars.csv"
OUT_GPKG = OUT_DIR / "access_vars.gpkg"

CITY_TYPES = {"เทศบาลเมือง", "เทศบาลนคร"}

EARTH_R_KM = 6371.0


def haversine_km(lat1, lon1, lat2_arr, lon2_arr):
    """Vectorised haversine distance (km) from one point to an array of points."""
    lat1, lon1 = np.radians(lat1), np.radians(lon1)
    lat2 = np.radians(lat2_arr)
    lon2 = np.radians(lon2_arr)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))


def main():
    # ── 1. Load city GPS points ──────────────────────────────────────────────
    print("Loading DLA city locations...")
    dla = pd.read_csv(DLA, encoding="utf-8-sig")
    cities = (
        dla[dla["ประเภท อปท."].isin(CITY_TYPES)]
        .dropna(subset=["LAT", "LONG"])
        .drop_duplicates(subset=["LAT", "LONG"])
        [["ประเภท อปท.", "อปท.", "จังหวัด", "LAT", "LONG"]]
        .reset_index(drop=True)
    )
    print(f"  {len(cities)} distinct city GPS points "
          f"({cities['ประเภท อปท.'].value_counts().to_dict()})")

    city_coords = np.radians(cities[["LAT", "LONG"]].values)  # (N, 2) in radians

    # Build BallTree with haversine metric (expects radians)
    tree = cKDTree(city_coords)

    # ── 2. Load tambon centroids ─────────────────────────────────────────────
    print("Loading tambon geometries from terrain_vars.gpkg...")
    tambons = gpd.read_file(GPKG)
    print(f"  {len(tambons)} tambons loaded")

    # Centroids: compute in UTM to avoid geographic-CRS warning, then back to WGS84
    centroids_proj = tambons.to_crs(epsg=32647).geometry.centroid
    centroids_wgs = gpd.GeoSeries(centroids_proj, crs="EPSG:32647").to_crs(epsg=4326)
    cent_lat = centroids_wgs.y.values
    cent_lon = centroids_wgs.x.values
    cent_rad = np.column_stack([np.radians(cent_lat), np.radians(cent_lon)])

    # ── 3. Nearest city via BallTree ─────────────────────────────────────────
    print("Computing nearest city distances...")
    dist_rad, idx = tree.query(cent_rad, k=1)

    # BallTree haversine distance is arc-length on unit sphere → multiply by R
    dist_km = dist_rad * EARTH_R_KM

    # ── 4. Assemble output ───────────────────────────────────────────────────
    out = tambons[["tambon_code"]].copy()
    out["dist_city_km"] = np.round(dist_km, 3)

    # Nearest city name (for QA)
    nearest_city_name = cities.iloc[idx]["อปท."].values
    nearest_city_prov = cities.iloc[idx]["จังหวัด"].values
    out["nearest_city"]      = nearest_city_name
    out["nearest_city_prov"] = nearest_city_prov

    # ── 5. Write outputs ─────────────────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"  Wrote {OUT_CSV}")

    out_geo = tambons[["tambon_code", "geometry"]].merge(
        out.drop(columns="tambon_code", errors="ignore").assign(tambon_code=out["tambon_code"]),
        on="tambon_code"
    )
    out_geo = gpd.GeoDataFrame(out_geo, crs=tambons.crs)
    out_geo.to_file(OUT_GPKG, driver="GPKG", layer="access_vars")
    print(f"  Wrote {OUT_GPKG}")

    # ── 6. Quick summary ─────────────────────────────────────────────────────
    print()
    print("dist_city_km summary:")
    print(f"  min  = {out['dist_city_km'].min():.3f} km")
    print(f"  mean = {out['dist_city_km'].mean():.3f} km")
    print(f"  max  = {out['dist_city_km'].max():.3f} km")
    print()
    print("Sample (10 random rows):")
    print(out.sample(10, random_state=42).to_string(index=False))


if __name__ == "__main__":
    main()
