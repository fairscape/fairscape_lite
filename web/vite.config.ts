import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built app is served by the lite server itself under /ui/, so the API
// owns the origin root (/rocrate, /search, /ark:..., /evidencegraph) and
// client routes can never collide with it. In dev, vite serves /ui/ and
// proxies those API prefixes to a locally running `uvicorn app:app`.
export default defineConfig({
  plugins: [react()],
  base: "/ui/",
  server: {
    proxy: Object.fromEntries(
      ["/rocrate", "/entity", "/identifier", "/search", "/evidencegraph", "/ark:"].map(
        (prefix) => [prefix, { target: "http://localhost:8000", changeOrigin: true }],
      ),
    ),
  },
});
