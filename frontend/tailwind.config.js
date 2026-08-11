/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "rgb(var(--paper-rgb) / <alpha-value>)",
        "paper-dim": "rgb(var(--paper-dim-rgb) / <alpha-value>)",
        ink: "rgb(var(--ink-rgb) / <alpha-value>)",
        "ink-soft": "rgb(var(--ink-soft-rgb) / <alpha-value>)",
        "stamp-approved": "rgb(var(--stamp-approved-rgb) / <alpha-value>)",
        "stamp-flagged": "rgb(var(--stamp-flagged-rgb) / <alpha-value>)",
        "stamp-review": "rgb(var(--stamp-review-rgb) / <alpha-value>)",
        "rule-line": "rgb(var(--rule-line-rgb) / <alpha-value>)",
      },
      fontFamily: {
        display: ['"Oswald"', "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
        sans: ['"IBM Plex Sans"', "sans-serif"],
      },
      borderRadius: {
        dossier: "3px",
      },
      letterSpacing: {
        stencil: "0.12em",
        label: "0.08em",
      },
      keyframes: {
        stampIn: {
          "0%": { transform: "scale(1.35) rotate(-12deg)", opacity: "0" },
          "70%": { transform: "scale(0.96) rotate(-4deg)", opacity: "1" },
          "100%": { transform: "scale(1) rotate(var(--stamp-rot, -4deg))", opacity: "1" },
        },
      },
      animation: {
        stamp: "stampIn 180ms ease-out both",
      },
    },
  },
  plugins: [],
};
