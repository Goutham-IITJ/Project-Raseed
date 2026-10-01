import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

if (!process.env.DEMO_E2E_DATABASE_URL) throw new Error("Set DEMO_E2E_DATABASE_URL to an isolated loopback *_demo database.");
const root = resolve(__dirname, "../..");
const python = resolve(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
export const backendEnv = {
  APP_ENV: "development", LOCAL_DEMO: "true",
  DATABASE_URL: process.env.DEMO_E2E_DATABASE_URL,
  LOCAL_STORAGE_PATH: resolve(root, ".local/demo-e2e-receipts"),
  STORAGE_PROVIDER: "local", CORS_ORIGINS: '["http://127.0.0.1:3101"]',
};

export default defineConfig({
  globalSetup: "./demo-e2e/setup.ts",
  testDir: "./demo-e2e", fullyParallel: false, workers: 1, retries: 0, reporter: "list",
  outputDir: "./test-results/demo",
  use: { baseURL: "http://127.0.0.1:3101", trace: "retain-on-failure" },
  projects: [
    { name: "demo-desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "demo-mobile", use: { ...devices["Pixel 7"], defaultBrowserType: "chromium" } },
  ],
  webServer: [
    { command: `"${python}" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8101 --no-proxy-headers`, cwd: root, url: "http://127.0.0.1:8101/health", timeout: 60000, env: backendEnv },
    { command: "npm run dev -- --hostname 127.0.0.1 --port 3101", url: "http://127.0.0.1:3101", timeout: 120000, env: {
      RASEED_WEB_TEST: "demo",
      NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8101", NEXT_PUBLIC_LOCAL_DEMO: "true",
      NEXT_PUBLIC_FIREBASE_API_KEY: "", NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: "",
      NEXT_PUBLIC_FIREBASE_PROJECT_ID: "", NEXT_PUBLIC_FIREBASE_APP_ID: "",
    } },
  ],
});
