import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { startPipeline } from "../api/client";

const EX = [
  "CRM for a real estate agency. Agents manage leads, properties, and deals. WhatsApp notifications when a deal closes.",
  "Task manager for an engineering team. Tasks have due dates, assignees, priorities. Slack alert when a task is overdue.",
  "E-commerce backend. Products, orders, customers, payments via Stripe. Gmail order confirmation.",
];

export default function HomePage() {
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const go = async () => {
    if (!prompt.trim()) return;
    setLoading(true); setError("");
    try {
      const { session_id } = await startPipeline(prompt.trim());
      navigate(`/generate?session=${session_id}`);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-ink-50 flex flex-col">
      {/* Header */}
      <header className="border-b border-ink-200 bg-ink-100 px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-base font-semibold text-ink-900">AppSpec</span>
          <span className="text-ink-300">/</span>
          <span className="font-mono text-xs text-ink-400">engine</span>
        </div>
        <nav className="flex items-center gap-4">
          <a href="/eval" className="text-xs text-ink-500 hover:text-ink-800 font-mono">eval</a>
          <a href="https://github.com/Lokesh-916/oneatlas" target="_blank" rel="noreferrer" className="text-xs text-ink-500 hover:text-ink-800 font-mono">github</a>
        </nav>
      </header>

      {/* Main */}
      <main className="flex-1 flex flex-col lg:flex-row max-w-5xl mx-auto w-full gap-12 px-8 py-16">
        {/* Left */}
        <div className="flex-1 space-y-8">
          <div className="space-y-3">
            <p className="text-xs font-mono text-ink-400 tracking-widest uppercase">OneAtlas · AppSpec Engine</p>
            <h1 className="font-mono text-3xl font-semibold text-ink-900 leading-snug">
              Describe your app.<br/>Get the spec.
            </h1>
            <p className="text-sm text-ink-500 leading-relaxed max-w-sm">
              Multi-stage AI pipeline that converts natural language into a validated AppSpec — entities, APIs, auth, integrations, and workflow stubs.
            </p>
          </div>

          <div className="space-y-2">
            <textarea
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) go(); }}
              placeholder="Describe the application you want to build…"
              rows={5}
              className="input-field resize-none"
            />
            {error && <p className="text-xs text-red-600 font-mono">{error}</p>}
            <div className="flex items-center gap-3">
              <button onClick={go} disabled={!prompt.trim() || loading} className="btn-primary">
                {loading ? "Starting…" : "Generate AppSpec"}
              </button>
              <span className="text-xs text-ink-400 font-mono">Ctrl+Enter</span>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-mono text-ink-400 uppercase tracking-wider">Examples</p>
            {EX.map(ex => (
              <button key={ex} onClick={() => setPrompt(ex)} className="w-full text-left text-xs text-ink-600 hover:text-ink-900 px-3 py-2 rounded border border-ink-200 hover:border-ink-400 bg-ink-100 hover:bg-ink-200 transition-all font-mono leading-relaxed">
                {ex}
              </button>
            ))}
          </div>
        </div>

        {/* Right — pipeline stages */}
        <div className="lg:w-64 space-y-4">
          <p className="text-xs font-mono text-ink-400 uppercase tracking-wider">Pipeline stages</p>
          <div className="space-y-px">
            {[
              "01  Intent Extraction",
              "02  Architecture Design",
              "03  DB / API / UI / Auth",
              "04  Workflow Stubs",
              "05  Cross-layer Validation",
              "06  Repair Loop",
              "07  Runtime Simulation",
              "08  AppSpec Assembly",
            ].map(s => (
              <div key={s} className="flex items-center gap-3 py-2 border-b border-ink-100">
                <span className="text-xs font-mono text-ink-700">{s}</span>
              </div>
            ))}
          </div>
          <div className="space-y-px mt-4">
            <p className="text-xs font-mono text-ink-400 uppercase tracking-wider mb-2">Integrations</p>
            {["Slack","Gmail","Stripe","WhatsApp","Google Sheets","Webhook"].map(i => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b border-ink-100">
                <span className="text-xs text-ink-700">{i}</span>
                <span className="text-[10px] font-mono text-green-700">live</span>
              </div>
            ))}
            {["Jira","HubSpot","Notion","Twilio SMS"].map(i => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b border-ink-100">
                <span className="text-xs text-ink-400">{i}</span>
                <span className="text-[10px] font-mono text-ink-400">stub</span>
              </div>
            ))}
          </div>
        </div>
      </main>

      <footer className="border-t border-ink-200 px-8 py-3 flex items-center justify-between">
        <span className="text-xs font-mono text-ink-300">AppSpec Engine · OneAtlas</span>
        <span className="text-xs font-mono text-ink-300">Python · CrewAI · Groq</span>
      </footer>
    </div>
  );
}