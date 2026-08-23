import { DragEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchCategories,
  getUserErrorMessage,
  fetchUnihackSchema,
  fetchUnihackStatus,
  ingestText,
  ingestUpload,
  runDemoBatch,
  runUnihackJob,
  uploadUnihackFile,
} from "../api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type Workflow = "product" | "catalog" | null;

type DetectedInput = {
  file: File | null;
  fileName: string;
  fileType: string;        // "PDF" | "CSV" | "XLSX" | "XLS" | "Image" | "TXT" | "Pasted Text" | "URL"
  workflow: Workflow;
  /** Backend-reported metadata (populated after upload for catalog files). */
  rows: number | null;
  columns: number | null;
  deliveryHeaders: number | null;
  analyzing: boolean;
};

type UiError = {
  title: string;
  body: string;
} | null;

type DatasetProgress = {
  processed: number;
  total: number;
  successful: number;
  failed: number;
};

type DatasetResult = {
  status: string;
  inputRows: number | null;
  inputColumns: number | null;
  deliveryHeaders: number | null;
  schemaValidation: string | null;
  missingHeaders: number | null;
  unexpectedHeaders: number | null;
  headerOrder: string | null;
  groundTruth: string;
  jobId: string | null;
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const PRODUCT_EXTENSIONS = new Set(["pdf", "png", "jpg", "jpeg", "webp", "txt"]);
const CATALOG_EXTENSIONS = new Set(["csv", "xlsx", "xls"]);
const ALL_ACCEPTED = [...PRODUCT_EXTENSIONS, ...CATALOG_EXTENSIONS].map((e) => `.${e}`).join(",");

function classifyFile(file: File): { fileType: string; workflow: Workflow } {
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  const mime = file.type.toLowerCase();
  if (CATALOG_EXTENSIONS.has(ext) || mime.includes("spreadsheet") || mime.includes("excel") || mime === "text/csv") {
    return { fileType: ext ? `${ext.toUpperCase()} dataset` : "Catalog dataset", workflow: "catalog" };
  }
  if (ext === "pdf") return { fileType: "PDF document", workflow: "product" };
  if (ext === "txt") return { fileType: "TXT", workflow: "product" };
  if (["png", "jpg", "jpeg", "webp"].includes(ext) || mime.startsWith("image/")) {
    return { fileType: ext ? `${ext.toUpperCase()} image` : "Image", workflow: "product" };
  }
  if (mime === "application/pdf") return { fileType: "PDF document", workflow: "product" };
  if (mime.startsWith("text/")) return { fileType: "TXT", workflow: "product" };
  return { fileType: ext ? ext.toUpperCase() : "Unknown", workflow: null };
}

function classifyText(): { fileType: string; workflow: Workflow } {
  return { fileType: "Pasted Text", workflow: "product" };
}

function classifyUrl(): { fileType: string; workflow: Workflow } {
  return { fileType: "URL", workflow: "product" };
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function UploadPage() {
  const nav = useNavigate();

  // Existing product-ingest state (preserved)
  const [categories, setCategories] = useState<{ id: string; name: string }[]>([]);
  const [sku, setSku] = useState("");
  const [categoryId, setCategoryId] = useState("auto");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<UiError>(null);
  const [loading, setLoading] = useState(false);

  // Demo batch state (preserved)
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchMsg, setBatchMsg] = useState("");

  // Unified detection state
  const [dragActive, setDragActive] = useState(false);
  const [detected, setDetected] = useState<DetectedInput | null>(null);
  const [inputMode, setInputMode] = useState<"file" | "text" | "url" | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Dataset (catalog) processing state
  const [datasetProcessing, setDatasetProcessing] = useState(false);
  const [datasetProgress, setDatasetProgress] = useState<DatasetProgress | null>(null);
  const [datasetResult, setDatasetResult] = useState<DatasetResult | null>(null);

  // Product processing state (for showing inline status)
  const [productProcessing, setProductProcessing] = useState(false);

  // Disambiguation state
  const [showAmbiguous, setShowAmbiguous] = useState(false);

  useEffect(() => {
    fetchCategories()
      .then((c) => setCategories(c))
      .catch((e) => setError(getUserErrorMessage(e, "service")));
  }, []);

  /* ---------------------------------------------------------------- */
  /*  File detection                                                    */
  /* ---------------------------------------------------------------- */

  const handleFiles = useCallback((files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0]; // Process one file at a time
    const { fileType, workflow } = classifyFile(file);

    if (!workflow) {
      setShowAmbiguous(true);
      setDetected({
        file,
        fileName: file.name,
        fileType,
        workflow: null,
        rows: null,
        columns: null,
        deliveryHeaders: null,
        analyzing: false,
      });
      setInputMode("file");
      setError({
        title: "INPUT TYPE NOT RECOGNIZED",
        body: "Choose how you want to process this file.",
      });
      return;
    }

    setShowAmbiguous(false);
    setDetected({
      file,
      fileName: file.name,
      fileType,
      workflow,
      rows: null,
      columns: null,
      deliveryHeaders: null,
      analyzing: false,
    });
    setInputMode("file");
    setError(null);
    setDatasetResult(null);
    setDatasetProgress(null);
  }, []);

  async function loadCatalogSchemaMetadata() {
    try {
      const schema = await fetchUnihackSchema();
      setDetected((prev) =>
        prev
          ? {
              ...prev,
              analyzing: false,
              deliveryHeaders: schema.available ? schema.header_count : null,
            }
          : null
      );
    } catch (err) {
      setError(getUserErrorMessage(err, "service"));
      setDetected((prev) => (prev ? { ...prev, analyzing: false } : null));
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Text / URL detection                                              */
  /* ---------------------------------------------------------------- */

  function handleTextDetect() {
    if (!text.trim()) return;
    const { fileType, workflow } = classifyText();
    setDetected({
      file: null,
      fileName: "",
      fileType,
      workflow,
      rows: null,
      columns: null,
      deliveryHeaders: null,
      analyzing: false,
    });
    setInputMode("text");
    setShowAmbiguous(false);
    setError(null);
    setDatasetResult(null);
  }

  function handleUrlDetect() {
    if (!url.trim()) return;
    const { fileType, workflow } = classifyUrl();
    setDetected({
      file: null,
      fileName: "",
      fileType,
      workflow,
      rows: null,
      columns: null,
      deliveryHeaders: null,
      analyzing: false,
    });
    setInputMode("url");
    setShowAmbiguous(false);
    setError(null);
    setDatasetResult(null);
  }

  /* ---------------------------------------------------------------- */
  /*  Drag & Drop                                                       */
  /* ---------------------------------------------------------------- */

  function onDragOver(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(true);
  }
  function onDragLeave(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
  }
  function onDrop(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    handleFiles(e.dataTransfer.files);
  }

  /* ---------------------------------------------------------------- */
  /*  Product submission (existing logic preserved)                      */
  /* ---------------------------------------------------------------- */

  async function onSubmitProduct(e?: FormEvent) {
    e?.preventDefault();
    if (loading || productProcessing) return;
    setLoading(true);
    setProductProcessing(true);
    setError(null);
    try {
      let record;
      if (detected?.file && detected.workflow === "product") {
        const fd = new FormData();
        fd.append("sku", sku || detected.file.name.replace(/\.[^.]+$/, ""));
        fd.append("category_id", categoryId);
        if (text) fd.append("text", text);
        if (url) fd.append("url", url);

        // Determine the correct form field based on file type
        const ext = (detected.file.name.split(".").pop() || "").toLowerCase();
        if (ext === "pdf") {
          fd.append("pdf", detected.file);
        } else if (["png", "jpg", "jpeg", "webp"].includes(ext)) {
          fd.append("image", detected.file);
        } else if (ext === "txt") {
          // TXT files: read content and send as text
          const fileText = await detected.file.text();
          fd.append("text", fileText);
        }
        record = await ingestUpload(fd);
      } else if (inputMode === "text" || inputMode === "url") {
        record = await ingestText({
          sku: sku || "PASTED-INPUT",
          category_id: categoryId,
          text: text || undefined,
          url: url || undefined,
        });
      } else {
        setError({
          title: "INPUT COULD NOT BE PROCESSED",
          body: "Upload a file, paste text, or enter a URL.",
        });
        setLoading(false);
        setProductProcessing(false);
        return;
      }
      nav(`/review/${record.id}`);
    } catch (err) {
      setError(getUserErrorMessage(err, "processing"));
    } finally {
      setLoading(false);
      setProductProcessing(false);
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Dataset submission (calls existing UniHack APIs)                   */
  /* ---------------------------------------------------------------- */

  async function onSubmitDataset() {
    if (datasetProcessing || !detected?.file) return;
    setDatasetProcessing(true);
    setDatasetProgress(null);
    setDatasetResult(null);
    setError(null);

    try {
      setDetected((prev) => (prev ? { ...prev, analyzing: true } : null));
      await uploadUnihackFile("input", detected.file);
      await loadCatalogSchemaMetadata();
      const job = await runUnihackJob(true);
      const jobId = job.id as string;

      if (job.status === "FAILED") {
        setError(getUserErrorMessage(new Error(String(job.error || "")), "processing"));
        setDatasetProcessing(false);
        return;
      }

      let pollFailures = 0;
      // Poll status
      const poll = setInterval(async () => {
        try {
          const status = await fetchUnihackStatus(jobId);
          pollFailures = 0;
          const progress = status.progress as DatasetProgress | undefined;
          if (progress) {
            setDatasetProgress({
              processed: progress.processed || 0,
              total: progress.total || 0,
              successful: progress.successful || 0,
              failed: progress.failed || 0,
            });
          }

          const jobStatus = String(status.status || "");
          if (jobStatus === "COMPLETED" || jobStatus === "PARTIAL" || jobStatus === "FAILED") {
            clearInterval(poll);
            setDatasetProcessing(false);

            const schemaCompliance = status.schema_compliance as Record<string, unknown> | undefined;
            const inputHeaders = (status.input_headers as string[]) || [];

            setDatasetResult({
              status: jobStatus,
              inputRows: (status.input_row_count as number) || null,
              inputColumns: inputHeaders.length > 0 ? inputHeaders.length : null,
              deliveryHeaders: (status.header_count as number) || null,
              schemaValidation: schemaCompliance?.valid ? "PASS" : schemaCompliance ? "FAIL" : null,
              missingHeaders: Array.isArray(schemaCompliance?.missing) ? (schemaCompliance.missing as unknown[]).length : null,
              unexpectedHeaders: Array.isArray(schemaCompliance?.unexpected) ? (schemaCompliance.unexpected as unknown[]).length : null,
              headerOrder: schemaCompliance?.order as string || null,
              groundTruth: (status.evaluation as Record<string, unknown>)?.available ? "RUN" : "N/A",
              jobId,
            });
            if (jobStatus === "FAILED") {
              setError(getUserErrorMessage(new Error(String(status.error || "")), "processing"));
            }
          }
        } catch (err) {
          pollFailures += 1;
          if (pollFailures >= 3) {
            clearInterval(poll);
            setDatasetProcessing(false);
            setError(getUserErrorMessage(err, "status"));
          }
        }
      }, 2000);
    } catch (err) {
      setError(getUserErrorMessage(err, "processing"));
      setDatasetProcessing(false);
      setDetected((prev) => (prev ? { ...prev, analyzing: false } : null));
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Demo batch (existing logic preserved)                             */
  /* ---------------------------------------------------------------- */

  async function onDemoBatch() {
    setBatchLoading(true);
    setBatchMsg("");
    setError(null);
    try {
      const batch = await runDemoBatch();
      setBatchMsg(`Loaded ${batch.product_ids.length} products. Opening review…`);
      nav("/review");
    } catch (err) {
      setError(getUserErrorMessage(err, "processing"));
    } finally {
      setBatchLoading(false);
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Disambiguation                                                    */
  /* ---------------------------------------------------------------- */

  function forceWorkflow(wf: Workflow) {
    setDetected((prev) => (prev ? { ...prev, workflow: wf } : null));
    setShowAmbiguous(false);
    if (wf === "catalog" && detected?.file) {
      setDetected((prev) => (prev ? { ...prev, analyzing: true } : null));
      loadCatalogSchemaMetadata();
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Reset                                                             */
  /* ---------------------------------------------------------------- */

  function resetInput() {
    setDetected(null);
    setInputMode(null);
    setDatasetResult(null);
    setDatasetProgress(null);
    setDatasetProcessing(false);
    setProductProcessing(false);
    setShowAmbiguous(false);
    setError(null);
    setBatchMsg("");
    if (fileRef.current) fileRef.current.value = "";
  }

  /* ---------------------------------------------------------------- */
  /*  Render                                                            */
  /* ---------------------------------------------------------------- */

  const showProductForm = detected?.workflow === "product" && !productProcessing;
  const showDatasetCard = detected?.workflow === "catalog";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <p className="font-mono text-[11px] uppercase tracking-label text-ink-soft">Intake desk</p>
        <h1 className="page-title mt-1">Ingest Product Data</h1>
        <p className="mt-2 max-w-2xl font-sans text-sm text-ink-soft">
          Upload a product document, catalog dataset, image, or text. The Copilot automatically
          detects the appropriate workflow.
        </p>
      </div>

      {error && (
        <div className="border border-stamp-flagged bg-paper p-4" role="alert">
          <p className="font-display text-sm uppercase tracking-stencil text-stamp-flagged">{error.title}</p>
          <p className="mt-1 font-sans text-sm text-ink-soft">{error.body}</p>
          <button type="button" className="btn-secondary mt-3" onClick={() => setError(null)}>
            Retry
          </button>
        </div>
      )}
      {batchMsg && <p className="font-mono text-sm text-stamp-approved">{batchMsg}</p>}

      {/* ============================================================ */}
      {/*  DROPZONE — only show when no input detected yet              */}
      {/* ============================================================ */}
      {!detected && !datasetResult && (
        <>
          <div
            className={`dropzone ${dragActive ? "dropzone-active" : ""}`}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") fileRef.current?.click();
            }}
            role="button"
            tabIndex={0}
            aria-label="Drop files here or click to choose a file"
          >
            <p className="font-display text-lg font-semibold uppercase tracking-stencil text-ink sm:text-xl">
              Drop your product data here
            </p>
            <p className="mt-2 font-mono text-xs uppercase tracking-label text-ink-soft">
              PDF · CSV · XLSX · XLS · JPG · PNG · WEBP · TXT
            </p>
            <button
              type="button"
              className="btn-secondary mt-4"
              onClick={(e) => {
                e.stopPropagation();
                fileRef.current?.click();
              }}
            >
              Choose File
            </button>
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              accept={ALL_ACCEPTED}
              onChange={(e) => handleFiles(e.target.files)}
              aria-label="File upload"
            />
            <p className="mt-3 font-sans text-xs text-ink-soft">or paste text / enter a URL below</p>
          </div>

          {/* Text & URL inputs */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block">
                <span className="form-label">Paste product text</span>
                <textarea
                  className="form-underline mt-1 h-28 resize-y"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Paste datasheet text here…"
                />
              </label>
              {text.trim() && (
                <button type="button" className="btn-primary mt-2" onClick={handleTextDetect}>
                  Detect Input
                </button>
              )}
            </div>
            <div>
              <label className="block">
                <span className="form-label">Enter product URL</span>
                <input
                  className="form-underline"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://…"
                />
              </label>
              {url.trim() && (
                <button type="button" className="btn-primary mt-2" onClick={handleUrlDetect}>
                  Detect Input
                </button>
              )}
            </div>
          </div>

          {/* Demo */}
          <div className="border-t border-dashed border-rule-line pt-5 text-center">
            <p className="font-sans text-sm text-ink-soft">Want to see the Copilot in action first?</p>
            <button
              type="button"
              onClick={onDemoBatch}
              disabled={batchLoading}
              className="btn-secondary mt-3"
            >
              {batchLoading ? "Running demo batch…" : "Try 26-Product Demo"}
            </button>
          </div>
        </>
      )}

      {/* ============================================================ */}
      {/*  DISAMBIGUATION — workflow uncertain                          */}
      {/* ============================================================ */}
      {showAmbiguous && detected && (
        <section className="panel p-5 sm:p-6">
          <h2 className="font-display text-sm uppercase tracking-stencil text-stamp-review">
            Input Type Uncertain
          </h2>
          <hr className="rule-tear" />
          <p className="font-sans text-sm text-ink-soft">
            Choose how you want to process this file.
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <button type="button" className="btn-primary" onClick={() => forceWorkflow("catalog")}>
              Catalog Data
            </button>
            <button type="button" className="btn-secondary" onClick={() => forceWorkflow("product")}>
              Product Data
            </button>
            <button type="button" className="btn-ghost" onClick={resetInput}>
              Cancel
            </button>
          </div>
        </section>
      )}

      {/* ============================================================ */}
      {/*  DETECTION CARD — input detected                              */}
      {/* ============================================================ */}
      {detected && !showAmbiguous && !datasetResult && (
        <section className="panel p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h2 className="font-display text-sm uppercase tracking-stencil text-ink">
              File Detected
            </h2>
            <button type="button" className="btn-ghost" onClick={resetInput}>
              Change input
            </button>
          </div>
          <hr className="rule-tear" />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {detected.fileName && (
              <div>
                <p className="form-label">File</p>
                <p className="mt-1 font-mono text-sm text-ink truncate" title={detected.fileName}>
                  {detected.fileName}
                </p>
              </div>
            )}
            <div>
              <p className="form-label">Type</p>
              <p className="mt-1 font-mono text-sm text-ink">{detected.fileType}</p>
            </div>
            <div>
              <p className="form-label">Detected workflow</p>
              <p className="mt-1 font-mono text-sm font-semibold uppercase text-ink">
                {detected.workflow === "catalog" ? "Catalog Enrichment" : "Product Intelligence"}
              </p>
            </div>
            {detected.analyzing && (
              <div>
                <p className="form-label">Status</p>
                <p className="mt-1 font-mono text-sm text-ink-soft">Analyzing dataset…</p>
              </div>
            )}
            {detected.deliveryHeaders !== null && !detected.analyzing && (
              <div>
                <p className="form-label">Delivery schema</p>
                <p className="mt-1 font-mono text-sm text-ink">{detected.deliveryHeaders} fields</p>
              </div>
            )}
          </div>

          {/* Catalog — process button */}
          {showDatasetCard && !detected.analyzing && !datasetProcessing && (
            <div className="mt-6 flex flex-wrap gap-3 border-t border-dashed border-rule-line pt-5">
              <button type="button" className="btn-primary" onClick={onSubmitDataset} disabled={datasetProcessing}>
                Process Dataset
              </button>
            </div>
          )}

          {/* Dataset processing progress */}
          {datasetProcessing && datasetProgress && (
            <div className="mt-6 border-t border-dashed border-rule-line pt-5">
              <h3 className="font-display text-sm uppercase tracking-stencil text-ink">
                Processing
              </h3>
              <div className="mt-3 grid gap-4 sm:grid-cols-3">
                <div>
                  <p className="form-label">Rows processed</p>
                  <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
                    {datasetProgress.processed} / {datasetProgress.total || "…"}
                  </p>
                </div>
                <div>
                  <p className="form-label">Successful</p>
                  <p className="mt-1 font-mono text-3xl font-semibold tabular-nums text-stamp-approved">
                    {datasetProgress.successful}
                  </p>
                </div>
                <div>
                  <p className="form-label">Failed</p>
                  <p className="mt-1 font-mono text-3xl font-semibold tabular-nums text-stamp-flagged">
                    {datasetProgress.failed}
                  </p>
                </div>
              </div>
              {/* Pipeline steps */}
              <div className="mt-4 space-y-1">
                <div className="pipeline-step pipeline-step-done">
                  <span className="pipeline-step-icon">✓</span> Input detected
                </div>
                <div className="pipeline-step pipeline-step-done">
                  <span className="pipeline-step-icon">✓</span> Schema loaded
                </div>
                <div className="pipeline-step pipeline-step-active">
                  <span className="pipeline-step-icon">...</span> Enrichment
                </div>
                <div className="pipeline-step">
                  <span className="pipeline-step-icon">○</span> Validation
                </div>
                <div className="pipeline-step">
                  <span className="pipeline-step-icon">○</span> Export
                </div>
              </div>
            </div>
          )}
          {datasetProcessing && !datasetProgress && (
            <div className="mt-6 border-t border-dashed border-rule-line pt-5">
              <p className="font-mono text-sm text-ink-soft">Starting dataset processing…</p>
            </div>
          )}
        </section>
      )}

      {/* ============================================================ */}
      {/*  DATASET RESULT                                                */}
      {/* ============================================================ */}
      {datasetResult && (
        <section className="panel p-5 sm:p-6">
          <h2 className="font-display text-sm uppercase tracking-stencil text-ink">
            {datasetResult.status === "COMPLETED" ? "Processing Complete" : `Processing ${datasetResult.status}`}
          </h2>
          <hr className="rule-tear" />
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="form-label">Rows processed</p>
              <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
                {datasetResult.inputRows ?? "—"}
              </p>
            </div>
            <div>
              <p className="form-label">Input columns</p>
              <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
                {datasetResult.inputColumns ?? "—"}
              </p>
            </div>
            <div>
              <p className="form-label">Delivery fields</p>
              <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
                {datasetResult.deliveryHeaders ?? "—"}
              </p>
            </div>
            <div>
              <p className="form-label">Ground-truth evaluation</p>
              <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
                {datasetResult.groundTruth}
              </p>
              <p className="mt-1 font-mono text-[10px] uppercase text-ink-soft">
                {datasetResult.groundTruth === "N/A"
                  ? "No labelled ground truth loaded"
                  : "Exact-match vs labelled file"}
              </p>
            </div>
          </div>

          {/* Schema validation */}
          {datasetResult.schemaValidation && (
            <>
              <hr className="rule-tear" />
              <h3 className="font-display text-sm uppercase tracking-stencil text-ink">
                Schema Validation
              </h3>
              <div className="mt-3 grid gap-4 sm:grid-cols-4">
                <div>
                  <p className="form-label">Status</p>
                  <p className={`mt-1 font-mono text-2xl font-semibold ${datasetResult.schemaValidation === "PASS" ? "text-stamp-approved" : "text-stamp-flagged"}`}>
                    {datasetResult.schemaValidation}
                  </p>
                </div>
                <div>
                  <p className="form-label">Missing headers</p>
                  <p className="mt-1 font-mono text-2xl font-semibold tabular-nums">
                    {datasetResult.missingHeaders ?? "—"}
                  </p>
                </div>
                <div>
                  <p className="form-label">Unexpected headers</p>
                  <p className="mt-1 font-mono text-2xl font-semibold tabular-nums">
                    {datasetResult.unexpectedHeaders ?? "—"}
                  </p>
                </div>
                <div>
                  <p className="form-label">Header order</p>
                  <p className={`mt-1 font-mono text-2xl font-semibold ${datasetResult.headerOrder === "PASS" ? "text-stamp-approved" : datasetResult.headerOrder === "FAIL" ? "text-stamp-flagged" : ""}`}>
                    {datasetResult.headerOrder ?? "—"}
                  </p>
                </div>
              </div>
            </>
          )}

          {/* Pipeline complete steps */}
          <div className="mt-4 space-y-1">
            <div className="pipeline-step pipeline-step-done">
              <span className="pipeline-step-icon">✓</span> Input detected
            </div>
            <div className="pipeline-step pipeline-step-done">
              <span className="pipeline-step-icon">✓</span> Schema loaded
            </div>
            <div className="pipeline-step pipeline-step-done">
              <span className="pipeline-step-icon">✓</span> Enrichment
            </div>
            <div className="pipeline-step pipeline-step-done">
              <span className="pipeline-step-icon">✓</span> Validation
            </div>
            <div className="pipeline-step pipeline-step-done">
              <span className="pipeline-step-icon">✓</span> Export
            </div>
          </div>

          {/* Actions */}
          <div className="mt-6 flex flex-wrap gap-3 border-t border-dashed border-rule-line pt-5">
            <Link to="/evaluation" className="btn-primary">
              View Results
            </Link>
            <button type="button" className="btn-secondary" onClick={resetInput}>
              Start New Ingestion
            </button>
          </div>
        </section>
      )}

      {/* ============================================================ */}
      {/*  PRODUCT FORM — shown when product workflow detected           */}
      {/* ============================================================ */}
      {showProductForm && (
        <form onSubmit={onSubmitProduct} className="panel p-5 sm:p-7">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-dashed border-rule-line pb-4">
            <div>
              <h2 className="font-display text-lg font-semibold uppercase tracking-stencil text-ink">
                Product Extraction
              </h2>
              <p className="mt-1 font-sans text-xs text-ink-soft">
                Complete the fields below and run extraction.
                {detected?.fileType === "TXT" && " The file contents will be sent as text."}
              </p>
            </div>
            <p className="font-mono text-[11px] uppercase tracking-label text-ink-soft">Form PI-014</p>
          </div>

          <div className="mt-6 grid gap-6 sm:grid-cols-2">
            <label className="block">
              <span className="form-label">SKU</span>
              <input
                className="form-underline"
                value={sku}
                onChange={(e) => setSku(e.target.value)}
                placeholder={detected?.fileName?.replace(/\.[^.]+$/, "") || "VALVE-A-001"}
              />
            </label>
            <label className="block">
              <span className="form-label">Category</span>
              <select
                className="form-underline appearance-none"
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
              >
                <option value="auto">Auto-infer category</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {/* Show text/URL fields if input mode is text or url, or allow additional context */}
          {(inputMode === "text" || inputMode === "url" || detected?.fileType === "TXT") && (
            <>
              <hr className="rule-tear" />
              {(inputMode === "text" || detected?.fileType === "TXT") && (
                <label className="block">
                  <span className="form-label">Product text</span>
                  <textarea
                    className="form-underline mt-1 h-40 resize-y"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder="Paste datasheet text here"
                  />
                </label>
              )}
              {inputMode === "url" && (
                <label className="mt-4 block">
                  <span className="form-label">URL</span>
                  <input
                    className="form-underline"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://…"
                  />
                </label>
              )}
            </>
          )}

          <div className="mt-8 flex flex-wrap gap-3 border-t border-dashed border-rule-line pt-5">
            <button type="submit" disabled={loading} className="btn-primary">
              {loading ? "Processing…" : "Extract Product Data"}
            </button>
            <button type="button" className="btn-ghost" onClick={resetInput}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Product processing inline status */}
      {productProcessing && (
        <div className="panel p-5 text-center">
          <p className="font-display text-sm uppercase tracking-stencil text-ink">Processing</p>
          <p className="mt-2 font-mono text-sm text-ink-soft">
            Extracting product data… This may take a moment.
          </p>
        </div>
      )}
    </div>
  );
}
