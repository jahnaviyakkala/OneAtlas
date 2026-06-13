const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
export async function startPipeline(prompt:string):Promise<{session_id:string}> {
  const r = await fetch(`${BASE}/generate`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt})});
  if(!r.ok) throw new Error(await r.text()); return r.json();
}
export async function submitClarify(session_id:string,answers:string[],chosen_option?:string):Promise<void> {
  const r = await fetch(`${BASE}/clarify`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({session_id,answers,chosen_option:chosen_option??null})});
  if(!r.ok) throw new Error(await r.text());
}
export async function submitModification(session_id:string,modification:string) {
  const r = await fetch(`${BASE}/modify`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({session_id,modification})});
  if(!r.ok) throw new Error(await r.text()); return r.json();
}
export async function getResult(session_id:string):Promise<Record<string,unknown>> {
  const r = await fetch(`${BASE}/result/${session_id}`);
  if(!r.ok) throw new Error(`Result not ready: ${r.status}`); return r.json();
}
export async function getIntegrations():Promise<Record<string,unknown>> {
  const r = await fetch(`${BASE}/integrations`);
  if(!r.ok) throw new Error("Failed to load integrations"); return r.json();
}
export function createSSEStream(session_id:string):EventSource {
  return new EventSource(`${BASE}/stream/${session_id}`);
}