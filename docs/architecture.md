# Architecture Deep Dive

## 1. GIS Processing Architecture

### Why Rasterio over PyQGIS?

PyQGIS requires a running QGIS installation and is GUI-dependent, making headless Docker deployment difficult. Rasterio wraps GDAL with a clean Pythonic API, is pip-installable, and operates without X11. For production batch processing, Rasterio is the industry-standard choice.

### Coordinate Reference System Strategy

Dallas sits at ~96.8°W, 32.8°N - within WGS84 UTM Zone 14N (EPSG:32614). All internal processing is done in UTM:

- **Why not WGS84 (EPSG:4326)?** Geographic coordinates are degree-based. Area calculations using degree × degree produce errors proportional to cos(latitude). At 32.8°N, 1° latitude ≈ 110.6 km but 1° longitude ≈ 109.8 km - a 0.7% mismatch that compounds over large scenes.
- **Why UTM 14N?** Provides true-metre coordinates. All area calculations (km²) are exact. The distortion at Dallas is < 0.04%.
- **Storage in WGS84:** Geometry in PostGIS `spatial_extent` is stored as WGS84 EPSG:4326 for web map compatibility (Leaflet, Mapbox, GEE all expect lon/lat).

### Band Normalisation: Why Percentile Stretching?

Raw Landsat DN values range 0–65535. Pixel values vary significantly between:
- Different acquisition dates (seasonal sun angle changes)
- Different sensors (Landsat 8 vs 9 radiometric differences)
- Atmospheric conditions

The 2nd/98th percentile stretch:
1. Clips outliers caused by clouds, cloud shadows, and sensor anomalies
2. Produces a scene-relative [0, 1] range
3. Makes features comparable across dates without requiring full atmospheric correction

For production deployment, surface reflectance products (Landsat Collection 2 Level-2) are preferred as they apply rigorous atmospheric correction, removing the need for normalisation.

### Spectral Index Rationale

Each index was selected for its discriminating power on specific Dallas land cover types:

| Index | Formula | Key advantage |
|-------|---------|---------------|
| NDVI | (NIR-RED)/(NIR+RED) | Best vegetation discriminator; separates sparse vs dense green cover |
| NDWI | (GREEN-NIR)/(GREEN+NIR) | Detects open water; positive values almost exclusively water |
| MNDWI | (GREEN-SWIR1)/(GREEN+SWIR1) | Suppresses built-up noise that confuses NDWI; better for urban fringe |
| NDBI | (SWIR1-NIR)/(SWIR1+NIR) | Built-up index; exploits high SWIR reflectance of rooftops and roads |
| BSI | ((SWIR1+RED)-(NIR+BLUE))/((SWIR1+RED)+(NIR+BLUE)) | Distinguishes bare soil from urban; important for Dallas's construction sites |

### Random Forest Configuration

- **200 trees**: diminishing returns beyond 150 trees; 200 gives stable OOB estimates
- **max_depth=15**: prevents overfitting to noisy synthetic labels while capturing spectral complexity
- **class_weight="balanced"**: Dallas water bodies cover ~8% of AOI - without balancing, water would be underclassified
- **n_jobs=-1**: uses all available CPU cores; critical for workers with 4+ cores

### Synthetic Training vs Ground Truth

The current implementation generates training labels from spectral thresholds. Limitations:
- Threshold values are tuned for Landsat 8 imagery over Dallas; may not generalise to Sentinel-2 or other cities
- Mixed pixels at class boundaries are ambiguous (e.g., flooded urban land)
- No validation against independent reference data

**Production upgrade path:**
1. Digitise training polygons in QGIS over the actual study imagery
2. Sample pixels from training polygons → true training data
3. Perform stratified random sampling to ensure spatial independence of training/validation sets
4. Report producer's accuracy, user's accuracy, and Cohen's Kappa coefficient

## 2. Async Architecture

### FastAPI + asyncpg vs Django ORM

Django's ORM is synchronous. A single `Django ORM query.filter()` call blocks the event loop. Under concurrent load (10+ users uploading scenes simultaneously), this serialises requests.

FastAPI + asyncpg uses `await session.execute(query)` - the database query is truly non-blocking. The GCP/AWS network round-trip to PostgreSQL (typically 2–5ms) releases the event loop to serve other requests during that wait.

### Celery Worker Memory Model

Each Celery task (`run_full_analysis`) loads an entire scene into memory for classification. For a 110km × 60km AOI at 30m resolution with 6 bands:

```
110,000m / 30m × 60,000m / 30m = ~3,667 × 2,000 = 7.3M pixels
6 bands × 7.3M pixels × 4 bytes (float32) ≈ 175 MB
+ classifier features (5 × 7.3M × 4 bytes) ≈ 146 MB
Total ≈ 320 MB per scene
```

With two scenes in memory simultaneously: ~640 MB. This is why workers are configured with `worker_prefetch_multiplier=1` - each worker processes one task at a time to avoid OOM.

**For scenes > 500 MB:** Implement windowed processing:
```python
with rasterio.open(input_path) as src:
    windows = list(src.block_windows())
    for ji, window in windows:
        data = src.read(window=window)
        # classify tile...
        dst.write(result, window=window)
```

## 3. Database Schema Decisions

### Why PostGIS for Scene Metadata?

Even though the initial implementation doesn't perform spatial queries on scene extents, storing the `spatial_extent` as a PostGIS POLYGON enables future queries like:

```sql
-- Find all analyses that include a specific municipality
SELECT a.* FROM change_detection_analyses a
JOIN imagery_scenes s ON a.scene_t1_id = s.id
WHERE ST_Intersects(
    s.spatial_extent,
    ST_GeomFromText('POLYGON((3.3 6.4, 3.5 6.4, 3.5 6.6, 3.3 6.6, 3.3 6.4))', 4326)
);
```

This spatial indexing capability is the core value of PostGIS over plain PostgreSQL for GIS applications.

### Change Code Encoding Trade-offs

The `T1_class × 10 + T2_class` encoding:

**Advantages:**
- Single integer stores complete transition information
- Fast vectorised computation with NumPy
- Easy to decode: `from_class = code // 10`, `to_class = code % 10`
- Works with any number of classes up to 9

**Limitations:**
- Cannot directly store more than 9 classes (would need `T1 × 100 + T2`)
- Requires documentation to interpret codes without a lookup table

For a future deep-learning segmentation model with 15+ classes, switch to two-band output: band 1 = T1 class, band 2 = T2 class.
