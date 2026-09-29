import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: 2,
  retries: 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"], defaultBrowserType: "chromium" } },
  ],
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: false,
    timeout: 120000,
    env: {
      NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8100",
      NEXT_PUBLIC_FIREBASE_API_KEY: "raseed-browser-test",
      NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: "raseed-test.firebaseapp.com",
      NEXT_PUBLIC_FIREBASE_PROJECT_ID: "raseed-test",
      NEXT_PUBLIC_FIREBASE_APP_ID: "raseed-browser-test-app",
    },
  },
});
