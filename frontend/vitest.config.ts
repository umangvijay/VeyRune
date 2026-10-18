import { defineConfig } from "vitest/config";

// Unit tests live in tests/; e2e/*.spec.ts belongs to Playwright.
export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    exclude: ["e2e/**", "node_modules/**", ".next/**"],
    environment: "happy-dom",
  },
});
