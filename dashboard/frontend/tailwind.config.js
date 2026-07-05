/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'friend': {
          'running': '#22c55e',
          'error': '#ef4444',
          'stopped': '#9ca3af',
        }
      }
    },
  },
  plugins: [],
}
