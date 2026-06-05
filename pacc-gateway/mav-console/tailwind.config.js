/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        "mav-black": "#020205",
        "mav-dark": "#0a0a15",
        "mav-blue": "#00A3FF",
        "mav-chrome": "#d8f3ff",
        "mav-alert": "#ff2b45",
        "neon-green": "#25ff8a",
      },
      boxShadow: {
        "glow-mav": "0 0 14px rgba(0, 163, 255, 0.45)",
        "glow-alert": "0 0 14px rgba(255, 43, 69, 0.45)",
      },
    },
  },
  plugins: [],
};
