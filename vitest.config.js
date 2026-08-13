import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    environmentMatchGlobs: [["**/*.test.jsx", "jsdom"]],
    exclude: [
      "**/node_modules/**",
      "**/dist/**",
      "**/.worktrees/**",
      "**/tests/e2e/**",
    ],
  },
});
