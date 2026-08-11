import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchCategories, ingestText, runDemoBatch } from "../api";

export default function UploadPage() {
  const nav = useNavigate();
  const [categories, setCategories] = useState<{ id: string; name: string }[]>([]);
  const [sku, setSku] = useState("");
  const [categoryId, setCategoryId] = useState("industrial_valve");
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
        if (c.length) setCategoryId(c[0].id);
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
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Ingest product data</h1>
          <p className="mt-1 text-slate-400">
            PDF, image, pasted text, or URL — multi-source extraction with provenance.
          </p>
        </div>
        <button
          type="button"
          onClick={onDemoBatch}
          disabled={batchLoading}
          className="rounded-lg border border-emerald-700/80 bg-emerald-950/60 px-4 py-2 text-sm text-emerald-300 hover:bg-emerald-900 disabled:opacity-50"
        >
          {batchLoading ? "Running demo batch…" : "Load 20-product demo batch"}
        </button>
      </div>

      {batchMsg && <p className="text-sm text-emerald-400">{batchMsg}</p>}

      <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900/40 p-6 shadow-xl shadow-black/20">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            SKU
            <input
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
              value={sku}
              onChange={(e) => setSku(e.target.value)}
              required
              placeholder="VALVE-A-001"
            />
          </label>
          <label className="block text-sm">
            Category
            <select
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
            >
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="block text-sm">
          Raw text
          <textarea
            className="mt-1 h-40 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste datasheet text, or use Load demo batch"
          />
        </label>
        <label className="block text-sm">
          URL (optional)
          <input
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://…"
          />
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            PDF (optional)
            <input
              type="file"
              accept=".pdf"
              className="mt-1 block w-full text-sm text-slate-400"
              onChange={(e) => setPdf(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className="block text-sm">
            Image (optional, VLM when API key set)
            <input
              type="file"
              accept="image/*"
              className="mt-1 block w-full text-sm text-slate-400"
              onChange={(e) => setImage(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <div className="flex flex-wrap gap-3">
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
          >
            {loading ? "Processing…" : "Run pipeline"}
          </button>
          <Link to="/dashboard" className="rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-800">
            Open dashboard
          </Link>
        </div>
      </form>
    </div>
  );
}
