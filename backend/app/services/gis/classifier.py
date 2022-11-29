"""
Land Use Classification Engine
================================
Implements a two-stage classification pipeline:

Stage 1 – Spectral Index Features
    Computes NDVI, NDWI, NDBI, MNDWI from Landsat bands. These indices
    are robust, physically interpretable, and highly effective for
    urban/vegetation/water discrimination.

Stage 2 – Random Forest Classifier
    Trained on synthetic training data derived from spectral rules.
    In a production deployment, this would be replaced with ground-truth
    training polygons sampled from the imagery.

Output Classes:
    0 = No Data / Cloud
    1 = Urban / Built-up
    2 = Vegetation
    3 = Water
    4 = Bare Soil

Reference:
    Zha, Y., Gao, J., & Ni, S. (2003). Use of normalized difference
    built-up index in automatically mapping urban areas from TM imagery.
    International Journal of Remote Sensing, 24(3), 583–594.
"""

from pathlib import Path
from typing import Optional

import numpy as np
import rasterio
import structlog
from rasterio.features import shapes
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

logger = structlog.get_logger(__name__)

# Class definitions
CLASS_MAP = {
    0: {"name": "no_data", "label": "No Data / Cloud", "color": "#808080"},
    1: {"name": "urban", "label": "Urban / Built-up", "color": "#E74C3C"},
    2: {"name": "vegetation", "label": "Vegetation", "color": "#27AE60"},
    3: {"name": "water", "label": "Water", "color": "#2980B9"},
    4: {"name": "bare_soil", "label": "Bare Soil", "color": "#E67E22"},
}


class SpectralIndexCalculator:
    """Computes remote sensing spectral indices from multi-band raster."""

    def __init__(self, bands: dict[str, np.ndarray]):
        """
        Args:
            bands: dict mapping band name → 2D float32 array.
                   Expected keys: 'blue', 'green', 'red', 'nir', 'swir1', 'swir2'
        """
        self.bands = bands
        self._epsilon = 1e-10  # avoid division by zero

    def ndvi(self) -> np.ndarray:
        """
        Normalised Difference Vegetation Index
        NDVI = (NIR - RED) / (NIR + RED)
        Range: -1 (water/urban) to +1 (dense vegetation)
        """
        nir = self.bands["nir"].astype("float32")
        red = self.bands["red"].astype("float32")
        return (nir - red) / (nir + red + self._epsilon)

    def ndwi(self) -> np.ndarray:
        """
        Normalised Difference Water Index (McFeeters 1996)
        NDWI = (GREEN - NIR) / (GREEN + NIR)
        Positive values indicate water bodies.
        """
        green = self.bands["green"].astype("float32")
        nir = self.bands["nir"].astype("float32")
        return (green - nir) / (green + nir + self._epsilon)

    def mndwi(self) -> np.ndarray:
        """
        Modified NDWI (Xu 2006) – better at suppressing built-up noise
        MNDWI = (GREEN - SWIR1) / (GREEN + SWIR1)
        """
        green = self.bands["green"].astype("float32")
        swir1 = self.bands["swir1"].astype("float32")
        return (green - swir1) / (green + swir1 + self._epsilon)

    def ndbi(self) -> np.ndarray:
        """
        Normalised Difference Built-up Index (Zha et al., 2003)
        NDBI = (SWIR1 - NIR) / (SWIR1 + NIR)
        Positive values indicate built-up / urban areas.
        """
        swir1 = self.bands["swir1"].astype("float32")
        nir = self.bands["nir"].astype("float32")
        return (swir1 - nir) / (swir1 + nir + self._epsilon)

    def bsi(self) -> np.ndarray:
        """
        Bare Soil Index
        BSI = ((SWIR1 + RED) - (NIR + BLUE)) / ((SWIR1 + RED) + (NIR + BLUE))
        """
        swir1 = self.bands["swir1"].astype("float32")
        red = self.bands["red"].astype("float32")
        nir = self.bands["nir"].astype("float32")
        blue = self.bands["blue"].astype("float32")
        return ((swir1 + red) - (nir + blue)) / (
            (swir1 + red) + (nir + blue) + self._epsilon
        )

    def compute_all(self) -> np.ndarray:
        """
        Returns stacked feature array of shape (H, W, 5).
        Features: [NDVI, NDWI, MNDWI, NDBI, BSI]
        """
        return np.stack(
            [self.ndvi(), self.ndwi(), self.mndwi(), self.ndbi(), self.bsi()],
            axis=-1,
        )


