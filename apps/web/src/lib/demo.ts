export const DEMO_TOKEN = "raseed-local-demo-v1";

export function localDemoEnabled(): boolean {
  return process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_LOCAL_DEMO === "true";
}

export function demoToken(): string {
  if (!localDemoEnabled() || typeof window === "undefined" ||
      !["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname)) {
    throw new Error("Local demo is available only on localhost in development.");
  }
  const api = new URL(process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000");
  if (api.protocol !== "http:" || !["localhost", "127.0.0.1", "[::1]"].includes(api.hostname) || api.username || api.password) {
    throw new Error("Local demo requires a loopback HTTP API.");
  }
  return DEMO_TOKEN;
}
