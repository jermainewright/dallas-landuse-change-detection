export type JobStatus = "pending" | "running" | "completed" | "failed";
export type LandUseClass = "urban" | "vegetation" | "water" | "bare_soil";
export type ExportFormat = "geotiff" | "png" | "json";

export interface ImageryScene {
  id: string;
  name: string;
  acquisition_year: number;
  satellite_source: string;
  file_path: string;
  file_size_mb: number | null;
  crs_epsg: number;
  band_count: number;
  resolution_m: number;
  created_at: string;
}

export interface LandUseStatistic {
  land_use_class: LandUseClass;
  time_period: "t1" | "t2";
  area_km2: number;
  area_percent: number;
  pixel_count: number;
  change_km2: number | null;
  change_percent: number | null;
}

export interface Analysis {
  id: string;
  name: string;
  description: string | null;
  scene_t1_id: string;
  scene_t2_id: string;
  status: JobStatus;
  celery_task_id: string | null;
  error_message: string | null;
  classified_t1_path: string | null;
  classified_t2_path: string | null;
  change_raster_path: string | null;
  change_png_path: string | null;
  processing_time_seconds: number | null;
  algorithm_version: string;
  created_at: string;
  completed_at: string | null;
  statistics: LandUseStatistic[];
}

export interface AnalysisSummary {
  id: string;
  name: string;
  status: JobStatus;
  processing_time_seconds: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface CreateAnalysisPayload {
  name: string;
  description?: string;
  scene_t1_id: string;
  scene_t2_id: string;
}

// Computed chart data types
export interface ClassChartDatum {
  name: string;
  t1: number;
  t2: number;
  change: number;
  color: string;
}

export interface TransitionDatum {
  from: LandUseClass;
  to: LandUseClass;
  area_km2: number;
}
