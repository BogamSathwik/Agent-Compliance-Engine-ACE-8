/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        cream: {
          50: '#FAF9F5',
          100: '#F5F4EE',
          200: '#EAE8DE',
          300: '#DEDBD0',
        },
        sage: {
          50: '#F2F6F3',
          100: '#E3ECE5',
          200: '#C7D9CA',
          300: '#A4C0AA',
          400: '#7E9F85',
          500: '#5C715E',
          600: '#4E6150',
          700: '#3D4D3F',
          800: '#2F3B30',
        },
        charcoal: {
          50: '#F5F6F6',
          100: '#E4E6E5',
          200: '#C5C9C7',
          300: '#9BA29F',
          400: '#6E7773',
          500: '#4E5753',
          600: '#3C4340',
          700: '#2E3532',
          800: '#242927',
          900: '#1A1E1C',
        },
        borderMuted: '#E2E4DE',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
