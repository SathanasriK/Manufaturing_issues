/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          900: '#0f1729',
          800: '#152035',
          700: '#1a2844',
          600: '#1e3054',
        }
      }
    },
  },
  plugins: [],
}
