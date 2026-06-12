import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true, // lets Testing Library auto-cleanup between tests
    setupFiles: ["./vitest.setup.ts"],
    include: ["__tests__/**/*.test.tsx"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname) },
  },
});
