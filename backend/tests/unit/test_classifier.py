"""
Unit tests for the land use classification engine.
Tests spectral index calculations, synthetic training data generation,
and end-to-end raster classification logic.
"""

import numpy as np
import pytest

from app.services.gis.classifier import (
    SpectralIndexCalculator,
    LandUseClassifier,
    generate_synthetic_training_data,
    CLASS_MAP,
)


@pytest.fixture
def synthetic_bands():
    """Returns a 50x50 synthetic multi-band scene."""
    np.random.seed(42)
    H, W = 50, 50
    # Simulate vegetation: high NIR, low RED
    nir  = np.random.uniform(0.6, 0.9, (H, W)).astype("float32")
    red  = np.random.uniform(0.05, 0.2, (H, W)).astype("float32")
    green = np.random.uniform(0.1, 0.3, (H, W)).astype("float32")
    blue  = np.random.uniform(0.05, 0.15, (H, W)).astype("float32")
    swir1 = np.random.uniform(0.1, 0.3, (H, W)).astype("float32")
    swir2 = np.random.uniform(0.05, 0.2, (H, W)).astype("float32")
    return {"blue": blue, "green": green, "red": red, "nir": nir, "swir1": swir1, "swir2": swir2}


class TestSpectralIndexCalculator:
    def test_ndvi_range(self, synthetic_bands):
        calc = SpectralIndexCalculator(synthetic_bands)
        ndvi = calc.ndvi()
        assert ndvi.shape == (50, 50)
        assert ndvi.min() >= -1.0
        assert ndvi.max() <= 1.0

    def test_ndvi_vegetation_positive(self, synthetic_bands):
        """High NIR, low RED → positive NDVI (vegetation)."""
        calc = SpectralIndexCalculator(synthetic_bands)
        ndvi = calc.ndvi()
        assert ndvi.mean() > 0.4, "Expected high NDVI for synthetic vegetation scene"

    def test_ndwi_range(self, synthetic_bands):
        calc = SpectralIndexCalculator(synthetic_bands)
        ndwi = calc.ndwi()
        assert ndwi.min() >= -1.0
        assert ndwi.max() <= 1.0

    def test_ndbi_range(self, synthetic_bands):
        calc = SpectralIndexCalculator(synthetic_bands)
        ndbi = calc.ndbi()
        assert ndbi.shape == (50, 50)

    def test_bsi_no_nans(self, synthetic_bands):
        calc = SpectralIndexCalculator(synthetic_bands)
        bsi = calc.bsi()
        assert not np.any(np.isnan(bsi))

    def test_compute_all_shape(self, synthetic_bands):
        calc = SpectralIndexCalculator(synthetic_bands)
        features = calc.compute_all()
        assert features.shape == (50, 50, 5)

    def test_epsilon_avoids_division_by_zero(self):
        """All-zero bands should not produce NaN or Inf."""
        zero_bands = {k: np.zeros((10, 10), dtype="float32") for k in ["blue","green","red","nir","swir1","swir2"]}
        calc = SpectralIndexCalculator(zero_bands)
        for method in [calc.ndvi, calc.ndwi, calc.mndwi, calc.ndbi, calc.bsi]:
            result = method()
            assert not np.any(np.isnan(result))
            assert not np.any(np.isinf(result))


class TestSyntheticTrainingData:
    def test_returns_arrays(self, synthetic_bands):
        calc = SpectralIndexCalculator(synthetic_bands)
        features = calc.compute_all()
        valid_mask = np.ones((50, 50), dtype=bool)
        X, y = generate_synthetic_training_data(features, valid_mask, n_samples_per_class=100)
        assert X.ndim == 2
        assert y.ndim == 1
        assert X.shape[0] == y.shape[0]
        assert X.shape[1] == 5

    def test_classes_in_range(self, synthetic_bands):
        calc = SpectralIndexCalculator(synthetic_bands)
        features = calc.compute_all()
        valid_mask = np.ones((50, 50), dtype=bool)
        _, y = generate_synthetic_training_data(features, valid_mask, n_samples_per_class=50)
        assert set(y).issubset({1, 2, 3, 4})

    def test_empty_valid_mask_raises(self, synthetic_bands):
        calc = SpectralIndexCalculator(synthetic_bands)
        features = calc.compute_all()
        empty_mask = np.zeros((50, 50), dtype=bool)
        with pytest.raises(ValueError, match="No training samples"):
            generate_synthetic_training_data(features, empty_mask)


class TestLandUseClassifier:
    def test_untrained_predict_raises(self):
        clf = LandUseClassifier()
        with pytest.raises(RuntimeError, match="not been trained"):
            clf.predict(np.zeros((10, 5)))

    def test_train_and_predict(self, synthetic_bands):
        calc = SpectralIndexCalculator(synthetic_bands)
        features = calc.compute_all()
        valid_mask = np.ones((50, 50), dtype=bool)
        X, y = generate_synthetic_training_data(features, valid_mask, n_samples_per_class=200)

        clf = LandUseClassifier(n_estimators=10)
        clf.train(X, y)
        preds = clf.predict(X[:20])
        assert preds.shape == (20,)
        assert set(preds).issubset({1, 2, 3, 4})
        assert preds.dtype == np.uint8


class TestClassMap:
    def test_all_classes_have_required_keys(self):
        for class_id, meta in CLASS_MAP.items():
            assert "name" in meta
            assert "label" in meta
            assert "color" in meta
            assert meta["color"].startswith("#")
