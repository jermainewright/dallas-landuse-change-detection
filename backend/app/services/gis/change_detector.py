"""
Change Detection Engine
========================
Implements pixel-wise land use change detection between two classified rasters.

Algorithm:
    For each pixel, encode change as: change_code = (class_t1 * 10) + class_t2
    This produces a 'from-to' change matrix enabling transition analysis
    (e.g., code 21 = vegetation → urban, code 32 = water → vegetation).

Outputs:
    - change_raster.tif  : Integer raster with change codes
    - change_map.png     : RGBA colour composite for web display
    - statistics dict    : Per-class areas, percentages, deltas

Reference:
    Jensen, J.R. (2016). Introductory Digital Image Processing:
    A Remote Sensing Perspective. 4th ed. Pearson.
"""

import json
from pathlib import Path

import numpy as np
import rasterio
import structlog
from PIL import Image
from rasterio.transform import from_bounds

logger = structlog.get_logger(__name__)

# Class colours for PNG output (RGBA)
CLASS_COLORS = {
    0: (128, 128, 128, 0),    # No data – transparent
    1: (231, 76, 60, 255),    # Urban – red
    2: (39, 174, 96, 255),    # Vegetation – green
    3: (41, 128, 185, 255),   # Water – blue
    4: (230, 126, 34, 255),   # Bare Soil – orange
}

# Change highlight colour (magenta) – indicates meaningful change
CHANGE_COLOR = (220, 20, 220, 200)
NO_CHANGE_COLOR = (255, 255, 255, 40)


