/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        base: {
          950: "#08090d",
          900: "#0e1015",
          850: "#12141b",
          800: "#181b24",
          700: "#232733",
          600: "#31374a",
        },
        accent: {
          400: "#7c9cff",
          500: "#5b7cfa",
          600: "#4560db",
        },
      },
      boxShadow: {
        soft: "0 1px 0 rgba(255,255,255,0.04) inset, 0 8px 30px rgba(0,0,0,0.35)",
      },
    },
  },
  plugins: [],
};