def generate_synthetic_training_data(
    features: np.ndarray, valid_mask: np.ndarray, n_samples_per_class: int = 5000
) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate synthetic training labels based on spectral index thresholds.

    This rule-based approach bootstraps the classifier when no ground-truth
    shapefile is available. In production, replace with QGIS-digitised
    training polygons.

    Rules derived from literature and Dallas-specific spectral behaviour:
        Water:      MNDWI > 0.0 AND NDWI > -0.1
        Vegetation: NDVI > 0.35 AND MNDWI < 0.0
        Urban:      NDBI > 0.0 AND NDVI < 0.2
        Bare Soil:  BSI > 0.1 AND NDVI < 0.15 AND MNDWI < -0.1
    """
    H, W, _ = features.shape
    ndvi = features[:, :, 0]
    ndwi = features[:, :, 1]
    mndwi = features[:, :, 2]
    ndbi = features[:, :, 3]
    bsi = features[:, :, 4]

    # Binary masks per class (only where valid data exists)
    masks = {
        3: (mndwi > 0.0) & (ndwi > -0.1) & valid_mask,          # Water
        2: (ndvi > 0.35) & (mndwi < 0.0) & valid_mask,           # Vegetation
        1: (ndbi > 0.0) & (ndvi < 0.2) & valid_mask,             # Urban
        4: (bsi > 0.1) & (ndvi < 0.15) & (mndwi < -0.1) & valid_mask,  # Bare soil
    }

    X_list, y_list = [], []

    for class_id, class_mask in masks.items():
        indices = np.argwhere(class_mask)
        if len(indices) == 0:
            logger.warning("No training pixels found for class", class_id=class_id)
            continue

        n = min(n_samples_per_class, len(indices))
        sampled = indices[np.random.choice(len(indices), n, replace=False)]
        X_list.append(features[sampled[:, 0], sampled[:, 1]])
        y_list.append(np.full(n, class_id, dtype=np.int32))

    if not X_list:
        raise ValueError("No training samples could be generated. Check input raster.")

    return np.vstack(X_list), np.concatenate(y_list)


class LandUseClassifier:
    """
    Random Forest land use classifier operating on spectral index features.

    The classifier is trained fresh for each scene to adapt to local
    radiometric conditions (no transfer learning across scenes).
    """

    def __init__(self, n_estimators: int = 200, random_state: int = 42):
        self.rf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=15,
            min_samples_leaf=5,
            n_jobs=-1,
            random_state=random_state,
            class_weight="balanced",
        )
        self.scaler = StandardScaler()
        self._is_trained = False

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        X_scaled = self.scaler.fit_transform(X)
        self.rf.fit(X_scaled, y)
        self._is_trained = True
        logger.info(
            "Classifier trained",
            n_samples=len(y),
            classes=list(np.unique(y)),
            oob_score=self.rf.oob_score if hasattr(self.rf, "oob_score_") else "N/A",
        )

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self._is_trained:
            raise RuntimeError("Classifier has not been trained.")
        X_scaled = self.scaler.transform(X)
        return self.rf.predict(X_scaled).astype(np.uint8)


def classify_raster(input_path: str, output_path: str) -> str:
    """
    Full classification pipeline for a single preprocessed raster.

    Steps:
    1. Load bands from preprocessed multi-band GeoTIFF
    2. Compute spectral indices (NDVI, NDWI, MNDWI, NDBI, BSI)
    3. Generate synthetic training samples from spectral rules
    4. Train Random Forest classifier
    5. Classify all valid pixels
    6. Write classified GeoTIFF (uint8, single band)

    Args:
        input_path: Path to preprocessed multi-band float32 GeoTIFF
        output_path: Path for classified output GeoTIFF

    Returns:
        output_path on success
    """
    log = logger.bind(input=input_path, output=output_path)
    log.info("Starting land use classification")

    with rasterio.open(input_path) as src:
        if src.count < 6:
            raise ValueError(
                f"Expected at least 6 bands, got {src.count}. "
                "Ensure input is preprocessed Landsat multi-band raster."
            )

        # Read bands into dict (0-indexed from rasterio)
        band_names = ["blue", "green", "red", "nir", "swir1", "swir2"]
        bands = {
            name: src.read(i + 1).astype("float32")
            for i, name in enumerate(band_names)
        }
        profile = src.profile.copy()

    H, W = bands["red"].shape

    # Valid pixel mask (no NaN or negative)
    valid_mask = np.all(
        np.stack([~np.isnan(b) & (b >= 0) for b in bands.values()], axis=0), axis=0
    )

    log.info("Valid pixel coverage", percent=round(valid_mask.mean() * 100, 2))

    # Compute spectral indices
    calc = SpectralIndexCalculator(bands)
    features = calc.compute_all()  # (H, W, 5)

    # Flatten for sklearn
    flat_features = features.reshape(-1, 5)
    flat_valid = valid_mask.ravel()

    # Generate training data
    X_train, y_train = generate_synthetic_training_data(features, valid_mask)

    # Train classifier
    classifier = LandUseClassifier()
    classifier.train(X_train, y_train)

    # Classify all valid pixels
    classified_flat = np.zeros(H * W, dtype=np.uint8)
    valid_indices = np.where(flat_valid)[0]

    if len(valid_indices) > 0:
        predictions = classifier.predict(flat_features[valid_indices])
        classified_flat[valid_indices] = predictions

    classified = classified_flat.reshape(H, W)

    # Write output
    profile.update(
        dtype="uint8",
        count=1,
        nodata=0,
        compress="lzw",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(classified.astype("uint8"), 1)
        dst.update_tags(
            CLASSIFICATION_SCHEME="LandUse_v1",
            CLASS_1="Urban/Built-up",
            CLASS_2="Vegetation",
            CLASS_3="Water",
            CLASS_4="Bare Soil",
        )

    log.info("Classification complete", output=output_path)
    return output_path