class ChangeDetector:
    """
    Pixel-wise change detection between two classified rasters.

    The rasters MUST share identical CRS, transform, and dimensions.
    Use preprocessor.align_rasters() to ensure this before calling.
    """

    def __init__(self, classified_t1_path: str, classified_t2_path: str):
        self.t1_path = classified_t1_path
        self.t2_path = classified_t2_path
        self._validate_inputs()

    def _validate_inputs(self) -> None:
        with rasterio.open(self.t1_path) as t1, rasterio.open(self.t2_path) as t2:
            if t1.crs != t2.crs:
                raise ValueError(
                    f"CRS mismatch: T1={t1.crs}, T2={t2.crs}. "
                    "Run align_rasters() before change detection."
                )
            if t1.shape != t2.shape:
                raise ValueError(
                    f"Shape mismatch: T1={t1.shape}, T2={t2.shape}."
                )

    def run(
        self, output_dir: str
    ) -> dict:
        """
        Execute change detection pipeline.

        Returns dict containing:
            change_raster_path: str
            change_png_path: str
            statistics: dict
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        with rasterio.open(self.t1_path) as src_t1:
            arr_t1 = src_t1.read(1).astype(np.int16)
            profile = src_t1.profile.copy()
            pixel_area_m2 = abs(src_t1.transform.a * src_t1.transform.e)
            pixel_area_km2 = pixel_area_m2 / 1_000_000

        with rasterio.open(self.t2_path) as src_t2:
            arr_t2 = src_t2.read(1).astype(np.int16)

        # ─── Compute change code ──────────────────────────────────────────────
        # change_code = t1_class * 10 + t2_class
        # Example: 21 means class 2 → class 1 (vegetation to urban)
        valid_mask = (arr_t1 > 0) & (arr_t2 > 0)
        change_raster = np.zeros_like(arr_t1, dtype=np.int16)
        change_raster[valid_mask] = arr_t1[valid_mask] * 10 + arr_t2[valid_mask]

        # ─── Write change raster ──────────────────────────────────────────────
        change_raster_path = str(output_dir / "change_raster.tif")
        profile.update(dtype="int16", count=1, nodata=0, compress="lzw")
        with rasterio.open(change_raster_path, "w", **profile) as dst:
            dst.write(change_raster.astype("int16"), 1)
            dst.update_tags(
                DESCRIPTION="Change detection encoded as T1_class*10 + T2_class",
                SAME_CLASS_EXAMPLE="11=urban→urban, 22=veg→veg",
                CHANGE_EXAMPLE="21=veg→urban, 31=water→urban",
            )

        # ─── Generate change map PNG ──────────────────────────────────────────
        change_png_path = str(output_dir / "change_map.png")
        self._generate_change_png(arr_t1, arr_t2, valid_mask, change_png_path)

        # ─── Compute statistics ───────────────────────────────────────────────
        statistics = self._compute_statistics(
            arr_t1, arr_t2, valid_mask, pixel_area_km2
        )

        # Write stats JSON
        stats_path = str(output_dir / "statistics.json")
        with open(stats_path, "w") as f:
            json.dump(statistics, f, indent=2, default=str)

        logger.info(
            "Change detection complete",
            change_raster=change_raster_path,
            change_png=change_png_path,
            total_changed_km2=statistics["summary"]["total_changed_km2"],
        )

        return {
            "change_raster_path": change_raster_path,
            "change_png_path": change_png_path,
            "statistics": statistics,
        }

    def _generate_change_png(
        self,
        arr_t1: np.ndarray,
        arr_t2: np.ndarray,
        valid_mask: np.ndarray,
        output_path: str,
    ) -> None:
        """
        Generate RGBA PNG for web map overlay.
        Pixels with change are highlighted; unchanged pixels are semi-transparent.
        """
        H, W = arr_t1.shape
        rgba = np.zeros((H, W, 4), dtype=np.uint8)

        # Colour by T2 classification for context
        for class_id, color in CLASS_COLORS.items():
            mask = (arr_t2 == class_id) & valid_mask
            rgba[mask] = color

        # Highlight changed pixels
        changed = valid_mask & (arr_t1 != arr_t2)
        unchanged = valid_mask & (arr_t1 == arr_t2)
        rgba[changed] = CHANGE_COLOR
        rgba[unchanged, 3] = 60  # Semi-transparent for unchanged

        img = Image.fromarray(rgba, mode="RGBA")
        img.save(output_path, format="PNG", optimize=True)

    def _compute_statistics(
        self,
        arr_t1: np.ndarray,
        arr_t2: np.ndarray,
        valid_mask: np.ndarray,
        pixel_area_km2: float,
    ) -> dict:
        """Compute per-class area statistics and change matrix."""
        class_names = {1: "urban", 2: "vegetation", 3: "water", 4: "bare_soil"}
        total_valid = valid_mask.sum()

        def class_stats(arr: np.ndarray, period: str) -> dict:
            stats = {}
            for class_id, name in class_names.items():
                count = int(((arr == class_id) & valid_mask).sum())
                area_km2 = round(count * pixel_area_km2, 4)
                pct = round((count / max(total_valid, 1)) * 100, 2)
                stats[name] = {
                    "pixel_count": count,
                    "area_km2": area_km2,
                    "area_percent": pct,
                    "period": period,
                }
            return stats

        t1_stats = class_stats(arr_t1, "t1")
        t2_stats = class_stats(arr_t2, "t2")

        # Compute change per class
        change_stats = {}
        for name in class_names.values():
            delta_km2 = round(t2_stats[name]["area_km2"] - t1_stats[name]["area_km2"], 4)
            pct_change = round(
                (delta_km2 / max(t1_stats[name]["area_km2"], 0.0001)) * 100, 2
            )
            change_stats[name] = {
                "delta_km2": delta_km2,
                "percent_change": pct_change,
                "direction": "gain" if delta_km2 > 0 else "loss" if delta_km2 < 0 else "stable",
            }

        # Transition matrix (from-to pixel counts)
        transition_matrix = {}
        for from_id, from_name in class_names.items():
            transition_matrix[from_name] = {}
            for to_id, to_name in class_names.items():
                count = int(
                    (valid_mask & (arr_t1 == from_id) & (arr_t2 == to_id)).sum()
                )
                transition_matrix[from_name][to_name] = {
                    "pixel_count": count,
                    "area_km2": round(count * pixel_area_km2, 4),
                }

        # Summary
        changed_pixels = int((valid_mask & (arr_t1 != arr_t2)).sum())
        total_changed_km2 = round(changed_pixels * pixel_area_km2, 4)
        change_pct = round((changed_pixels / max(total_valid, 1)) * 100, 2)

        return {
            "t1": t1_stats,
            "t2": t2_stats,
            "change": change_stats,
            "transition_matrix": transition_matrix,
            "summary": {
                "total_valid_pixels": int(total_valid),
                "total_area_km2": round(total_valid * pixel_area_km2, 4),
                "total_changed_pixels": changed_pixels,
                "total_changed_km2": total_changed_km2,
                "total_changed_percent": change_pct,
                "pixel_area_km2": pixel_area_km2,
            },
        }
