import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  DashboardStats,
  downloadExport,
  fetchDashboard,
  fetchEvalMatchRate,
  fetchProducts,
  ProductRecord,
  runDemoBatch,
} from "../api";
import RoutingTag from "../components/RoutingTag";

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [evalInfo, setEvalInfo] = useState<{
    fields_compared?: number;
    match_rate?: number;
    high_band_matches?: number;
    exact_matches?: number;
  } | null>(null);
  const [products, setProducts] = useState<ProductRecord[]>([]);
  const [error, setError] = useState("");
  const [loadingBatch, setLoadingBatch] = useState(false);
  const [exporting, setExporting] = useState<"csv" | "json" | null>(null);

  function refresh() {
    fetchDashboard()
      .then(setStats)
      .catch((e) => setError(String(e)));
    fetchEvalMatchRate()
      .then(setEvalInfo)
      .catch(() => setEvalInfo(null));
    fetchProducts()
      .then(setProducts)
      .catch(() => setProducts([]));
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 8000);
    return () => clearInterval(t);
  }, []);

  if (!stats && !error) {
    return <p className="font-mono text-sm text-ink-soft">Loading dashboard…</p>;
  }

  const summary = stats
    ? [
        { label: "Products processed", value: String(stats.total_products) },
        { label: "High confidence %", value: `${stats.high_confidence_pct}%` },
        { label: "Conflicts open", value: String(stats.conflicts_count) },
        { label: "Propagations applied", value: String(stats.propagations_applied) },
        { label: "Outliers flagged", value: String(stats.outliers_flagged ?? 0) },
        { label: "KG nodes", value: String(stats.kg_nodes ?? 0) },
        { label: "Fields tracked", value: String(stats.total_fields) },
        { label: "Medium confidence %", value: `${stats.medium_confidence_pct}%` },
        { label: "Low confidence %", value: `${stats.low_confidence_pct}%` },
        { label: "Est. minutes saved", value: String(stats.estimated_minutes_saved) },
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-dashed border-rule-line pb-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-label text-ink-soft">
            Inspection summary — batch report
          </p>
          <h1 className="page-title mt-1">Batch dashboard</h1>
          <p className="mt-2 max-w-xl font-sans text-sm text-ink-soft">
            Aggregates from stored pipeline runs. Pre-run via Ingest → demo batch or{" "}
            <code className="font-mono text-xs text-ink">scripts/run_batch.py</code>.
          </p>
        </div>
        <button
          type="button"
          disabled={loadingBatch}
          className="btn-secondary"
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

      {error && <p className="font-mono text-sm text-stamp-flagged">{error}</p>}

      {!stats || stats.total_products === 0 ? (
        <div className="panel border-dashed p-8 text-center">
          <p className="font-sans text-ink-soft">No batch data yet.</p>
          <Link to="/upload" className="btn-primary mt-4 inline-flex">
            Load demo batch
          </Link>
        </div>
      ) : (
        <>
          <section className="panel p-5 sm:p-6">
            <h2 className="font-display text-sm uppercase tracking-stencil text-ink">Report totals</h2>
            <hr className="rule-tear" />
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {summary.map((c) => (
                <div key={c.label} className="border-b border-dashed border-rule-line pb-3 sm:border-0 sm:pb-0">
                  <p className="form-label">{c.label}</p>
                  <p className="mt-1 font-mono text-3xl font-semibold tabular-nums text-ink sm:text-4xl">
                    {c.value}
                  </p>
                </div>
              ))}
            </div>
            <hr className="rule-tear" />
            <p className="font-mono text-xs text-ink-soft">
              Approved fields: {stats.fields_approved} · Pending review: {stats.fields_pending}
            </p>
            {evalInfo && evalInfo.fields_compared ? (
              <p className="mt-2 font-mono text-xs text-ink-soft">
                Gold-label eval: {evalInfo.exact_matches ?? 0}/{evalInfo.fields_compared} exact (
                {Math.round((evalInfo.match_rate || 0) * 100)}%) · High-band matches:{" "}
                {evalInfo.high_band_matches ?? 0}
              </p>
            ) : null}
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                className="btn-secondary"
                disabled={!!exporting}
                onClick={async () => {
                  setExporting("csv");
                  setError("");
                  try {
                    await downloadExport("csv", false);
                  } catch (e) {
                    setError(String(e));
                  } finally {
                    setExporting(null);
                  }
                }}
              >
                {exporting === "csv" ? "Downloading…" : "Download CSV"}
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={!!exporting}
                onClick={async () => {
                  setExporting("json");
                  setError("");
                  try {
                    await downloadExport("json", false);
                  } catch (e) {
                    setError(String(e));
                  } finally {
                    setExporting(null);
                  }
                }}
              >
                {exporting === "json" ? "Downloading…" : "Download JSON"}
              </button>
              <Link to="/review" className="btn-primary">
                Open review
              </Link>
            </div>
          </section>

          {products.length > 0 && (
            <section>
              <h2 className="font-display text-sm uppercase tracking-stencil text-ink">Routing tags</h2>
              <hr className="rule-tear" />
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {products.map((p) => (
                  <RoutingTag
                    key={p.id}
                    sku={p.sku}
                    category={p.category_id}
                    to={`/review/${p.id}`}
                    flagged={p.conflicts.some((c) => !c.resolved)}
                  />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
