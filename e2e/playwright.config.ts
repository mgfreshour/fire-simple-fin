import { defineConfig, devices } from '@playwright/test';

/**
 * E2E tests for Fire SimpleFIN.
 * Starts backend (8080) and frontend (5173) before tests; frontend proxies /api to backend.
 * Run from repo root: make e2e  (or: cd e2e && npm install && npx playwright install && npm test)
 */
export default defineConfig({
  testDir: 'tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'dot' : 'html',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'sh -c "cd ../backend && . .venv/bin/activate && uvicorn firesimplefin.main:app --host 0.0.0.0 --port 8080"',
      url: 'http://localhost:8080/api/health',
      name: 'Backend',
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      cwd: '../frontend',
      name: 'Frontend',
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
});
