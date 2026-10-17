import { defineConfig } from "vite";

// Relative base so the same build runs at a domain root, under a sub-path, or as an
// Artifact preview. The data bundle (public/data, public/geo) comes from `make atlas`
// via scripts/link-data.mjs and is never committed.
//
// Two builds:
//   npm run build           the website (dist/), with the Supabase settings from .env.production
//   npm run build:preview   a no-login preview for a claude.ai artifact (dist-preview/): one
//                           classic script, no account code, since the artifact sandbox
//                           cannot reach Supabase anyway
export default defineConfig(({ mode }) => ({
  base: "./",
  build: {
    outDir: mode === "preview" ? "dist-preview" : "dist",
    emptyOutDir: true,
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 900,
    rollupOptions: mode === "preview"
      ? { output: { format: "iife", inlineDynamicImports: true, entryFileNames: "assets/atlas.js" } }
      : {},
  },
  server: { fs: { allow: [".."] } },
}));
