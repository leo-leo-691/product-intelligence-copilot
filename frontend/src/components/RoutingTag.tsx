import { Link } from "react-router-dom";

type Props = {
  sku: string;
  category: string;
  to?: string;
  active?: boolean;
  flagged?: boolean;
  onClick?: () => void;
  className?: string;
};

/** Routing tag — product as a hang-tag with hole punch. */
export default function RoutingTag({ sku, category, to, active, flagged, onClick, className }: Props) {
  const body = (
    <div
      className={[
        "relative flex min-h-[4.5rem] flex-col justify-center border border-rule-line bg-paper pl-7 pr-3 py-2",
        active ? "border-ink ring-1 ring-ink" : "hover:border-ink/60",
        className ?? "",
      ].join(" ")}
    >
      {/* hole punch */}
      <span
        className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border border-rule-line bg-paper shadow-[inset_0_0_0_1px_var(--rule-line)]"
        aria-hidden
      />
      {/* string hint */}
      <span
        className="absolute left-[0.85rem] top-0 h-1/2 w-px -translate-x-1/2 border-l border-dashed border-rule-line"
        aria-hidden
      />
      <p className="font-mono text-sm font-medium text-ink truncate">{sku}</p>
      <p className="mt-0.5 font-sans text-[11px] uppercase tracking-label text-ink-soft truncate">{category}</p>
      {flagged && (
        <p className="mt-1 font-display text-[10px] uppercase tracking-stencil text-stamp-flagged">Unresolved</p>
      )}
    </div>
  );

  if (to) {
    return (
      <Link to={to} onClick={onClick} className="block focus-visible:outline-offset-4">
        {body}
      </Link>
    );
  }
  return body;
}
