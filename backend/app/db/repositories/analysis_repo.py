"""
Repository layer – data access abstraction over SQLAlchemy ORM.
Keeps business logic out of route handlers and service layer decoupled from ORM.
"""

import uuid
from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.analysis import (
    ChangeDetectionAnalysis,
    ImageryScene,
    JobStatus,
    LandUseStatistic,
)


class ImagerySceneRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, **kwargs) -> ImageryScene:
        scene = ImageryScene(**kwargs)
        self.db.add(scene)
        await self.db.flush()
        await self.db.refresh(scene)
        return scene

    async def get_by_id(self, scene_id: uuid.UUID) -> Optional[ImageryScene]:
        result = await self.db.execute(
            select(ImageryScene).where(ImageryScene.id == scene_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[ImageryScene]:
        result = await self.db.execute(
            select(ImageryScene).order_by(ImageryScene.created_at.desc())
        )
        return result.scalars().all()


class AnalysisRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, **kwargs) -> ChangeDetectionAnalysis:
        analysis = ChangeDetectionAnalysis(**kwargs)
        self.db.add(analysis)
        await self.db.flush()
        await self.db.refresh(analysis)
        return analysis

    async def get_by_id(
        self, analysis_id: uuid.UUID
    ) -> Optional[ChangeDetectionAnalysis]:
        result = await self.db.execute(
            select(ChangeDetectionAnalysis)
            .where(ChangeDetectionAnalysis.id == analysis_id)
            .options(
                selectinload(ChangeDetectionAnalysis.statistics),
                selectinload(ChangeDetectionAnalysis.scene_t1),
                selectinload(ChangeDetectionAnalysis.scene_t2),
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[ChangeDetectionAnalysis]:
        result = await self.db.execute(
            select(ChangeDetectionAnalysis)
            .order_by(ChangeDetectionAnalysis.created_at.desc())
            .options(selectinload(ChangeDetectionAnalysis.statistics))
        )
        return result.scalars().all()

    async def update_status(
        self,
        analysis_id: uuid.UUID,
        status: JobStatus,
        celery_task_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        values: dict = {"status": status}
        if celery_task_id:
            values["celery_task_id"] = celery_task_id
        if error_message:
            values["error_message"] = error_message

        await self.db.execute(
            update(ChangeDetectionAnalysis)
            .where(ChangeDetectionAnalysis.id == analysis_id)
            .values(**values)
        )

    async def update_results(
        self,
        analysis_id: uuid.UUID,
        classified_t1_path: str,
        classified_t2_path: str,
        change_raster_path: str,
        change_png_path: str,
        processing_time_seconds: float,
    ) -> None:
        from datetime import datetime, timezone

        await self.db.execute(
            update(ChangeDetectionAnalysis)
            .where(ChangeDetectionAnalysis.id == analysis_id)
            .values(
                status=JobStatus.COMPLETED,
                classified_t1_path=classified_t1_path,
                classified_t2_path=classified_t2_path,
                change_raster_path=change_raster_path,
                change_png_path=change_png_path,
                processing_time_seconds=processing_time_seconds,
                completed_at=datetime.now(timezone.utc),
            )
        )

    async def add_statistics(
        self, stats: list[LandUseStatistic]
    ) -> None:
        self.db.add_all(stats)
        await self.db.flush()
