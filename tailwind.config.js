/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './static/js/**/*.js',
    './accounts/**/*.py',
    './naissances/**/*.py',
  ],
  theme: {
    extend: {},
  },
  corePlugins: {
    preflight: false,
  },
  plugins: [require('daisyui')],
  daisyui: {
    themes: [
      {
        gestcivil: {
          'primary': '#1f6fa8',
          'primary-content': '#ffffff',
          'secondary': '#2f7d5a',
          'secondary-content': '#ffffff',
          'accent': '#d38b38',
          'accent-content': '#ffffff',
          'neutral': '#1f2f3d',
          'neutral-content': '#f5fbff',
          'base-100': '#f7fbff',
          'base-200': '#edf4fb',
          'base-300': '#dde8f3',
          'base-content': '#1f3448',
          'info': '#2b7fb7',
          'success': '#2f7d5a',
          'warning': '#b8732e',
          'error': '#b35a5a',
        },
      },
      'corporate',
      'light',
    ],
    logs: false,
  },
}
