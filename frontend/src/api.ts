export type ConfidenceBand = "High" | "Medium" | "Low";

export interface FieldProvenance {
  value: unknown;
  confidence_score: ConfidenceBand;
  confidence_raw: number;
  confidence_reasoning: Record<string, number>;
  source_type?: string;
  source_snippet?: string;
  source_location?: string;
  extraction_method: string;
  needs_review: boolean;
  review_status: string;
  not_found: boolean;
  validation_errors: string[];
}

export interface FieldConflict {
  field_name: string;
  candidates: {
    value: unknown;
    source_type: string;
    source_snippet?: string;
    source_location?: string;
    extraction_method: string;
    provider?: string;
  }[];
  resolved: boolean;
  kind?: string;
}

export interface DualLLMFieldComparison {
  field_name: string;
  gemini_value?: unknown;
  claude_value?: unknown;
  status: string;
  requires_review: boolean;
}

export interface DualLLMMeta {
  enabled: boolean;
  gemini_status: string;
  claude_status: string;
  gemini_model?: string | null;
  claude_model?: string | null;
  comparisons: DualLLMFieldComparison[];
}

export interface EvalMatchRate {
  fields_compared?: number;
  match_rate?: number;
  high_band_matches?: number;
  exact_matches?: number;
  error?: string;
}

export interface DashboardStats {
  total_products: number;
  total_fields: number;
  high_confidence_pct: number;
  medium_confidence_pct: number;
  low_confidence_pct: number;
  fields_approved: number;
  fields_pending: number;
  conflicts_count: number;
  propagations_applied: number;
  estimated_minutes_saved: number;
  outliers_flagged?: number;
  kg_nodes?: number;
}

export interface ProductRecord {
  id: string;
  sku: string;
  category_id: string;
  source_template_id?: string;
  fields: Record<string, FieldProvenance>;
  conflicts: FieldConflict[];
  batch_id?: string;
  status: string;
  category_inference?: { category_id: string; reasoning: string; confidence: number };
  language?: Record<string, unknown>;
  outliers?: { field_name: string; message: string; value?: unknown }[];
  kg?: Record<string, unknown>;
  dual_llm?: DualLLMMeta | null;
}

export interface PropagationSuggestion {
  id: string;
  source_template_id: string;
  field_name: string;
  old_value: unknown;
  new_value: unknown;
  source_product_id: string;
  candidate_product_ids: string[];
  status: string;
}

export interface HealthInfo {
  status: string;
  llm_provider?: string;
  llm_configured?: boolean;
  anthropic_configured: boolean;
  web_search_configured: boolean;
  dual_llm_enabled?: boolean;
  env?: string;
}

/** Backend base URL. Empty in local dev → Vite proxy handles /api and /health. */
export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

const API_KEY = import.meta.env.VITE_API_KEY ?? "";

export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalized}`;
}

function mergeHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers();
  if (API_KEY) {
    headers.set("X-API-Key", API_KEY);
  }
  if (extra) {
    new Headers(extra).forEach((value, key) => headers.set(key, value));
  }
  return headers;
}

/** Fetch wrapper: applies API base URL and optional X-API-Key header. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = mergeHeaders(init?.headers);
  return fetch(apiUrl(path), { ...init, headers });
}

async function parseJson<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r.json();
}

export async function fetchHealth(): Promise<HealthInfo> {
  const r = await apiFetch("/health");
  return parseJson(r);
}

export async function fetchProducts(): Promise<ProductRecord[]> {
  const r = await apiFetch("/api/products");
  return parseJson(r);
}

export async function fetchProduct(id: string): Promise<ProductRecord> {
  const r = await apiFetch(`/api/products/${id}`);
  return parseJson(r);
}

export async function fetchDashboard(): Promise<DashboardStats> {
  const r = await apiFetch("/api/dashboard");
  return parseJson(r);
}

export async function ingestText(body: {
  sku: string;
  category_id: string;
  text?: string;
  url?: string;
}): Promise<ProductRecord> {
  const r = await apiFetch("/api/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseJson(r);
}

export async function ingestUpload(formData: FormData): Promise<ProductRecord> {
  const r = await apiFetch("/api/ingest/upload", { method: "POST", body: formData });
  return parseJson(r);
}

export async function reviewField(
  productId: string,
  fieldName: string,
  review_status: string,
  value?: unknown
): Promise<{ product: ProductRecord; propagation_suggestion?: PropagationSuggestion }> {
  const r = await apiFetch(`/api/products/${productId}/fields/${fieldName}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ review_status, value }),
  });
  return parseJson(r);
}

