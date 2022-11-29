"""Unit tests for the change detection engine."""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS

from app.services.gis.change_detector import ChangeDetector, CLASS_COLORS


def _write_classified_tif(path: str, data: np.ndarray) -> None:
    """Write a uint8 single-band classified GeoTIFF for testing."""
    H, W = data.shape
    transform = from_bounds(-97.0, 32.6, -96.5, 33.0, W, H)
    with rasterio.open(
        path, "w",
        driver="GTiff",
        width=W, height=H, count=1,
        dtype="uint8",
        crs=CRS.from_epsg(4326),
        transform=transform,
        nodata=0,
    ) as dst:
        dst.write(data.astype("uint8"), 1)


@pytest.fixture
def sample_classified_pair(tmp_path):
    """Creates a matching T1/T2 classified raster pair in a temp directory."""
    H, W = 30, 30
    t1 = np.ones((H, W), dtype=np.uint8)
    t1[:10, :] = 2   # vegetation in top third
    t1[20:, :] = 3   # water in bottom third

    t2 = t1.copy()
    # Simulate urban expansion: some vegetation → urban
    t2[5:10, :15] = 1

    t1_path = str(tmp_path / "t1_classified.tif")
    t2_path = str(tmp_path / "t2_classified.tif")
    _write_classified_tif(t1_path, t1)
    _write_classified_tif(t2_path, t2)
    return t1_path, t2_path, t1, t2


class TestChangeDetectorValidation:
    def test_validates_mismatched_crs(self, tmp_path):
        H, W = 10, 10
        arr = np.ones((H, W), dtype=np.uint8)
        transform = from_bounds(-97.0, 32.6, -96.5, 33.0, W, H)

        t1_path = str(tmp_path / "t1.tif")
        t2_path = str(tmp_path / "t2.tif")

        for path, epsg in [(t1_path, 4326), (t2_path, 32614)]:
            with rasterio.open(
                path, "w", driver="GTiff", width=W, height=H, count=1,
                dtype="uint8", crs=CRS.from_epsg(epsg), transform=transform
            ) as dst:
                dst.write(arr, 1)

        with pytest.raises(ValueError, match="CRS mismatch"):
            ChangeDetector(t1_path, t2_path)


class TestChangeDetectorRun:
    def test_run_returns_expected_keys(self, sample_classified_pair, tmp_path):
        t1_path, t2_path, _, _ = sample_classified_pair
        detector = ChangeDetector(t1_path, t2_path)
        result = detector.run(str(tmp_path / "output"))
        assert "change_raster_path" in result
        assert "change_png_path" in result
        assert "statistics" in result

    def test_output_files_exist(self, sample_classified_pair, tmp_path):
        t1_path, t2_path, _, _ = sample_classified_pair
        out_dir = tmp_path / "output"
        detector = ChangeDetector(t1_path, t2_path)
        result = detector.run(str(out_dir))
        assert Path(result["change_raster_path"]).exists()
        assert Path(result["change_png_path"]).exists()

    def test_statistics_structure(self, sample_classified_pair, tmp_path):
        t1_path, t2_path, _, _ = sample_classified_pair
        detector = ChangeDetector(t1_path, t2_path)
        result = detector.run(str(tmp_path / "output"))
        stats = result["statistics"]

        assert "t1" in stats
        assert "t2" in stats
        assert "change" in stats
        assert "summary" in stats
        assert "transition_matrix" in stats

        assert stats["summary"]["total_valid_pixels"] > 0
        assert stats["summary"]["total_area_km2"] > 0

    def test_change_detected(self, sample_classified_pair, tmp_path):
        t1_path, t2_path, _, _ = sample_classified_pair
        detector = ChangeDetector(t1_path, t2_path)
        result = detector.run(str(tmp_path / "output"))
        changed = result["statistics"]["summary"]["total_changed_pixels"]
        assert changed > 0, "Expected non-zero change between T1 and T2 scenes"

    def test_statistics_json_written(self, sample_classified_pair, tmp_path):
        t1_path, t2_path, _, _ = sample_classified_pair
        out_dir = tmp_path / "output"
        detector = ChangeDetector(t1_path, t2_path)
        detector.run(str(out_dir))
        stats_file = out_dir / "statistics.json"
        assert stats_file.exists()
        with open(stats_file) as f:
            data = json.load(f)
        assert "summary" in data

    def test_class_colors_valid(self):
        for class_id, rgba in CLASS_COLORS.items():
            assert len(rgba) == 4
            assert all(0 <= v <= 255 for v in rgba)
