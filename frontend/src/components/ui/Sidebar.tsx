"use client";

import clsx from "clsx";
import { LayoutDashboard, Layers, Map, Activity, Github } from "lucide-react";

type View = "dashboard" | "scenes" | "map";

interface SidebarProps {
  activeView: View;
  onViewChange: (v: View) => void;
}

const navItems: { view: View; icon: React.ElementType; label: string }[] = [
  { view: "dashboard", icon: LayoutDashboard, label: "Analyses" },
  { view: "scenes", icon: Layers, label: "Scenes" },
  { view: "map", icon: Map, label: "Map" },
];

export default function Sidebar({ activeView, onViewChange }: SidebarProps) {
  return (
    <aside className="w-16 flex flex-col items-center py-5 gap-2 border-r border-white/5 bg-void-900/60 backdrop-blur-sm z-20 relative">
      <div className="mb-4 flex flex-col items-center">
        <div className="w-8 h-8 rounded-lg bg-signal-500/10 border border-signal-500/30 flex items-center justify-center">
          <Activity className="w-4 h-4 text-signal-500" />
        </div>
      </div>

      {navItems.map(({ view, icon: Icon, label }) => (
        <button
          key={view}
          onClick={() => onViewChange(view)}
          title={label}
          className={clsx(
            "w-10 h-10 rounded-lg flex items-center justify-center transition-all duration-200 group relative",
            activeView === view
              ? "bg-signal-500/15 text-signal-400 border border-signal-500/30"
              : "text-muted hover:text-slate-300 hover:bg-white/5"
          )}
        >
          <Icon className="w-4 h-4" />
          <span className="absolute left-full ml-3 px-2 py-1 rounded bg-void-700 text-xs font-mono text-slate-200 whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50">
            {label}
          </span>
        </button>
      ))}

      <div className="flex-1" />

      <a
        href="https://github.com"
        target="_blank"
        rel="noopener noreferrer"
        className="w-10 h-10 rounded-lg flex items-center justify-center text-muted hover:text-slate-300 hover:bg-white/5 transition-all"
        title="GitHub"
      >
        <Github className="w-4 h-4" />
      </a>
    </aside>
  );
}