export async function resolveConflict(
  productId: string,
  fieldName: string,
  chosen_value: unknown
): Promise<ProductRecord> {
  const r = await apiFetch(`/api/products/${productId}/conflicts/${fieldName}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chosen_value }),
  });
  return parseJson(r);
}

export async function bulkApproveHigh(productId: string): Promise<ProductRecord> {
  const r = await apiFetch(`/api/products/${productId}/bulk-approve-high`, { method: "POST" });
  return parseJson(r);
}

export async function approveRecord(productId: string): Promise<ProductRecord> {
  const r = await apiFetch(`/api/products/${productId}/approve-record`, { method: "POST" });
  return parseJson(r);
}

export async function propagationAction(id: string, action: "apply" | "dismiss") {
  const r = await apiFetch(`/api/propagations/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  return parseJson(r);
}

export async function fetchCategories(): Promise<{ id: string; name: string }[]> {
  const r = await apiFetch("/api/categories");
  return parseJson(r);
}

export async function runDemoBatch(): Promise<{ id: string; product_ids: string[] }> {
  const r = await apiFetch("/api/batch/from-manifest?reset=true", { method: "POST" });
  return parseJson(r);
}

export async function fetchEvalMatchRate(): Promise<EvalMatchRate> {
  const r = await apiFetch("/api/eval/match-rate");
  return parseJson(r);
}

/** Trigger a browser file download from an API path. */
export async function downloadExport(kind: "csv" | "json", approvedOnly = false): Promise<void> {
  const r = await apiFetch(`/api/export/${kind}?approved_only=${approvedOnly}`);
  if (!r.ok) {
    throw new Error((await r.text()) || `Export failed (${r.status})`);
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = kind === "csv" ? "products.csv" : "products.json";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export type UnihackFileInfo = {
  present: boolean;
  path: string | null;
  missing_hint: string | null;
};

export async function fetchUnihackSchema(): Promise<{
  available: boolean;
  header_count: number | null;
  headers: string[];
  error?: string;
}> {
  const r = await apiFetch("/api/unihack/schema");
  return parseJson(r);
}

export async function fetchUnihackFiles(): Promise<{ files: Record<string, UnihackFileInfo> }> {
  const r = await apiFetch("/api/unihack/files");
  return parseJson(r);
}

export async function uploadUnihackFile(kind: string, file: File): Promise<unknown> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await apiFetch(`/api/unihack/import?kind=${encodeURIComponent(kind)}`, {
    method: "POST",
    body: fd,
  });
  return parseJson(r);
}

export async function runUnihackJob(evaluate = true): Promise<Record<string, unknown>> {
  const r = await apiFetch(`/api/unihack/run?evaluate=${evaluate}&use_official=true`, {
    method: "POST",
  });
  return parseJson(r);
}

export async function fetchUnihackStatus(jobId?: string): Promise<Record<string, unknown>> {
  const r = await apiFetch(jobId ? `/api/unihack/status/${jobId}` : "/api/unihack/status");
  return parseJson(r);
}

export async function fetchUnihackEvaluation(): Promise<Record<string, unknown>> {
  const r = await apiFetch("/api/unihack/evaluation");
  return parseJson(r);
}

export async function fetchUnihackRows(flaggedOnly = true): Promise<{ rows: Record<string, unknown>[] }> {
  const r = await apiFetch(`/api/unihack/rows?flagged_only=${flaggedOnly}&limit=40`);
  return parseJson(r);
}

export async function downloadUnihackExport(kind: "csv" | "xlsx"): Promise<void> {
  const r = await apiFetch(`/api/unihack/export/${kind}`);
  if (!r.ok) {
    throw new Error((await r.text()) || `UniHack export failed (${r.status})`);
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = kind === "csv" ? "unihack-delivery.csv" : "unihack-delivery.xlsx";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
