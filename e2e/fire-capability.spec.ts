import { test, expect } from '@playwright/test';

test('model hazır değilse yangın görevi nedeni ile devre dışıdır', async ({ page }) => {
  await page.route('**/api/capabilities', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ fire: {
      enabled: true,
      available: false,
      engine: 'rfdetr',
      model: 'models/fire.pt',
      reason: 'Yangın modeli bulunamadı: models/fire.pt',
    }}),
  }));

  await page.goto('/');
  await page.locator('[data-nav="cams"]').click();

  await expect(page.getByText(
    'Yangın erken uyarısı kullanılamıyor: Yangın modeli bulunamadı: models/fire.pt'
  )).toBeVisible();
  const fireButtons = page.getByRole('button', { name: 'Yangın' });
  await expect(fireButtons.first()).toBeDisabled();
  await expect(fireButtons.first()).toHaveAttribute(
    'title', 'Yangın modeli bulunamadı: models/fire.pt');
});
