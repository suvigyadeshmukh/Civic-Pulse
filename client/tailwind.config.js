/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        civic: {
          ink: '#0B1F3A',
          inkLight: '#16324F',
          teal: '#0F766E',
          tealLight: '#14B8A6',
          saffron: '#E8871E',
          saffronLight: '#F6AD55',
          parchment: '#F7F5F0',
          mist: '#EEF2F6',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          '"Noto Sans"',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'sans-serif',
        ],
      },
      boxShadow: {
        soft: '0 18px 50px -24px rgba(11, 31, 58, 0.28)',
        lift: '0 26px 60px -30px rgba(11, 31, 58, 0.38)',
      },
      backgroundImage: {
        'grid-civic':
          'linear-gradient(to right, rgba(11, 31, 58, 0.045) 1px, transparent 1px), linear-gradient(to bottom, rgba(11, 31, 58, 0.045) 1px, transparent 1px)',
      },
      backgroundSize: {
        'grid-civic': '32px 32px',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 500ms ease-out both',
      },
    },
  },
  plugins: [],
};
