"""
Imagery Scene Endpoints – /api/v1/scenes
"""

import os
import uuid
from pathlib import Path
from typing import Annotated

import aiofiles
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.analysis import (
    ImagerySceneCreate,
    ImagerySceneResponse,
    MessageResponse,
)
from app.core.config import settings
from app.db.repositories.analysis_repo import ImagerySceneRepository
from app.db.session import get_db

router = APIRouter(prefix="/scenes", tags=["Imagery Scenes"])
logger = structlog.get_logger(__name__)

ALLOWED_EXTENSIONS = {".tif", ".tiff", ".img"}
MAX_SIZE_BYTES = settings.MAX_RASTER_SIZE_MB * 1024 * 1024


@router.post(
    "/upload",
    response_model=ImagerySceneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a satellite imagery scene",
)
async def upload_scene(
    name: Annotated[str, Form()],
    acquisition_year: Annotated[int, Form()],
    satellite_source: Annotated[str, Form()] = "Landsat8",
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a multi-band GeoTIFF satellite imagery file.

    Accepted formats: GeoTIFF (.tif, .tiff), ERDAS Imagine (.img)
    Maximum file size: 500 MB (configurable via MAX_RASTER_SIZE_MB)

    The uploaded file is saved to the raster data directory and
    registered in the database for use in analysis jobs.
    """
    # Validate file extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type '{suffix}' not supported. Allowed: {ALLOWED_EXTENSIONS}",
        )

    # Validate schema
    scene_data = ImagerySceneCreate(
        name=name,
        acquisition_year=acquisition_year,
        satellite_source=satellite_source,
    )

    # Build output path
    scene_id = uuid.uuid4()
    raster_dir = Path(settings.RASTER_DATA_PATH) / str(scene_id)
    raster_dir.mkdir(parents=True, exist_ok=True)
    save_path = raster_dir / f"scene{suffix}"

    # Stream file to disk in chunks (avoids loading large rasters into memory)
    total_bytes = 0
    async with aiofiles.open(save_path, "wb") as f:
        while chunk := await file.read(8 * 1024 * 1024):  # 8 MB chunks
            total_bytes += len(chunk)
            if total_bytes > MAX_SIZE_BYTES:
                await f.close()
                os.remove(save_path)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds {settings.MAX_RASTER_SIZE_MB} MB limit.",
                )
            await f.write(chunk)

    file_size_mb = round(total_bytes / (1024 * 1024), 2)
    logger.info(
        "Scene uploaded",
        scene_id=str(scene_id),
        name=name,
        size_mb=file_size_mb,
    )

    # Persist to DB
    repo = ImagerySceneRepository(db)
    scene = await repo.create(
        id=scene_id,
        name=scene_data.name,
        acquisition_year=scene_data.acquisition_year,
        satellite_source=scene_data.satellite_source,
        file_path=str(save_path),
        file_size_mb=file_size_mb,
    )

    return scene


@router.get(
    "/",
    response_model=list[ImagerySceneResponse],
    summary="List all uploaded scenes",
)
async def list_scenes(db: AsyncSession = Depends(get_db)):
    repo = ImagerySceneRepository(db)
    return await repo.list_all()


@router.get(
    "/{scene_id}",
    response_model=ImagerySceneResponse,
    summary="Get a single scene by ID",
)
async def get_scene(scene_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = ImagerySceneRepository(db)
    scene = await repo.get_by_id(scene_id)
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scene {scene_id} not found.",
        )
    return scene


@router.delete(
    "/{scene_id}",
    response_model=MessageResponse,
    summary="Delete a scene and its associated raster file",
)
async def delete_scene(scene_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = ImagerySceneRepository(db)
    scene = await repo.get_by_id(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found.")

    # Remove file from disk
    file_path = Path(scene.file_path)
    if file_path.exists():
        file_path.unlink()
    if file_path.parent.exists() and not any(file_path.parent.iterdir()):
        file_path.parent.rmdir()

    await db.delete(scene)
    logger.info("Scene deleted", scene_id=str(scene_id))
    return MessageResponse(message=f"Scene {scene_id} deleted successfully.")
