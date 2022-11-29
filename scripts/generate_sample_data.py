#!/usr/bin/env python3
"""
Generate synthetic Landsat-style multi-band GeoTIFF test scenes
for Dallas, Texas — usable without real satellite imagery.

Produces two scenes (2015 and 2023) with realistic spectral signatures
for urban, vegetation, water, and bare soil land cover types.
Simulates Dallas-Fort Worth metropolitan sprawl between the two dates.

Usage:
    python scripts/generate_sample_data.py --output-dir ./data/rasters/sample
"""

import argparse
from pathlib import Path
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

# Dallas AOI (UTM Zone 14N, EPSG:32614)
# Approximate bbox in degrees: -97.0–-96.5 W, 32.6–33.0 N
# In UTM14N: roughly 700000–740000 E, 3610000–3655000 N
BBOX_UTM = (700000, 3_610_000, 740_000, 3_655_000)  # minx, miny, maxx, maxy

RESOLUTION = 30  # metres
WIDTH  = int((BBOX_UTM[2] - BBOX_UTM[0]) / RESOLUTION)   # ~1333 px
HEIGHT = int((BBOX_UTM[3] - BBOX_UTM[1]) / RESOLUTION)   # ~1500 px

# Downsample for quick test generation
SCALE = 10  # Use 1/10 scale for speed
W = WIDTH  // SCALE
H = HEIGHT // SCALE

BAND_NAMES = ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"]

# Spectral signatures per land class (approx. surface reflectance, 0-1)
SPECTRAL_SIGNATURES = {
    "water":      [0.05, 0.08, 0.05, 0.02, 0.01, 0.01],
    "vegetation": [0.04, 0.10, 0.05, 0.45, 0.20, 0.10],
    "urban":      [0.18, 0.20, 0.22, 0.25, 0.30, 0.28],
    "bare_soil":  [0.20, 0.22, 0.25, 0.28, 0.35, 0.32],
}


def make_land_mask(h: int, w: int, seed: int) -> np.ndarray:
    """Create a spatial land class mask (0=water, 1=veg, 2=urban, 3=bare)."""
    np.random.seed(seed)
    from scipy.ndimage import gaussian_filter
    noise = gaussian_filter(np.random.randn(h, w), sigma=8)
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[noise > 0.8] = 0   # water (Trinity River corridor)
    mask[(noise > 0.0) & (noise <= 0.8)] = 1  # vegetation (eastern greenbelts)
    mask[(noise > -0.5) & (noise <= 0.0)] = 2  # urban (DFW metro core)
    mask[noise <= -0.5] = 3  # bare soil (construction, prairie)
    return mask


def scene_to_array(mask: np.ndarray) -> np.ndarray:
    """Convert class mask to 6-band reflectance array."""
    h, w = mask.shape
    arr = np.zeros((6, h, w), dtype=np.float32)
    classes = ["water", "vegetation", "urban", "bare_soil"]
    for cls_id, cls_name in enumerate(classes):
        sig = np.array(SPECTRAL_SIGNATURES[cls_name], dtype=np.float32)
        for b in range(6):
            noise = np.random.normal(0, 0.01, (h, w)).astype(np.float32)
            arr[b][mask == cls_id] = sig[b]
            arr[b] += noise
    arr = np.clip(arr, 0, 1)
    return arr


def write_scene(arr: np.ndarray, path: str, year: int) -> None:
    transform = from_bounds(*BBOX_UTM, arr.shape[2], arr.shape[1])
    with rasterio.open(
        path, "w",
        driver="GTiff",
        width=arr.shape[2],
        height=arr.shape[1],
        count=6,
        dtype="float32",
        crs=CRS.from_epsg(32614),
        transform=transform,
        compress="lzw",
        nodata=np.nan,
    ) as dst:
        dst.write(arr)
        for i, name in enumerate(BAND_NAMES, 1):
            dst.update_tags(i, name=name)
        dst.update_tags(
            satellite="Landsat8_Simulated",
            acquisition_year=str(year),
            aoi="Dallas_Texas",
        )
    print(f"  Written: {path} ({arr.shape[2]}x{arr.shape[1]} px, 6 bands)")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic Dallas, TX scenes")
    parser.add_argument("--output-dir", default="./data/rasters/sample")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Generating synthetic Dallas scenes ({W}x{H} px @ {RESOLUTION*SCALE}m res)…")

    # T1 – 2015 (less urban)
    print("T1 (2015):")
    mask_2015 = make_land_mask(H, W, seed=42)
    arr_2015 = scene_to_array(mask_2015)
    write_scene(arr_2015, str(out / "dallas_2015_L8.tif"), year=2015)

    # T2 – 2023 (more urban: DFW sprawl replaces vegetation and bare soil)
    print("T2 (2023):")
    mask_2023 = mask_2015.copy()
    veg_indices = np.argwhere(mask_2023 == 1)
    n_urbanize = int(len(veg_indices) * 0.15)  # 15% vegetation → urban
    chosen = veg_indices[np.random.choice(len(veg_indices), n_urbanize, replace=False)]
    mask_2023[chosen[:, 0], chosen[:, 1]] = 2
    arr_2023 = scene_to_array(mask_2023)
    write_scene(arr_2023, str(out / "dallas_2023_L8.tif"), year=2023)

    print(f"\nDone. Upload both scenes via the web UI or API to begin analysis.")
    print(f"Output directory: {out.resolve()}")


if __name__ == "__main__":
    main()
