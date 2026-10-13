import { defineConfig, devices } from '@playwright/test';

/**
 * Two ways to run (frontend/CLAUDE.md, e2e/README.md):
 *   npm run e2e       – against the mock (`npm run dev`), runs in CI;
 *   npm run e2e:live  – against the real API (`npm run dev:api`, compose from infra/ must be up),
 *                       only the tests tagged @live, never in CI.
 * The live run needs the network and real processing time, so it gets its own port and timeouts.
 */
const LIVE = process.env.E2E_LIVE === '1';
const PORT = LIVE ? 5174 : 5173;

export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/.results',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: LIVE ? 12 * 60_000 : 90_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI
    ? [['list'], ['html', { open: 'never', outputFolder: 'e2e/.report' }]]
    : 'list',
  use: {
    baseURL: `http://localhost:${PORT}`,
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
    colorScheme: 'light',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: LIVE
    ? [{ name: 'live', grep: /@live/, use: { ...devices['Desktop Chrome'] } }]
    : [{ name: 'mock', grepInvert: /@live/, use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: LIVE
      ? `npm run dev:api -- --port ${PORT} --strictPort`
      : `npm run dev -- --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}/`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
