import { test, expect } from '@playwright/test';
import { mockAPI, eventTime } from './fixtures/ui-api';

test.beforeEach(async ({ page }) => { await mockAPI(page); });

test('V12: giriş kapısı yalnız tek giriş eylemi gösterir', async ({ page }) => {
  await page.setViewportSize({ width: 647, height: 844 });
  await page.goto('/?welcome=1');
  await expect(page.getByRole('heading', { name: 'Operasyon merkezine hoş geldiniz.' })).toBeVisible();
  await expect(page.locator('.welcome-gate input')).toHaveCount(0);
  const visual = await page.locator('.welcome-visual').boundingBox();
  const auth = await page.locator('.welcome-auth').boundingBox();
  expect(auth!.x).toBeGreaterThan(visual!.x + visual!.width - 2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(647);
  const dome = page.locator('.welcome-dome-pro');
  const sphere = dome.locator('.sphere');
  const beforeDrag = await sphere.evaluate(el => (el as HTMLElement).style.transform);
  const domeBox = await dome.boundingBox();
  await page.mouse.move(domeBox!.x + domeBox!.width / 2, domeBox!.y + domeBox!.height / 2);
  await page.mouse.down();
  await page.mouse.move(domeBox!.x + domeBox!.width / 2 + 55, domeBox!.y + domeBox!.height / 2 + 12, { steps: 5 });
  await page.mouse.up();
  await expect.poll(() => sphere.evaluate(el => (el as HTMLElement).style.transform)).not.toBe(beforeDrag);
  await page.getByRole('button', { name: 'Giriş yap' }).click();
  await expect(page.getByRole('heading', { name: 'Operasyon paneli', exact: true })).toBeVisible();
});

test('V5: panel canlı kameraları, alarmları ve analizi tek ekranda birleştirir', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Operasyon paneli', exact: true })).toBeVisible();
  const live = page.getByRole('region', { name: 'Canlı kamera izleme' });
  await expect(live).toBeVisible();
  await expect(live.getByRole('button', { name: /Ana giriş kamera görüntüsü/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Aktif alarmlar/ })).toBeVisible();
  const analytics = page.getByRole('region', { name: 'Olay analizi' });
  await expect(analytics).toBeVisible();
  await expect(analytics.getByText('Olay yoğunluğu', { exact: true })).toBeVisible();
  await expect(analytics.getByText('Olay dağılımı', { exact: true })).toBeVisible();
  await expect(analytics.getByText('Kamera bazlı', { exact: true })).toBeVisible();
  await expect(analytics.getByText('Yangın analizi etkin değil')).toBeVisible();
  // Bant KPI'ların hemen altında, kamera duvarının üstünde: sayfa açılınca konu görünür
  expect((await analytics.boundingBox())!.y).toBeLessThan(330);
  expect((await analytics.boundingBox())!.y).toBeLessThan((await live.boundingBox())!.y);
});

test('V13: KPI gerçek kaynak kapsamını ve alarm sınırını dürüstçe gösterir', async ({ page }) => {
  await page.route('**/api/alerts?*', route => route.fulfill({ json: Array.from({ length: 500 }, (_, id) => ({ id, kind: 'intrusion', camera_id: 'demo-2', time: eventTime, ref: 'Depo A' })) }));
  await page.goto('/');
  await expect(page.getByText('İnceleme bekleyen')).toBeVisible();
  await expect(page.getByLabel('Operasyon göstergeleri').getByText('500+')).toBeVisible();
  await expect(page.getByText('Son olay')).toBeVisible();
  await expect(page.getByText('Kayıt kapsamı')).toBeVisible();
  await expect(page.getByLabel('Operasyon göstergeleri').getByText(/18[/.]09/)).toBeVisible();
  await expect(page.getByLabel('Operasyon göstergeleri').getByText(/Geçiş · Koridor/)).toBeVisible();
  await expect(page.getByText('Yangın analizi etkin değil')).toBeVisible();
});

test('V13: boş olay ve kapalı kayıt durumu uydurma sayı üretmez', async ({ page }) => {
  await page.route('**/api/events?*', route => route.fulfill({ json: [] }));
  await page.route('**/api/recordings/stats', route => route.fulfill({ json: { enabled: false, cameras: [] } }));
  await page.goto('/');
  const metrics = page.getByLabel('Operasyon göstergeleri');
  await expect(metrics.getByText('Yok', { exact: true })).toBeVisible();
  await expect(metrics.getByText('Kayıt servisi etkin değil')).toBeVisible();
  await expect(page.getByText('Henüz analiz olayı kaydedilmedi.')).toBeVisible();
});

test('V13: kamera çubukları kırpılmış özeti ve etkin olmayan görevleri ayırır', async ({ page }) => {
  await page.route('**/api/events/summary?*', route => route.fulfill({ json: { hours: 24, cameras: [
    { camera_id: 'demo-0', count: 20000, count_events: 20000, plate: 0, face: 0, fire: 0, alerts: 0 },
  ] } }));
  await page.goto('/');
  await expect(page.getByText('Son 20.000 olay tarandı; sayılar alt sınırdır.')).toBeVisible();
  const bars = page.getByRole('list', { name: 'Kameralara göre son 24 saatin olay sayısı' });
  await expect(bars.getByRole('listitem')).toHaveCount(1);
  await expect(bars).toContainText('20.000');
  await expect(page.locator('.ring-legend')).toContainText('Yangın analizi etkin değil');
});

