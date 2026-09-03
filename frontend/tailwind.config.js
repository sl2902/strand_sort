/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Fraunces", "ui-serif", "Georgia", "serif"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        cream: {
          50: "#FFFDFA",
          100: "#FBF3E7",
          200: "#F4E6D2",
          300: "#EBD5B5",
        },
        ink: {
          700: "#4A3B2E",
          800: "#332921",
          900: "#221B15",
        },
        terracotta: {
          50: "#FDF1EC",
          100: "#FADFD3",
          300: "#F0A487",
          400: "#E97F5B",
          500: "#E2572B",
          600: "#C74521",
          700: "#A3371A",
        },
        plum: {
          100: "#EFE1EC",
          300: "#C79AC0",
          500: "#8A4A80",
          600: "#6E3A67",
          700: "#5B2F55",
        },
        saffron: {
          100: "#FDF0D6",
          300: "#F5CA75",
          400: "#F0A93A",
          500: "#DE9424",
          600: "#B8781A",
        },
        success: {
          100: "#E1EFE4",
          400: "#5A9E6F",
          500: "#3F8455",
          600: "#2F6941",
        },
        danger: {
          100: "#FBE4E1",
          400: "#D96B57",
          500: "#C24B34",
          600: "#A23A26",
        },
      },
      boxShadow: {
        soft: "0 2px 10px -2px rgba(51, 41, 33, 0.08), 0 1px 2px -1px rgba(51, 41, 33, 0.06)",
        lift: "0 12px 28px -8px rgba(51, 41, 33, 0.18)",
      },
      keyframes: {
        "pop-in": {
          "0%": { opacity: "0", transform: "scale(0.85)" },
          "60%": { opacity: "1", transform: "scale(1.03)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-out-collapse": {
          "0%": { opacity: "1", maxHeight: "600px", transform: "scale(1)" },
          "60%": { opacity: "0", maxHeight: "600px", transform: "scale(0.97)" },
          "100%": { opacity: "0", maxHeight: "0px", transform: "scale(0.97)", marginBottom: "0px", paddingTop: "0px", paddingBottom: "0px" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "ring-pulse": {
          "0%": { boxShadow: "0 0 0 0 rgba(226, 87, 43, 0.35)" },
          "100%": { boxShadow: "0 0 0 14px rgba(226, 87, 43, 0)" },
        },
      },
      animation: {
        "pop-in": "pop-in 0.45s cubic-bezier(0.16, 1, 0.3, 1) both",
        "fade-up": "fade-up 0.35s ease-out both",
        "fade-out-collapse": "fade-out-collapse 0.4s ease-in both",
        shimmer: "shimmer 1.6s linear infinite",
        "ring-pulse": "ring-pulse 1.4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};
