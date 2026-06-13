import { Info } from "lucide-react";

interface AssumptionsPanelProps {
  assumptions: string[];
}

export default function AssumptionsPanel({ assumptions }: AssumptionsPanelProps) {
  if (!assumptions.length) return null;
  return (
    <div className="rounded-xl border border-canvas-800 bg-canvas-900 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Info className="w-4 h-4 text-blue-400" />
        <h3 className="text-sm font-semibold text-canvas-200">
          Assumptions
          <span className="ml-2 text-xs font-normal text-canvas-500">({assumptions.length})</span>
        </h3>
      </div>
      <ul className="space-y-1.5">
        {assumptions.map((a, i) => (
          <li key={i} className="text-xs text-canvas-400 flex gap-2">
            <span className="text-canvas-700 flex-shrink-0 font-mono">{String(i + 1).padStart(2, "0")}</span>
            <span>{a}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
