/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#F7F8FA",
          surface: "#FFFFFF",
          muted: "#F1F3F6",
        },
        ink: {
          DEFAULT: "#0F172A",
          soft: "#334155",
          muted: "#64748B",
          faint: "#94A3B8",
        },
        line: {
          DEFAULT: "#E2E8F0",
          soft: "#EEF1F5",
        },
        sidebar: {
          DEFAULT: "#0B1220",
          hover: "#111A2E",
          active: "#1B2742",
          text: "#CBD5E1",
          textMuted: "#64748B",
        },
        brand: {
          DEFAULT: "#D4001A",
          hover: "#B30016",
          soft: "#FEE2E5",
        },
        status: {
          ok: "#16A34A",
          okSoft: "#DCFCE7",
          warn: "#D97706",
          warnSoft: "#FEF3C7",
          err: "#DC2626",
          errSoft: "#FEE2E2",
          info: "#2563EB",
          infoSoft: "#DBEAFE",
          neutral: "#64748B",
          neutralSoft: "#F1F5F9",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgba(15, 23, 42, 0.04), 0 1px 3px 0 rgba(15, 23, 42, 0.06)",
        cardHover: "0 4px 12px -2px rgba(15, 23, 42, 0.08)",
      },
      borderRadius: {
        xl: "12px",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
      },
      animation: {
        "fade-in": "fade-in 200ms ease-out",
      },
    },
  },
  plugins: [],
};
