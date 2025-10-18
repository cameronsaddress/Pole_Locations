/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#003B5C',  // Dark navy blue (Verizon compatible, professional)
          light: '#00A1DE',    // Light blue for data visualization
          foreground: '#FFFFFF',
        },
        secondary: {
          DEFAULT: '#5A6C7D',  // Neutral gray-blue
          foreground: '#FFFFFF',
        },
        accent: '#CD040B',     // Verizon red - ONLY for accents, borders, logo (not full tiles)
        success: '#00A82D',    // Green for approved
        warning: '#FF9800',    // Amber for review
        danger: '#CD040B',     // Verizon red for critical alerts
        info: '#00A1DE',       // Light blue for info
        background: '#F5F5F5', // Light neutral gray
        foreground: '#1E293B', // Dark text
        card: '#FFFFFF',       // White cards
        'card-foreground': '#1E293B',
        border: '#E0E0E0',     // Light gray border
        muted: '#757575',      // Mid gray
        'muted-foreground': '#9E9E9E',
      },
      fontFamily: {
        sans: ['Geist', 'system-ui', 'sans-serif'],
        mono: ['Geist Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
