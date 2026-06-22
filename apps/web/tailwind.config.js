/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        runtime: {
          bg: '#0d1117',
          panel: '#161b22',
          border: '#30363d',
          accent: '#58a6ff',
          warn: '#d29922',
          ok: '#3fb950',
          err: '#f85149',
          muted: '#8b949e',
        },
      },
    },
  },
  plugins: [],
}
