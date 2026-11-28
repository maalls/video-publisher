// Pilot build: one JS + one CSS file (ui.js / ui.css) + index.html in ../web/ui, served by ../server.py under /ui/.
// react, tailwind, vite and lucide come from ../node_modules (shared with the YABBE frontend checkout).
import path from "node:path"
import { fileURLToPath } from "node:url"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

const here = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  root: here,
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.join(here, "src"), "@maskedit": path.join(here, "..", "src") },
    dedupe: ["react", "react-dom"],
  },
  build: {
    outDir: path.join(here, "..", "web", "ui"),
    emptyOutDir: true,
    rollupOptions: {
      input: path.join(here, "index.html"),
      output: { entryFileNames: "ui.js", chunkFileNames: "ui-[name].js", assetFileNames: "ui[extname]" },
    },
  },
})
