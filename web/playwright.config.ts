import { defineConfig } from "@playwright/test";

// e2e runs against docker compose (make e2e brings it up and passes E2E_BASE_URL).
const baseURL = process.env.E2E_BASE_URL;
if (!baseURL) throw new Error("E2E_BASE_URL не задан: запускайте через make e2e");

export default defineConfig({
  testDir: "e2e",
  // Each /planner page loads many 3D models. Parallel browser workers exhaust memory.
  workers: 1,
  use: { baseURL },
});
