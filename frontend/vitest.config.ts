import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

/**
 * Test configuration.
 *
 * Kept separate from `vite.config.ts` so the dev server settings (port, proxy)
 * are not dragged into the test environment.  jsdom is used because the auth
 * code touches `window.location`, `sessionStorage` and `fetch`.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    coverage: {
      provider: "v8",
      include: ["src/auth/**", "src/api/**", "src/components/IdentityPanel.tsx"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**"],
    },
  },
});
