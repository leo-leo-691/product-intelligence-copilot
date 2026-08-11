import type { CSSProperties } from "react";
import type { ConfidenceBand } from "../api";

type StampKind = "approved" | "flagged" | "review" | "live" | "down";

const LABEL: Record<StampKind, string> = {
  approved: "APPROVED",
  flagged: "FLAGGED",
  review: "REVIEW",
  live: "LIVE",
  down: "DOWN",
};

const COLOR: Record<StampKind, string> = {
  approved: "text-stamp-approved border-stamp-approved",
  flagged: "text-stamp-flagged border-stamp-flagged",
  review: "text-stamp-review border-stamp-review",
  live: "text-stamp-approved border-stamp-approved",
  down: "text-stamp-flagged border-stamp-flagged",
};

const ROT: Record<StampKind, string> = {
  approved: "-4deg",
  flagged: "-5deg",
  review: "-3deg",
  live: "-6deg",
  down: "-5deg",
};

export function bandToStamp(
  band: ConfidenceBand,
  opts?: { notFound?: boolean; needsReview?: boolean }
): StampKind {
  if (opts?.notFound) return "flagged";
  if (band === "High") return "approved";
  if (band === "Medium") return "review";
  return "flagged";
}

type Props = {
  kind?: StampKind;
  band?: ConfidenceBand;
  notFound?: boolean;
  needsReview?: boolean;
  title?: string;
  compact?: boolean;
  animate?: boolean;
};

/** Rubber-stamp confidence / status marker — tactile edge, flat print colors. */
export default function ConfidenceStamp({
  kind,
  band,
  notFound,
  needsReview,
  title,
  compact,
  animate = true,
}: Props) {
  const resolved: StampKind =
    kind ?? (band ? bandToStamp(band, { notFound, needsReview }) : "review");
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