test('V13: grafik açık ve koyu temada yeniden renklendirilir', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const line = page.locator('.ts-line');
  await expect(line).toBeVisible();
  const light = await line.evaluate(el => getComputedStyle(el).stroke);
  await page.screenshot({ path: testInfo.outputPath('panel-light-1440.png'), fullPage: true });
  await page.getByRole('button', { name: 'tema' }).click();
  const dark = await line.evaluate(el => getComputedStyle(el).stroke);
  expect(dark).not.toBe(light);
  await page.screenshot({ path: testInfo.outputPath('panel-dark-1440.png'), fullPage: true });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.screenshot({ path: testInfo.outputPath('panel-dark-1920.png') });
  await page.getByRole('button', { name: 'tema' }).click();
  await page.screenshot({ path: testInfo.outputPath('panel-light-1920.png') });
});

test('V5: dört kamera önizlemesi istenir, görüntü yoksa canlı denmez', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', request => { if (request.url().includes('/snapshot?')) requests.push(request.url()); });
  await page.goto('/');
  // Analitik bandı kamera duvarını aşağı iter; önizlemeler ızgara görünür olunca istenir (görünürlük güdümlü yükleme).
  await page.getByRole('region', { name: 'Canlı kamera izleme' }).scrollIntoViewIfNeeded();
  await expect.poll(() => new Set(requests.map(url => new URL(url).searchParams.get('camera'))).size).toBe(4);
  await expect(page.getByText('Görüntü alınamadı', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Canlı', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Tüm kameraları göster' }).click();
  await expect(page.getByRole('button', { name: /Koridor kamera görüntüsü/ })).toBeVisible();
});

test('V11: alarm yenilenirken gerçek işlem durumu gösterilir', async ({ page }) => {
  await page.goto('/');
  const refresh = page.getByRole('button', { name: 'Alarmları yenile' });
  await expect(refresh).toBeEnabled();
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/alerts?*', async route => {
    await held;
    await route.fulfill({ json: [] });
  });
  await refresh.click();
  await expect(page.getByRole('status', { name: 'Alarm kuyruğu güncelleniyor' })).toBeVisible();
  await expect(page.getByText('Mevcut sonuçlar korundu', { exact: true })).toBeVisible();
  release();
  await expect(page.getByRole('status', { name: 'Alarm kuyruğu güncelleniyor' })).toBeHidden();
});

test('V8: bütün sayfalar izleme, analizler ve ayarlar gruplarında yer alır', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.nav-group-toggle')).toHaveText([/İzleme/, /Analizler/, /Ayarlar/]);
  await expect(page.locator('.nav').getByRole('button', { name: 'Panel', exact: true })).toBeVisible();
  await expect(page.locator('.nav').getByRole('button', { name: 'Kamera duvarı', exact: true })).toBeVisible();
  await page.locator('.nav-group-toggle').filter({ hasText: 'Analizler' }).click();
  await expect(page.locator('.nav').getByRole('button', { name: 'Raporlar', exact: true })).toBeVisible();
  await expect(page.locator('.nav').getByRole('button', { name: 'Test ve doğrulama', exact: true })).toBeVisible();
  await page.locator('.nav-group-toggle').filter({ hasText: 'Ayarlar' }).click();
  await expect(page.locator('.nav').getByRole('button', { name: 'Tanıma listeleri', exact: true })).toBeVisible();
  await expect(page.locator('.nav').getByRole('button', { name: 'Sistem ve alarmlar', exact: true })).toBeVisible();
});

test('V6: alarm davranışı kamera, tür, popup, ses ve tekrar süresiyle ayarlanır', async ({ page }) => {
  await page.goto('/');
  await page.locator('.nav-group-toggle').filter({ hasText: 'Ayarlar' }).click();
  await page.locator('.nav').getByRole('button', { name: 'Sistem ve alarmlar', exact: true }).click();
  await expect(page.getByText('Alarm davranışı', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Kamera').first()).toHaveValue('demo-2');
  await expect(page.getByLabel('Alarm türü').first()).toHaveValue('fire');
  await expect(page.getByLabel('Ekranda aç').first()).toBeChecked();
  await expect(page.getByLabel('Ses çal').first()).toBeChecked();
  await expect(page.getByLabel('Ses tonu').first()).toHaveValue('urgent');
  await expect(page.getByLabel('Tekrar süresi').first()).toHaveValue('60');
  await expect(page.getByRole('button', { name: 'Sesi dene' })).toBeVisible();
});

test('V5: azaltılmış hareket ve mobil görünüm yatay taşmaz', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Operasyon paneli', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  expect(await page.evaluate(() => document.getAnimations().filter(animation => animation.playState === 'running').length)).toBe(0);
  await page.getByRole('button', { name: 'Menüyü aç' }).click();
  await expect(page.locator('.nav-group-toggle').filter({ hasText: 'Ayarlar' })).toBeVisible();
});

test('V5: WebGL olmadığında statik arka plan ve temel kontroller korunur', async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      if (type === 'webgl2') return null;
      return original.call(this, type, ...args);
    };
  });
  await page.goto('/');
  await expect(page.locator('.rb-aurora')).toHaveClass(/fallback/);
  await expect(page.getByRole('region', { name: 'Canlı kamera izleme' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Sınırlı alana giriş/ })).toBeVisible();
});

test('V5: olay inceleme kanıtı öne alır, kabul ikincil kalır', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /Sınırlı alana giriş/ }).click();
  await expect(page.getByRole('button', { name: 'Olay anına git' })).toHaveClass(/pri/);
  await expect(page.getByRole('button', { name: 'Gördüm, kabul et' })).not.toHaveClass(/pri/);
  await expect(page.getByRole('dialog')).toContainText('Önce olay anını inceleyin');
});
