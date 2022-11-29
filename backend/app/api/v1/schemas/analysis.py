"""
Pydantic v2 schemas for API request validation and response serialization.
Separate from ORM models (DTO pattern) to decouple API contract from DB schema.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ─── Enums ────────────────────────────────────────────────────────────────────

class JobStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class LandUseClassEnum(str, Enum):
    URBAN = "urban"
    VEGETATION = "vegetation"
    WATER = "water"
    BARE_SOIL = "bare_soil"


# ─── Imagery Scene ────────────────────────────────────────────────────────────

class ImagerySceneCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=255)
    acquisition_year: int = Field(..., ge=1972, le=2100)
    satellite_source: str = Field(default="Landsat8", max_length=50)

    @field_validator("acquisition_year")
    @classmethod
    def year_reasonable(cls, v):
        if v < 1972:
            raise ValueError("Landsat was launched in 1972; earlier dates not supported.")
        return v


class ImagerySceneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    acquisition_year: int
    satellite_source: str
    file_path: str
    file_size_mb: Optional[float]
    crs_epsg: int
    band_count: int
    resolution_m: float
    created_at: datetime


# ─── Analysis ─────────────────────────────────────────────────────────────────

class AnalysisCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    scene_t1_id: uuid.UUID
    scene_t2_id: uuid.UUID

    @field_validator("scene_t2_id")
    @classmethod
    def t1_t2_differ(cls, v, info):
        if "scene_t1_id" in info.data and v == info.data["scene_t1_id"]:
            raise ValueError("T1 and T2 scenes must be different.")
        return v


class LandUseStatisticResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    land_use_class: LandUseClassEnum
    time_period: str
    area_km2: float
    area_percent: float
    pixel_count: int
    change_km2: Optional[float]
    change_percent: Optional[float]


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str]
    scene_t1_id: uuid.UUID
    scene_t2_id: uuid.UUID
    status: JobStatusEnum
    celery_task_id: Optional[str]
    error_message: Optional[str]
    classified_t1_path: Optional[str]
    classified_t2_path: Optional[str]
    change_raster_path: Optional[str]
    change_png_path: Optional[str]
    processing_time_seconds: Optional[float]
    algorithm_version: str
    created_at: datetime
    completed_at: Optional[datetime]
    statistics: list[LandUseStatisticResponse] = []


class AnalysisSummaryResponse(BaseModel):
    """Lightweight response for list endpoints (no statistics)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: JobStatusEnum
    processing_time_seconds: Optional[float]
    created_at: datetime
    completed_at: Optional[datetime]


# ─── Export ───────────────────────────────────────────────────────────────────

class ExportFormat(str, Enum):
    GEOTIFF = "geotiff"
    PNG = "png"
    JSON = "json"


# ─── Generic Responses ────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None
