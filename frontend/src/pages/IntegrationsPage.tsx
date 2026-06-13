import { useEffect, useState } from "react";
import { getIntegrations } from "../api/client";

export default function IntegrationsPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getIntegrations()
      .then(res => {
        setData(res);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-h-screen p-8 pt-16">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-4xl font-bold mb-4">Integration Registry</h1>
        <p className="text-ink-400 mb-8 max-w-2xl">
          View all supported third-party integrations that can be utilized to generate automated workflow stubs.
        </p>
        
        {loading && <div className="text-accent-400 font-mono">Loading integrations...</div>}
        {error && <div className="text-red-500 font-mono">Error: {error}</div>}
        
        {data && (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {data.integrations?.map((integ: any) => (
              <div key={integ.id} className="card p-6 flex flex-col hover:border-accent-500 transition-colors">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-xl font-bold text-white">{integ.display_name}</h2>
                  {integ.is_stub && <span className="text-xs font-mono px-2 py-1 bg-ink-800 text-ink-400 rounded">STUB</span>}
                </div>
                <p className="text-sm text-ink-300 mb-6 flex-grow">{integ.description}</p>
                
                <div>
                  <div className="section-label mb-2">Available Actions</div>
                  <div className="flex flex-wrap gap-2">
                    {integ.actions?.map((a: any) => (
                      <span key={a.id} className="text-xs font-mono bg-ink-800 text-ink-200 px-2 py-1 rounded">
                        {a.id}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
