"""
ORM models with PostGIS geometry support.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base


class JobStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class LandUseClass(str, PyEnum):
    URBAN = "urban"
    VEGETATION = "vegetation"
    WATER = "water"
    BARE_SOIL = "bare_soil"
    CLOUD = "cloud"


class ImageryScene(Base):
    """Represents an uploaded or fetched satellite imagery scene."""

    __tablename__ = "imagery_scenes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    acquisition_year: Mapped[int] = mapped_column(nullable=False)
    satellite_source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Landsat8"
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_mb: Mapped[Optional[float]] = mapped_column(Float)
    crs_epsg: Mapped[int] = mapped_column(default=32614)  # UTM Zone 14N for Dallas, TX
    spatial_extent: Mapped[Optional[str]] = mapped_column(
        Geometry("POLYGON", srid=4326)
    )
    band_count: Mapped[int] = mapped_column(default=6)
    resolution_m: Mapped[float] = mapped_column(default=30.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    analyses: Mapped[list["ChangeDetectionAnalysis"]] = relationship(
        back_populates="scene_t1",
        foreign_keys="ChangeDetectionAnalysis.scene_t1_id",
    )


class ChangeDetectionAnalysis(Base):
    """A change detection job comparing two imagery scenes."""

    __tablename__ = "change_detection_analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    scene_t1_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("imagery_scenes.id"), nullable=False
    )
    scene_t2_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("imagery_scenes.id"), nullable=False
    )

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING
    )
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255))
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Output file paths
    classified_t1_path: Mapped[Optional[str]] = mapped_column(Text)
    classified_t2_path: Mapped[Optional[str]] = mapped_column(Text)
    change_raster_path: Mapped[Optional[str]] = mapped_column(Text)
    change_png_path: Mapped[Optional[str]] = mapped_column(Text)

    # Processing metadata
    processing_time_seconds: Mapped[Optional[float]] = mapped_column(Float)
    algorithm_version: Mapped[str] = mapped_column(String(20), default="1.0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    scene_t1: Mapped["ImageryScene"] = relationship(
        foreign_keys=[scene_t1_id], back_populates="analyses"
    )
    scene_t2: Mapped["ImageryScene"] = relationship(foreign_keys=[scene_t2_id])
    statistics: Mapped[list["LandUseStatistic"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class LandUseStatistic(Base):
    """Per-class land use area statistics for an analysis."""

    __tablename__ = "land_use_statistics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_detection_analyses.id"), nullable=False
    )
    time_period: Mapped[str] = mapped_column(String(5), nullable=False)  # "t1" | "t2"
    land_use_class: Mapped[LandUseClass] = mapped_column(Enum(LandUseClass))
    area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    area_percent: Mapped[float] = mapped_column(Float, nullable=False)
    pixel_count: Mapped[int] = mapped_column(nullable=False)

    # Change from t1 to t2 (only populated for t2 rows)
    change_km2: Mapped[Optional[float]] = mapped_column(Float)
    change_percent: Mapped[Optional[float]] = mapped_column(Float)

    analysis: Mapped["ChangeDetectionAnalysis"] = relationship(
        back_populates="statistics"
    )
