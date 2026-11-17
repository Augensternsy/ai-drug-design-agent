import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "localhost", port: 3000, strictPort: true,
    proxy: { "/api": { target: "https://bianjilong.tailb99a04.ts.net", changeOrigin: true, secure: true } },
  },
  preview: { host: "localhost", port: 3000, strictPort: true },
});
