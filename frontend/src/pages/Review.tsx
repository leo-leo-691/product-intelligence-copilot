import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  approveRecord,
  bulkApproveHigh,
  fetchProduct,
  fetchProducts,
  getUserErrorMessage,
  propagationAction,
  ProductRecord,
  PropagationSuggestion,
  resolveConflict,
  reviewField,
} from "../api";
import ConfidenceStamp from "../components/ConfidenceStamp";
import RoutingTag from "../components/RoutingTag";

export default function ReviewPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [list, setList] = useState<ProductRecord[]>([]);
  const [record, setRecord] = useState<ProductRecord | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [modal, setModal] = useState<PropagationSuggestion | null>(null);
  const [error, setError] = useState<{ title: string; body: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    fetchProducts()
      .then(setList)
      .catch((e) => setError(getUserErrorMessage(e, "service")));
  }, []);

  useEffect(() => {
    if (id) {
      fetchProduct(id)
        .then(setRecord)
        .catch((e) => setError(getUserErrorMessage(e, "service")));
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
      <div className="panel p-8 text-center">
        <p className="font-display text-lg uppercase tracking-stencil text-ink">NO PRODUCTS YET</p>
        <p className="mt-2 font-sans text-sm text-ink-soft">
          Upload a product document from Ingest to begin extraction.
        </p>
        <Link to="/upload" className="btn-primary mt-5 inline-flex">
          Go to Ingest
        </Link>
      </div>
    );
  }

  if (!record) {
    return (
      <div className="space-y-4">
        {error ? (
          <div className="border border-stamp-flagged bg-paper p-4" role="alert">
            <p className="font-display text-sm uppercase tracking-stencil text-stamp-flagged">{error.title}</p>
            <p className="mt-1 font-sans text-sm text-ink-soft">{error.body}</p>
            <Link to="/upload" className="btn-secondary mt-3 inline-flex">
              Go to Ingest
            </Link>
          </div>
        ) : (
          <p className="font-mono text-sm text-ink-soft">Loading product...</p>
        )}
      </div>
    );
  }

  const conflictFields = new Set(record.conflicts.filter((c) => !c.resolved).map((c) => c.field_name));

  async function onApprove(name: string) {
    setBusy(true);
    try {
      const res = await reviewField(record!.id, name, "approved");
      setRecord(res.product);
    } catch (e) {
      setError(getUserErrorMessage(e, "processing"));
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
      setError(getUserErrorMessage(e, "processing"));
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
      setError(getUserErrorMessage(e, "processing"));
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
      setError(getUserErrorMessage(e, "processing"));
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
      setError(getUserErrorMessage(e, "processing"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
      <aside className="panel p-3">
        <p className="mb-2 font-display text-xs uppercase tracking-stencil text-ink">Routing log</p>
        <input
          className="form-underline mb-3 text-xs"
          placeholder="Filter SKU…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <ul className="max-h-[70vh] space-y-2 overflow-auto">
          {filtered.map((p) => (
            <li key={p.id}>
              <RoutingTag
                sku={p.sku}
                category={p.category_id}
                to={`/review/${p.id}`}
                active={p.id === record.id}
                flagged={p.conflicts.some((c) => !c.resolved)}
              />
            </li>
          ))}
        </ul>
      </aside>

      <div className="space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-dashed border-rule-line pb-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-label text-ink-soft">Inspection sheet</p>
            <h1 className="mt-1 font-mono text-2xl font-semibold text-ink sm:text-3xl">{record.sku}</h1>
            <p className="mt-1 font-sans text-sm text-ink-soft">
              <span className="font-mono">{record.category_id}</span>
              {" · template "}
              <span className="font-mono">{record.source_template_id ?? "—"}</span>
              {" · status "}
              <span
                className={[
                  "font-mono uppercase",
                  record.status === "approved" ? "text-stamp-approved" : "text-stamp-review",
                ].join(" ")}
              >
                {record.status.replace(/_/g, " ")}
              </span>
            </p>
            {record.category_inference && (
              <p className="mt-1 font-mono text-[11px] text-ink-soft">
                Inferred: {record.category_inference.reasoning} (conf{" "}
                {record.category_inference.confidence})
              </p>
            )}
            {record.language && (
              <p className="mt-1 font-mono text-[11px] text-ink-soft">
                Language: {String(record.language.source_language ?? "en")}
                {record.language.translation_applied ? " → en translated" : ""}
                {record.language.translation_confidence != null
                  ? ` (tx ${String(record.language.translation_confidence)})`
                  : ""}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={onBulk} disabled={busy || record.status === "approved"} className="btn-primary">
              Bulk-approve High
            </button>
            <button onClick={onApproveAll} disabled={busy || record.status === "approved"} className="btn-secondary">
              {record.status === "approved" ? "Record approved" : "Approve record"}
            </button>
          </div>
        </div>

        {error && (
          <div className="border border-stamp-flagged bg-paper p-4" role="alert">
            <p className="font-display text-sm uppercase tracking-stencil text-stamp-flagged">{error.title}</p>
            <p className="mt-1 font-sans text-sm text-ink-soft">{error.body}</p>
          </div>
        )}

        {(record.outliers?.length ?? 0) > 0 && (
          <section className="border border-stamp-review bg-paper p-4">
            <h2 className="font-display text-sm uppercase tracking-stencil text-stamp-review">
              Consistency outliers
            </h2>
            <ul className="mt-2 space-y-1 font-mono text-xs text-ink">
              {record.outliers!.map((o, i) => (
                <li key={`${o.field_name}-${i}`}>{o.message}</li>
              ))}
            </ul>
          </section>
        )}

        {record.dual_llm?.enabled && (
          <section className="border border-rule-line bg-paper p-4">
            <h2 className="font-display text-sm uppercase tracking-stencil text-ink">
              Dual LLM ({record.dual_llm.gemini_status} / {record.dual_llm.claude_status})
            </h2>
            <ul className="mt-2 space-y-1 font-mono text-xs text-ink">
              {record.dual_llm.comparisons.filter((row) => row.status === "AGREEMENT").length > 0 && (
                <li>
                  Gemini + Claude Agreement:{" "}
                  {record.dual_llm.comparisons.filter((row) => row.status === "AGREEMENT").length} field(s)
                </li>
              )}
              {(record.dual_llm.gemini_status === "provider_unavailable" ||
                record.dual_llm.claude_status === "provider_unavailable") && (
                <li>
                  Provider unavailable — using the successful extraction; not treated as field disagreement
                </li>
              )}
              {record.dual_llm.comparisons
                .filter((row) => row.status === "DISAGREEMENT")
                .map((row) => (
                  <li key={row.field_name}>
                    LLM Disagreement · {row.field_name}: Gemini {String(row.gemini_value)} · Claude{" "}
                    {String(row.claude_value)} → human review required
                  </li>
                ))}
            </ul>
          </section>
        )}

        {record.conflicts.filter((c) => !c.resolved).length > 0 && (
          <section className="border border-stamp-flagged bg-paper p-4 sm:p-5">
            <div className="flex flex-wrap items-center gap-3">
              <ConfidenceStamp kind="flagged" animate={false} />
              <h2 className="font-display text-base uppercase tracking-stencil text-stamp-flagged">
                Conflicts — not auto-resolved
              </h2>
              <span className="font-mono text-[10px] uppercase tracking-label text-stamp-flagged">Unresolved</span>
              <span className="font-mono text-[10px] uppercase tracking-label text-stamp-flagged">
                Human review
              </span>
            </div>
            <p className="mt-2 font-mono text-xs text-stamp-flagged">
              Both source values are shown. Neither is auto-selected.
            </p>
            {record.conflicts
              .filter((c) => !c.resolved)
              .map((c) => (
                <div key={c.field_name} className="mt-4">
                  <p className="font-mono text-sm text-ink">{c.field_name}</p>
                  <div className="mt-2 grid gap-0 sm:grid-cols-[1fr_3px_1fr]">
                    {c.candidates.map((x, i) => (
                      <div key={i} className="contents">
                        {i === 1 && (
                          <div className="hidden bg-stamp-flagged sm:block" aria-hidden />
                        )}
                        <div
                          className={[
                            "border border-rule-line bg-paper-dim p-3",
                            i === 1 ? "sm:border-l-0" : "sm:border-r-0",
                          ].join(" ")}
                        >
                          <p className="font-display text-[10px] uppercase tracking-stencil text-stamp-flagged">
                            {x.source_type}
                            {x.provider ? ` · ${x.provider}` : ""}
                          </p>
                          <p className="mt-1 font-mono text-lg font-semibold text-ink">{String(x.value)}</p>
                          <p className="mt-2 inline-block border border-dashed border-rule-line bg-paper px-2 py-1 font-mono text-[10px] uppercase tracking-label text-ink-soft">
                            Provenance · {x.source_type}
                          </p>
                          <p className="mt-2 font-mono text-xs text-ink-soft">{x.extraction_method}</p>
                          <p className="mt-1 font-mono text-xs text-ink-soft">{x.source_snippet}</p>
                          <button
                            className="btn-ghost mt-3"
                            disabled={busy}
                            onClick={async () => {
                              setBusy(true);
                              try {
                                const updated = await resolveConflict(record.id, c.field_name, x.value);
                                setRecord(updated);
                              } catch (e) {
                                setError(getUserErrorMessage(e, "processing"));
                              } finally {
                                setBusy(false);
                              }
                            }}
                          >
                            Use this value
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
          </section>
        )}

        <ul className="space-y-3">
          {Object.entries(record.fields).map(([name, fp]) => (
            <li
              key={name}
              className={[
                "panel p-4",
                conflictFields.has(name) ? "border-stamp-flagged" : "",
              ].join(" ")}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="form-label">{name}</p>
                  <p className="mt-1 font-mono text-lg text-ink">
                    {fp.not_found ? (
                      <span className="italic text-ink-soft">not found</span>
                    ) : (
                      String(fp.value)
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[10px] uppercase tracking-label text-ink-soft">
                    Review: {fp.review_status}
                    {fp.needs_review && fp.review_status === "pending" ? " · needs review" : ""}
                    {" · confidence: "}
                    {fp.confidence_score}
                  </p>
                </div>
                <ConfidenceStamp
                  band={fp.confidence_score}
                  notFound={fp.not_found}
                  conflicted={conflictFields.has(name)}
                  reviewStatus={fp.review_status}
                  title={JSON.stringify(fp.confidence_reasoning)}
                />
              </div>

              <button
                type="button"
                className="mt-3 inline-flex items-center gap-1.5 border border-dashed border-rule-line bg-paper px-2 py-1 font-mono text-[10px] uppercase tracking-label text-ink-soft hover:border-ink hover:text-ink"
                onClick={() => setExpanded(expanded === name ? null : name)}
              >
                <span
                  className="inline-block h-2.5 w-2.5 rotate-45 border border-rule-line bg-paper-dim"
                  aria-hidden
                />
                {expanded === name ? "Hide source" : "Source"}
              </button>
              {expanded === name && (
                <div className="mt-2 border border-dashed border-rule-line bg-paper p-3 font-mono text-xs text-ink-soft">
                  <p className="text-ink">{fp.source_snippet ?? "—"}</p>
                  <p className="mt-1">{fp.source_location}</p>
                  <p className="mt-1">method: {fp.extraction_method}</p>
                  <p className="mt-2 break-all">{JSON.stringify(fp.confidence_reasoning)}</p>
                  {fp.validation_errors.length > 0 && (
                    <p className="mt-1 text-stamp-flagged">
                      Validation: {fp.validation_errors.join(", ")}
                    </p>
                  )}
                </div>
              )}

              <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-dashed border-rule-line pt-3">
                <button
                  className="btn-ghost"
                  disabled={busy || fp.review_status === "approved"}
                  onClick={() => onApprove(name)}
                >
                  {fp.review_status === "approved" ? "Approved" : "Approve"}
                </button>
                <button
                  className="btn-ghost"
                  disabled={busy || fp.review_status === "rejected"}
                  onClick={() => onReject(name)}
                >
                  {fp.review_status === "rejected" ? "Rejected" : "Reject"}
                </button>
                <label className="flex flex-col">
                  <span className="form-label mb-0.5">Edit value</span>
                  <input
                    className="form-underline w-40 py-1 text-xs"
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
                </label>
                <button className="btn-primary !px-3 !py-1.5 text-xs" disabled={busy} onClick={() => onEdit(name)}>
                  Save edit
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4">
          <div className="panel max-w-md bg-paper p-6 shadow-none">
            <h3 className="font-display text-lg uppercase tracking-stencil text-ink">
              Propagation suggestion
            </h3>
            <p className="mt-3 font-sans text-sm text-ink-soft">
              Field <span className="font-mono text-ink">{modal.field_name}</span>: change{" "}
              <strong className="font-mono text-ink">{String(modal.old_value)}</strong> →{" "}
              <strong className="font-mono text-ink">{String(modal.new_value)}</strong> on{" "}
              {modal.candidate_product_ids.length} other product(s) sharing template{" "}
              <span className="font-mono text-ink">{modal.source_template_id}</span>?
            </p>
            <div className="mt-5 flex justify-end gap-2 border-t border-dashed border-rule-line pt-4">
              <button
                className="btn-secondary"
                onClick={async () => {
                  await propagationAction(modal.id, "dismiss");
                  setModal(null);
                }}
              >
                Dismiss
              </button>
              <button
                className="btn-primary"
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
