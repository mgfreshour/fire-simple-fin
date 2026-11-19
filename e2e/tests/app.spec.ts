import { test, expect } from '@playwright/test';

test.describe('App', () => {
  test('home page shows title and API status', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Fire SimpleFIN' })).toBeVisible();
    await expect(page.getByText('Connect your bank via SimpleFIN')).toBeVisible();
    // Health check runs client-side; we should see "API: ok" once the proxy hits the backend
    await expect(page.getByTestId('health')).toContainText('ok', { timeout: 10_000 });
  });
});
