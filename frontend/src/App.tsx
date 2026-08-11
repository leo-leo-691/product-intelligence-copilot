import { Link, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";
import { fetchHealth, HealthInfo } from "./api";
import DashboardPage from "./pages/Dashboard";
import ReviewPage from "./pages/Review";
import UploadPage from "./pages/Upload";

export default function App() {
  const [health, setHealth] = useState<HealthInfo | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_#0f1f1a_0%,_#0b1220_45%,_#070b14_100%)] text-slate-100">
      <header className="border-b border-slate-800/80 bg-slate-950/70 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-lg font-semibold tracking-tight text-emerald-400">
            Product Intelligence Copilot
          </Link>
          <nav className="flex items-center gap-4 text-sm text-slate-300">
            <Link to="/upload" className="hover:text-white">
              Ingest
            </Link>
            <Link to="/review" className="hover:text-white">
              Review
            </Link>
            <Link to="/dashboard" className="hover:text-white">
              Dashboard
            </Link>
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${
                health?.status === "ok"
                  ? "border-emerald-800 text-emerald-400"
                  : "border-red-800 text-red-400"
              }`}
              title={
                health
                  ? `LLM: ${health.anthropic_configured ? "on" : "off"} · Search: ${
                      health.web_search_configured ? "on" : "off"
                    }`
                  : "API unreachable"
              }
            >
              {health?.status === "ok" ? "API ok" : "API down"}
            </span>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/review/:id" element={<ReviewPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </main>
    </div>
  );
}
