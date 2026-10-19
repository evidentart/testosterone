import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', "ui-sans-serif", "system-ui", "sans-serif"]
      },
      colors: {
        // Deep navy surfaces (Vision UI-style glass dashboard); 950 is the page, 900 the card base.
        ink: {
          950: "#060b26",
          900: "#0b1437",
          850: "#111a45",
          800: "#1a2352",
          700: "#252f66",
          600: "#343f7c",
          500: "#56618f",
          400: "#7e88ae",
          300: "#a0aec0",
          200: "#cbd2e1",
          100: "#f0f3fa"
        },
        // Single brand accent: the electric blue of the icon tiles and active nav.
        brand: {
          300: "#8cbcff",
          400: "#4a9bff",
          500: "#0075ff",
          600: "#0062d6",
          700: "#004fb0"
        },
        success: {
          300: "#6ee7b7",
          400: "#34d399",
          500: "#10b981",
          600: "#059669"
        },
        danger: {
          300: "#fca5a5",
          400: "#f87171",
          500: "#ef4444",
          600: "#dc2626"
        },
        warn: {
          300: "#fcd34d",
          400: "#fbbf24",
          500: "#f59e0b"
        }
      },
      keyframes: {
        "muscle-flex": {
          "0%, 100%": { transform: "scale(1)" },
          "35%": { transform: "scale(1.12) rotate(-4deg)" },
          "65%": { transform: "scale(1.06) rotate(2deg)" }
        },
        "muscle-droop": {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(3px)" }
        }
      },
      animation: {
        "muscle-flex": "muscle-flex 900ms ease-in-out infinite",
        "muscle-droop": "muscle-droop 1.8s ease-in-out infinite"
      }
    }
  },
  plugins: []
} satisfies Config;
