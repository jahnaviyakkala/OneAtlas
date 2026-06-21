import { useEffect, useRef } from "react";
import { createSSEStream } from "../api/client";
import type { SSEEvent } from "../api/types";
interface UseSSEOptions { sessionId:string|null; onEvent:(e:SSEEvent)=>void; onError?:(e:Event)=>void; }
export function useSSE({sessionId,onEvent,onError}:UseSSEOptions) {
  const esRef = useRef<EventSource|null>(null);
  const retry = useRef(0);
  const onEventRef = useRef(onEvent);
  const onErrRef = useRef(onError);
  useEffect(() => {
    onEventRef.current = onEvent;
    onErrRef.current = onError;
  });
  useEffect(() => {
    if(!sessionId) return;
    retry.current=0; let cancelled=false;
    function connect() {
      if(cancelled||!sessionId) return;
      const es = createSSEStream(sessionId); esRef.current=es;
      const h = (e:MessageEvent) => {
        try {
          const p:SSEEvent=JSON.parse(e.data);
          onEventRef.current(p);
          if(p.event==="pipeline_complete"||p.event==="pipeline_failed") es.close();
        } catch {
          // ignore parsing errors
        }
      };
      ["stage_update","stage_start","stage_complete","generation_complete","hitl_required","log_update","pipeline_complete","pipeline_failed","ping","modification_queued","modification_applied"].forEach(t=>es.addEventListener(t,h as EventListener));
      es.onmessage=h;
      es.onerror=(err)=>{ es.close(); if(!cancelled&&retry.current<5){retry.current++;setTimeout(connect,Math.min(1000*retry.current,5000));}else if(!cancelled) onErrRef.current?.(err); };
    }
    connect(); return ()=>{ cancelled=true; esRef.current?.close(); };
  },[sessionId]);
}