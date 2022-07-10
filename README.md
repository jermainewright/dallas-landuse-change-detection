# 🛰️ Dallas LandScan - Land Use Change Detection System

> **A production-grade, full-stack geospatial platform for satellite imagery analysis, temporal land use classification, and interactive change detection visualisation over Dallas, Texas.**

<a href="https://jermainewright.github.io/dallas-landuse-change-detection/">
  <img src="/images/app-image.png" width="100%" />
</a>

---

🔗 **[Live Demo](https://jermainewright.github.io/dallas-landuse-change-detection/)**

</div>

> **Note:** - This dashboard is for demonstration purposes only.

---

[![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?style=flat-square)](https://nextjs.org)
[![PostGIS](https://img.shields.io/badge/PostGIS-15-336791?style=flat-square)](https://postgis.net)
[![Celery](https://img.shields.io/badge/Celery-5.4-37814a?style=flat-square)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square)](https://docker.com)

---

## Problem Statement

The Dallas–Fort Worth metroplex is one of the fastest-growing urban regions in the United States. Dallas has expanded its built footprint by an estimated **400 km²** between 2000 and 2020, converting prairie grasslands, bottomland forests, and agricultural fields into impervious urban surface. Remote sensing offers the only cost-effective mechanism to quantify this transformation at city-wide scale.

Existing tools (QGIS, Google Earth Engine) require specialist GIS knowledge and produce static outputs unsuitable for operational dashboards or programmatic access. Organisations need a **self-hostable, API-driven change detection pipeline** that is reproducible, auditable, and integrates with modern web infrastructure.

---

## Solution

Dallas LandScan provides an end-to-end automated pipeline:

1. **Ingest** multi-band Landsat 8/9 GeoTIFF scenes via REST API or drag-and-drop upload
2. **Preprocess** scenes: reproject to UTM, clip to Dallas AOI, normalise bands
3. **Classify** each scene into four land use classes using spectral indices + Random Forest
4. **Detect changes** via pixel-wise transition analysis with a from-to change matrix
5. **Serve results** as interactive web maps, analytics dashboards, and downloadable exports (GeoTIFF, PNG, JSON)

All heavy processing runs asynchronously in Celery workers, keeping the API responsive and the system horizontally scalable.

---

## Architecture Diagram

```
+-------------------------------------------------------------------+
|                         CLIENT BROWSER                            |
|           Next.js 14  |  React 18  |  Leaflet  |  Recharts        |
+---------------------------+---------------------------------------+
                            | HTTP/REST
                            v
+-------------------------------------------------------------------+
|                    NGINX (Reverse Proxy)                           |
|          Rate limiting  |  Gzip  |  512 MB body limit             |
+---------------+---------------------------+-----------------------+
                |  /api/v1/*               |  /*
                v                          v
+---------------------------+   +----------------------------------+
|   FastAPI (Uvicorn)       |   |   Next.js (Node runtime)         |
|                           |   |                                  |
|   REST Endpoints:         |   |   Dashboard | Scenes | Map       |
|   /api/v1/scenes/         |   |   Charts | Upload | Modals       |
|   /api/v1/analyses/       |   |   TanStack Query + Zustand       |
|   /health                 |   +----------------------------------+
|   /metrics                |
|            |dispatch      |        +-----------------------------+
|            v              |        |  Redis (Broker + Backend)   |
|   Celery Task Dispatch ---+--------->                            |
|                           |        +-----------------------------+
|   PostgreSQL + PostGIS    |
|   imagery_scenes          |        +-----------------------------+
|   analyses                |        |   Celery Worker(s)          |
|   statistics              |        |                             |
|                           |        |   GIS Pipeline:             |
|   Prometheus /metrics     |        |   RasterPreprocessor        |
+---------------------------+        |   LandUseClassifier         |
                                     |   ChangeDetector            |
                                     +-----------------------------+

                                     +-----------------------------+
                                     |   Flower (Job Monitor)      |
                                     |   localhost:5555            |
                                     +-----------------------------+

                                     +-----------------------------+
                                     |  Local Volumes / S3         |
                                     |  /data/rasters/             |
                                     |  /data/outputs/             |
                                     +-----------------------------+
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | Next.js 14, React 18, TypeScript | UI framework, SSR |
| Mapping | Leaflet + react-leaflet | Interactive web maps |
| Charts | Recharts | Analytics visualisations |
| State | TanStack React Query | Server state, adaptive polling |
| Styling | Tailwind CSS | Utility-first design system |
| Backend | FastAPI + Uvicorn | Async REST API |
| Task Queue | Celery 5 + Redis | Background GIS processing |
| Database | PostgreSQL 15 + PostGIS 3.3 | Geospatial metadata storage |
| ORM | SQLAlchemy 2 (async) | Database abstraction layer |
| Migrations | Alembic | Schema versioning |
| GIS Core | GDAL 3.6, Rasterio 1.3 | Raster I/O and reprojection |
| ML | scikit-learn Random Forest | Land use classification |
| Spectral | NumPy, SciPy | Index computation |
| Monitoring | structlog, Prometheus, Flower | Observability stack |
| Storage | Local volumes / S3-compatible | Raster file persistence |
| Containers | Docker + Docker Compose | Service orchestration |

---

## Architecture Decisions

### ADR-001: FastAPI over Django REST Framework
FastAPI is async-native, allowing the API server to remain non-blocking while Celery workers handle raster I/O. Django would require `sync_to_async` wrappers or a synchronous server model.

### ADR-002: Celery for GIS processing (not background threads)
GIS tasks can consume 2-8 GB RAM for real Landsat scenes. Celery isolates memory, provides retry semantics, enables horizontal scaling, and lets Flower monitor job health.

### ADR-003: Random Forest over deep learning
For deployment without ground-truth training labels, spectral-rule-derived synthetic labels bootstrap a Random Forest. This requires no GPU, trains in seconds, is interpretable via feature importances, and can be swapped for a U-Net without changing the pipeline interface.

### ADR-004: Spectral indices as features (not raw bands)
NDVI, NDWI, MNDWI, NDBI, BSI provide physically interpretable features that cancel atmospheric effects (being ratio indices), reduce dimensionality from 6 bands to 5 features, and transfer across sensors and dates.

### ADR-005: Filesystem for rasters, PostGIS for metadata
Raster files are stored on disk/S3; only metadata and statistics live in PostGIS. Storing large rasters in PostgreSQL degrades query performance. Spatial queries on scene extents use PostGIS geometry columns.

### ADR-006: Change code encoding as `t1 * 10 + t2`
A single integer encodes both source and destination class. Enables SQL queries like `WHERE change_code = 21` (vegetation to urban) without join tables, and efficient transition matrix aggregation.

---

## Key Features with Code Explanations

### 1. Spectral Index Feature Engineering

```python
# app/services/gis/classifier.py

def ndvi(self) -> np.ndarray:
    """NDVI = (NIR - RED) / (NIR + RED). Values > 0.35 = dense vegetation."""
    nir = self.bands["nir"].astype("float32")
    red = self.bands["red"].astype("float32")
    return (nir - red) / (nir + red + self._epsilon)

def ndbi(self) -> np.ndarray:
    """NDBI = (SWIR1 - NIR) / (SWIR1 + NIR). Positive = urban/built-up.
    Ref: Zha et al. (2003), International Journal of Remote Sensing."""
    swir1 = self.bands["swir1"].astype("float32")
    nir   = self.bands["nir"].astype("float32")
    return (swir1 - nir) / (swir1 + nir + self._epsilon)
```

### 2. Raster Grid Alignment (critical for change detection)

```python
# app/services/gis/preprocessor.py

def align_rasters(reference_path, target_path, output_path):
    """Snaps target to reference grid via bilinear resampling.
    Even 1-pixel misalignment causes false change detections."""
    with rasterio.open(reference_path) as ref:
        ref_transform = ref.transform
    with rasterio.open(target_path) as src:
        reproject(
            source=rasterio.band(src, band_idx),
            destination=dest_array,
            dst_transform=ref_transform,  # Key: snap to reference
            resampling=Resampling.bilinear,
        )
```

### 3. From-To Change Encoding

```python
# app/services/gis/change_detector.py

# Encodes source + destination in one integer:
#  21 = class 2 (vegetation) -> class 1 (urban)
#  31 = class 3 (water)      -> class 1 (urban)
#  11 = class 1 (urban)      -> class 1 (unchanged)

change_raster[valid_mask] = arr_t1[valid_mask] * 10 + arr_t2[valid_mask]
```

### 4. Async Celery Dispatch from FastAPI

```python
# app/api/v1/endpoints/analyses.py

@router.post("/", response_model=AnalysisResponse, status_code=201)
async def create_analysis(payload: AnalysisCreate, db: AsyncSession = Depends(get_db)):
    analysis = await analysis_repo.create(status=JobStatus.PENDING, ...)
    task = run_full_analysis.apply_async(
        kwargs={"analysis_id": str(analysis.id), ...},
        queue="gis_processing",
    )
    # Returns immediately; client polls /status endpoint
    return analysis
```

### 5. Adaptive React Query Polling

```typescript
// frontend/src/components/dashboard/AnalysisDashboard.tsx

const { data } = useQuery({
  queryKey: ["analyses"],
  queryFn: analysesApi.list,
  refetchInterval: (query) => {
    // Poll every 4s only while jobs are active (saves bandwidth)
    const hasRunning = query.state.data?.some(
      (a) => a.status === "running" || a.status === "pending"
    );
    return hasRunning ? 4000 : false;
  },
});
```

---

## Repository Structure

```
dallas-landuse-change-detection/
├── .github/
│   └── workflows/
│       └── ci.yml
├── backend/
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       ├── endpoints/
│   │   │       │   ├── analyses.py
│   │   │       │   └── scenes.py
│   │   │       └── schemas/
│   │   │           └── analysis.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── logging.py
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   ├── models/
│   │   │   │   ├── analysis.py
│   │   │   │   └── base.py
│   │   │   └── repositories/
│   │   │       └── analysis_repo.py
│   │   ├── services/
│   │   │   └── gis/
│   │   │       ├── change_detector.py
│   │   │       ├── classifier.py
│   │   │       └── preprocessor.py
│   │   └── worker/
│   │       └── celery_app.py
│   └── tests/
│       ├── unit/
│       │   ├── test_change_detector.py
│       │   └── test_classifier.py
│       └── integration/
│           └── test_api.py
├── frontend/
│   ├── Dockerfile
│   ├── next.config.mjs
│   ├── package.json
│   ├── tailwind.config.js
│   └── src/
│       ├── app/
│       │   ├── globals.css
│       │   ├── layout.tsx
│       │   └── page.tsx
│       ├── components/
│       │   ├── dashboard/
│       │   │   ├── AnalysisCard.tsx
│       │   │   ├── AnalysisDashboard.tsx
│       │   │   ├── ChangeChart.tsx
│       │   │   ├── NewAnalysisModal.tsx
│       │   │   ├── SceneManager.tsx
│       │   │   └── StatsOverview.tsx
│       │   ├── map/
│       │   │   ├── LayerToggle.tsx
│       │   │   ├── LeafletMap.tsx
│       │   │   └── MapView.tsx
│       │   └── ui/
│       │       ├── QueryProvider.tsx
│       │       ├── Sidebar.tsx
│       │       └── TopBar.tsx
│       ├── lib/
│       │   └── api.ts
│       └── types/
│           └── api.ts
├── images/
│   └── app-image.png
├── infrastructure/
│   ├── nginx/
│   │   └── nginx.conf
│   └── postgres/
│       └── init.sql
├── scripts/
│   └── generate_sample_data.py
├── .env.example
├── .gitignore
├── CONTRIBUTING.md
├── docker-compose.yml
├── LICENSE
├── Makefile
└── README.md
```

---

## Setup Instructions

### Prerequisites

- Docker >= 24.0 and Docker Compose >= 2.20
- 8 GB RAM minimum (16 GB recommended for large rasters)
- 20 GB free disk space

### Quick Start (Docker Compose)

```bash
# 1. Clone repository
git clone https://github.com/jermainewright/dallas-landuse-change-detection.git
cd dallas-landuse-change-detection

# 2. Configure environment
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, MAPBOX_TOKEN, SECRET_KEY

# 3. Start all services
docker compose up -d

# 4. Run database migrations
docker compose exec backend alembic upgrade head

# 5. Generate synthetic test data (no real satellite imagery needed)
docker compose exec backend python scripts/generate_sample_data.py \
  --output-dir /app/data/rasters/sample

# 6. Open the application
open http://localhost           # Web UI via Nginx
open http://localhost:8000/api/docs  # Swagger UI
open http://localhost:5555      # Celery Flower monitor
```

### Local Development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/landuse_db"
export CELERY_BROKER_URL="redis://localhost:6379/0"
alembic upgrade head
uvicorn app.main:app --reload

# Worker (separate terminal)
celery -A app.worker.celery_app worker --loglevel=info -Q gis_processing

# Frontend
cd frontend && npm install && npm run dev
```

### Running Tests

```bash
# Unit tests
docker compose exec backend pytest tests/unit -v --tb=short

# Integration tests
docker compose exec backend pytest tests/integration -v

# With coverage report
docker compose exec backend pytest --cov=app --cov-report=term-missing

# Linting
docker compose exec backend ruff check app/
```

### Obtaining Real Satellite Imagery

Real Landsat 8/9 scenes for Dallas are freely available:
- **USGS Earth Explorer**: https://earthexplorer.usgs.gov (search: path 191, row 055)
- **Copernicus Open Access Hub**: https://scihub.copernicus.eu
- **Google Earth Engine**: Export via `ee.Image.getDownloadURL()`

Download Collection 2 Level-2 (surface reflectance) products, stack bands 2-7 into a single multi-band GeoTIFF, then upload via the web UI.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | /scenes/ | List all imagery scenes |
| POST | /scenes/upload | Upload GeoTIFF (multipart) |
| GET | /scenes/{id} | Get scene metadata |
| DELETE | /scenes/{id} | Delete scene and file |
| GET | /analyses/ | List all analyses |
| POST | /analyses/ | Create and dispatch analysis |
| GET | /analyses/{id} | Full analysis with statistics |
| GET | /analyses/{id}/status | Lightweight status poll |
| GET | /analyses/{id}/export/geotiff | Download change raster |
| GET | /analyses/{id}/export/png | Download change map PNG |
| GET | /analyses/{id}/export/json | Download statistics JSON |
| GET | /health | Health check |
| GET | /metrics | Prometheus metrics |

---

## GIS Processing Pipeline

```
Input GeoTIFF (multi-band, any CRS)
         |
         v
  [Reprojection] --> UTM Zone 14N (EPSG:32614), 30m resolution
         |
         v
  [AOI Clipping] --> Dallas AOI bbox: -97.0--96.5 W, 32.6-33.0 N
         |
         v
  [Band Normalisation] --> 2nd-98th percentile -> [0, 1]
         |
         v
  [Spectral Indices] --> NDVI, NDWI, MNDWI, NDBI, BSI (5 features)
         |
         v
  [Random Forest] --> 200 estimators, balanced class weights
         |
         v
  [Classes: 1=Urban 2=Vegetation 3=Water 4=Bare Soil]
         |
   (both T1 and T2 classified)
         |
         v
  [Raster Alignment] --> T2 snapped to T1 pixel grid (critical)
         |
         v
  [Change Detection] --> change_code = t1*10 + t2
         |
         v
  [Outputs] --> change_raster.tif | change_map.png | statistics.json
```

---

## Observability

**Structured Logging** (structlog): JSON in production, colourised console in dev. Every log line includes timestamp, level, logger name, request ID, task ID, and domain context.

**Prometheus Metrics** at `/metrics`:
- `http_request_duration_seconds` - API latency histograms
- `celery_tasks_total` - Task counts by queue and status
- `celery_task_duration_seconds` - GIS job processing time

**Celery Flower** at `localhost:5555`: Real-time queue depth, per-worker utilisation, task history, failure inspection.

---

## Simulated Throughput Metrics

Benchmarked on 4-core / 16 GB RAM (downsampled 500x330 px vs full 5000x3300 px scene):

| Step | Sample (500x330) | Full Scene (5000x3300) |
|---|---|---|
| Reprojection + Clip | ~2s | ~35s |
| Band Normalisation | ~0.5s | ~8s |
| Spectral Index Computation | ~0.3s | ~5s |
| Random Forest Training | ~1s | ~4s |
| Classification | ~2s | ~18s |
| Change Detection | ~0.5s | ~6s |
| PNG Export | ~0.2s | ~3s |
| **Total (one analysis)** | **~7s** | **~80s** |

Scale workers: `docker compose up --scale celery_worker=4` for parallel jobs.

---

## Scalability Considerations

1. **Worker scaling**: Celery workers are stateless. Scale to N workers bounded by RAM (2-4 GB per full-scene job).
2. **Windowed raster reads**: Use Rasterio `block_windows()` for scenes > 1 GB to keep per-job memory bounded.
3. **TiTiler tile service**: Replace PNG overlay with COG tile server for proper slippy-map tiling at scale.
4. **S3 raster storage**: Set `USE_S3=true` to route all raster I/O through S3-compatible object storage.
5. **DB read replicas**: Route heavy analytics queries to a PostGIS read replica via SQLAlchemy.
6. **Redis Cluster**: For > 100 concurrent jobs, upgrade to Redis Cluster to eliminate the broker bottleneck.

---

## Security Considerations

- **Secrets**: All credentials in environment variables, `.env` gitignored. Use Vault/AWS Secrets Manager in production.
- **Upload validation**: Extension allowlist, 8 MB chunked streaming, size enforcement before disk write.
- **Non-root containers**: All images run as UID 1000.
- **Rate limiting**: Nginx `limit_req_zone` at 30 req/min per IP on API routes.
- **CORS**: Configurable `ALLOWED_ORIGINS` in `.env`.
- **Input validation**: Pydantic v2 with strict field validators on all endpoints.
- **SQL injection**: SQLAlchemy parameterised ORM queries throughout.

---

## Future Improvements

- [ ] Ground-truth training polygons from QGIS digitisation
- [ ] Sentinel-2 10m resolution processing path
- [ ] U-Net segmentation head for higher classification accuracy
- [ ] N-scene time series analysis with trend detection
- [ ] Confusion matrix and accuracy assessment against validation polygons
- [ ] TiTiler integration for COG tile serving
- [ ] Multi-city AOI configuration
- [ ] JWT authentication with user workspaces
- [ ] WebSocket real-time job progress (replace HTTP polling)
- [ ] Kubernetes Helm chart for production cloud deployment

---

## References

- Zha, Y., Gao, J., & Ni, S. (2003). Use of normalized difference built-up index. *IJRS*, 24(3).
- McFeeters, S.K. (1996). The use of the NDWI in delineation of open water. *IJRS*, 17(7).
- Xu, H. (2006). Modification of NDWI to enhance open water features. *IJRS*, 27(14).
- Jensen, J.R. (2016). Introductory Digital Image Processing (4th ed.). Pearson.

---

## Licence

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.