import { test, expect } from '@playwright/test';
import { mockAPI } from './fixtures/ui-api';

// Her ekran geçişi ölçülür: tıklamadan boyanmış ekrana kadar geçen süre,
// geçiş sırasında ana iş parçacığını kilitleyen uzun görevler ve düzen kayması.
const EKRANLAR: [string, string][] = [
  ['panel', 'Operasyon merkezi'], ['live', 'Canlı görünüm'], ['events', 'Olaylar'],
  ['rec', 'Kayıtlar'], ['rapor', 'Raporlar'], ['arama', 'Arama'],
  ['test', 'Test'], ['cams', 'Kameralar'], ['zones', 'Bölgeler'],
  ['lists', 'Tanıma listeleri'], ['sys', 'Sistem'],
];

// Kosu komutu: npx playwright test -c playwright.ui.config.ts --project=performans --workers=1
// Paralel kosuda olcum CPU rekabetine takilir; bu dosya varsayilan pakete dahil degildir.
const SURE_ESIGI = 600;      // ms — tıklamadan boyanmış ekrana
const UZUN_GOREV_ESIGI = 250; // ms — tek bir uzun görev bu kadar sürerse ekran donmuş demektir

test('tüm ekran geçişleri hızlı ve takılmasız', async ({ page }) => {
  await mockAPI(page);
  await page.addInitScript(() => {
    (window as any).__perf = { uzun: [] as { bas: number; sure: number }[], kayma: 0 };
    new PerformanceObserver(list => list.getEntries().forEach(e =>
      (window as any).__perf.uzun.push({ bas: e.startTime, sure: e.duration }))).observe({ entryTypes: ['longtask'] });
    new PerformanceObserver(list => list.getEntries().forEach((e: any) => {
      if (!e.hadRecentInput) (window as any).__perf.kayma += e.value;
    })).observe({ type: 'layout-shift', buffered: true } as any);
  });
  // Betik hatası gerçek kusurdur; taklit sunucunun karşılamadığı uçtan dönen
  // 503 ise fikstür eksiğidir, arayüz kusuru değil.
  const hatalar: string[] = [];
  page.on('console', m => { if (m.type() === 'error' && !m.text().includes('Failed to load resource')) hatalar.push(m.text()); });
  page.on('pageerror', e => hatalar.push(String(e.message)));

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Operasyon paneli', exact: true })).toBeVisible();
  await page.waitForTimeout(600);

  const olcumler: { ekran: string; sure: number; uzun: number; enUzun: number; kayma: number }[] = [];
  for (const [id, baslik] of EKRANLAR) {
    const kaymaOnce = await page.evaluate(() => (window as any).__perf.kayma);
    const t0 = await page.evaluate(() => performance.now());
    await page.evaluate(ekran => (window as any).go(ekran), id);
    await expect(page.locator('.topbar h1')).toHaveText(baslik);
    const sonuc = await page.evaluate(async (bas: number) => {
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      const p = (window as any).__perf;
      const uzun = p.uzun.filter((u: any) => u.bas >= bas);
      return {
        sure: performance.now() - bas,
        uzun: uzun.length,
        enUzun: uzun.reduce((m: number, u: any) => Math.max(m, u.sure), 0),
        kayma: p.kayma,
      };
    }, t0);
    olcumler.push({ ekran: id, sure: Math.round(sonuc.sure), uzun: sonuc.uzun, enUzun: Math.round(sonuc.enUzun), kayma: +(sonuc.kayma - kaymaOnce).toFixed(3) });
  }

  console.info('\nekran      süre(ms)  uzun görev  en uzun(ms)  düzen kayması');
  for (const o of olcumler) {
    console.info(`${o.ekran.padEnd(10)} ${String(o.sure).padStart(7)} ${String(o.uzun).padStart(11)} ${String(o.enUzun).padStart(12)} ${String(o.kayma).padStart(14)}`);
  }

  expect(hatalar, `konsol hatası: ${hatalar.join(' | ')}`).toEqual([]);
  for (const o of olcumler) {
    expect(o.sure, `${o.ekran} ekranı ${o.sure}ms'de açıldı`).toBeLessThan(SURE_ESIGI);
    expect(o.enUzun, `${o.ekran} geçişinde ${o.enUzun}ms süren uzun görev var`).toBeLessThan(UZUN_GOREV_ESIGI);
  }
});
