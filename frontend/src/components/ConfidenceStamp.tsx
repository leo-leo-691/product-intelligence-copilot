import type { CSSProperties } from "react";
import type { ConfidenceBand } from "../api";

type StampKind =
  | "approved"
  | "rejected"
  | "edited"
  | "high"
  | "medium"
  | "low"
  | "flagged"
  | "review"
  | "live"
  | "down";

const LABEL: Record<StampKind, string> = {
  approved: "APPROVED",
  rejected: "REJECTED",
  edited: "EDITED",
  high: "HIGH",
  medium: "MEDIUM",
  low: "LOW",
  flagged: "FLAGGED",
  review: "REVIEW",
  live: "LIVE",
  down: "DOWN",
};

const COLOR: Record<StampKind, string> = {
  approved: "text-stamp-approved border-stamp-approved",
  rejected: "text-stamp-flagged border-stamp-flagged",
  edited: "text-stamp-review border-stamp-review",
  high: "text-ink border-ink",
  medium: "text-stamp-review border-stamp-review",
  low: "text-ink-soft border-ink-soft",
  flagged: "text-stamp-flagged border-stamp-flagged",
  review: "text-stamp-review border-stamp-review",
  live: "text-stamp-approved border-stamp-approved",
  down: "text-stamp-flagged border-stamp-flagged",
};

const ROT: Record<StampKind, string> = {
  approved: "-4deg",
  rejected: "-5deg",
  edited: "-3deg",
  high: "-4deg",
  medium: "-3deg",
  low: "-5deg",
  flagged: "-5deg",
  review: "-3deg",
  live: "-6deg",
  down: "-5deg",
};

/** Confidence band only — never maps High → APPROVED (that is human review_status). */
export function bandToStamp(
  band: ConfidenceBand,
  opts?: { notFound?: boolean; conflicted?: boolean }
): StampKind {
  if (opts?.notFound || opts?.conflicted) return "flagged";
  if (band === "High") return "high";
  if (band === "Medium") return "medium";
  return "low";
}

export function reviewStatusToStamp(
  reviewStatus?: string,
  band?: ConfidenceBand,
  opts?: { notFound?: boolean; conflicted?: boolean }
): StampKind {
  const status = (reviewStatus || "pending").toLowerCase();
  if (status === "approved") return "approved";
  if (status === "rejected") return "rejected";
  if (status === "edited") return "edited";
  if (band) return bandToStamp(band, opts);
  if (opts?.notFound || opts?.conflicted) return "flagged";
  return "review";
}

type Props = {
  kind?: StampKind;
  band?: ConfidenceBand;
  notFound?: boolean;
  conflicted?: boolean;
  reviewStatus?: string;
  title?: string;
  compact?: boolean;
  animate?: boolean;
};

/** Rubber-stamp confidence / status marker — tactile edge, flat print colors. */
export default function ConfidenceStamp({
  kind,
  band,
  notFound,
  conflicted,
  reviewStatus,
  title,
  compact,
  animate = true,
}: Props) {
  const resolved: StampKind =
    kind ?? reviewStatusToStamp(reviewStatus, band, { notFound, conflicted });
  const rot = ROT[resolved];
  const style = {
    ["--stamp-rot" as string]: rot,
    transform: `rotate(${rot})`,
    borderRadius: "2px",
    filter: "url(#stamp-rough)",
  } as CSSProperties;

  return (
    <span
      className={[
        "stamp-mark inline-flex select-none items-center justify-center border-2 font-display font-semibold uppercase tracking-stencil",
        COLOR[resolved],
        compact ? "px-1.5 py-0.5 text-[9px] leading-none" : "px-2.5 py-1 text-[11px] leading-none sm:text-xs",
        animate ? "animate-stamp" : "",
      ].join(" ")}
      style={style}
      title={title}
      aria-label={`Stamp: ${LABEL[resolved]}`}
    >
      {LABEL[resolved]}
    </span>
  );
}

/** Shared SVG filter defs — mount once near app root. */
export function StampFilterDefs() {
  return (
    <svg width="0" height="0" className="absolute" aria-hidden>
      <defs>
        <filter id="stamp-rough">
          <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="2" result="noise" />
          <feDisplacementMap
            in="SourceGraphic"
            in2="noise"
            scale="1.2"
            xChannelSelector="R"
            yChannelSelector="G"
          />
        </filter>
      </defs>
    </svg>
  );
}
