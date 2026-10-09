/** @type {import('tailwindcss').Config} */
const token = name => `rgb(var(--color-${name}) / <alpha-value>)`

export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // Every color is a theme token from src/style.css (see DESIGN_SPEC.md).
      colors: {
        // Surfaces, darkest to lightest.
        background: token('background'),
        sidebar: token('sidebar'),
        surface: token('surface'),
        'surface-2': token('surface-2'),
        'surface-3': token('surface-3'),
        // Hairlines.
        line: token('line'),
        'line-strong': token('line-strong'),
        // Text, strongest to weakest.
        ink: token('ink'),
        muted: token('muted'),
        subtle: token('subtle'),
        faint: token('faint'),
        // Accent.
        accent: token('accent'),
        'accent-glow': token('accent-glow'),
        'on-accent': token('on-accent'),
        // Status.
        success: token('success'),
        warning: token('warning'),
        danger: token('danger'),
        info: token('info'),
        star: token('star'),
      },
    },
  },
  plugins: [],
}
