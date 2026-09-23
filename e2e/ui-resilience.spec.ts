import { test, expect } from '@playwright/test';
import { mockAPI, alerts, eventTime } from './fixtures/ui-api';

test.beforeEach(async ({ page }) => {
  // Ağ/yaşam döngüsü testlerini GPU animasyon yükünden ayır; hareket V2 testlerinde ölçülür.
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockAPI(page);
});

test('K1: aynı ekranda ters filtre yanıtı son seçimi değiştirmez', async ({ page }) => {
  await page.goto('/');
  await page.locator('[data-nav="events"]').click();
  await expect(page.getByText('Olay akışı', { exact: true })).toBeVisible();
  await page.route('**/api/events?*', async route => {
    const plate = new URL(route.request().url()).searchParams.get('tur') === 'plate';
    await new Promise(r => setTimeout(r, plate ? 500 : 30));
    await route.fulfill({ json: [{ camera_id: 'demo-0', type: plate ? 'plate' : 'fire', detail: plate ? 'ESKİ FİLTRE' : 'SON FİLTRE', time: eventTime }] });
  });
  await page.evaluate(() => { window._ef.tur = 'plate'; SCREENS.events(); window._ef.tur = 'fire'; SCREENS.events(); });
  await expect(page.getByText('SON FİLTRE', { exact: false })).toBeVisible();
  await page.waitForTimeout(650);
  await expect(page.getByText('ESKİ FİLTRE', { exact: false })).toHaveCount(0);
});

test('K5: inceleme penceresinden olay anına gidiş kayıt ekranını açar', async ({ page }) => {
  // Kabul isteği kaldırıldı; pencere yalnız kayda gönderir ve kapanır
  await page.goto('/');
  await page.getByRole('button', { name: /Sınırlı alana giriş/ }).click();
  await page.getByRole('button', { name: 'Olay anına git', exact: true }).click();
  await expect(page.locator('#recvid')).toBeVisible();
  await expect(page.locator('dialog')).toHaveCount(0);
});

test('K2: başarısız alarm yenilemesi eski sıfırı güncel göstermez', async ({ page }) => {
  await page.route('**/api/alerts?*', route => route.fulfill({ json: [] }));
  await page.goto('/');
  const metric = page.locator('.ops-metric').filter({ hasText: 'Alarm · son 24 saat' });
  await expect(metric.locator('.ops-metric-value')).toHaveText('0');
  await page.route('**/api/alerts?*', route => route.fulfill({ status: 503, json: { detail: 'Bağlantı kesildi' } }));
  await page.getByRole('button', { name: 'Alarmları yenile' }).click();
  await expect(metric.locator('.ops-metric-value')).toHaveText('—');
  await expect(metric).toContainText('Güncellenemedi');
});

test('K6: olay zamanı kayıt boşluğundaysa komşu video sessizce oynatılmaz', async ({ page }) => {
  await page.route('**/api/recordings?*', route => route.fulfill({ json: [{
    path: 'demo-2/previous.mp4', start_time: '2026-09-18T10:20:00+00:00', duration: 30,
  }] }));
  await page.goto('/?view=rec&camera=demo-2&at=' + encodeURIComponent(eventTime));
  await expect(page.getByText('Bu olay anında kayıt yok', { exact: false })).toBeVisible();
  expect(await page.locator('#recvid').getAttribute('src')).toBeNull();
});

test('K7: kayıt sorgusu hatası boş arşiv olarak sunulmaz', async ({ page }) => {
  await page.route('**/api/recordings?*', route => route.fulfill({ status: 503, json: { detail: 'Kayıt servisi erişilemiyor' } }));
  await page.goto('/?view=rec&camera=demo-2');
  await expect(page.getByRole('alert')).toContainText('Kayıt servisi erişilemiyor');
  await expect(page.getByText('Bu gün için kayıt yok')).toHaveCount(0);
});

test('K9: kullanılamayan yangın görevi nedenini korur', async ({ page }) => {
  await page.goto('/'); await page.locator('.nav-group-toggle').filter({ hasText: 'Ayarlar' }).click(); await page.locator('[data-nav="cams"]').click();
  await expect(page.getByText(/Yangın erken uyarısı kullanılamıyor:/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Yangın', exact: true }).first()).toBeDisabled();
});

test('K4: azaltılmış harekette sayılar doğru ve sürekli animasyon yok', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.locator('.ops-metric').filter({ hasText: 'Kayıt kapsamı' }).locator('.ops-metric-value')).toHaveText('6/6');
  await expect(page.locator('.ops')).toHaveAttribute('data-motion', 'off');
  expect(await page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running').length)).toBe(0);
});

test('K3: polling gizliyken durur, açık isteğin üstüne yenisi binmez', async ({ page }) => {
  await page.goto('/');
  await page.clock.install();
  await page.evaluate(() => {
    window.pollCalls = 0;
    window.pollStop = AurasRuntime.poll(() => { window.pollCalls++; return new Promise(r => window.finishPoll = r); }, 1000);
  });
  await page.clock.fastForward(8000);
  expect(await page.evaluate(() => window.pollCalls)).toBe(1);
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: true }); window.finishPoll(); document.dispatchEvent(new Event('visibilitychange')); });
  await page.clock.fastForward(5000);
  expect(await page.evaluate(() => window.pollCalls)).toBe(1);
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: false }); document.dispatchEvent(new Event('visibilitychange')); });
  await expect.poll(() => page.evaluate(() => window.pollCalls)).toBe(2);
  await page.evaluate(() => { window.finishPoll(); window.pollStop(); });
});

