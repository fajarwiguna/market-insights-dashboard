import type { Config } from "tailwindcss";

export default {
  content: ["./src/app/equity-snapshot/**/*.{ts,tsx}"],
  prefix: "eq-",
  corePlugins: { preflight: false },
  theme: { extend: {} },
  plugins: [],
} satisfies Config;
