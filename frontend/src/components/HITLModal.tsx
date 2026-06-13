import { useState, useEffect } from "react";
import type { HITLRequiredEvent } from "../api/types";
import { submitClarify } from "../api/client";

interface Props { event: HITLRequiredEvent; onResume: () => void; }

export default function HITLModal({ event, onResume }: Props) {
  const [answers, setAnswers] = useState(event.questions.map(() => ""));
  const [chosen, setChosen] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [timeLeft, setTimeLeft] = useState(event.timeout_seconds);

  useEffect(() => {
    if (timeLeft <= 0) return;
    const t = setInterval(() => setTimeLeft(s => s - 1), 1000);
    return () => clearInterval(t);
  }, [timeLeft]);

  const canSubmit = event.options ? chosen !== "" : answers.every(a => a.trim() !== "");

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await submitClarify(event.session_id, event.options ? [chosen] : answers, event.options ? chosen : undefined);
      onResume();
    } catch { setSubmitting(false); }
  };

  const mins = Math.floor(timeLeft/60);
  const secs = String(timeLeft%60).padStart(2,"0");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md mx-4 bg-ink-100 border border-ink-200 rounded-lg shadow-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-ink-100">
          <div>
            <p className="text-sm font-semibold text-ink-900">Clarification needed</p>
            <p className="text-xs text-ink-400 font-mono mt-0.5">stage: {event.stage}</p>
          </div>
          <span className="font-mono text-sm text-ink-500">{mins}:{secs}</span>
        </div>
        <div className="px-5 py-4 space-y-4">
          {event.options ? (
            <div className="space-y-2">
              <p className="text-sm text-ink-700">{event.questions[0]}</p>
              {event.options.map(opt => (
                <label key={opt} className={`flex items-center gap-3 p-3 rounded border cursor-pointer ${chosen===opt?"border-accent-500 bg-accent-50":"border-ink-200 hover:border-ink-300"}`}>
                  <span className={`w-3.5 h-3.5 rounded-full border-2 flex-shrink-0 ${chosen===opt?"border-accent-600 bg-accent-600":"border-ink-300"}`} />
                  <input type="radio" className="sr-only" value={opt} checked={chosen===opt} onChange={()=>setChosen(opt)} />
                  <span className="text-sm text-ink-700">{opt}</span>
                </label>
              ))}
            </div>
          ) : event.questions.map((q,i) => (
            <div key={i}>
              <label className="block text-sm text-ink-700 mb-1">{q}</label>
              <input value={answers[i]} onChange={e=>{const n=[...answers];n[i]=e.target.value;setAnswers(n);}} onKeyDown={e=>{if(e.key==="Enter"&&canSubmit&&!submitting)handleSubmit();}} placeholder="Your answer…" className="input-field" />
            </div>
          ))}
        </div>
        <div className="px-5 pb-4">
          <button onClick={handleSubmit} disabled={!canSubmit||submitting} className="btn-primary w-full justify-center">
            {submitting ? "Resuming…" : "Resume pipeline"}
          </button>
        </div>
      </div>
    </div>
  );
}