/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Warm, appetizing palette — not a generic admin grey.
        cream: '#fbf7f0',
        paper: '#fffdf9',
        ember: '#c1502e',
        emberDark: '#9d3f22',
        herb: '#5b7052',
        bark: '#3d342c',
        muted: '#8a7f72',
      },
      fontFamily: {
        display: ['ui-serif', 'Georgia', 'Cambria', 'serif'],
        body: ['ui-sans-serif', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
