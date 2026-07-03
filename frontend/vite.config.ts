import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  base: "./",
  css: {
    postcss: "./postcss.config.cjs",
  },
  server: {
    port: 5173,
    strictPort: true,
  },
});
