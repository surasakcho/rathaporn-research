"""
Mosaic JAXA AW3D30 slope tiles into Thailand-slope.tif at float16 precision.

float16 is sufficient for slope in degrees (0-90°, ~3 significant digits).
Halves file size vs float32 — keeps the mosaic under GitHub LFS 2 GB limit.

Nodata: we write NaN as nodata (float16 supports NaN), which avoids the
-9999 rounding issue (float16 rounds -9999 to -10000).
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
import numpy as np
import rasterio
from rasterio.merge import merge as rio_merge

BASE = Path(__file__).parent
SLOPE_DIR = BASE / "data" / "raw" / "elevation-slope" / "redownload"
OUT = BASE / "data" / "raw" / "elevation-slope" / "Thailand-slope.tif"

slope_tiles = sorted(SLOPE_DIR.glob("*slope*.tif"))
print(f"Found {len(slope_tiles)} slope tiles:")
for t in slope_tiles:
    print(f"  {t.name}")

# Check source nodata values
srcs = [rasterio.open(t) for t in slope_tiles]
src_nodatas = [s.nodata for s in srcs]
print(f"\nSource nodata values: {set(src_nodatas)}")

# Merge — let each source use its own nodata metadata; output uses NaN
mosaic, transform = rio_merge(srcs)
for s in srcs:
    s.close()

data = mosaic[0].astype(np.float32)

# Convert any source nodata values present in the data to NaN
for nd in set(src_nodatas):
    if nd is not None:
        data[data == nd] = np.nan

# Cast to float16
data_f16 = data.astype(np.float16)

meta = srcs[0].meta.copy()
meta.update({
    "height": data_f16.shape[0],
    "width":  data_f16.shape[1],
    "transform": transform,
    "count": 1,
    "dtype": "float16",
    "nodata": np.float16("nan"),
    "compress": "deflate",
    "predictor": 1,
    "zlevel": 6,
})

print(f"\nWriting {OUT.name} as float16 ...")
with rasterio.open(OUT, "w", **meta) as dst:
    dst.write(data_f16, 1)

size_mb = OUT.stat().st_size / 1024**2
print(f"Done. {OUT.name}: {size_mb:.0f} MB")
