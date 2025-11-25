/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#131314', // Google AI Studio dark bg
        surface: '#1e1f20',
        primary: '#a8c7fa',
        secondary: '#444746',
        accent: '#669df6',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['Fira Code', 'monospace'],
      }
    },
  },
  plugins: [],
}