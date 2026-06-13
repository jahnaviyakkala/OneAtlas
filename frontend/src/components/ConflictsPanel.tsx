import { AlertTriangle, CheckCircle2 } from "lucide-react";

interface Conflict {
  description: string;
  resolution_strategy: string;
}

interface ConflictsPanelProps {
  conflicts: Conflict[];
}

export default function ConflictsPanel({ conflicts }: ConflictsPanelProps) {
  if (!conflicts.length) return null;
  return (
    <div className="rounded-xl border border-orange-900/40 bg-canvas-900 p-4">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="w-4 h-4 text-orange-400" />
        <h3 className="text-sm font-semibold text-canvas-200">
          Conflicts
          <span className="ml-2 text-xs font-normal text-canvas-500">({conflicts.length})</span>
        </h3>
      </div>
      <div className="space-y-3">
        {conflicts.map((c, i) => (
          <div key={i} className="rounded-lg bg-canvas-800/60 border border-canvas-800 p-3 space-y-1.5">
            <p className="text-xs text-orange-300 flex gap-2">
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              {c.description}
            </p>
            <p className="text-xs text-green-400 flex gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              {c.resolution_strategy}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
