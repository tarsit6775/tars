import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        void: {
          950: '#020408',
          900: '#060b14',
          800: '#0a1020',
          700: '#0f172a',
          600: '#141e33',
        },
        nebula: {
          purple: '#6d28d9',
          blue: '#1e40af',
          cyan: '#0e7490',
          pink: '#a21caf',
        },
        star: {
          white: '#f1f5f9',
          blue: '#60a5fa',
          yellow: '#fbbf24',
          orange: '#fb923c',
        },
        thrust: {
          DEFAULT: '#f97316',
          bright: '#fb923c',
          dim: '#c2410c',
        },
        signal: {
          green: '#10b981',
          red: '#ef4444',
          amber: '#f59e0b',
          blue: '#3b82f6',
          cyan: '#06b6d4',
          purple: '#8b5cf6',
        },
        panel: {
          bg: '#0c1322',
          surface: '#111b2e',
          border: '#1a2d47',
          hover: '#162340',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'SF Mono', 'Fira Code', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'float': 'float 6s ease-in-out infinite',
        'scan': 'scan 2s linear infinite',
        'fade-in': 'fadeIn 0.3s ease forwards',
        'slide-up': 'slideUp 0.3s ease forwards',
        'typing': 'typing 1.4s infinite',
      },
      keyframes: {
        glow: {
          from: { filter: 'drop-shadow(0 0 6px rgba(6,182,212,0.3))' },
          to: { filter: 'drop-shadow(0 0 20px rgba(6,182,212,0.6))' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-8px)' },
        },
        scan: {
          '0%': { backgroundPosition: '0% 0%' },
          '100%': { backgroundPosition: '0% 100%' },
        },
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          from: { opacity: '0', transform: 'translateY(16px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        typing: {
          '0%, 100%': { opacity: '0.2' },
          '50%': { opacity: '1' },
        },
      },
      boxShadow: {
        'glow-cyan': '0 0 20px rgba(6,182,212,0.15), 0 0 40px rgba(6,182,212,0.05)',
        'glow-blue': '0 0 20px rgba(59,130,246,0.15)',
        'glow-green': '0 0 20px rgba(16,185,129,0.15)',
        'glow-red': '0 0 20px rgba(239,68,68,0.2)',
        'glow-purple': '0 0 20px rgba(139,92,246,0.15)',
        'glow-orange': '0 0 20px rgba(249,115,22,0.15)',
      },
    },
  },
  plugins: [],
} satisfies Config
