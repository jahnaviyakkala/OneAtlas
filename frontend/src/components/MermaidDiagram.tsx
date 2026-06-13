import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
mermaid.initialize({ startOnLoad:false, theme:"dark" });
let _id=0;
function clean(s:string):string {
  if(!s) return s;
  let r=s.replace(/\\n/g,"\n").replace(/(\|[^|]*\|)>/g,"");
  // Strip out %%{...}%% blocks completely
  r = r.replace(/%%\{[\s\S]*?\}%%/g, "");
  // Strip hardcoded inline styles, class definitions, and class assignments
  r = r.split("\n").filter(l => {
    const t = l.trim();
    return !(t.startsWith("style ") || t.startsWith("classDef ") || t.startsWith("class "));
  }).join("\n");
  return r;
}
interface Props { title:string; source:string; }
export default function MermaidDiagram({title,source}:Props) {
  const ref=useRef<HTMLDivElement>(null);
  const [err,setErr]=useState<string|null>(null);
  const [show,setShow]=useState(false);
  const id=useRef(`mermaid_${++_id}`);
  useEffect(()=>{ if(!source||!ref.current) return; setErr(null);
    mermaid.render(id.current,clean(source)).then(({svg})=>{ if(ref.current) ref.current.innerHTML=svg; }).catch(e=>setErr(String(e.message??e)));
  },[source]);
  if(!source) return <div className="card p-6 text-center text-xs text-ink-400 font-mono">{title} — not generated</div>;
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-ink-100">
        <span className="text-xs font-mono font-medium text-ink-600">{title}</span>
        <div className="flex gap-2">
          {err && <button onClick={()=>setShow(v=>!v)} className="text-xs text-amber-600 hover:text-amber-800">{show?"hide":"show source"}</button>}
          <button onClick={()=>navigator.clipboard.writeText(source)} className="text-xs text-ink-400 hover:text-ink-700">copy</button>
        </div>
      </div>
      {err ? <div className="p-4 space-y-2">{show&&<pre className="text-xs font-mono text-ink-500 bg-ink-50 p-3 rounded overflow-auto max-h-48">{source.replace(/\\n/g,"\n")}</pre>}</div>
           : <div ref={ref} className="p-4 overflow-x-auto flex justify-center" />}
    </div>
  );
}