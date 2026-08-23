import { FormEvent, useEffect, useState } from "react";
import {
  downloadUnihackExport,
  fetchUnihackEvaluation,
  fetchUnihackFiles,
  fetchUnihackRows,
  fetchUnihackSchema,
  fetchUnihackStatus,
  runUnihackJob,
  UnihackFileInfo,
  uploadUnihackFile,
} from "../api";

function metric(value: unknown): string {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value === "number" && Number.isNaN(value)) return "N/A";
  return String(value);
}

export default function EvaluationPage() {
  const [files, setFiles] = useState<Record<string, UnihackFileInfo>>({});
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [evalData, setEvalData] = useState<Record<string, unknown> | null>(null);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [headerCount, setHeaderCount] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploadKind, setUploadKind] = useState("input");

  async function refresh() {
    try {
      const schema = await fetchUnihackSchema();
      setHeaderCount(schema.available ? schema.header_count : null);
    } catch {
      setHeaderCount(null);
    }
    try {
      const f = await fetchUnihackFiles();
      setFiles(f.files || {});
    } catch (e) {
      setError(String(e));
    }
    try {
      setStatus(await fetchUnihackStatus());
    } catch {
      setStatus(null);
    }
    try {
      setEvalData(await fetchUnihackEvaluation());
    } catch {
      setEvalData(null);
    }
    try {
      const r = await fetchUnihackRows(true);
      setRows(r.rows || []);
    } catch {
      setRows([]);
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, []);

  async function onUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const input = e.currentTarget.elements.namedItem("dataset") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      await uploadUnihackFile(uploadKind, file);
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onRun() {
    setBusy(true);
    setError("");
    try {
      await runUnihackJob(true);
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  const jobStatus = String(status?.status ?? "");
  const evaluated = Boolean(evalData && evalData.available);
  const progress = status?.progress as { total?: number } | undefined;
  const processedRows = Number(status?.input_row_count ?? progress?.total) || null;
  const loadedHeaders = Number(status?.header_count) || headerCount;
  const inputHeaders = (status?.input_headers as string[] | undefined) ?? [];
  const inputColumns = inputHeaders.length > 0 ? inputHeaders.length : null;
  const schemaCompliance = (status?.schema_compliance as Record<string, unknown> | undefined) ?? null;

  return (
    <div className="space-y-6">
      <div className="border-b border-dashed border-rule-line pb-4">
        <p className="font-mono text-[11px] uppercase tracking-label text-ink-soft">
          UniHack 2026 · Separate from 26-product demo
        </p>
        <h1 className="page-title mt-1">Catalog Enrichment Pipeline</h1>
        <p className="mt-1 font-mono text-[11px] uppercase tracking-label text-ink-soft">
          UniHack 2026
        </p>
        <p className="mt-2 max-w-2xl font-sans text-sm text-ink-soft">
          This workflow processes the official evaluation input and writes every header from the
          official Expected Output sheet. It is separate from Ingest / Review / Dashboard (the
          26-product Product Intelligence Copilot demo). Confidence scores are not accuracy.
        </p>
        <div className="mt-3 font-mono text-[10px] uppercase text-ink-soft space-y-0.5">
          <div>Input · Dynamic rows · Dynamic source columns</div>
          <div className="ml-2">↓</div>
          <div>AI / Data Enrichment</div>
          <div className="ml-2">↓</div>
          <div>Validation</div>
          <div className="ml-2">↓</div>
          <div>Official Delivery Format · {loadedHeaders ? `${loadedHeaders} fields` : "252 fields"}</div>
          <div className="ml-2">↓</div>
          <div>CSV / XLSX</div>
        </div>
      </div>

      {error && <p className="font-mono text-sm text-stamp-flagged">{error}</p>}

      <section className="panel p-5 sm:p-6">
        <h2 className="font-display text-sm uppercase tracking-stencil text-ink">Dataset (loaded)</h2>
        <hr className="rule-tear" />
        <div className="grid gap-6 sm:grid-cols-4">
          <div>
            <p className="form-label">Input rows detected</p>
            <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
              {processedRows ?? "—"}
            </p>
            <p className="mt-1 font-mono text-[10px] uppercase text-ink-soft">Dynamic — whatever the file contains</p>
          </div>
          <div>
            <p className="form-label">Input columns detected</p>
            <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
              {inputColumns ?? "—"}
            </p>
            <p className="mt-1 font-mono text-[10px] uppercase text-ink-soft">Dynamic — whatever the file contains</p>
          </div>
          <div>
            <p className="form-label">Delivery headers detected</p>
            <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
              {loadedHeaders ?? "—"}
            </p>
            <p className="mt-1 font-mono text-[10px] uppercase text-ink-soft">Loaded from official sheet</p>
          </div>
          <div>
            <p className="form-label">Ground-truth evaluation</p>
            <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
              {evaluated ? "RUN" : "N/A"}
            </p>
            <p className="mt-1 font-mono text-[10px] uppercase text-ink-soft">
              {evaluated ? "Exact-match vs labelled file" : "No labelled ground truth loaded"}
            </p>
          </div>
        </div>
      </section>

      <section className="panel p-5 sm:p-6">
        <h2 className="font-display text-sm uppercase tracking-stencil text-ink">Files</h2>
        <hr className="rule-tear" />
        <ul className="space-y-1 font-mono text-xs text-ink">
          {Object.entries(files).map(([kind, info]) => (
            <li key={kind}>
              {info.present ? "PRESENT" : "MISSING"} · {kind}
              {!info.present && info.missing_hint ? ` — ${info.missing_hint}` : ""}
            </li>
          ))}
        </ul>
        <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={onUpload}>
          <label className="block">
            <span className="form-label">Upload kind</span>
            <select
              className="form-underline appearance-none"
              value={uploadKind}
              onChange={(e) => setUploadKind(e.target.value)}
            >
              <option value="input">Evaluation input</option>
              <option value="ground_truth">Ground truth (optional)</option>
              <option value="delivery_schema">Expected Output sheet</option>
              <option value="manufacturers">Manufacturer list (optional)</option>
              <option value="lov">LOV (optional)</option>
              <option value="uom">UOM (optional)</option>
            </select>
          </label>
          <input name="dataset" type="file" accept=".xlsx,.csv" className="font-mono text-xs" />
          <button type="submit" className="btn-secondary" disabled={busy}>
            Upload
          </button>
        </form>
      </section>

      <section className="panel p-5 sm:p-6">
        <h2 className="font-display text-sm uppercase tracking-stencil text-ink">Schema Validation</h2>
        <hr className="rule-tear" />
        <p className="mb-3 font-mono text-[10px] uppercase text-ink-soft">
          Header names loaded from official Expected Output CSV — never hardcoded
        </p>
        <div className="grid gap-4 sm:grid-cols-5">
          <div>
            <p className="form-label">Expected headers</p>
            <p className="mt-1 font-mono text-2xl font-semibold tabular-nums">
              {schemaCompliance ? String(schemaCompliance.expected_count ?? "—") : (loadedHeaders ?? "—")}
            </p>
          </div>
          <div>
            <p className="form-label">Generated headers</p>
            <p className="mt-1 font-mono text-2xl font-semibold tabular-nums">
              {schemaCompliance ? String(schemaCompliance.generated_count ?? schemaCompliance.actual_count ?? "—") : "—"}
            </p>
          </div>
          <div>
            <p className="form-label">Missing headers</p>
            <p className="mt-1 font-mono text-2xl font-semibold tabular-nums">
              {schemaCompliance ? String((schemaCompliance.missing as unknown[])?.length ?? 0) : "—"}
            </p>
          </div>
          <div>
            <p className="form-label">Unexpected headers</p>
            <p className="mt-1 font-mono text-2xl font-semibold tabular-nums">
              {schemaCompliance ? String((schemaCompliance.unexpected as unknown[])?.length ?? 0) : "—"}
            </p>
          </div>
          <div>
            <p className="form-label">Header order</p>
            <p className={`mt-1 font-mono text-2xl font-semibold tabular-nums ${schemaCompliance?.order === "PASS" ? "text-green-600" : schemaCompliance?.order === "FAIL" ? "text-red-600" : ""}`}>
              {schemaCompliance ? String(schemaCompliance.order ?? "—") : "—"}
            </p>
          </div>
        </div>
      </section>

      <section className="panel p-5 sm:p-6">
        <h2 className="font-display text-sm uppercase tracking-stencil text-ink">Evaluation metrics</h2>
        <hr className="rule-tear" />
        {!evaluated ? (
          <p className="font-sans text-sm text-ink-soft">
            Evaluation has not been run. Metrics stay N/A until a labelled ground-truth file is
            compared. These numbers are never inferred from confidence.
          </p>
        ) : (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <p className="form-label">Field-level accuracy</p>
              <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
                {metric(evalData?.field_level_accuracy_pct)}
                {typeof evalData?.field_level_accuracy_pct === "number" ? "%" : ""}
              </p>
            </div>
            <div>
              <p className="form-label">LOV compliance</p>
              <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
                {metric(evalData?.lov_compliance_pct)}
                {typeof evalData?.lov_compliance_pct === "number" ? "%" : ""}
              </p>
            </div>
            <div>
              <p className="form-label">UOM compliance</p>
              <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
                {metric(evalData?.uom_compliance_pct)}
                {typeof evalData?.uom_compliance_pct === "number" ? "%" : ""}
              </p>
            </div>
            <div>
              <p className="form-label">Character-limit compliance</p>
              <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
                {metric(evalData?.char_limit_compliance_pct)}
                {typeof evalData?.char_limit_compliance_pct === "number" ? "%" : ""}
              </p>
            </div>
            <div>
              <p className="form-label">Exact-match fields</p>
              <p className="mt-1 font-mono text-2xl font-semibold tabular-nums">
                {metric(evalData?.exact_match_fields)}
              </p>
            </div>
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="button" className="btn-primary" disabled={busy} onClick={onRun}>
            {busy ? "Running…" : "Process evaluation dataset"}
          </button>
          <p className="self-center font-mono text-xs text-ink-soft">Job: {jobStatus || "none"}</p>
        </div>
      </section>

      <section className="panel p-5 sm:p-6">
        <h2 className="font-display text-sm uppercase tracking-stencil text-ink">Downloadable output</h2>
        <hr className="rule-tear" />
        <p className="mb-3 font-sans text-xs text-ink-soft">
          CSV and XLSX use the official Expected Output headers in official order. Unfilled fields are
          blank.
        </p>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            className="btn-secondary"
            disabled={!jobStatus || jobStatus === "FAILED" || jobStatus === "none"}
            onClick={() => downloadUnihackExport("csv").catch((e) => setError(String(e)))}
          >
            Download CSV
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={!jobStatus || jobStatus === "FAILED" || jobStatus === "none"}
            onClick={() => downloadUnihackExport("xlsx").catch((e) => setError(String(e)))}
          >
            Download XLSX
          </button>
        </div>
      </section>

      <section className="panel p-5 sm:p-6">
        <h2 className="font-display text-sm uppercase tracking-stencil text-ink">Pipeline</h2>
        <hr className="rule-tear" />
        <p className="font-mono text-xs leading-6 text-ink">
          Official input → normalize placeholders → copy matching fields → optional catalog/LOV/UOM
          → descriptions from source text only → validate → human review flags → Expected Output
          CSV/XLSX
        </p>
      </section>

      {rows.length > 0 && (
        <section className="panel p-5 sm:p-6">
          <h2 className="font-display text-sm uppercase tracking-stencil text-ink">Flagged rows</h2>
          <hr className="rule-tear" />
          <ul className="space-y-2 font-mono text-xs">
            {rows.map((r) => (
              <li key={String(r.row_number)}>
                #{String(r.row_number)} {String(r.mfg_part_num || "")} · confidence{" "}
                {String(r.confidence || "")} · review {r.review_required ? "required" : "optional"}
                {r.error ? ` · ${String(r.error)}` : ""}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}