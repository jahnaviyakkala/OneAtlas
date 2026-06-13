interface Hook { hook_id:string; integration_id:string; action_id:string; auth_type:string; validation_status:string; }
interface Stub { name:string; trigger:{entity:string;event:string;condition?:string}; integration_id:string; action_id:string; hook_id?:string; is_valid:boolean; }
interface RepairEntry { attempt_number:number; strategy:string; outcome:string; error_input:string; errors_before:number; errors_after:number; }
interface Props { hooks?:Hook[]; stubs?:Stub[]; repairLog?:RepairEntry[]; appSpec?:Record<string,unknown>; }

const STRATEGY_CLS: Record<string,string> = {
  STRUCTURAL:"bg-red-50 text-red-700 border-red-200",
  FIELD:"bg-amber-50 text-amber-700 border-amber-200",
  CONSISTENCY:"bg-blue-50 text-blue-700 border-blue-200",
  ESCALATED:"bg-purple-50 text-purple-700 border-purple-200",
};
const OUTCOME_CLS: Record<string,string> = {
  repaired:"text-green-700", escalated:"text-amber-700", failed:"text-red-700",
};

export default function IntegrationsPanel({ hooks=[], stubs=[], repairLog=[], appSpec }: Props) {
  const meta = appSpec as Record<string,unknown>|undefined;
  const appSpecMeta = meta?.meta as Record<string,unknown>|undefined;
  const entities = ((meta?.entities as unknown[])||([])).length;
  const pages = ((meta?.pages as unknown[])||([])).length;
  const apis = ((meta?.api_endpoints as unknown[])||([])).length;
  const workflows = stubs.length;

  return (
    <div className="space-y-6">

      {/* AppSpec Summary */}
      {meta && (
        <div>
          <p className="section-label mb-3">AppSpec Summary</p>
          <div className="card divide-y divide-ink-100">
            {!!appSpecMeta?.app_name && (
              <div className="flex items-center justify-between px-4 py-2.5">
                <span className="text-sm text-ink-600">App name</span>
                <span className="text-sm font-medium text-ink-900">{String(appSpecMeta.app_name)}</span>
              </div>
            )}
            {[
              { label:"Entities", value:entities },
              { label:"Pages", value:pages },
              { label:"API endpoints", value:apis },
              { label:"Workflows", value:workflows },
            ].map(row => (
              <div key={row.label} className="flex items-center justify-between px-4 py-2.5">
                <span className="text-sm text-ink-600">{row.label}</span>
                <span className="font-mono text-sm font-medium text-ink-900">{row.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Integrations */}
      {hooks.length > 0 && (
        <div>
          <p className="section-label mb-3">Integrations</p>
          <div className="card divide-y divide-ink-100">
            {hooks.map(h => (
              <div key={h.hook_id} className="flex items-center justify-between px-4 py-2.5">
                <div>
                  <p className="text-sm font-medium text-ink-900 capitalize">{h.integration_id.replace(/_/g," ")}</p>
                  <p className="text-xs text-ink-400 font-mono">{h.action_id} · {h.auth_type}</p>
                </div>
                <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${h.validation_status === 'valid' ? 'bg-green-50 text-green-700 border-green-200' : 'bg-red-50 text-red-700 border-red-200'}`}>
                  {h.validation_status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Workflow Stubs */}
      {stubs.length > 0 && (
        <div>
          <p className="section-label mb-3">Workflow Stubs</p>
          <div className="card divide-y divide-ink-100">
            {stubs.map((s,i) => (
              <div key={i} className="px-4 py-3">
                <p className="text-sm font-medium text-ink-900">{s.name}</p>
                <p className="text-xs text-ink-400 font-mono mt-0.5">
                  {s.trigger.entity} · {s.trigger.event}{s.trigger.condition ? ` · ${s.trigger.condition}` : ""}
                </p>
                <p className="text-xs text-accent-600 font-mono mt-0.5">{s.integration_id} → {s.action_id}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Repair Log */}
      {repairLog.length > 0 && (
        <div>
          <p className="section-label mb-3">Repair Log</p>
          <div className="space-y-2">
            {repairLog.map((r,i) => (
              <div key={i} className="card px-4 py-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${STRATEGY_CLS[r.strategy] || 'bg-ink-100 border-ink-200'}`}>{r.strategy}</span>
                  <span className={`text-xs font-mono ${OUTCOME_CLS[r.outcome] || 'text-ink-600'}`}>{r.outcome}</span>
                  <span className="text-[10px] text-ink-400 font-mono ml-auto">attempt {r.attempt_number} · {r.errors_before}→{r.errors_after} errors</span>
                </div>
                {r.error_input && <p className="text-xs text-ink-500 mt-1 leading-relaxed">{r.error_input.slice(0,120)}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}