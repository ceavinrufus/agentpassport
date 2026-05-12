import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts", "../../tests/cross-sdk/*.test.ts"],
  },
});
