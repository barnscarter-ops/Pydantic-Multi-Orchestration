/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        "mav-black":      "#020205",
        "mav-deep":       "#050509",
        "mav-dark":       "#0b0b18",
        "mav-panel":      "#0d0d1f",
        "mav-blue":       "#00C2FF",
        "mav-blue-dim":   "#005580",
        "mav-amber":      "#C47800",
        "mav-amber-glow": "#FF9A00",
        "mav-chrome":     "#C4C8D4",
        "mav-chrome-dim": "#545870",
        "mav-alert":      "#FF003C",
        "neon-green":     "#00FF88",
      },
      boxShadow: {
        "glow-mav":       "0 0 6px rgba(0,194,255,0.5), 0 0 20px rgba(0,194,255,0.18)",
        "glow-mav-lg":    "0 0 10px rgba(0,194,255,0.7), 0 0 35px rgba(0,194,255,0.25), inset 0 0 20px rgba(0,194,255,0.04)",
        "glow-alert":     "0 0 6px rgba(255,0,60,0.55),  0 0 20px rgba(255,0,60,0.2)",
        "glow-amber":     "0 0 6px rgba(196,120,0,0.6),  0 0 20px rgba(196,120,0,0.2)",
        "glow-green":     "0 0 6px rgba(0,255,136,0.55), 0 0 20px rgba(0,255,136,0.2)",
        "inner-mav":      "inset 0 0 30px rgba(0,194,255,0.04)",
      },
      animation: {
        "spin-slow":    "spin-slow 12s linear infinite",
        "flicker":      "flicker 8s step-end infinite",
        "scan":         "scan 6s linear infinite",
      },
      keyframes: {
        "spin-slow": {
          "0%":   { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
        "flicker": {
          "0%,100%": { opacity: "1" },
          "92%":     { opacity: "1" },
          "93%":     { opacity: "0.7" },
          "94%":     { opacity: "1" },
          "96%":     { opacity: "0.85" },
          "97%":     { opacity: "1" },
        },
        "scan": {
          "0%":   { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100vh)" },
        },
      },
    },
  },
  plugins: [],
};
