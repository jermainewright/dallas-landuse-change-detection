"use client";

import { useQuery } from "@tanstack/react-query";
import { analysesApi } from "@/lib/api";
import AnalysisCard from "./AnalysisCard";
import StatsOverview from "./StatsOverview";
import { PlusCircle, Loader2 } from "lucide-react";

interface Props {
  onSelectAnalysis: (id: string) => void;
  onNewAnalysis: () => void;
}

export default function AnalysisDashboard({ onSelectAnalysis, onNewAnalysis }: Props) {
  const { data: analyses, isLoading, error } = useQuery({
    queryKey: ["analyses"],
    queryFn: analysesApi.list,
    refetchInterval: (query) => {
      // Poll every 4 s while any job is running
      const hasRunning = query.state.data?.some((a) => a.status === "running" || a.status === "pending");
      return hasRunning ? 4000 : false;
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-muted gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="font-mono text-sm">Loading analyses…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-panel p-6 text-red-400 font-mono text-sm">
        Failed to load analyses: {(error as Error).message}
      </div>
    );
  }

  const completed = analyses?.filter((a) => a.status === "completed") ?? [];

  return (
    <div className="space-y-6 animate-[fadeInUp_0.4s_ease_forwards]">
      {/* Stats row */}
      <StatsOverview analyses={analyses ?? []} />

      {/* Analysis grid */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <span className="terminal-label">All Analyses · {analyses?.length ?? 0} jobs</span>
        </div>

        {(!analyses || analyses.length === 0) ? (
          <div className="glass-panel p-12 flex flex-col items-center gap-4 text-center">
            <div className="w-12 h-12 rounded-full bg-signal-500/10 border border-signal-500/20 flex items-center justify-center">
              <PlusCircle className="w-5 h-5 text-signal-500" />
            </div>
            <div>
              <p className="text-slate-300 font-display font-medium mb-1">No analyses yet</p>
              <p className="text-muted text-sm font-mono">
                Upload two imagery scenes and run your first change detection analysis.
              </p>
            </div>
            <button onClick={onNewAnalysis} className="btn-primary mt-2">
              <PlusCircle className="w-4 h-4" />
              Run First Analysis
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {analyses?.map((analysis) => (
              <AnalysisCard
                key={analysis.id}
                analysis={analysis}
                onSelect={() => onSelectAnalysis(analysis.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
