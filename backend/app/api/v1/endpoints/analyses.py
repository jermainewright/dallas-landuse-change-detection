"""
Change Detection Analysis Endpoints – /api/v1/analyses
"""

import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.analysis import (
    AnalysisCreate,
    AnalysisResponse,
    AnalysisSummaryResponse,
    ExportFormat,
    MessageResponse,
)
from app.core.config import settings
from app.db.models.analysis import JobStatus
from app.db.repositories.analysis_repo import AnalysisRepository, ImagerySceneRepository
from app.db.session import get_db
from app.worker.celery_app import run_full_analysis

router = APIRouter(prefix="/analyses", tags=["Change Detection Analyses"])
logger = structlog.get_logger(__name__)


@router.post(
    "/",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and dispatch a new change detection analysis",
)
async def create_analysis(
    payload: AnalysisCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Creates an analysis record and dispatches the processing pipeline
    to a Celery worker. Returns immediately with status=pending.

    Poll GET /analyses/{id} to track progress.
    """
    scene_repo = ImagerySceneRepository(db)
    analysis_repo = AnalysisRepository(db)

    # Validate both scenes exist
    scene_t1 = await scene_repo.get_by_id(payload.scene_t1_id)
    scene_t2 = await scene_repo.get_by_id(payload.scene_t2_id)

    if not scene_t1:
        raise HTTPException(404, detail=f"T1 scene {payload.scene_t1_id} not found.")
    if not scene_t2:
        raise HTTPException(404, detail=f"T2 scene {payload.scene_t2_id} not found.")

    if scene_t1.acquisition_year >= scene_t2.acquisition_year:
        raise HTTPException(
            422,
            detail=(
                f"T1 scene year ({scene_t1.acquisition_year}) must be "
                f"earlier than T2 scene year ({scene_t2.acquisition_year})."
            ),
        )

    # Create DB record
    analysis = await analysis_repo.create(
        name=payload.name,
        description=payload.description,
        scene_t1_id=payload.scene_t1_id,
        scene_t2_id=payload.scene_t2_id,
        status=JobStatus.PENDING,
    )

    # Dispatch Celery task
    task = run_full_analysis.apply_async(
        kwargs={
            "analysis_id": str(analysis.id),
            "scene_t1_path": scene_t1.file_path,
            "scene_t2_path": scene_t2.file_path,
        },
        queue="gis_processing",
    )

    # Save Celery task ID & mark as running
    await analysis_repo.update_status(
        analysis.id,
        status=JobStatus.RUNNING,
        celery_task_id=task.id,
    )

    logger.info(
        "Analysis dispatched",
        analysis_id=str(analysis.id),
        celery_task_id=task.id,
    )

    refreshed = await analysis_repo.get_by_id(analysis.id)
    return refreshed


@router.get(
    "/",
    response_model=list[AnalysisSummaryResponse],
    summary="List all analyses",
)
async def list_analyses(db: AsyncSession = Depends(get_db)):
    repo = AnalysisRepository(db)
    return await repo.list_all()


@router.get(
    "/{analysis_id}",
    response_model=AnalysisResponse,
    summary="Get analysis detail with statistics",
)
async def get_analysis(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = AnalysisRepository(db)
    analysis = await repo.get_by_id(analysis_id)
    if not analysis:
        raise HTTPException(404, detail=f"Analysis {analysis_id} not found.")
    return analysis


@router.get(
    "/{analysis_id}/status",
    summary="Poll analysis job status (lightweight)",
)
async def get_analysis_status(
    analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    repo = AnalysisRepository(db)
    analysis = await repo.get_by_id(analysis_id)
    if not analysis:
        raise HTTPException(404, detail="Analysis not found.")
    return {
        "analysis_id": str(analysis.id),
        "status": analysis.status,
        "celery_task_id": analysis.celery_task_id,
        "processing_time_seconds": analysis.processing_time_seconds,
        "error_message": analysis.error_message,
    }


@router.get(
    "/{analysis_id}/export/{format}",
    summary="Download analysis output files",
)
async def export_analysis(
    analysis_id: uuid.UUID,
    format: ExportFormat,
    db: AsyncSession = Depends(get_db),
):
    """
    Download analysis outputs:
    - `geotiff` – Change detection raster (GeoTIFF)
    - `png`     – Change map visual (PNG)
    - `json`    – Statistics report (JSON)
    """
    repo = AnalysisRepository(db)
    analysis = await repo.get_by_id(analysis_id)
    if not analysis:
        raise HTTPException(404, detail="Analysis not found.")
    if analysis.status != JobStatus.COMPLETED:
        raise HTTPException(
            409,
            detail=f"Analysis is not complete yet (status: {analysis.status}).",
        )

    if format == ExportFormat.GEOTIFF:
        file_path = analysis.change_raster_path
        media_type = "image/tiff"
        filename = f"change_raster_{analysis_id}.tif"
    elif format == ExportFormat.PNG:
        file_path = analysis.change_png_path
        media_type = "image/png"
        filename = f"change_map_{analysis_id}.png"
    else:  # JSON
        output_dir = Path(settings.OUTPUT_DATA_PATH) / str(analysis_id)
        file_path = str(output_dir / "statistics.json")
        media_type = "application/json"
        filename = f"statistics_{analysis_id}.json"

    if not file_path or not Path(file_path).exists():
        raise HTTPException(404, detail="Output file not found on disk.")

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )


@router.delete(
    "/{analysis_id}",
    response_model=MessageResponse,
    summary="Delete an analysis and all its output files",
)
async def delete_analysis(
    analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    repo = AnalysisRepository(db)
    analysis = await repo.get_by_id(analysis_id)
    if not analysis:
        raise HTTPException(404, detail="Analysis not found.")

    # Clean up output files
    output_dir = Path(settings.OUTPUT_DATA_PATH) / str(analysis_id)
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)

    await db.delete(analysis)
    logger.info("Analysis deleted", analysis_id=str(analysis_id))
    return MessageResponse(message=f"Analysis {analysis_id} deleted.")
