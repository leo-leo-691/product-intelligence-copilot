import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { DashboardStats, fetchDashboard, fetchEvalMatchRate, runDemoBatch } from "../api";

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [evalInfo, setEvalInfo] = useState<{
    fields_compared?: number;
    match_rate?: number;
    high_band_matches?: number;
    exact_matches?: number;
  } | null>(null);
  const [error, setError] = useState("");
  const [loadingBatch, setLoadingBatch] = useState(false);

  function refresh() {
    fetchDashboard()
      .then(setStats)
      .catch((e) => setError(String(e)));
    fetchEvalMatchRate()
      .then(setEvalInfo)
      .catch(() => setEvalInfo(null));
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 8000);
    return () => clearInterval(t);
  }, []);

  if (!stats && !error) return <p className="text-slate-400">Loading dashboard…</p>;

  const cards = stats
    ? [
        { label: "Products processed", value: stats.total_products },
        { label: "Fields tracked", value: stats.total_fields },
        { label: "High confidence %", value: `${stats.high_confidence_pct}%` },
        { label: "Medium confidence %", value: `${stats.medium_confidence_pct}%` },
        { label: "Low confidence %", value: `${stats.low_confidence_pct}%` },
        { label: "Conflicts open", value: stats.conflicts_count },
        { label: "Propagations applied", value: stats.propagations_applied },
        { label: "Est. minutes saved", value: stats.estimated_minutes_saved },
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Batch dashboard</h1>
          <p className="text-slate-400">
            Aggregates from stored pipeline runs. Pre-run via Ingest → demo batch or{" "}
            <code className="text-xs text-slate-300">scripts/run_batch.py</code>.
          </p>
        </div>
        <button
          type="button"
          disabled={loadingBatch}
          className="rounded-lg border border-emerald-700 bg-emerald-950 px-3 py-1.5 text-sm text-emerald-300 hover:bg-emerald-900 disabled:opacity-50"
          onClick={async () => {
            setLoadingBatch(true);
            setError("");
            try {
              await runDemoBatch();
              refresh();
            } catch (e) {
              setError(String(e));
            } finally {
              setLoadingBatch(false);
            }
          }}
        >
          {loadingBatch ? "Running…" : "Re-run demo batch"}
        </button>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {!stats || stats.total_products === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-700 p-8 text-center text-slate-400">
          No batch data yet.{" "}
          <Link to="/upload" className="text-emerald-400 hover:underline">
            Load demo batch
          </Link>
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {cards.map((c) => (
              <div key={c.label} className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-500">{c.label}</p>
                <p className="mt-2 text-3xl font-semibold text-emerald-400">{c.value}</p>
              </div>
            ))}
          </div>
          <p className="text-sm text-slate-500">
            Approved fields: {stats.fields_approved} · Pending review: {stats.fields_pending}
          </p>
          {evalInfo && evalInfo.fields_compared ? (
            <p className="text-sm text-slate-400">
              Gold-label eval: {evalInfo.exact_matches ?? 0}/{evalInfo.fields_compared} exact (
              {Math.round((evalInfo.match_rate || 0) * 100)}%) · High-band matches:{" "}
              {evalInfo.high_band_matches ?? 0}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-3">
            <a
              href="/api/export/csv?approved_only=false"
              className="inline-block rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-800"
            >
              Download CSV
            </a>
            <a
              href="/api/export/json?approved_only=false"
              className="inline-block rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-800"
            >
              Download JSON
            </a>
            <Link to="/review" className="inline-block rounded-lg bg-emerald-700/80 px-4 py-2 text-sm hover:bg-emerald-600">
              Open review
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
