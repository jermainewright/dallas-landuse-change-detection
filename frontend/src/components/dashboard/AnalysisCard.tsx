"use client";

import { useQuery } from "@tanstack/react-query";
import { analysesApi } from "@/lib/api";
import { formatDistanceToNow } from "date-fns";
import { Map, Download, Loader2, ChevronRight } from "lucide-react";
import clsx from "clsx";
import type { AnalysisSummary, ExportFormat } from "@/types/api";

interface Props {
  analysis: AnalysisSummary;
  onSelect: () => void;
}

const STATUS_CONFIG = {
  pending:   { cls: "status-pending",   label: "Pending",   pulse: false },
  running:   { cls: "status-running",   label: "Running",   pulse: true  },
  completed: { cls: "status-completed", label: "Completed", pulse: false },
  failed:    { cls: "status-failed",    label: "Failed",    pulse: false },
};

export default function AnalysisCard({ analysis, onSelect }: Props) {
  const { status, id, name, created_at, processing_time_seconds } = analysis;
  const cfg = STATUS_CONFIG[status];

  const handleExport = (format: ExportFormat) => {
    window.open(analysesApi.exportUrl(id, format), "_blank");
  };

  return (
    <div
      className={clsx(
        "glass-panel p-5 flex flex-col gap-4 cursor-pointer group transition-all duration-200",
        "hover:border-signal-500/25 hover:shadow-[0_0_20px_rgba(0,229,204,0.04)]"
      )}
      onClick={onSelect}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-display font-semibold text-slate-100 truncate group-hover:text-signal-400 transition-colors">
            {name}
          </h3>
          <p className="text-xs text-muted font-mono mt-0.5">
            {formatDistanceToNow(new Date(created_at), { addSuffix: true })}
          </p>
        </div>
        <span className={cfg.cls}>
          {cfg.pulse && (
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-signal-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-signal-500" />
            </span>
          )}
          {cfg.label}
        </span>
      </div>

      {/* Processing time */}
      {processing_time_seconds != null && (
        <div className="flex items-center gap-1.5 text-xs text-muted font-mono">
          <Loader2 className="w-3 h-3 text-signal-500/60" />
          Processed in {processing_time_seconds.toFixed(1)}s
        </div>
      )}

      {/* Actions */}
      {status === "completed" && (
        <div className="flex items-center gap-2 pt-1 border-t border-white/5">
          <button
            onClick={(e) => { e.stopPropagation(); onSelect(); }}
            className="btn-ghost text-xs py-1.5 px-3 flex-1"
          >
            <Map className="w-3 h-3" /> View Map
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); handleExport("geotiff"); }}
            className="btn-ghost text-xs py-1.5 px-3"
            title="Download GeoTIFF"
          >
            <Download className="w-3 h-3" />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); handleExport("json"); }}
            className="btn-ghost text-xs py-1.5 px-3"
            title="Download JSON Stats"
          >
            JSON
          </button>
        </div>
      )}

      {status === "failed" && (
        <div className="text-xs text-red-400 font-mono bg-red-500/5 border border-red-500/10 rounded-lg px-3 py-2">
          Processing failed. Check worker logs.
        </div>
      )}
    </div>
  );
}
