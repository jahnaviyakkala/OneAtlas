import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import SchemaViewer from "../components/SchemaViewer";
import MermaidDiagram from "../components/MermaidDiagram";
import IntegrationsPanel from "../components/IntegrationsPanel";
import { getResult } from "../api/client";

type Tab = "appspec"|"database"|"api"|"auth"|"validation"|"diagrams"|"raw";
const TABS:Tab[] = ["appspec","database","api","auth","validation","diagrams","raw"];
const TAB_LABELS:Record<Tab,string> = { appspec:"AppSpec", database:"Database", api:"API", auth:"Auth", validation:"Validation", diagrams:"Diagrams", raw:"Raw JSON" };

export default function ResultsPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const sessionId = params.get("session");
  const [tab, setTab] = useState<Tab>("appspec");
  const [result, setResult] = useState<Record<string,unknown>|null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!sessionId) { navigate("/"); return; }
    getResult(sessionId).then(d => { setResult(d); setLoading(false); }).catch(e => {
      if (e.message.includes("202")) navigate(`/generate?session=${sessionId}`);
      else { setError(e.message); setLoading(false); }
    });
  }, [sessionId, navigate]);

  if (loading) return <div className="h-screen bg-ink-50 flex items-center justify-center"><span className="text-xs font-mono text-ink-400">loading…</span></div>;
  if (error) return <div className="h-screen bg-ink-50 flex items-center justify-center"><div className="text-center"><p className="text-sm text-red-600 font-mono">{error}</p><button onClick={() => navigate("/")} className="mt-4 text-xs text-ink-400 hover:text-ink-700 font-mono underline">back</button></div></div>;

  const mermaid = (result?.mermaid_diagrams??{}) as Record<string,string>;
  const metrics = result?.eval_metrics as Record<string,unknown>|undefined;
  const validation = result?.validation_report as Record<string,unknown>|undefined;
  const hooks = (result?.integration_hooks as unknown[]??[]) as Array<{hook_id:string;integration_id:string;action_id:string;auth_type:string;validation_status:string}>;
  const stubs = (result?.workflow_stubs as unknown[]??[]) as Array<{name:string;trigger:{entity:string;event:string;condition?:string};integration_id:string;action_id:string;hook_id?:string;is_valid:boolean}>;
  const repairLog = (result?.repair_log as unknown[]??[]) as Array<{attempt_number:number;strategy:string;outcome:string;error_input:string;errors_before:number;errors_after:number}>;
  const appSpec = result?.app_spec as Record<string,unknown>|undefined;
  const validationErrors = (validation?.errors as unknown[])??[];
  const validationPassed = validationErrors.length === 0 && !!validation?.validated_at;

  return (
    <div className="h-screen bg-ink-50 flex flex-col overflow-hidden">
      {/* Nav */}
      <header className="border-b border-ink-200 bg-ink-100 px-6 py-3 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <button onClick={() => navigate("/")} className="text-xs font-mono text-ink-400 hover:text-ink-800">AppSpec</button>
          <span className="text-ink-300">/</span>
          <span className="text-xs font-mono text-ink-700">results</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => { const b=new Blob([JSON.stringify(result,null,2)],{type:"application/json"});const u=URL.createObjectURL(b);const a=document.createElement("a");a.href=u;a.download=`appspec-${sessionId}.json`;a.click();URL.revokeObjectURL(u); }} className="btn-ghost text-xs py-1.5 px-3">Download JSON</button>
          <button onClick={() => navigate("/")} className="btn-ghost text-xs py-1.5 px-3">New</button>
        </div>
      </header>

      {/* Tabs */}
      <div className="border-b border-ink-200 bg-ink-100 px-4 flex items-end gap-0 overflow-x-auto flex-shrink-0">
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)} className={`px-4 py-2.5 text-xs font-mono border-b-2 transition-all whitespace-nowrap ${tab === t ? "border-ink-900 text-ink-900" : "border-transparent text-ink-500 hover:text-ink-700 hover:border-ink-200"}`}>
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Main panel */}
        <div className="flex-1 overflow-y-auto p-6">
          {tab === "appspec" && (
            <div className="max-w-2xl mx-auto space-y-6">
              {/* Metrics strip */}
              {metrics && (
                <div className="grid grid-cols-4 gap-3">
                  {[
                    {k:"Latency", v:`${Math.round((metrics.total_latency_ms as number)/1000)}s`},
                    {k:"Tokens", v:String(metrics.total_tokens??0)},
                    {k:"Repairs", v:String(metrics.repair_count??0)},
                    {k:"Cost", v:`$${(metrics.total_cost_usd as number || 0).toFixed(3)}`},
                  ].map(c => (
                    <div key={c.k} className="card px-4 py-3">
                      <p className="text-[10px] font-mono text-ink-400 uppercase">{c.k}</p>
                      <p className="text-lg font-mono font-semibold text-ink-900 mt-0.5">{c.v}</p>
                    </div>
                  ))}
                </div>
              )}
              <IntegrationsPanel hooks={hooks} stubs={stubs} repairLog={repairLog} appSpec={appSpec} />
            </div>
          )}
          {tab === "database" && <SchemaViewer data={result?.db_schema} title="Database Schema" />}
          {tab === "api" && <SchemaViewer data={result?.api_schema} title="API Schema" />}
          {tab === "auth" && <SchemaViewer data={result?.auth_schema} title="Auth Schema" />}
          {tab === "validation" && (
            <div className="max-w-2xl mx-auto space-y-4">
              <div className={`card px-4 py-3 flex items-center gap-3 ${validationPassed ? "bg-green-50 border-green-200 text-green-800" : "bg-red-50 border-red-200 text-red-800"}`}>
                <span className="font-mono text-sm">{validationPassed ? "✓ valid" : `✗ ${validationErrors.length} error(s)`}</span>
              </div>
              <SchemaViewer data={result?.validation_report} title="Validation Report" />
            </div>
          )}
          {tab === "diagrams" && (
            <div className="max-w-4xl mx-auto space-y-6">
              <MermaidDiagram title="Pipeline Flow" source={mermaid.pipeline_flow??""} />
              <MermaidDiagram title="ER Diagram" source={mermaid.er_diagram??""} />
              <MermaidDiagram title="API Sequence" source={mermaid.api_sequence??""} />
            </div>
          )}
          {tab === "raw" && <SchemaViewer data={result} title="Full Output" />}
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-ink-200 bg-ink-100 px-5 py-2 flex items-center justify-between flex-shrink-0">
        <span className="text-[10px] font-mono text-ink-300">{sessionId?.slice(0,16)}…</span>
        <button onClick={() => navigate(`/generate?session=${sessionId}`)} className="text-xs font-mono text-ink-400 hover:text-ink-700">← pipeline</button>
      </div>
    </div>
  );
}