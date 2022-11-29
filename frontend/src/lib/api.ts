/**
 * Typed API client for the Dallas LandScan backend.
 * All methods return typed responses and throw on non-2xx status.
 */

import axios from "axios";
import type {
  ImageryScene,
  Analysis,
  AnalysisSummary,
  CreateAnalysisPayload,
  ExportFormat,
} from "@/types/api";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 30_000,
  headers: { "Content-Type": "application/json" },
});

// ─── Request interceptor: attach correlation ID ───────────────────────────────
apiClient.interceptors.request.use((config) => {
  config.headers["X-Request-ID"] = crypto.randomUUID();
  return config;
});

// ─── Response interceptor: normalise errors ───────────────────────────────────
apiClient.interceptors.response.use(
  (r) => r,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.error ||
      error.message ||
      "An unexpected error occurred";
    return Promise.reject(new Error(message));
  }
);

// ─── Scene API ────────────────────────────────────────────────────────────────
export const scenesApi = {
  list: async (): Promise<ImageryScene[]> => {
    const { data } = await apiClient.get("/scenes/");
    return data;
  },

  get: async (id: string): Promise<ImageryScene> => {
    const { data } = await apiClient.get(`/scenes/${id}`);
    return data;
  },

  upload: async (
    file: File,
    meta: { name: string; acquisition_year: number; satellite_source?: string },
    onProgress?: (pct: number) => void
  ): Promise<ImageryScene> => {
    const form = new FormData();
    form.append("file", file);
    form.append("name", meta.name);
    form.append("acquisition_year", String(meta.acquisition_year));
    form.append("satellite_source", meta.satellite_source || "Landsat8");

    const { data } = await apiClient.post("/scenes/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 300_000, // 5 min for large uploads
      onUploadProgress: (evt) => {
        if (onProgress && evt.total) {
          onProgress(Math.round((evt.loaded / evt.total) * 100));
        }
      },
    });
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/scenes/${id}`);
  },
};

// ─── Analysis API ─────────────────────────────────────────────────────────────
export const analysesApi = {
  list: async (): Promise<AnalysisSummary[]> => {
    const { data } = await apiClient.get("/analyses/");
    return data;
  },

  get: async (id: string): Promise<Analysis> => {
    const { data } = await apiClient.get(`/analyses/${id}`);
    return data;
  },

  getStatus: async (id: string) => {
    const { data } = await apiClient.get(`/analyses/${id}/status`);
    return data;
  },

  create: async (payload: CreateAnalysisPayload): Promise<Analysis> => {
    const { data } = await apiClient.post("/analyses/", payload);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/analyses/${id}`);
  },

  exportUrl: (id: string, format: ExportFormat): string => {
    return `${BASE_URL}/api/v1/analyses/${id}/export/${format}`;
  },
};
