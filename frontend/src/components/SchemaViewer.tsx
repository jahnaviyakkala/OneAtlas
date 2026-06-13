import { useState } from "react";
interface Props { data: unknown; title?: string; }
function JNode({ v, d=0 }: { v:unknown; d?:number }) {
  const [c,setC]=useState(d>2);
  const pad=d*12;
  if(v===null) return <span className="text-ink-400">null</span>;
  if(typeof v==="boolean") return <span className="text-amber-700">{String(v)}</span>;
  if(typeof v==="number") return <span className="text-accent-600">{v}</span>;
  if(typeof v==="string") return <span className="text-green-700">"{v}"</span>;
  if(Array.isArray(v)) {
    if(!v.length) return <span className="text-ink-400">[]</span>;
    return <span><button onClick={()=>setC(!c)} className="text-ink-500 hover:text-ink-800">{c?"[…]":"["}</button>
      {!c&&<div style={{marginLeft:pad+12}}>{v.map((x,i)=><div key={i}><JNode v={x} d={d+1}/>{i<v.length-1&&<span className="text-ink-300">,</span>}</div>)}<div style={{marginLeft:-12}}>]</div></div>}</span>;
  }
  if(typeof v==="object") {
    const e=Object.entries(v as Record<string,unknown>);
    if(!e.length) return <span className="text-ink-400">{"{}"}</span>;
    return <span><button onClick={()=>setC(!c)} className="text-ink-500 hover:text-ink-800">{c?"{…}":"{"}</button>
      {!c&&<div style={{marginLeft:pad+12}}>{e.map(([k,x],i)=><div key={k}><span className="text-accent-600">"{k}"</span><span className="text-ink-400">: </span><JNode v={x} d={d+1}/>{i<e.length-1&&<span className="text-ink-300">,</span>}</div>)}<div style={{marginLeft:-12}}>{"}"}</div></div>}</span>;
  }
  return <span className="text-ink-700">{String(v)}</span>;
}
export default function SchemaViewer({ data, title }: Props) {
  const [raw,setRaw]=useState(false);
  const json=JSON.stringify(data,null,2);
  return (
    <div className="card overflow-hidden">
      {title && <div className="flex items-center justify-between px-4 py-2.5 border-b border-ink-100">
        <span className="text-sm font-medium text-ink-800">{title}</span>
        <div className="flex gap-2">
          <button onClick={()=>setRaw(!raw)} className="text-xs text-ink-500 hover:text-ink-800 px-2 py-1 rounded hover:bg-ink-100">{raw?"Tree":"Raw"}</button>
          <button onClick={()=>{const b=new Blob([json],{type:"application/json"});const u=URL.createObjectURL(b);const a=document.createElement("a");a.href=u;a.download=`${title}.json`;a.click();URL.revokeObjectURL(u);}} className="text-xs text-ink-500 hover:text-ink-800 px-2 py-1 rounded hover:bg-ink-100">↓ JSON</button>
        </div>
      </div>}
      <div className="p-4 overflow-auto max-h-[600px] font-mono text-xs">
        {raw?<pre className="text-ink-700 whitespace-pre-wrap break-all">{json}</pre>:<JNode v={data} d={0}/>}
      </div>
    </div>
  );
}