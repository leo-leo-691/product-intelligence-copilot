import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchCategories, ingestText, runDemoBatch } from "../api";

export default function UploadPage() {
  const nav = useNavigate();
  const [categories, setCategories] = useState<{ id: string; name: string }[]>([]);
  const [sku, setSku] = useState("");
  const [categoryId, setCategoryId] = useState("auto");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [pdf, setPdf] = useState<File | null>(null);
  const [image, setImage] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchMsg, setBatchMsg] = useState("");

  useEffect(() => {
    fetchCategories()
      .then((c) => {
        setCategories(c);
      })
      .catch((e) => setError(String(e)));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      let record;
      if (pdf || image) {
        const fd = new FormData();
        fd.append("sku", sku);
        fd.append("category_id", categoryId);
        if (text) fd.append("text", text);
        if (url) fd.append("url", url);
        if (pdf) fd.append("pdf", pdf);
        if (image) fd.append("image", image);
        const r = await fetch("/api/ingest/upload", { method: "POST", body: fd });
        if (!r.ok) throw new Error(await r.text());
        record = await r.json();
      } else {
        record = await ingestText({
          sku,
          category_id: categoryId,
          text: text || undefined,
          url: url || undefined,
        });
      }
      nav(`/review/${record.id}`);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  async function onDemoBatch() {
    setBatchLoading(true);
    setBatchMsg("");
    setError("");
    try {
      const batch = await runDemoBatch();
      setBatchMsg(`Loaded ${batch.product_ids.length} products. Opening review…`);
      nav("/review");
    } catch (err) {
      setError(String(err));
    } finally {
      setBatchLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-label text-ink-soft">Intake desk</p>
          <h1 className="page-title mt-1">Ingest product data</h1>
          <p className="mt-2 max-w-xl font-sans text-sm text-ink-soft">
            PDF, image, pasted text, or URL — multi-source extraction with provenance.
          </p>
        </div>
        <button type="button" onClick={onDemoBatch} disabled={batchLoading} className="btn-secondary">
          {batchLoading ? "Running demo batch…" : "Load 20-product demo batch"}
        </button>
      </div>

      {batchMsg && <p className="font-mono text-sm text-stamp-approved">{batchMsg}</p>}

      <form onSubmit={onSubmit} className="panel p-5 sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-dashed border-rule-line pb-4">
          <div>
            <h2 className="font-display text-lg font-semibold uppercase tracking-stencil text-ink">
              Intake Form — Product Data
            </h2>
            <p className="mt-1 font-sans text-xs text-ink-soft">
              Complete required fields. Attach source documents when available.
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
              required
              placeholder="VALVE-A-001"
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

        <hr className="rule-tear" />

        <label className="block">
          <span className="form-label">Raw text</span>
          <textarea
            className="form-underline mt-1 h-40 resize-y"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste datasheet text here"
          />
        </label>

        <label className="mt-6 block">
          <span className="form-label">URL (optional)</span>
          <input
            className="form-underline"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://…"
          />
        </label>

        <hr className="rule-tear" />

        <div className="grid gap-6 sm:grid-cols-2">
          <label className="block">
            <span className="form-label">PDF (optional)</span>
            <input
              type="file"
              accept=".pdf"
              className="mt-2 block w-full font-mono text-xs text-ink-soft file:mr-3 file:rounded-[3px] file:border file:border-rule-line file:bg-paper file:px-3 file:py-1.5 file:font-sans file:text-xs file:text-ink"
              onChange={(e) => setPdf(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className="block">
            <span className="form-label">Image (optional)</span>
            <input
              type="file"
              accept="image/*"
              className="mt-2 block w-full font-mono text-xs text-ink-soft file:mr-3 file:rounded-[3px] file:border file:border-rule-line file:bg-paper file:px-3 file:py-1.5 file:font-sans file:text-xs file:text-ink"
              onChange={(e) => setImage(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>

        {error && <p className="mt-4 font-mono text-sm text-stamp-flagged">{error}</p>}

        <div className="mt-8 flex flex-wrap gap-3 border-t border-dashed border-rule-line pt-5">
          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? "Processing…" : "Run"}
          </button>
          <Link to="/dashboard" className="btn-secondary">
            Open dashboard
          </Link>
        </div>
      </form>
    </div>
  );
}
