import StageCard from "./StageCard";
import type { StageStatus } from "../api/types";
import { STAGE_ORDER, STAGE_META } from "../api/types";

export interface StageState { status: StageStatus; model?: string; latencyMs?: number; tokens?: number; confidence?: number; outputSummary?: string; assumptions?: string[]; conflicts?: string[]; repaired?: boolean; }
interface Props { stages: Record<string, StageState>; onViewResults?: () => void; complete?: boolean; }

export default function PipelineProgress({ stages, onViewResults, complete }: Props) {
  const done = Object.values(stages).filter(s => s.status === "complete").length;
  const pct = Math.round((done / STAGE_ORDER.length) * 100);
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex-1 h-0.5 bg-ink-100 rounded-full overflow-hidden">
          <div className="h-full bg-accent-500 transition-all duration-500" style={{width:`${pct}%`}} />
        </div>
        <span className="text-xs font-mono text-ink-400">{done}/{STAGE_ORDER.length}</span>
      </div>
      <div className="space-y-1">
        {STAGE_ORDER.map(k => {
          const m = STAGE_META[k];
          const s = stages[k] ?? { status: "pending" as StageStatus };
          return <StageCard key={k} label={m.label} model={s.model || m.model} status={s.status} latencyMs={s.latencyMs} outputSummary={s.outputSummary} assumptions={s.assumptions} conflicts={s.conflicts} repaired={s.repaired} />;
        })}
      </div>
      {complete && onViewResults && (
        <button onClick={onViewResults} className="btn-primary w-full justify-center mt-2">
          View AppSpec →
        </button>
      )}
    </div>
  );
}