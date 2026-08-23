import { Link, NavLink, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";
import { fetchHealth, HealthInfo } from "./api";
import ConfidenceStamp, { StampFilterDefs } from "./components/ConfidenceStamp";
import DashboardPage from "./pages/Dashboard";
import EvaluationPage from "./pages/Evaluation";
import ReviewPage from "./pages/Review";
import UploadPage from "./pages/Upload";

export default function App() {
  const [health, setHealth] = useState<HealthInfo | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  const navClass = ({ isActive }: { isActive: boolean }) =>
    [
      "font-mono text-[11px] uppercase tracking-label transition-colors",
      isActive ? "text-ink border-b border-ink pb-0.5" : "text-ink-soft hover:text-ink",
    ].join(" ");

  return (
    <div className="min-h-screen bg-paper text-ink">
      <StampFilterDefs />
      <header className="border-b border-rule-line bg-paper">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link to="/" className="font-display text-lg font-semibold uppercase tracking-stencil text-ink sm:text-xl">
            Product Intelligence Copilot
          </Link>
          <nav className="flex flex-wrap items-center gap-4 sm:gap-5">
            <NavLink to="/upload" className={navClass}>
              Ingest
            </NavLink>
            <NavLink to="/review" className={navClass}>
              Review
            </NavLink>
            <NavLink to="/dashboard" className={navClass}>
              Dashboard
            </NavLink>
            <NavLink to="/evaluation" className={navClass}>
              Evaluation
            </NavLink>
            <span
              title={
                health
                  ? `LLM (${health.llm_provider ?? "gemini"}): ${
                      (health.llm_configured ?? health.anthropic_configured) ? "on" : "off"
                    } · Search: ${health.web_search_configured ? "on" : "off"}`
                  : "API unreachable"
              }
            >
              <ConfidenceStamp
                kind={health?.status === "ok" ? "live" : "down"}
                compact
                animate={false}
              />
            </span>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/review/:id" element={<ReviewPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
        </Routes>
      </main>
    </div>
  );
}
