"""
Celery Application & GIS Processing Tasks
==========================================
All heavy raster processing runs in Celery workers, keeping the
FastAPI event loop free. Workers consume from the 'gis_processing' queue.

Task flow for a change detection analysis:
    1. preprocess_scene (T1) ──┐
    2. preprocess_scene (T2) ──┤─→ 3. run_change_detection ──→ 4. persist_results
"""

import time
import uuid
from pathlib import Path

import structlog
from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun

from app.core.config import settings

logger = structlog.get_logger(__name__)

# ─── Celery App ───────────────────────────────────────────────────────────────
celery_app = Celery(
    "dallas_landuse_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Chicago",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # One task at a time (memory-intensive GIS work)
    task_routes={
        "app.worker.tasks.*": {"queue": "gis_processing"},
    },
    task_soft_time_limit=1800,  # 30 min soft limit
    task_time_limit=2400,       # 40 min hard limit
    result_expires=86400 * 7,   # Keep results 7 days
)


# ─── Celery Signals (structured logging) ─────────────────────────────────────
@task_prerun.connect
def on_task_prerun(task_id, task, args, kwargs, **extras):
    logger.info("Task started", task_id=task_id, task_name=task.name)


@task_postrun.connect
def on_task_postrun(task_id, task, args, kwargs, state, **extras):
    logger.info("Task finished", task_id=task_id, task_name=task.name, state=state)


@task_failure.connect
def on_task_failure(task_id, exception, traceback, **extras):
    logger.error(
        "Task failed",
        task_id=task_id,
        error=str(exception),
        exc_info=True,
    )


# ─── Tasks ────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="app.worker.tasks.preprocess_scene", max_retries=2)
def preprocess_scene(self, input_path: str, output_dir: str) -> str:
    """
    Preprocess a single raster scene.

    Steps: reproject → clip to Dallas AOI → normalize bands
    Returns the path to the preprocessed GeoTIFF.
    """
    from app.services.gis.preprocessor import RasterPreprocessor

    log = logger.bind(task_id=self.request.id, input_path=input_path)
    log.info("Preprocessing scene")

    try:
        preprocessor = RasterPreprocessor(input_path, output_dir)
        result_path = preprocessor.run()
        log.info("Preprocessing complete", output=result_path)
        return result_path
    except Exception as exc:
        log.error("Preprocessing failed", error=str(exc))
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, name="app.worker.tasks.run_full_analysis", max_retries=1)
def run_full_analysis(
    self,
    analysis_id: str,
    scene_t1_path: str,
    scene_t2_path: str,
) -> dict:
    """
    Orchestrates the full change detection pipeline for an analysis job.

    Steps:
        1. Preprocess T1 scene
        2. Preprocess T2 scene
        3. Align T2 to T1 grid
        4. Classify T1
        5. Classify T2
        6. Run change detection
        7. Persist results to DB

    Returns a dict with all output file paths and statistics.
    """
    from app.services.gis.preprocessor import RasterPreprocessor, align_rasters
    from app.services.gis.classifier import classify_raster
    from app.services.gis.change_detector import ChangeDetector

    start_time = time.perf_counter()
    analysis_uuid = uuid.UUID(analysis_id)
    output_dir = Path(settings.OUTPUT_DATA_PATH) / analysis_id
    output_dir.mkdir(parents=True, exist_ok=True)

    log = logger.bind(analysis_id=analysis_id, task_id=self.request.id)
    log.info("Full analysis pipeline started")

    try:
        # Step 1 & 2: Preprocess both scenes
        log.info("Preprocessing T1 scene")
        prep_t1 = RasterPreprocessor(scene_t1_path, str(output_dir / "prep"))
        preprocessed_t1 = prep_t1.run()

        log.info("Preprocessing T2 scene")
        prep_t2 = RasterPreprocessor(scene_t2_path, str(output_dir / "prep"))
        preprocessed_t2 = prep_t2.run()

        # Step 3: Align T2 to T1 (critical for pixel-wise comparison)
        log.info("Aligning T2 to T1 grid")
        aligned_t2 = str(output_dir / "prep" / "t2_aligned.tif")
        align_rasters(preprocessed_t1, preprocessed_t2, aligned_t2)

        # Step 4 & 5: Classify both scenes
        log.info("Classifying T1")
        classified_t1 = str(output_dir / "classified_t1.tif")
        classify_raster(preprocessed_t1, classified_t1)

        log.info("Classifying T2")
        classified_t2 = str(output_dir / "classified_t2.tif")
        classify_raster(aligned_t2, classified_t2)

        # Step 6: Change detection
        log.info("Running change detection")
        detector = ChangeDetector(classified_t1, classified_t2)
        change_results = detector.run(str(output_dir))

        elapsed = time.perf_counter() - start_time

        result = {
            "analysis_id": analysis_id,
            "classified_t1_path": classified_t1,
            "classified_t2_path": classified_t2,
            "change_raster_path": change_results["change_raster_path"],
            "change_png_path": change_results["change_png_path"],
            "statistics": change_results["statistics"],
            "processing_time_seconds": round(elapsed, 2),
        }

        log.info(
            "Full analysis complete",
            processing_time_s=result["processing_time_seconds"],
            changed_km2=change_results["statistics"]["summary"]["total_changed_km2"],
        )

        # Step 7: Persist results to DB (synchronous call from worker)
        _persist_results_sync(analysis_uuid, result)

        return result

    except Exception as exc:
        log.error("Analysis pipeline failed", error=str(exc), exc_info=True)
        _mark_analysis_failed_sync(analysis_uuid, str(exc))
        raise


