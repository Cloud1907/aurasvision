import { test, expect } from '@playwright/test';
import { mockAPI } from './fixtures/ui-api';
test.beforeEach(async ({ page }) => { await mockAPI(page); });

test('V2: kamera çalışma alanı ve alarm kuyruğu ilk ekranda birlikte görünür', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Görüntü merkezi', exact: true })).toBeVisible();
  const stage = page.getByRole('region', { name: 'Seçili kamera görüntüsü' });
  await expect(stage).toBeVisible();
  expect((await stage.boundingBox())!.y).toBeLessThan(340);
  const alarm = page.getByRole('button', { name: /Sınırlı alana giriş/ });
  await expect(alarm).toBeInViewport();
});

test('V2: kamera seçimi doğru önizlemeyi açar, görüntü yoksa canlı denmez', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', req => { if(req.url().includes('/snapshot?')) requests.push(req.url()); });
  await page.goto('/');
  await page.getByRole('tab', { name: /Otopark/ }).click();
  await expect(page.getByRole('region', { name: 'Seçili kamera görüntüsü' })).toContainText('Otopark');
  await expect.poll(() => requests.some(url => url.includes('camera=demo-1'))).toBe(true);
  await expect(page.getByText('Görüntü alınamadı', { exact: true })).toBeVisible();
  await expect(page.locator('[data-testid="preview-mode"]')).toHaveText('GÖRÜNTÜ YOK');
});

test('V2: azaltılmış hareket tüm efektleri durdurur ve dar ekran taşmaz', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Görüntü merkezi', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  expect(await page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running').length)).toBe(0);
});

test('V2: WebGL olmadığında statik arka planla çalışma alanı açılır', async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      if (type === 'webgl2') return null;
      return original.call(this, type, ...args);
    };
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Görüntü merkezi', exact: true })).toBeVisible();
  await expect(page.locator('.rb-aurora')).toHaveClass(/fallback/);
  await expect(page.getByRole('button', { name: /Sınırlı alana giriş/ })).toBeVisible();
});

test('V2: hareket tercihi açılıp kapanınca Aurora tekrar çalışır', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.rb-aurora')).toHaveClass(/ready/);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(page.locator('.rb-aurora')).toHaveClass(/fallback/);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await expect(page.locator('.rb-aurora')).toHaveClass(/ready/);
});

test('V2: kamera şeridi yön tuşuyla seçimi ve odağı taşır', async ({ page }) => {
  await page.goto('/');
  const first = page.getByRole('tab', { name: /Ana giriş/ });
  await first.focus(); await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: /Otopark/ })).toBeFocused();
  await expect(page.getByRole('tab', { name: /Otopark/ })).toHaveAttribute('aria-selected', 'true');
});

test('V2: GPU bağlamı kaybolduğunda statik arka plan ve kontroller korunur', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.rb-aurora')).toHaveClass(/ready/);
  await page.locator('.rb-aurora canvas').evaluate((canvas: HTMLCanvasElement) => {
    const extension = canvas.getContext('webgl2')!.getExtension('WEBGL_lose_context');
    if (!extension) throw new Error('Context loss test extension unavailable');
    extension.loseContext();
  });
  await expect(page.locator('.rb-aurora')).toHaveClass(/fallback/);
  await page.getByRole('tab', { name: /Otopark/ }).click();
  await expect(page.getByRole('region', { name: 'Seçili kamera görüntüsü' })).toContainText('Otopark');
});

test('V3: ilk kullanım açık tema, kamera sahnesi sade ve ana aksiyon erişilebilir', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.locator('.scan-orbit')).toHaveCount(0);
  await expect(page.getByText('Sahanızı görün. Olayı anlayın. Kontrolü elinizde tutun.')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Canlı akışı aç/ })).toBeVisible();
  await expect(page.locator('.rb-aurora')).toHaveClass(/ready/);
});

test('V3: kayıtlı koyu tema korunur, iki temada tablet yatay taşmaz', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('vai-theme', 'dark'));
  await page.setViewportSize({width:768,height:1024});
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.getByRole('heading', { name:'Görüntü merkezi', exact:true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(768);
  await page.evaluate(() => document.documentElement.dataset.theme = 'light');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(768);
});

test('V4: kompakt navigasyon kamera alanını ilk ekranda öne çıkarır', async ({ page }) => {
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Görüntü merkezi',exact:true})).toBeVisible();
  expect((await page.locator('.rail').boundingBox())!.width).toBeLessThanOrEqual(110);
  expect((await page.getByRole('region',{name:'Seçili kamera görüntüsü'}).boundingBox())!.y).toBeLessThan(300);
  await expect(page.getByRole('button',{name:/Sınırlı alana giriş/})).toBeInViewport();
  await page.getByRole('button',{name:'Kayıtlar',exact:true}).first().click();
  await expect(page.locator('#recvid')).toBeVisible();
});

test('V4: operasyon metrikleri anında doğrudur ve kamera sorunu genel durumda görünür', async ({ page }) => {
  await page.goto('/');
  const cameras = page.locator('.ops-metric').filter({ hasText: 'Tanımlı kamera' }).locator('.ops-metric-value');
  await expect(cameras).toHaveText('6');
  await expect(cameras.locator('span')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Platform çalışıyor · 1 kamera incelenmeli/ })).toBeVisible();
});

test('V4: olay inceleme kanıtı öne alır, kabul ikincil kalır', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /Sınırlı alana giriş/ }).click();
  await expect(page.getByRole('button', { name: 'Olay anına git' })).toHaveClass(/pri/);
  await expect(page.getByRole('button', { name: 'Gördüm, kabul et' })).not.toHaveClass(/pri/);
  await expect(page.getByRole('dialog')).toContainText('Önce olay anını inceleyin');
});

test('V4: mobil başlık kamerayı erkene alır ve büyük envanter seçilebilir kalır', async ({ page }) => {
  const rows = Array.from({ length: 10 }, (_, i) => ({ id: `extra-${i}`, name: `Kamera ${i + 1}`, enabled: true, tasks: {} }));
  await page.route('**/api/cameras', route => route.fulfill({ json: rows }));
  await page.route('**/api/health', route => route.fulfill({ json: rows.map(row => ({ camera_id: row.id, fps: 5, status: 'ok', time: new Date().toISOString() })) }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  const stage = page.getByRole('region', { name: 'Seçili kamera görüntüsü' });
  await expect(stage).toBeVisible();
  expect((await stage.boundingBox())!.y).toBeLessThan(260);
  await page.getByLabel('Kameraya git').selectOption('extra-9');
  await expect(stage.getByRole('heading', { name: 'Kamera 10', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});
