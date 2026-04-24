/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Courier New', 'monospace'],
        display: ['Orbitron', 'sans-serif'],
        body: ['Share Tech', 'sans-serif'],
      },
      colors: {
        neon: {
          green: '#00ff9d',
          cyan: '#00e5ff',
          blue: '#0080ff',
          red: '#ff003c',
          yellow: '#ffcc00',
        },
        dark: {
          900: '#020408',
          800: '#060d12',
          700: '#0a1520',
          600: '#0e1e2e',
          500: '#12273c',
          400: '#1a3a54',
          300: '#234d6e',
        }
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'scan': 'scan 3s linear infinite',
        'fadeIn': 'fadeIn 0.4s ease-out',
        'slideUp': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px #00ff9d33, 0 0 10px #00ff9d22' },
          '100%': { boxShadow: '0 0 10px #00ff9d66, 0 0 20px #00ff9d44, 0 0 30px #00ff9d22' },
        },
        scan: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        }
      }
    },
  },
  plugins: [],
}
