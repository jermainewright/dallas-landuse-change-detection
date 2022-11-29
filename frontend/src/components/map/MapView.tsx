"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { analysesApi } from "@/lib/api";
import dynamic from "next/dynamic";
import ChangeChart from "@/components/dashboard/ChangeChart";
import { Download, Layers, BarChart2, Map as MapIcon, Loader2 } from "lucide-react";
import clsx from "clsx";

// Leaflet must be loaded client-side only
const LeafletMap = dynamic(() => import("./LeafletMap"), { ssr: false, loading: () => (
  <div className="h-full flex items-center justify-center text-muted font-mono text-sm gap-2">
    <Loader2 className="w-4 h-4 animate-spin" /> Initialising map…
  </div>
) });

interface Props {
  analysisId: string | null;
}

type Panel = "chart" | "map";

export default function MapView({ analysisId }: Props) {
  const [activePanel, setActivePanel] = useState<Panel>("map");

  const { data: analysis, isLoading } = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => analysesApi.get(analysisId!),
    enabled: !!analysisId,
  });

  if (!analysisId) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-center">
        <div className="w-12 h-12 rounded-full bg-signal-500/10 border border-signal-500/20 flex items-center justify-center">
          <MapIcon className="w-5 h-5 text-signal-500" />
        </div>
        <p className="text-slate-300 font-display font-medium">No analysis selected</p>
        <p className="text-muted text-sm font-mono">
          Select a completed analysis from the Dashboard to view its map.
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-muted gap-2 font-mono text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading analysis…
      </div>
    );
  }

  if (!analysis || analysis.status !== "completed") {
    return (
      <div className="glass-panel p-6 text-muted font-mono text-sm">
        {analysis ? `Analysis status: ${analysis.status}` : "Analysis not found."}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full gap-4 animate-[fadeInUp_0.4s_ease_forwards]">
      {/* Panel toggle + export */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 glass-panel p-1 rounded-lg">
          {([
            { id: "map", icon: MapIcon, label: "Map" },
            { id: "chart", icon: BarChart2, label: "Analytics" },
          ] as const).map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setActivePanel(id)}
              className={clsx(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-mono transition-all",
                activePanel === id
                  ? "bg-signal-500/15 text-signal-400 border border-signal-500/30"
                  : "text-muted hover:text-slate-300"
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => window.open(analysesApi.exportUrl(analysis.id, "geotiff"), "_blank")}
            className="btn-ghost text-xs py-1.5 px-3"
          >
            <Download className="w-3 h-3" /> GeoTIFF
          </button>
          <button
            onClick={() => window.open(analysesApi.exportUrl(analysis.id, "png"), "_blank")}
            className="btn-ghost text-xs py-1.5 px-3"
          >
            <Download className="w-3 h-3" /> PNG
          </button>
          <button
            onClick={() => window.open(analysesApi.exportUrl(analysis.id, "json"), "_blank")}
            className="btn-ghost text-xs py-1.5 px-3"
          >
            <Download className="w-3 h-3" /> JSON
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0">
        {activePanel === "map" ? (
          <div className="h-full rounded-xl overflow-hidden border border-white/5">
            <LeafletMap analysis={analysis} />
          </div>
        ) : (
          <div className="glass-panel p-6 h-full overflow-auto">
            <ChangeChart analysis={analysis} />
          </div>
        )}
      </div>
    </div>
  );
}
