import { test, expect } from '@playwright/test';
import { mockAPI, alerts } from './fixtures/ui-api';

test.beforeEach(async ({ page }) => { await mockAPI(page); });

test('K1: geç olay yanıtı yeni ekranı ezmez', async ({ page }) => {
  await page.goto('/');
  await page.locator('[data-nav="events"]').waitFor();
  await page.route('**/api/events?*', async route => {
    await new Promise(resolve => setTimeout(resolve, 700));
    await route.fulfill({ json: [] });
  });
  await page.locator('[data-nav="events"]').click();
  await page.locator('.nav-group-toggle').filter({ hasText: 'Ayarlar' }).click();
  await page.locator('[data-nav="cams"]').click();
  await expect(page.getByRole('heading', { name: 'Kameralar', exact: true })).toBeVisible();
  await expect(page.getByText('Kamera envanteri', { exact: true })).toBeVisible();
  await page.waitForTimeout(1000);
  await expect(page.getByText('Kamera envanteri', { exact: true })).toBeVisible();
  await expect(page.getByText('Olay akışı', { exact: true })).toHaveCount(0);
});

test('K2: yavaş arşiv alarm kartlarını bekletmez', async ({ page }) => {
  await page.route('**/api/recordings/stats', async route => {
    await new Promise(resolve => setTimeout(resolve, 5000));
    await route.fulfill({ json: { total_bytes: 0, cameras: [] } });
  });
  await page.goto('/');
  await expect(page.getByText('Sınırlı alana giriş', { exact: false }).first()).toBeVisible({ timeout: 2500 });
});

test('K4: dar ekranda çalışma alanı ve klavye navigasyonu', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.locator('#content')).toBeVisible();
  expect((await page.locator('#content').boundingBox())!.y).toBeLessThan(180);
  await page.getByRole('button', { name: 'Menüyü aç' }).click();
  await page.locator('.nav-group-toggle').filter({ hasText: 'Ayarlar' }).click();
  const nav = page.locator('[data-nav="cams"]');
  await nav.focus();
  await expect(nav).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Kameralar', exact: true })).toBeVisible();
});

test('K6: mobil alarm kaydı kamera ve zamanla açılır', async ({ page }) => {
  await page.goto('/m');
  await page.getByRole('button', { name: 'Alarm Merkezi' }).click();
  await page.getByRole('button', { name: 'Kayda git', exact: true }).first().click();
  await expect(page).toHaveURL(/camera=demo-2/);
  expect(new URL(page.url()).searchParams.get('at')).toBe(alerts[0].time);
  await expect(page.locator('#recvid')).toBeVisible();
});

test('K7: mobil analiz FPS bilgisi REC olarak gösterilmez', async ({ page }) => {
  await page.goto('/m');
  await expect(page.getByText('Canlı İzleme', { exact: true }).first()).toBeVisible();
  await expect(page.locator('.rec')).toHaveCount(0);
});
