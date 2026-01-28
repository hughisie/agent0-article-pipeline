module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "bg-dark": "#0b0f17",
        "card-dark": "#121826",
        "accent": "#6ee7ff",
        "accent-2": "#f6c177"
      },
      fontFamily: {
        display: ["'Space Grotesk'", "system-ui", "sans-serif"],
        body: ["'Source Sans 3'", "system-ui", "sans-serif"]
      }
    }
  },
  plugins: [],
};
