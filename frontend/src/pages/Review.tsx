import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  approveRecord,
  bulkApproveHigh,
  fetchProduct,
  fetchProducts,
  propagationAction,
  ProductRecord,
  PropagationSuggestion,
  resolveConflict,
  reviewField,
} from "../api";

function badgeClass(band: string) {
  if (band === "High") return "bg-emerald-900/60 text-emerald-300 border-emerald-700";
  if (band === "Medium") return "bg-amber-900/40 text-amber-200 border-amber-700";
  return "bg-red-900/40 text-red-200 border-red-800";
}

export default function ReviewPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [list, setList] = useState<ProductRecord[]>([]);
  const [record, setRecord] = useState<ProductRecord | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [modal, setModal] = useState<PropagationSuggestion | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    fetchProducts()
      .then(setList)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (id) {
      fetchProduct(id)
        .then(setRecord)
        .catch((e) => setError(String(e)));
    } else if (list.length) {
      nav(`/review/${list[0].id}`, { replace: true });
    }
  }, [id, list, nav]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return list;
    return list.filter((p) => p.sku.toLowerCase().includes(q) || p.category_id.includes(q));
  }, [list, filter]);

  if (!list.length && !error) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-8 text-center">
        <p className="text-slate-300">No products yet.</p>
        <p className="mt-2 text-sm text-slate-500">Load the demo batch from Ingest, or upload a datasheet.</p>
        <Link to="/upload" className="mt-4 inline-block text-emerald-400 hover:underline">
          Go to Ingest →
        </Link>
      </div>
    );
  }

  if (!record) {
    return <p className="text-slate-400">{error || "Loading product…"}</p>;
  }

  const conflictFields = new Set(record.conflicts.filter((c) => !c.resolved).map((c) => c.field_name));

  async function onApprove(name: string) {
    setBusy(true);
    try {
      const res = await reviewField(record!.id, name, "approved");
      setRecord(res.product);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onReject(name: string) {
    setBusy(true);
    try {
      const res = await reviewField(record!.id, name, "rejected");
      setRecord(res.product);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onEdit(name: string) {
    const value = edits[name] ?? String(record!.fields[name]?.value ?? "");
    setBusy(true);
    try {
      const res = await reviewField(record!.id, name, "edited", value);
      setRecord(res.product);
      if (res.propagation_suggestion) setModal(res.propagation_suggestion);
      setEdits((prev) => ({ ...prev, [name]: "" }));
      fetchProducts().then(setList);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onBulk() {
    setBusy(true);
    try {
      const updated = await bulkApproveHigh(record!.id);
      setRecord(updated);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onApproveAll() {
    setBusy(true);
    try {
      const updated = await approveRecord(record!.id);
      setRecord(updated);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
      <aside className="rounded-2xl border border-slate-800 bg-slate-900/40 p-3">
        <p className="mb-2 text-xs font-medium uppercase text-slate-500">Products</p>
        <input
          className="mb-2 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs"
          placeholder="Filter SKU…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <ul className="max-h-[70vh] space-y-1 overflow-auto text-sm">
          {filtered.map((p) => (
            <li key={p.id}>
              <Link
                to={`/review/${p.id}`}
                className={`block rounded px-2 py-1 ${
                  p.id === record.id ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/60"
                }`}
              >
                {p.sku}
                {p.conflicts.some((c) => !c.resolved) && <span className="ml-1 text-amber-400">!</span>}
              </Link>
            </li>
          ))}
        </ul>
      </aside>

      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">{record.sku}</h1>
            <p className="text-sm text-slate-400">
              {record.category_id} · template {record.source_template_id ?? "—"} · status{" "}
              <span className="text-emerald-400">{record.status}</span>
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={onBulk}
              disabled={busy}
              className="rounded-lg border border-emerald-700 bg-emerald-950 px-3 py-1.5 text-sm text-emerald-300 hover:bg-emerald-900 disabled:opacity-50"
            >
              Bulk-approve High
            </button>
            <button
              onClick={onApproveAll}
              disabled={busy}
              className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm hover:bg-slate-800 disabled:opacity-50"
            >
              Approve record
            </button>
          </div>
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        {record.conflicts.filter((c) => !c.resolved).length > 0 && (
          <div className="rounded-2xl border border-amber-700/60 bg-amber-950/30 p-4">
            <h2 className="font-medium text-amber-200">Conflicts — not auto-resolved</h2>
            {record.conflicts
              .filter((c) => !c.resolved)
              .map((c) => (
                <div key={c.field_name} className="mt-3 text-sm">
                  <p className="font-mono text-amber-100">{c.field_name}</p>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    {c.candidates.map((x, i) => (
                      <div key={i} className="rounded-lg border border-slate-700 bg-slate-950/80 p-3">
                        <p className="text-lg font-semibold">{String(x.value)}</p>
                        <p className="text-xs text-slate-400">
                          {x.source_type} · {x.extraction_method}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">{x.source_snippet}</p>
                        <button
                          className="mt-2 text-xs text-emerald-400 hover:underline"
                          disabled={busy}
                          onClick={async () => {
                            setBusy(true);
                            try {
                              const updated = await resolveConflict(record.id, c.field_name, x.value);
                              setRecord(updated);
                            } catch (e) {
                              setError(String(e));
                            } finally {
                              setBusy(false);
                            }
                          }}
                        >
                          Use this value
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
          </div>
        )}

        <ul className="space-y-2">
          {Object.entries(record.fields).map(([name, fp]) => (
            <li
              key={name}
              className={`rounded-2xl border p-4 ${
                conflictFields.has(name) ? "border-amber-700" : "border-slate-800"
              } bg-slate-900/40`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-mono text-sm text-slate-300">{name}</p>
                  <p className="text-lg">
                    {fp.not_found ? (
                      <span className="italic text-slate-500">not found</span>
                    ) : (
                      String(fp.value)
                    )}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    review: {fp.review_status}
                    {fp.needs_review ? " · needs review" : ""}
                  </p>
                </div>
                <span
                  className={`rounded-full border px-2 py-0.5 text-xs ${badgeClass(fp.confidence_score)}`}
                  title={JSON.stringify(fp.confidence_reasoning)}
                >
                  {fp.confidence_score}
                </span>
              </div>
              <button
                type="button"
                className="mt-2 text-xs text-emerald-400 hover:underline"
                onClick={() => setExpanded(expanded === name ? null : name)}
              >
                {expanded === name ? "Hide citation" : "Show citation & reasoning"}
              </button>
              {expanded === name && (
                <div className="mt-2 rounded-lg bg-slate-950 p-3 text-xs text-slate-400">
                  <p>{fp.source_snippet ?? "—"}</p>
                  <p className="mt-1">{fp.source_location}</p>
                  <p className="mt-1">method: {fp.extraction_method}</p>
                  <p className="mt-2 font-mono text-slate-500">{JSON.stringify(fp.confidence_reasoning)}</p>
                  {fp.validation_errors.length > 0 && (
                    <p className="mt-1 text-red-400">Validation: {fp.validation_errors.join(", ")}</p>
                  )}
                </div>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  className="rounded bg-slate-800 px-2 py-1 text-xs hover:bg-slate-700 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => onApprove(name)}
                >
                  Approve
                </button>
                <button
                  className="rounded bg-slate-800 px-2 py-1 text-xs hover:bg-slate-700 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => onReject(name)}
                >
                  Reject
                </button>
                <input
                  className="w-36 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs"
                  placeholder="Edit value"
                  value={edits[name] ?? ""}
                  onFocus={() =>
                    setEdits((prev) => ({
                      ...prev,
                      [name]: prev[name] ?? String(fp.value ?? ""),
                    }))
                  }
                  onChange={(e) => setEdits((prev) => ({ ...prev, [name]: e.target.value }))}
                />
                <button
                  className="rounded bg-emerald-900 px-2 py-1 text-xs text-emerald-200 hover:bg-emerald-800 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => onEdit(name)}
                >
                  Save edit
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-emerald-300">Propagation suggestion</h3>
            <p className="mt-2 text-sm text-slate-300">
              Field <span className="font-mono">{modal.field_name}</span>: change{" "}
              <strong>{String(modal.old_value)}</strong> → <strong>{String(modal.new_value)}</strong> on{" "}
              {modal.candidate_product_ids.length} other product(s) sharing template{" "}
              <span className="font-mono">{modal.source_template_id}</span>?
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="rounded-lg px-3 py-1.5 text-sm text-slate-400 hover:bg-slate-800"
                onClick={async () => {
                  await propagationAction(modal.id, "dismiss");
                  setModal(null);
                }}
              >
                Dismiss
              </button>
              <button
                className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm hover:bg-emerald-500"
                onClick={async () => {
                  await propagationAction(modal.id, "apply");
                  setModal(null);
                  fetchProducts().then(setList);
                  fetchProduct(record.id).then(setRecord);
                }}
              >
                Apply to all
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
