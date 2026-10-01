import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Browser suites own their output and can run beside the local demo.
  distDir: process.env.RASEED_WEB_TEST === "product" ? ".next-product-test" : process.env.RASEED_WEB_TEST === "demo" ? ".next-demo-test" : ".next",
};

export default function config(phase: string): NextConfig {
  if (process.env.NEXT_PUBLIC_LOCAL_DEMO === "true" && phase !== PHASE_DEVELOPMENT_SERVER) {
    throw new Error("Local demo is development-only. Unset NEXT_PUBLIC_LOCAL_DEMO for production build/start.");
  }
  return nextConfig;
}
