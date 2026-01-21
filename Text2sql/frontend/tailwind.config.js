/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./**/*.{js,ts,jsx,tsx}", // 覆盖根目录文件
  ],
  theme: {
    extend: {
      colors: {
        background: '#131314', // Google AI Studio Dark
        surface: '#1E1F20',
        primary: '#A8C7FA',
        secondary: '#444746',
        accent: '#669DF6',
        text: '#E3E3E3',
        subtext: '#C4C7C5'
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      }
    },
  },
  plugins: [
    require('@tailwindcss/typography'), // 需要 npm install -D @tailwindcss/typography
  ],
}