import type { NextConfig } from "next";
import fs from "fs";
import path from "path";
import withBundleAnalyzer from "@next/bundle-analyzer";

function loadRootEnv() {
  const envPath = path.join(__dirname, "..", ".env");
  if (!fs.existsSync(envPath)) return;
  for (const line of fs.readFileSync(envPath, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq < 1) continue;
    const key = trimmed.slice(0, eq).trim();
    let val = trimmed.slice(eq + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    if (process.env[key] === undefined) process.env[key] = val;
  }
}
loadRootEnv();

const nextConfig: NextConfig = {
  output: "standalone",
  compress: true,
  devIndicators: false,
  // Don't advertise the framework version (audit: x-powered-by leak)
  poweredByHeader: false,
  experimental: {
    optimizePackageImports: ["lucide-react", "radash", "@xyflow/react"],
    optimizeCss: true,
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
          { key: "X-DNS-Prefetch-Control", value: "off" },
          // Match the API's header stack (audit P1.8: frontend lacked HSTS/CSP).
          // script-src keeps 'unsafe-inline': this app's marketing pages are
          // statically prerendered, so nonce-based CSP (middleware) cannot
          // stamp its scripts — tried in Round 8 and reverted for exactly
          // that reason. Hardening requires giving up static prerendering.
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains",
          },
          {
            key: "Cross-Origin-Opener-Policy",
            value: "same-origin",
          },
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              // 'unsafe-eval' is dev-only: react-refresh evaluates strings.
              // (This gap is what broke the workspace e2e spec since Round 3.)
              `script-src 'self' 'unsafe-inline'${process.env.NODE_ENV !== "production" ? " 'unsafe-eval'" : ""}`,
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: blob:",
              "font-src 'self' data:",
              // localhost:8000 matches the API's own dev CSP exception — the
              // CSRF bootstrap needs it in dev/e2e; unreachable in production.
              "connect-src 'self' https://*.run.app https://accounts.google.com http://localhost:8000 http://127.0.0.1:8000",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
            ].join("; "),
          },
        ],
      },
      {
        source: "/images/(.*)",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=31536000, immutable",
          },
        ],
      },
    ];
  },
  webpack: (config, { dev, isServer }) => {
    // Forcefully disable core-js polyfills that Next.js aggressively injects
    if (!dev && !isServer) {
      config.resolve.alias = {
        ...config.resolve.alias,
        "core-js": false,
        "@swc/helpers": false,
        "next/dist/client/polyfills": false,
        "next/dist/build/polyfills/polyfill-nomodule": false,
        "next/dist/build/polyfills/polyfills": false,
      };
    }
    return config;
  },
};

const analyzer = withBundleAnalyzer({
  enabled: process.env.ANALYZE === "true",
});

export default analyzer(nextConfig);
