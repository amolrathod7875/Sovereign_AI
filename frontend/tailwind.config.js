/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: {
          primary: '#0D1117',
          secondary: '#161B22',
          tertiary: '#21262D',
        },
        border: '#30363D',
        text: {
          primary: '#E6EDF3',
          secondary: '#8B949E',
        },
        accent: {
          primary: '#58A6FF',
          success: '#3FB950',
          warning: '#D29922',
          danger: '#F85149',
          sovereign: '#2EA043',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
