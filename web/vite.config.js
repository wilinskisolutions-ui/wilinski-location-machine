import { defineConfig } from "vite";

// Relative base so the same build runs at a domain root, under a sub-path, or as an
// Artifact preview. The data bundle (public/data, public/geo) comes from `make atlas`
// via scripts/link-data.mjs and is never committed.
export default defineConfig({
  base: "./",
  build: { outDir: "dist", emptyOutDir: true, assetsInlineLimit: 0, chunkSizeWarningLimit: 900 },
  server: { fs: { allow: [".."] } },
});
