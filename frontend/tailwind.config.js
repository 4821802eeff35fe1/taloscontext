/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#0b0e14",
          raised: "#11141d",
          overlay: "#161a26",
          border: "#232838",
        },
        accent: {
          DEFAULT: "#5b7cfa",
          muted: "#3d4a7a",
          foreground: "#eef1ff",
        },
        ink: {
          DEFAULT: "#e6e8ef",
          muted: "#9aa3b8",
          faint: "#6b7389",
        },
        danger: "#e5566b",
        warning: "#d9a441",
        success: "#49b67d",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      borderRadius: {
        lg: "10px",
        xl: "14px",
      },
    },
  },
  plugins: [],
};
