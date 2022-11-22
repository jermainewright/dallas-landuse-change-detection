"""
Centralised configuration management using Pydantic Settings.
All values are read from environment variables or .env file.
"""

from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App ──────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    SECRET_KEY: str = "insecure-default-change-in-production"
    LOG_LEVEL: str = "INFO"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:80"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # ─── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+asyncpg://landuse:landuse_secret@localhost:5432/landuse_db"
    )
    SYNC_DATABASE_URL: str = (
        "postgresql+psycopg2://landuse:landuse_secret@localhost:5432/landuse_db"
    )

    # ─── Redis / Celery ───────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ─── GIS / Raster ─────────────────────────────────────────────────────────
    RASTER_DATA_PATH: str = "/app/data/rasters"
    OUTPUT_DATA_PATH: str = "/app/data/outputs"
    MAX_RASTER_SIZE_MB: int = 500
    GDAL_CACHEMAX: int = 512  # MB

    # Dallas bounding box (WGS84 EPSG:4326)
    DALLAS_BBOX_MINX: float = -97.0
    DALLAS_BBOX_MINY: float = 32.6
    DALLAS_BBOX_MAXX: float = -96.5
    DALLAS_BBOX_MAXY: float = 33.0

    # ─── Storage ──────────────────────────────────────────────────────────────
    USE_S3: bool = False
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "landuse-rasters"

    # ─── Observability ────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def dallas_bbox(self) -> tuple[float, float, float, float]:
        """Returns (minx, miny, maxx, maxy) tuple."""
        return (
            self.DALLAS_BBOX_MINX,
            self.DALLAS_BBOX_MINY,
            self.DALLAS_BBOX_MAXX,
            self.DALLAS_BBOX_MAXY,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
