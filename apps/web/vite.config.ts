import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type Plugin } from "vite";

// Production builds set VITE_SITE_URL so social tags are absolute.
// Local dev leaves it empty and falls back to same-origin paths.
function openGraphUrls(siteUrl: string): Plugin {
  const site = siteUrl.trim().replace(/\/+$/, "");
  const image = site ? `${site}/og.png` : "/og.png";
  const url = site ? `${site}/` : "/";
  return {
    name: "open-graph-urls",
    transformIndexHtml(html) {
      return html
        .replaceAll("__OG_IMAGE__", image)
        .replaceAll("__OG_URL__", url);
    },
  };
}

export default defineConfig(({ mode }) => {
  // loadEnv also copies VITE_* from the process environment, including Docker build args.
  const fileEnv = loadEnv(mode, ".", "VITE_");
  const siteUrl = fileEnv.VITE_SITE_URL || "";
  return {
    plugins: [react(), openGraphUrls(siteUrl)],
    server: {
      proxy: {
        "/api": "http://127.0.0.1:8000",
        "/health": "http://127.0.0.1:8000",
      },
    },
  };
});
