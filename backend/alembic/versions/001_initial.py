"""enable PostGIS and create initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
import geoalchemy2

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable PostGIS extension
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis_topology")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # imagery_scenes table
    op.create_table(
        "imagery_scenes",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("acquisition_year", sa.Integer, nullable=False),
        sa.Column("satellite_source", sa.String(50), nullable=False, server_default="Landsat8"),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("file_size_mb", sa.Float),
        sa.Column("crs_epsg", sa.Integer, server_default="32614"),
        sa.Column("spatial_extent", geoalchemy2.types.Geometry("POLYGON", srid=4326)),
        sa.Column("band_count", sa.Integer, server_default="6"),
        sa.Column("resolution_m", sa.Float, server_default="30.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # change_detection_analyses table
    op.create_table(
        "change_detection_analyses",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("scene_t1_id", sa.UUID(as_uuid=True), sa.ForeignKey("imagery_scenes.id"), nullable=False),
        sa.Column("scene_t2_id", sa.UUID(as_uuid=True), sa.ForeignKey("imagery_scenes.id"), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "completed", "failed", name="jobstatus"), server_default="pending"),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column("error_message", sa.Text),
        sa.Column("classified_t1_path", sa.Text),
        sa.Column("classified_t2_path", sa.Text),
        sa.Column("change_raster_path", sa.Text),
        sa.Column("change_png_path", sa.Text),
        sa.Column("processing_time_seconds", sa.Float),
        sa.Column("algorithm_version", sa.String(20), server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    # land_use_statistics table
    op.create_table(
        "land_use_statistics",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("analysis_id", sa.UUID(as_uuid=True), sa.ForeignKey("change_detection_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("time_period", sa.String(5), nullable=False),
        sa.Column("land_use_class", sa.Enum("urban", "vegetation", "water", "bare_soil", name="landuseclass"), nullable=False),
        sa.Column("area_km2", sa.Float, nullable=False),
        sa.Column("area_percent", sa.Float, nullable=False),
        sa.Column("pixel_count", sa.Integer, nullable=False),
        sa.Column("change_km2", sa.Float),
        sa.Column("change_percent", sa.Float),
    )

    # Indexes
    op.create_index("ix_analyses_status", "change_detection_analyses", ["status"])
    op.create_index("ix_stats_analysis_id", "land_use_statistics", ["analysis_id"])


def downgrade() -> None:
    op.drop_table("land_use_statistics")
    op.drop_table("change_detection_analyses")
    op.drop_table("imagery_scenes")
    op.execute("DROP TYPE IF EXISTS jobstatus")
    op.execute("DROP TYPE IF EXISTS landuseclass")
