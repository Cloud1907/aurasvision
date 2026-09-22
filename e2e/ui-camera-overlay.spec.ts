import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { mockAPI } from './fixtures/ui-api';

test('panel live button connects when optional system information fails', async ({ page }) => {
  await mockAPI(page);
  await page.route('**/api/sysinfo', route => route.fulfill({status: 503, json: {detail: 'unavailable'}}));
  await page.route('**/vendor/video-rtc.js', route => route.fulfill({
    contentType: 'text/javascript', body: `export class VideoRTC extends HTMLElement {
      connectedCallback(){if(!this.video)this.oninit();}
      oninit(){this.video=document.createElement('video');this.append(this.video);}
      set src(value){this.wsURL=value;this.dataset.connected=value;}
    }`
  }));
  await page.goto('/');
  // Ana dalın paneli ayrı 'Canlı akışı aç' düğmesi yerine kamera karosunu kullanır
  await page.locator('.live-monitoring .monitor-card.tile').first().click();
  await expect(page.locator('.camview auras-stream')).toHaveAttribute('data-connected', /\/api\/stream\?src=demo-0/);
  await page.locator('#cv-x').click();
  await expect(page.locator('.camview')).toHaveCount(0);
});

test('camera detection overlay leaves the live image visible', async ({ page }) => {
  const html = readFileSync('web/index.html', 'utf8');
  const css = html.match(/<style>([\s\S]*?)<\/style>/)![1];
  await page.setContent(`<style>${css}</style>
    <div class="camview full"><div class="tile" data-state="live">
      <auras-stream><video></video></auras-stream>
      <div class="ov-wrap"><canvas class="det-canvas"></canvas></div>
    </div></div><canvas id="zone-editor"></canvas>`);
  const overlay = page.locator('.det-canvas');
  await expect(overlay).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  await expect(overlay).toHaveCSS('border-top-width', '0px');
  await expect(overlay).toHaveCSS('box-shadow', 'none');
  // Bölge editörünün mevcut koyu zemini korunur.
  await expect(page.locator('#zone-editor')).toHaveCSS('background-color', 'rgb(11, 17, 32)');
});
