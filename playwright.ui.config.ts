import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e', testMatch: 'ui-*.spec.ts', fullyParallel: true,
  timeout: 20000, expect: { timeout: 6000 }, retries: 0,
  reporter: [['line']], outputDir: 'test-results/ui',
  use: { baseURL: 'http://127.0.0.1:8767', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: { command: 'node scripts/ui/preview.mjs', url: 'http://127.0.0.1:8767', reuseExistingServer: !process.env.CI },
});
