"use client";

import { useState } from "react";
import Sidebar from "@/components/ui/Sidebar";
import TopBar from "@/components/ui/TopBar";
import AnalysisDashboard from "@/components/dashboard/AnalysisDashboard";
import SceneManager from "@/components/dashboard/SceneManager";
import NewAnalysisModal from "@/components/dashboard/NewAnalysisModal";
import MapView from "@/components/map/MapView";

type ActiveView = "dashboard" | "scenes" | "map";

export default function HomePage() {
  const [activeView, setActiveView] = useState<ActiveView>("dashboard");
  const [showNewAnalysis, setShowNewAnalysis] = useState(false);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<string | null>(null);

  return (
    <div className="flex h-screen overflow-hidden bg-void-950">
      {/* Grid texture overlay */}
      <div
        className="pointer-events-none fixed inset-0 z-0 opacity-100"
        style={{
          backgroundImage:
            "linear-gradient(rgba(0,229,204,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(0,229,204,0.025) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />

      <Sidebar activeView={activeView} onViewChange={setActiveView} />

      <div className="flex flex-1 flex-col overflow-hidden relative z-10">
        <TopBar
          activeView={activeView}
          onNewAnalysis={() => setShowNewAnalysis(true)}
        />

        <main className="flex-1 overflow-auto p-6">
          {activeView === "dashboard" && (
            <AnalysisDashboard
              onSelectAnalysis={setSelectedAnalysisId}
              onNewAnalysis={() => setShowNewAnalysis(true)}
            />
          )}
          {activeView === "scenes" && <SceneManager />}
          {activeView === "map" && (
            <MapView analysisId={selectedAnalysisId} />
          )}
        </main>
      </div>

      {showNewAnalysis && (
        <NewAnalysisModal onClose={() => setShowNewAnalysis(false)} />
      )}
    </div>
  );
}
