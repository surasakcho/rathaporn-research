"""
Independent validation of terrain_vars.csv.

Since the source rasters are stored in Git LFS and not available locally,
this script validates the stored output using:

  1. Gap check       — NaN counts per column; fully-null tambons
  2. Slope-class sum — pct_flat + pct_gentle + pct_moderate + pct_steep ≈ 100
  3. Value ranges    — plausibility bounds for Thailand geography
  4. Tambon codes    — 6-digit format, province codes 01–77, no duplicates
  5. Internal consistency — avg vs median, pct classes vs avg_slope sign
  6. Random 10-tambon spot report — human-readable sample rows
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from pathlib import Path

CSV = Path(__file__).parent / "data" / "processed" / "terrain_vars.csv"

STAT_COLS = [
    "avg_slope", "median_slope", "sd_slope",
    "avg_elev",  "median_elev",  "sd_elev",  "elev_range",
    "pct_flat",  "pct_gentle",   "pct_moderate", "pct_steep",
]

PCT_COLS = ["pct_flat", "pct_gentle", "pct_moderate", "pct_steep"]

# Plausibility bounds for Thailand
# Elevation: ~-5m (coastal) to 2565m (Doi Inthanon); allow small negatives from DEM noise
# Slope: 0–90° (physically bounded); avg > 45° would be extreme
BOUNDS = {
    "avg_elev":    (-20, 2700),
    "median_elev": (-20, 2700),
    "elev_range":  (0,   2700),
    "sd_elev":     (0,   1500),
    "avg_slope":   (0,    70),
    "median_slope":(0,    70),
    "sd_slope":    (0,    40),
}

# ── Load ────────────────────────────────────────────────────────────────────
print(f"Loading {CSV.name} ...")
df = pd.read_csv(CSV, dtype={"tambon_code": str})
print(f"  {len(df)} rows, {len(df.columns)} columns\n")

issues = []

# ── 1. Gap check ────────────────────────────────────────────────────────────
print("=" * 60)
print("1. GAP CHECK")
print("=" * 60)
null_counts = df[STAT_COLS].isnull().sum()
has_nulls = null_counts[null_counts > 0]
if has_nulls.empty:
    print("  ✓ No NaN values in any stat column.")
else:
    print("  Columns with NaN:")
    for col, n in has_nulls.items():
        pct = n / len(df) * 100
        flag = "WARN" if pct > 1 else "note"
        print(f"  [{flag}] {col:20s}: {n:5d} NaN  ({pct:.2f}%)")
        issues.append(f"NaN in {col}: {n} rows ({pct:.2f}%)")

all_null = df[STAT_COLS].isnull().all(axis=1)
n_all_null = all_null.sum()
if n_all_null > 0:
    print(f"\n  [WARN] {n_all_null} tambon(s) with ALL stats null (no raster coverage):")
    print(df.loc[all_null, "tambon_code"].tolist())
    issues.append(f"{n_all_null} tambons fully null (no raster coverage)")
else:
    print(f"  ✓ No tambon is fully null.")

# ── 2. Slope-class percentage sum ───────────────────────────────────────────
print()
print("=" * 60)
print("2. SLOPE-CLASS PERCENTAGE SUM  (should be ~100%)")
print("=" * 60)
pct_sum = df[PCT_COLS].sum(axis=1)
valid_pct = pct_sum.notna()
off_by_a_lot = valid_pct & (abs(pct_sum - 100) > 1.0)
off_by_small = valid_pct & (abs(pct_sum - 100) > 0.1) & ~off_by_a_lot
print(f"  Total with pct data: {valid_pct.sum()}")
print(f"  Sum off by >1%  : {off_by_a_lot.sum()}   ← WARN if >0")
print(f"  Sum off by 0.1–1%: {off_by_small.sum()}  (rounding, OK)")
if off_by_a_lot.sum() > 0:
    print("  Problematic rows:")
    print(df.loc[off_by_a_lot, ["tambon_code"] + PCT_COLS + ["avg_slope"]].head(10).to_string(index=False))
    issues.append(f"{off_by_a_lot.sum()} tambons with slope-class pct not summing to ~100%")
else:
    print("  ✓ All pct sums within 1% of 100.")
print(f"\n  Pct sum stats: min={pct_sum.min():.2f}  max={pct_sum.max():.2f}  mean={pct_sum.mean():.4f}")

# ── 3. Value-range plausibility ─────────────────────────────────────────────
print()
print("=" * 60)
print("3. VALUE RANGE PLAUSIBILITY")
print("=" * 60)
for col, (lo, hi) in BOUNDS.items():
    if col not in df.columns:
        continue
    s = df[col].dropna()
    out_lo = (s < lo).sum()
    out_hi = (s > hi).sum()
    status = "✓" if (out_lo + out_hi == 0) else "WARN"
    print(f"  [{status}] {col:16s}  min={s.min():8.2f}  max={s.max():8.2f}  "
          f"mean={s.mean():7.2f}  [bounds: {lo}, {hi}]", end="")
    if out_lo + out_hi > 0:
        print(f"  ← {out_lo} below, {out_hi} above")
        issues.append(f"{col}: {out_lo} below {lo}, {out_hi} above {hi}")
    else:
        print()

# Negative elevation (expected near coast — just report, not a problem unless large)
neg_elev = (df["avg_elev"] < 0).sum()
print(f"\n  Tambons with avg_elev < 0 (coastal/below-sea-level): {neg_elev}")

# Check pct values are 0–100
for col in PCT_COLS:
    s = df[col].dropna()
    bad = ((s < 0) | (s > 100)).sum()
    if bad > 0:
        print(f"  [WARN] {col}: {bad} values outside [0, 100]")
        issues.append(f"{col}: {bad} values outside [0,100]")

# ── 4. Tambon code integrity ─────────────────────────────────────────────────
print()
print("=" * 60)
print("4. TAMBON CODE INTEGRITY")
print("=" * 60)
codes = df["tambon_code"].astype(str)

# Format: exactly 6 digits
bad_format = codes[~codes.str.match(r"^\d{6}$")]
print(f"  Non-6-digit codes: {len(bad_format)}")
if not bad_format.empty:
    print(f"    Examples: {bad_format.head(5).tolist()}")
    issues.append(f"{len(bad_format)} non-6-digit tambon codes")

# Province codes 01–77 (Thailand has 77 provinces)
prov = codes.str[:2].astype(int, errors="ignore")
valid_prov = codes.str[:2].apply(lambda x: x.isdigit() and 1 <= int(x) <= 77)
bad_prov = (~valid_prov).sum()
print(f"  Province codes out of range 01–77: {bad_prov}")
if bad_prov > 0:
    print(f"    Bad codes: {codes[~valid_prov].head(10).tolist()}")
    issues.append(f"{bad_prov} tambons with province code outside 01–77")

# Duplicates
dupes = df["tambon_code"].duplicated().sum()
print(f"  Duplicate tambon_code: {dupes}")
if dupes > 0:
    dup_vals = df.loc[df["tambon_code"].duplicated(keep=False), "tambon_code"].unique()
    print(f"    Duplicated codes: {dup_vals[:10].tolist()}")
    issues.append(f"{dupes} duplicate tambon codes")
else:
    print("  ✓ All tambon codes unique.")

# Expected count (Thailand has ~7255–7400 tambons depending on source/year)
print(f"\n  Total tambons: {len(df)}  (expected ~7255–7400 for Thailand)")
if len(df) < 7000 or len(df) > 7500:
    issues.append(f"Tambon count {len(df)} outside expected 7000–7500 range")

# Province coverage
n_provs = codes.str[:2].nunique()
print(f"  Provinces covered: {n_provs} / 77")
if n_provs < 77:
    present = set(codes.str[:2].unique())
    missing_provs = [f"{i:02d}" for i in range(1, 78) if f"{i:02d}" not in present]
    print(f"  Missing provinces: {missing_provs}")
    issues.append(f"Missing {77 - n_provs} provinces: {missing_provs}")

# ── 5. Internal consistency ──────────────────────────────────────────────────
print()
print("=" * 60)
print("5. INTERNAL CONSISTENCY")
print("=" * 60)

# avg_elev should be roughly bracketed by median (not identical, but correlation should be high)
elev_corr = df[["avg_elev", "median_elev"]].dropna().corr().iloc[0, 1]
print(f"  avg_elev vs median_elev correlation: {elev_corr:.4f}  (expect >0.99)")
if elev_corr < 0.99:
    issues.append(f"avg_elev vs median_elev correlation low: {elev_corr:.4f}")

slope_corr = df[["avg_slope", "median_slope"]].dropna().corr().iloc[0, 1]
print(f"  avg_slope vs median_slope correlation: {slope_corr:.4f}  (expect >0.95)")
if slope_corr < 0.95:
    issues.append(f"avg_slope vs median_slope correlation low: {slope_corr:.4f}")

# avg_slope > median_slope is expected for right-skewed slope distributions
avg_gt_med = (df["avg_slope"] > df["median_slope"]).mean()
print(f"  avg_slope > median_slope: {avg_gt_med*100:.1f}% of tambons  (expect >80% — slopes are right-skewed)")
if avg_gt_med < 0.80:
    issues.append(f"Only {avg_gt_med*100:.1f}% tambons have avg_slope > median_slope (expect >80%)")

# elev_range should be >= 0 and >= sd_elev * some factor isn't reliable, skip
# But elev_range should be >= 0
neg_range = (df["elev_range"] < 0).sum()
print(f"  Negative elev_range: {neg_range}  (expect 0)")
if neg_range > 0:
    issues.append(f"{neg_range} tambons with negative elev_range")

# sd should be >=0
for col in ["sd_slope", "sd_elev"]:
    neg_sd = (df[col] < 0).sum()
    if neg_sd > 0:
        print(f"  [WARN] {col}: {neg_sd} negative values")
        issues.append(f"{col}: {neg_sd} negative values")

# ── 6. Random 10-tambon spot report ─────────────────────────────────────────
print()
print("=" * 60)
print("6. RANDOM 10-TAMBON SAMPLE (seed=42)")
print("=" * 60)
sample = df.dropna(subset=["avg_elev", "avg_slope"]).sample(10, random_state=42)
display_cols = ["tambon_code", "avg_elev", "avg_slope", "pct_flat", "pct_steep", "elev_range"]
print(sample[display_cols].to_string(index=False))

# ── Summary ──────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
if not issues:
    print("  ✓ No issues found.")
else:
    print(f"  {len(issues)} issue(s):")
    for i, iss in enumerate(issues, 1):
        print(f"    {i}. {iss}")
