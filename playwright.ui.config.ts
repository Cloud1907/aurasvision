import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e', testMatch: 'ui-*.spec.ts', fullyParallel: true,
  timeout: 20000, expect: { timeout: 6000 }, retries: 0,
  reporter: [['line']], outputDir: 'test-results/ui',
  use: { baseURL: 'http://127.0.0.1:8767', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  // Performans olcumu paylasilan CPU'da anlamsizlasir: kalabalik kosuda ayni gecis
  // 238 ms yerine 1009 ms olculuyor. Bu yuzden ayri proje, tek isci ile kosar:
  //   npx playwright test -c playwright.ui.config.ts --project=performans --workers=1
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] }, testIgnore: /ui-gecis-performansi/ },
    { name: 'performans', use: { ...devices['Desktop Chrome'] }, testMatch: /ui-gecis-performansi/ },
  ],
  webServer: { command: 'node scripts/ui/preview.mjs', url: 'http://127.0.0.1:8767', reuseExistingServer: !process.env.CI },
});
