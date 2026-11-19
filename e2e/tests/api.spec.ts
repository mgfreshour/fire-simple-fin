import { test, expect } from '@playwright/test';

test.describe('API health', () => {
  test('GET /api/health returns ok', async ({ request }) => {
    const res = await request.get('http://localhost:8080/api/health');
    expect(res.ok()).toBe(true);
    const body = await res.json();
    expect(body).toEqual({ status: 'ok' });
  });

  test('GET /api/ready returns ready', async ({ request }) => {
    const res = await request.get('http://localhost:8080/api/ready');
    expect(res.ok()).toBe(true);
    const body = await res.json();
    expect(body).toEqual({ status: 'ready' });
  });
});
