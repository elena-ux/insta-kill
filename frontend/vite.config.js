import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  base: "/search/",
  server: {
    proxy: {
      "/search": {
        target: "http://127.0.0.1:8010",
        bypass(req) {
          if (
            req.headers.accept?.includes("text/html") ||
            req.url.startsWith("/search/")
          )
            return req.url;
        },
      },
      "/feed": "http://127.0.0.1:8010",
      "/dataset": "http://127.0.0.1:8010",
      "/posts": "http://127.0.0.1:8010",
      "/health": "http://127.0.0.1:8010",
    },
  },
});
