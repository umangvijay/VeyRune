import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    // Run against the actual production artifact when requested by the release gate.
    command: process.env.E2E_PRODUCTION === '1'
      ? 'HOSTNAME=127.0.0.1 PORT=3000 node .next/standalone/server.js'
      : 'npm run dev:fast',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI && process.env.E2E_PRODUCTION !== '1',
    timeout: 120 * 1000,
  },
});
