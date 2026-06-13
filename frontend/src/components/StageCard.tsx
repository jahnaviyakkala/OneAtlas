import { useState } from "react";
import type { StageStatus } from "../api/types";

interface Props {
  label: string; model: string; status: StageStatus;
  latencyMs?: number; outputSummary?: string;
  assumptions?: string[]; conflicts?: string[]; repaired?: boolean;
}

const DOT: Record<StageStatus, string> = {
  pending: "bg-ink-200",
  running: "bg-accent-500 animate-pulse",
  complete: "bg-green-600",
  failed: "bg-red-600",
  repair_triggered: "bg-amber-600",
  hitl_required: "bg-amber-500 animate-pulse",
};

const LABEL_CLS: Record<StageStatus, string> = {
  pending: "text-ink-400",
  running: "text-ink-800 font-medium",
  complete: "text-ink-800",
  failed: "text-red-700",
  repair_triggered: "text-amber-700",
  hitl_required: "text-amber-700",
};

export default function StageCard({ label, model, status, latencyMs, outputSummary, assumptions=[], conflicts=[], repaired }: Props) {
  const [open, setOpen] = useState(false);
  const hasExtra = assumptions.length > 0 || conflicts.length > 0 || !!outputSummary;

  return (
    <div className={`border-l-2 pl-4 py-1.5 ${status === 'complete' ? 'border-green-500' : status === 'failed' ? 'border-red-500' : status === 'repair_triggered' ? 'border-amber-500' : 'border-ink-200'}`}>
      <div className="flex items-center gap-2.5">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${DOT[status]}`} />
        <span className={`text-sm flex-1 flex items-center gap-2 ${LABEL_CLS[status]}`}>
          {label}
          {model && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-sm bg-ink-100 text-ink-500 font-mono tracking-tighter truncate max-w-[120px]" title={model}>
              {model.split('/').pop()}
            </span>
          )}
        </span>
        {repaired && <span className="text-[10px] font-mono bg-amber-50 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded">repaired</span>}
        {status === "hitl_required" && <span className="text-[10px] font-mono bg-amber-50 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded">awaiting input</span>}
        {status === "complete" && latencyMs && <span className="text-[10px] font-mono text-ink-400">{latencyMs}ms</span>}
        {hasExtra && status !== "pending" && (
          <button onClick={() => setOpen(o => !o)} className="text-[10px] text-ink-400 hover:text-ink-700 font-mono">
            {open ? "▲" : "▼"}
          </button>
        )}
      </div>
      {open && hasExtra && (
        <div className="mt-2 ml-4 space-y-1.5 text-xs">
          {outputSummary && <p className="font-mono text-ink-500 break-all">{outputSummary}</p>}
          {assumptions.map((a,i) => <p key={i} className="text-ink-500">→ {a}</p>)}
          {conflicts.map((c,i) => <p key={i} className="text-amber-700">⚠ {c}</p>)}
        </div>
      )}
    </div>
  );
}