def _persist_results_sync(analysis_uuid: uuid.UUID, result: dict) -> None:
    """Synchronously persist analysis results using a sync DB connection."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.models.analysis import (
        ChangeDetectionAnalysis,
        JobStatus,
        LandUseStatistic,
        LandUseClass,
    )

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        analysis = session.get(ChangeDetectionAnalysis, analysis_uuid)
        if not analysis:
            logger.error("Analysis not found in DB", id=str(analysis_uuid))
            return

        analysis.status = JobStatus.COMPLETED
        analysis.classified_t1_path = result["classified_t1_path"]
        analysis.classified_t2_path = result["classified_t2_path"]
        analysis.change_raster_path = result["change_raster_path"]
        analysis.change_png_path = result["change_png_path"]
        analysis.processing_time_seconds = result["processing_time_seconds"]

        from datetime import datetime, timezone
        analysis.completed_at = datetime.now(timezone.utc)

        # Persist per-class statistics
        stats = result["statistics"]
        class_map = {
            "urban": LandUseClass.URBAN,
            "vegetation": LandUseClass.VEGETATION,
            "water": LandUseClass.WATER,
            "bare_soil": LandUseClass.BARE_SOIL,
        }

        for period in ["t1", "t2"]:
            for class_name, lu_class in class_map.items():
                class_data = stats[period][class_name]
                change_data = stats["change"].get(class_name, {}) if period == "t2" else {}
                stat = LandUseStatistic(
                    analysis_id=analysis_uuid,
                    time_period=period,
                    land_use_class=lu_class,
                    area_km2=class_data["area_km2"],
                    area_percent=class_data["area_percent"],
                    pixel_count=class_data["pixel_count"],
                    change_km2=change_data.get("delta_km2") if period == "t2" else None,
                    change_percent=change_data.get("percent_change") if period == "t2" else None,
                )
                session.add(stat)

        session.commit()
    engine.dispose()


def _mark_analysis_failed_sync(analysis_uuid: uuid.UUID, error: str) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.models.analysis import ChangeDetectionAnalysis, JobStatus

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        analysis = session.get(ChangeDetectionAnalysis, analysis_uuid)
        if analysis:
            analysis.status = JobStatus.FAILED
            analysis.error_message = error[:2000]
            session.commit()
    engine.dispose()
