import { useEffect, useRef } from "react";
interface Props { entries: string[]; }
export default function LogViewer({ entries }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.scrollIntoView({ behavior: "smooth" }); }, [entries.length]);
  if (!entries.length) return (
    <div className="h-full flex items-center justify-center text-ink-400 text-xs font-mono">
      waiting for pipeline...
    </div>
  );
  return (
    <div className="h-full overflow-y-auto font-mono text-xs leading-5 p-4 space-y-px">
      {entries.map((e, i) => {
        const isErr = /error|failed/i.test(e);
        const isWarn = /warn|repair|conflict/i.test(e);
        const isOk = /complete|valid|success/i.test(e);
        const cls = isErr ? "text-red-600" : isWarn ? "text-amber-700" : isOk ? "text-green-700" : "text-ink-500";
        return <div key={i} className={cls}>{e}</div>;
      })}
      <div ref={ref} />
    </div>
  );
}