test('K3: snapshot kuyruğu en fazla iki istek açar ve sayfa çıkışında iptal eder', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Görüntü alınamadı', { exact: true }).first()).toBeVisible();
  const pending = new Set<string>(), failures: string[] = [];
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/snapshot?*', async route => {
    pending.add(route.request().url());
    await held;
    await route.fulfill({ status: 503, body: '' });
  });
  page.on('requestfailed', r => { if (pending.has(r.url())) failures.push(r.url()); });
  try {
    await page.locator('[data-nav="live"]').click();
    await expect.poll(() => pending.size).toBe(2);
    await page.waitForTimeout(150);
    expect(pending.size).toBe(2);
    await page.locator('[data-nav="events"]').click();
    await expect.poll(() => failures.length).toBe(2);
    expect(pending.size).toBe(2);
  } finally { release(); }
});

test('K3: yeni görünür kamera sonraki 30 saniyeyi beklemez', async ({ page }) => {
  const requested = new Set<string>();
  await page.setViewportSize({ width: 1200, height: 450 });
  await page.route('**/api/snapshot?*', async route => {
    requested.add(new URL(route.request().url()).searchParams.get('camera')!);
    await route.fulfill({ status: 503, body: '' });
  });
  await page.goto('/'); await page.locator('[data-nav="live"]').click();
  await expect(page.locator('img[data-snapshot="demo-5"]')).toBeAttached();
  expect(requested.has('demo-5')).toBe(false);
  await page.locator('img[data-snapshot="demo-5"]').scrollIntoViewIfNeeded();
  await expect.poll(() => requested.has('demo-5'), { timeout: 1000 }).toBe(true);
});

test('K2: mobil açık alarm listesi yeni olayı kendiliğinden gösterir', async ({ page }) => {
  await page.clock.install();
  await page.goto('/m'); await page.getByRole('button', { name: 'Alarm Merkezi' }).click();
  await expect(page.getByText('Sınırlı alana giriş', { exact: false })).toBeVisible();
  await page.route('**/api/alerts?*', route => route.fulfill({ json: [...alerts, { ...alerts[0], id: 3, ref: 'YENİ MOBİL ALARM' }] }));
  await page.clock.fastForward(16000);
  await expect(page.getByText('YENİ MOBİL ALARM', { exact: true })).toBeVisible();
});

test('K2: mobil sağlık sorgusu hata verirse eski sağlıklı durumu kalmaz', async ({ page }) => {
  await page.clock.install();
  await page.goto('/m');
  await expect(page.locator('[data-analysis="demo-0"]')).toHaveText('Analiz çalışıyor');
  await page.route('**/api/health', route => route.fulfill({ status: 503, json: { detail: 'Sağlık erişilemiyor' } }));
  await page.clock.fastForward(11000);
  await expect(page.locator('[data-analysis="demo-0"]')).toHaveText('Sağlık bilgisi güncellenemedi');
});

test('K4: masaüstü kabul penceresi Escape sonrası odağı geri verir', async ({ page }) => {
  await page.goto('/');
  const trigger = page.getByRole('button', { name: /Sınırlı alana giriş/ });
  await trigger.click(); await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test('K4: mobil alarm filtresi Enter sonrası odağını korur', async ({ page }) => {
  await page.goto('/m'); await page.getByRole('button', { name: 'Alarm Merkezi' }).click();
  const filter = page.locator('[data-focus="filter-kritik"]');
  await filter.focus(); await page.keyboard.press('Enter');
  await expect(filter).toBeFocused();
});

test('K2: kanıt resmi yüklenmezse anlaşılır hata gösterilir', async ({ page }) => {
  await page.route('**/api/alerts?*', route => route.fulfill({ json: [{ ...alerts[0], snapshot: 'missing.jpg' }] }));
  await page.route('**/media/missing.jpg', route => route.fulfill({ status: 404, body: '' }));
  await page.goto('/'); await page.getByRole('button', { name: /Sınırlı alana giriş/ }).click();
  await expect(page.getByText('Kanıt görüntüsü yüklenemedi')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Olay anına git' })).toBeEnabled();
});

test('K9: sunucu kullanıcı silmeyi reddettiğinde neden görünür kalır', async ({ page }) => {
  await page.route('**/api/ben', route => route.fulfill({ json: { ad: 'Son yönetici', rol: 'yonetici' } }));
  await page.route('**/api/kullanicilar', route => route.fulfill({ json: [{ ad: 'Son yönetici', rol: 'yonetici' }] }));
  await page.route('**/api/kullanicilar/*', route => route.fulfill({ status: 400, json: { detail: 'Son yönetici silinemez' } }));
  page.on('dialog', dialog => dialog.accept());
  await page.goto('/'); await page.locator('.nav-group-toggle').filter({ hasText: 'Ayarlar' }).click(); await page.locator('[data-nav="sys"]').click();
  await page.locator('#sy-kul-b').getByRole('button', { name: 'sil', exact: true }).click();
  await expect(page.getByText('Son yönetici silinemez', { exact: true })).toBeVisible();
});
