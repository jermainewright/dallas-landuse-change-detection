"use client";

import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Analysis } from "@/types/api";

// Dallas centroid
const DALLAS_CENTER: [number, number] = [32.78, -96.80];
const DALLAS_ZOOM = 10;

const LEGEND_ITEMS = [
  { color: "#e74c3c", label: "Urban / Built-up" },
  { color: "#27ae60", label: "Vegetation" },
  { color: "#2980b9", label: "Water" },
  { color: "#e67e22", label: "Bare Soil" },
  { color: "#dc14dc", label: "Change Detected" },
];

interface Props {
  analysis: Analysis;
}

export default function LeafletMap({ analysis }: Props) {
  const mapRef = useRef<L.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [layerControl, setLayerControl] = useState<L.Control.Layers | null>(null);

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    // Base tiles – dark CartoDB
    const darkTiles = L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/">CARTO</a>',
        subdomains: "abcd",
        maxZoom: 19,
      }
    );

    const satelliteTiles = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { attribution: "Esri, Maxar, GeoEye", maxZoom: 18 }
    );

    const map = L.map(containerRef.current, {
      center: DALLAS_CENTER,
      zoom: DALLAS_ZOOM,
      layers: [darkTiles],
      zoomControl: false,
    });
    mapRef.current = map;

    L.control.zoom({ position: "bottomright" }).addTo(map);

    // Change detection PNG overlay
    // In a real deployment, GeoTIFF tile servers (TiTiler, GeoServer) serve
    // proper tiled web map layers. Here we overlay the PNG as an image layer
    // bounded to Dallas's approximate extent.
    const dallasBounds: L.LatLngBoundsExpression = [[32.6, -97.0], [33.0, -96.5]];

    const changeOverlay = L.imageOverlay(
      `${API_BASE}/api/v1/analyses/${analysis.id}/export/png`,
      dallasBounds,
      { opacity: 0.75, interactive: false }
    );

    // Layer control
    const ctrl = L.control.layers(
      { "Dark Base": darkTiles, "Satellite": satelliteTiles },
      { "Change Detection Overlay": changeOverlay },
      { position: "topright", collapsed: false }
    ).addTo(map);
    setLayerControl(ctrl);
    changeOverlay.addTo(map);

    // AOI rectangle
    L.rectangle(dallasBounds, {
      color: "#00e5cc",
      weight: 1,
      fill: false,
      dashArray: "4 4",
      opacity: 0.4,
    }).addTo(map).bindPopup(
      `<div style="font-family:monospace;font-size:12px;color:#00e5cc">
        <strong>Dallas AOI</strong><br/>
        Analysis: ${analysis.name}<br/>
        Algorithm: v${analysis.algorithm_version}<br/>
        Duration: ${analysis.processing_time_seconds?.toFixed(1)}s
      </div>`
    );

    // Fit to AOI
    map.fitBounds(dallasBounds, { padding: [20, 20] });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [analysis.id]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />

      {/* Legend */}
      <div className="absolute bottom-4 left-4 z-[1000] bg-void-900/90 backdrop-blur border border-white/10 rounded-xl p-3 space-y-1.5">
        <p className="text-xs font-mono text-muted mb-2 uppercase tracking-widest">Legend</p>
        {LEGEND_ITEMS.map(({ color, label }) => (
          <div key={label} className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-sm shrink-0" style={{ background: color }} />
            <span className="text-xs font-mono text-slate-300">{label}</span>
          </div>
        ))}
      </div>

      {/* Analysis info badge */}
      <div className="absolute top-3 left-3 z-[1000] bg-void-900/90 backdrop-blur border border-signal-500/20 rounded-lg px-3 py-2">
        <p className="text-xs font-mono text-signal-400 font-semibold">{analysis.name}</p>
        <p className="text-[10px] font-mono text-muted mt-0.5">
          {analysis.processing_time_seconds?.toFixed(1)}s · v{analysis.algorithm_version}
        </p>
      </div>
    </div>
  );
}
