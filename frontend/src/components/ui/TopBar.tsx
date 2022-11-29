"use client";

import { Plus, Satellite } from "lucide-react";

type View = "dashboard" | "scenes" | "map";

const VIEW_TITLES: Record<View, { title: string; subtitle: string }> = {
  dashboard: { title: "Change Detection Analyses", subtitle: "Dallas, Texas · Landsat 8/9" },
  scenes:    { title: "Imagery Scene Manager", subtitle: "Upload & manage satellite scenes" },
  map:       { title: "Interactive Map View", subtitle: "Spatial visualisation & layer control" },
};

interface TopBarProps {
  activeView: View;
  onNewAnalysis: () => void;
}

export default function TopBar({ activeView, onNewAnalysis }: TopBarProps) {
  const { title, subtitle } = VIEW_TITLES[activeView];

  return (
    <header className="h-14 flex items-center justify-between px-6 border-b border-white/5 bg-void-900/40 backdrop-blur-sm shrink-0">
      <div className="flex items-center gap-3">
        <Satellite className="w-4 h-4 text-signal-500" />
        <div>
          <h1 className="text-sm font-display font-semibold text-slate-100 leading-none">
            {title}
          </h1>
          <p className="text-xs text-muted font-mono mt-0.5">{subtitle}</p>
        </div>
      </div>

      <button onClick={onNewAnalysis} className="btn-primary text-xs py-2 px-4">
        <Plus className="w-3.5 h-3.5" />
        New Analysis
      </button>
    </header>
  );
}
