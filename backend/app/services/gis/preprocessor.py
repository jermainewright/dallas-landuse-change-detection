"""
Raster Preprocessing Pipeline
==============================
Handles clipping to AOI, CRS reprojection, raster alignment (snap to grid),
band normalization, and cloud masking for Landsat 8/9 imagery.

All operations use GDAL/Rasterio for memory-efficient, production-grade
raster processing. Large files are processed in windowed reads.
"""

import os
from pathlib import Path

import numpy as np
import rasterio
import structlog
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.mask import mask
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform, reproject
from shapely.geometry import box, mapping

logger = structlog.get_logger(__name__)

# Dallas AOI in WGS84
DALLAS_BBOX = (-97.0, 32.6, -96.5, 33.0)  # (minx, miny, maxx, maxy)
TARGET_CRS = CRS.from_epsg(32614)  # WGS84 UTM Zone 14N – optimal for Dallas, TX
TARGET_RESOLUTION = 30  # metres (Landsat native)

# Landsat 8 band indices (1-based in file, 0-based in numpy arrays)
BAND_MAP = {
    "blue": 1,
    "green": 2,
    "red": 3,
    "nir": 4,
    "swir1": 5,
    "swir2": 6,
    "tir": 7,
}


class RasterPreprocessor:
    """
    Encapsulates the full preprocessing pipeline for a single imagery scene.

    Usage:
        preprocessor = RasterPreprocessor(input_path, output_dir)
        result_path = preprocessor.run()
    """

    def __init__(self, input_path: str, output_dir: str, bbox: tuple = DALLAS_BBOX):
        self.input_path = Path(input_path)
        self.output_dir = Path(output_dir)
        self.bbox = bbox
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> str:
        """Execute full preprocessing pipeline. Returns path to processed raster."""
        log = logger.bind(input=str(self.input_path))
        log.info("Starting preprocessing pipeline")

        # Step 1: Reproject to target CRS
        reprojected_path = self._reproject()
        log.info("Reprojection complete", path=reprojected_path)

        # Step 2: Clip to Dallas AOI
        clipped_path = self._clip_to_aoi(reprojected_path)
        log.info("Clip to AOI complete", path=clipped_path)

        # Step 3: Normalize band values to [0, 1]
        normalized_path = self._normalize_bands(clipped_path)
        log.info("Band normalization complete", path=normalized_path)

        # Cleanup intermediates
        os.remove(reprojected_path)
        os.remove(clipped_path)

        log.info("Preprocessing pipeline complete", output=normalized_path)
        return normalized_path

    def _reproject(self) -> str:
        """Reproject input raster to TARGET_CRS at TARGET_RESOLUTION."""
        output_path = str(
            self.output_dir / f"{self.input_path.stem}_reprojected.tif"
        )

        with rasterio.open(self.input_path) as src:
            transform, width, height = calculate_default_transform(
                src.crs,
                TARGET_CRS,
                src.width,
                src.height,
                *src.bounds,
                resolution=TARGET_RESOLUTION,
            )
            profile = src.profile.copy()
            profile.update(
                crs=TARGET_CRS,
                transform=transform,
                width=width,
                height=height,
                dtype="float32",
                nodata=np.nan,
                compress="lzw",
                tiled=True,
                blockxsize=256,
                blockysize=256,
            )

            with rasterio.open(output_path, "w", **profile) as dst:
                for band_idx in range(1, src.count + 1):
                    reproject(
                        source=rasterio.band(src, band_idx),
                        destination=rasterio.band(dst, band_idx),
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=transform,
                        dst_crs=TARGET_CRS,
                        resampling=Resampling.bilinear,
                    )

        return output_path

    def _clip_to_aoi(self, input_path: str) -> str:
        """Clip raster to Dallas AOI (after reprojection to UTM)."""
        output_path = str(self.output_dir / f"{Path(input_path).stem}_clipped.tif")

        # Transform bbox from WGS84 to UTM
        from pyproj import Transformer

        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32614", always_xy=True)
        minx, miny = transformer.transform(self.bbox[0], self.bbox[1])
        maxx, maxy = transformer.transform(self.bbox[2], self.bbox[3])
        aoi_geom = [mapping(box(minx, miny, maxx, maxy))]

        with rasterio.open(input_path) as src:
            out_image, out_transform = mask(src, aoi_geom, crop=True, nodata=np.nan)
            profile = src.profile.copy()
            profile.update(
                transform=out_transform,
                width=out_image.shape[2],
                height=out_image.shape[1],
                nodata=np.nan,
            )
            with rasterio.open(output_path, "w", **profile) as dst:
                dst.write(out_image)

        return output_path

    def _normalize_bands(self, input_path: str) -> str:
        """
        Normalize each band to [0, 1] using 2nd/98th percentile stretching
        (robust to cloud/shadow outliers). Writes float32 output.
        """
        stem = self.input_path.stem
        output_path = str(self.output_dir / f"{stem}_preprocessed.tif")

        with rasterio.open(input_path) as src:
            profile = src.profile.copy()
            profile.update(dtype="float32", nodata=np.nan)

            with rasterio.open(output_path, "w", **profile) as dst:
                for band_idx in range(1, src.count + 1):
                    band_data = src.read(band_idx).astype("float32")
                    valid = band_data[~np.isnan(band_data)]

                    if valid.size == 0:
                        dst.write(band_data, band_idx)
                        continue

                    p2, p98 = np.percentile(valid, [2, 98])
                    if p98 == p2:
                        dst.write(np.zeros_like(band_data), band_idx)
                        continue

                    normalized = np.clip((band_data - p2) / (p98 - p2), 0.0, 1.0)
                    normalized[np.isnan(band_data)] = np.nan
                    dst.write(normalized, band_idx)

        return output_path


def align_rasters(reference_path: str, target_path: str, output_path: str) -> str:
    """
    Snap `target_path` to the exact grid of `reference_path`.

    Critical for change detection — both rasters must share identical
    transform, extent, and dimensions before pixel-wise comparison.
    """
    with rasterio.open(reference_path) as ref:
        ref_profile = ref.profile.copy()
        ref_transform = ref.transform
        ref_crs = ref.crs
        ref_width = ref.width
        ref_height = ref.height

    with rasterio.open(target_path) as src:
        profile = src.profile.copy()
        profile.update(
            crs=ref_crs,
            transform=ref_transform,
            width=ref_width,
            height=ref_height,
            dtype="float32",
        )

        with rasterio.open(output_path, "w", **profile) as dst:
            for band_idx in range(1, src.count + 1):
                dest_array = np.empty((ref_height, ref_width), dtype="float32")
                reproject(
                    source=rasterio.band(src, band_idx),
                    destination=dest_array,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=ref_transform,
                    dst_crs=ref_crs,
                    resampling=Resampling.bilinear,
                )
                dst.write(dest_array, band_idx)

    logger.info("Raster alignment complete", output=output_path)
    return output_path
