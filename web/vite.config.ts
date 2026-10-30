import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base so the build works from a GitHub Pages project URL.
export default defineConfig({ plugins: [react()], base: "./" });
