/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#0b0d12",
          raised: "#11141b",
          overlay: "#171b24",
          sunken: "#080a0e",
          border: "#222735",
          hover: "#1c2130",
        },
        accent: {
          DEFAULT: "#6d7cf5",
          hover: "#7f8cf7",
          muted: "#2b3160",
          foreground: "#f3f4ff",
        },
        ink: {
          DEFAULT: "#e7e9f0",
          muted: "#9aa1b5",
          faint: "#646b80",
        },
        danger: { DEFAULT: "#e5566b", muted: "#3a1c24" },
        warning: { DEFAULT: "#d9a441", muted: "#3a2f17" },
        success: { DEFAULT: "#43b07a", muted: "#163126" },
        info: { DEFAULT: "#4ea3d9", muted: "#16293a" },
        tg: { bg: "#0e1621", bubble: "#182533", link: "#6ab3f3", text: "#e4ecf2", meta: "#6d8399" },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: { "2xs": ["11px", "14px"] },
      borderRadius: { lg: "8px", xl: "12px", "2xl": "16px" },
      boxShadow: {
        overlay: "0 16px 48px -12px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "scale-in": { from: { opacity: "0", transform: "scale(0.97)" }, to: { opacity: "1", transform: "scale(1)" } },
        "slide-in-right": { from: { transform: "translateX(100%)" }, to: { transform: "translateX(0)" } },
        "slide-in-left": { from: { transform: "translateX(-100%)" }, to: { transform: "translateX(0)" } },
        shimmer: { "0%": { backgroundPosition: "-400px 0" }, "100%": { backgroundPosition: "400px 0" } },
      },
      animation: {
        "fade-in": "fade-in 120ms ease-out",
        "scale-in": "scale-in 140ms ease-out",
        "slide-in-right": "slide-in-right 180ms ease-out",
        "slide-in-left": "slide-in-left 180ms ease-out",
        shimmer: "shimmer 1.4s linear infinite",
      },
    },
  },
  plugins: [],
};
