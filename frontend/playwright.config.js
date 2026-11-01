import { defineConfig } from "@playwright/test";
import path from "node:path";
const evidenceDirectory =
  process.env.INSTAKILL_EVIDENCE_DIR ||
  `../docs/evidence/browser-runs/${new Date().toISOString().replace(/[:.]/g, "-")}`;
process.env.INSTAKILL_EVIDENCE_DIR = evidenceDirectory;
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  timeout: 120000,
  use: {
    baseURL: process.env.INSTAKILL_URL || "http://127.0.0.1:8010",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : {},
  },
  reporter: [
    ["list"],
    [
      "json",
      { outputFile: path.join(evidenceDirectory, "browser-tests.json") },
    ],
  ],
});
