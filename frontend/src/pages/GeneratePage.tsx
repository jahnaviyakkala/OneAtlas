import { useState, useCallback, useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Terminal, ArrowRight, Pencil, CheckCircle2, AlertTriangle, X, Send } from "lucide-react";
import PipelineProgress, { type StageState } from "../components/PipelineProgress";
import HITLModal from "../components/HITLModal";
import LogViewer from "../components/LogViewer";
import { useSSE } from "../hooks/useSSE";
import type { SSEEvent, HITLRequiredEvent, StageStatus } from "../api/types";
import { submitModification } from "../api/client";

// Stages that are "early enough" that a modification can still influence them.
// Once validation starts, modifications are informational only.
const MODIFIABLE_STAGES = new Set([
  "intent_extraction",
  "architecture_design",
  "db_schema",
  "api_schema",
  "ui_schema",
  "auth_schema",
]);

interface ModificationRecord {
  text: string;
  status: "queued" | "applied";
  appliedAtStage?: string;
  ts: string;
}

export default function GeneratePage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const sessionId = params.get("session");

  const [stages, setStages] = useState<Record<string, StageState>>({});
  const [logEntries, setLogEntries] = useState<string[]>([]);
  const [hitlEvent, setHitlEvent] = useState<HITLRequiredEvent | null>(null);
  const [complete, setComplete] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  // Modification state
  const [modifyText, setModifyText] = useState("");
  const [modifyOpen, setModifyOpen] = useState(false);
  const [modifySubmitting, setModifySubmitting] = useState(false);
  const [modifyError, setModifyError] = useState<string | null>(null);
  const [modifications, setModifications] = useState<ModificationRecord[]>([]);
  const modifyInputRef = useRef<HTMLTextAreaElement>(null);

  // Which stage is currently running (last "running" stage_update)
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  // Are we past the point where modifications can still influence remaining stages?
  const canStillModify = !complete && !failed && currentStage !== null;
  const modificationStillUseful =
    canStillModify && MODIFIABLE_STAGES.has(currentStage ?? "");

  useEffect(() => {
    if (!sessionId) navigate("/");
  }, [sessionId, navigate]);

  useEffect(() => {
    if (modifyOpen && modifyInputRef.current) {
      modifyInputRef.current.focus();
    }
  }, [modifyOpen]);

  const handleEvent = useCallback((event: SSEEvent) => {
    console.log("[GeneratePage] SSE:", event.event);

    if (event.event === "stage_update") {
      if (event.status === "running") {
        setCurrentStage(event.stage);
      }
      setStages(prev => ({
        ...prev,
        [event.stage]: {
          status: event.status as StageStatus,
          model: event.model,
          latencyMs: event.latency_ms,
          tokens: event.tokens_used,
          confidence: event.confidence,
          outputSummary: event.output_summary,
          assumptions: event.assumptions,
          conflicts: event.conflicts,
          repaired: event.status === "repair_triggered" ? true : prev[event.stage]?.repaired,
        },
      }));
      setLogEntries(prev => [
        ...prev,
        `[${new Date().toLocaleTimeString()}] ${event.stage} → ${event.status}${event.latency_ms ? ` (${event.latency_ms}ms)` : ""}`,
      ]);
    }

    if (event.event === "hitl_required") {
      setHitlEvent(event);
      setStages(prev => ({ ...prev, [event.stage]: { ...prev[event.stage], status: "hitl_required" } }));
    }

    if (event.event === "log_update") {
      setLogEntries(prev => [...prev, event.content]);
    }

    if (event.event === "pipeline_complete") {
      setComplete(true);
      setCurrentStage(null);
      setLogEntries(prev => [
        ...prev,
        `── Complete in ${event.total_latency_ms}ms · repairs:${event.repair_count} hitl:${event.hitl_count} ──`,
      ]);
    }

    if (event.event === "pipeline_failed") {
      setFailed(event.error);
      setCurrentStage(null);
      setLogEntries(prev => [...prev, `ERROR: ${event.error}`]);
    }

    if (event.event === "modification_queued") {
      setModifications(prev =>
        prev.map(m => m.text === event.modification && m.status === "queued"
          ? m  // already tracked
          : m
        )
      );
      setLogEntries(prev => [
        ...prev,
        `[${new Date().toLocaleTimeString()}] ✎ Modification queued: "${event.modification.slice(0, 60)}…"`,
      ]);
    }

    if (event.event === "modification_applied") {
      setModifications(prev =>
        prev.map(m =>
          m.text === event.modification
            ? { ...m, status: "applied", appliedAtStage: event.applied_at_stage }
            : m
        )
      );
      setLogEntries(prev => [
        ...prev,
        `[${new Date().toLocaleTimeString()}] ✔ Modification applied at stage: ${event.applied_at_stage}`,
      ]);
    }
  }, []);

  useSSE({ sessionId, onEvent: handleEvent });

  const handleModifySubmit = async () => {
    if (!sessionId || !modifyText.trim()) return;
    setModifySubmitting(true);
    setModifyError(null);
    try {
      await submitModification(sessionId, modifyText.trim());
      const record: ModificationRecord = {
        text: modifyText.trim(),
        status: "queued",
        ts: new Date().toLocaleTimeString(),
      };
      setModifications(prev => [...prev, record]);
      setModifyText("");
      setModifyOpen(false);
    } catch (err) {
      setModifyError(err instanceof Error ? err.message : String(err));
    } finally {
      setModifySubmitting(false);
    }
  };

  if (!sessionId) return null;

  return (
    <div className="h-screen bg-canvas-950 bg-noise flex flex-col overflow-hidden">

      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 border-b border-canvas-900 flex-shrink-0">
        <div className="flex items-center gap-3">
          <img src="/favicon.png" className="w-6 h-6 object-contain" alt="AppSpec logo" />
          <span className="font-display text-lg text-ink-900">AppSpec</span>
          <span className="text-canvas-700 mx-1 text-sm">/</span>
          <span className="text-xs text-canvas-500">Pipeline</span>
        </div>
        <div className="flex items-center gap-3">
          {/* Midway modify button */}
          {canStillModify && (
            <button
              onClick={() => setModifyOpen(v => !v)}
              className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-all border
                ${modifyOpen
                  ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                  : "bg-canvas-900 text-canvas-400 border-canvas-800 hover:text-canvas-200 hover:border-canvas-700"
                }`}
            >
              <Pencil className="w-3.5 h-3.5" />
              Modify Prompt
              {modifications.filter(m => m.status === "queued").length > 0 && (
                <span className="ml-0.5 w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
              )}
            </button>
          )}
          <span className="text-xs text-canvas-700 font-mono truncate max-w-[180px]">{sessionId?.slice(0, 16)}…</span>
        </div>
      </nav>

      {/* Disclaimer banner — shown while pipeline is running */}
      {!complete && !failed && (
        <div className="mx-5 mt-3 px-4 py-2.5 rounded-xl bg-amber-500/8 border border-amber-500/20 text-amber-300 text-xs flex items-center gap-2.5 flex-shrink-0">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
          <span>
            <strong>Intermediate results</strong> — schemas shown here are being actively generated and may change during the Validation &amp; Repair stages. Final output is shown on the Results page.
          </span>
        </div>
      )}

      {/* Modification queued / applied status */}
      {modifications.length > 0 && (
        <div className="mx-5 mt-2 flex flex-col gap-1 flex-shrink-0">
          {modifications.map((m, i) => (
            <div key={i} className={`px-3 py-1.5 rounded-lg text-xs flex items-center gap-2 border ${
              m.status === "applied"
                ? "bg-sage-600/8 border-sage-600/20 text-sage-400"
                : "bg-amber-500/8 border-amber-500/20 text-amber-300"
            }`}>
              {m.status === "applied"
                ? <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                : <Pencil className="w-3.5 h-3.5 flex-shrink-0 animate-pulse" />
              }
              <span className="truncate">
                {m.status === "applied"
                  ? `Applied at ${m.appliedAtStage}: `
                  : "Queued: "
                }
                <em className="not-italic font-medium">{m.text.slice(0, 80)}{m.text.length > 80 ? "…" : ""}</em>
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Modify prompt panel */}
      {modifyOpen && canStillModify && (
        <div className="mx-5 mt-2 flex-shrink-0 rounded-xl border border-amber-500/25 bg-canvas-900/80 p-4 backdrop-blur">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-amber-300 flex items-center gap-1.5">
              <Pencil className="w-3.5 h-3.5" />
              Midway Modification
            </span>
            <button onClick={() => setModifyOpen(false)} className="text-canvas-600 hover:text-canvas-400 transition-colors">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          {!modificationStillUseful && (
            <p className="text-xs text-canvas-500 mb-2 italic">
              ⚠ Validation has already started — your change will be logged but may not influence remaining stages.
            </p>
          )}
          <textarea
            ref={modifyInputRef}
            value={modifyText}
            onChange={e => setModifyText(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleModifySubmit();
            }}
            placeholder="e.g. Also add a notifications system with email alerts…"
            rows={3}
            className="w-full bg-canvas-950 border border-canvas-800 rounded-lg px-3 py-2 text-sm text-canvas-200 placeholder-canvas-700 resize-none focus:outline-none focus:border-amber-500/50 transition-colors"
          />
          {modifyError && (
            <p className="text-xs text-rose-400 mt-1">{modifyError}</p>
          )}
          <div className="flex items-center justify-between mt-2">
            <span className="text-xs text-canvas-600">Ctrl+Enter to send · Applied at next stage boundary</span>
            <button
              onClick={handleModifySubmit}
              disabled={!modifyText.trim() || modifySubmitting}
              className="flex items-center gap-1.5 text-xs font-semibold text-white px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              <Send className="w-3.5 h-3.5" />
              {modifySubmitting ? "Sending…" : "Send"}
            </button>
          </div>
        </div>
      )}

      {/* Error banner */}
      {failed && (
        <div className="mx-5 mt-4 px-4 py-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex-shrink-0">
          Pipeline failed: {failed}
        </div>
      )}

      {/* Body — two-panel layout */}
      <div className="flex-1 flex overflow-hidden mt-3">

        {/* Left — Pipeline (50%) */}
        <div className="w-1/2 border-r border-canvas-900 overflow-y-auto p-6">
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-xs font-semibold text-canvas-500 uppercase tracking-widest">
              Pipeline Stages
            </h2>
            {complete && (
              <button
                onClick={() => navigate(`/results?session=${sessionId}`)}
                className="flex items-center gap-1.5 text-xs font-semibold text-white
                           px-3 py-1.5 rounded-lg bg-terra-500 hover:bg-terra-400 transition-colors"
              >
                View Results <ArrowRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <PipelineProgress stages={stages} complete={complete} onViewResults={() => navigate(`/results?session=${sessionId}`)} />
        </div>

        {/* Right — Log (50%) */}
        <div className="w-1/2 flex flex-col overflow-hidden">
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-canvas-900 flex-shrink-0">
            <Terminal className="w-3.5 h-3.5 text-canvas-600" />
            <span className="text-xs font-semibold text-canvas-600 uppercase tracking-widest">Live Log</span>
          </div>
          <div className="flex-1 overflow-hidden">
            <LogViewer entries={logEntries} />
          </div>
        </div>
      </div>

      {/* HITL Modal */}
      {hitlEvent && (
        <HITLModal
          event={hitlEvent}
          onResume={() => {
            setHitlEvent(null);
            setStages(prev => ({ ...prev, [hitlEvent.stage]: { ...prev[hitlEvent.stage], status: "running" } }));
          }}
        />
      )}
    </div>
  );
}
