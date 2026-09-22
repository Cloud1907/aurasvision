import { test, expect } from '@playwright/test';
import { mockAPI } from './fixtures/ui-api';

test.beforeEach(async ({page}) => { await mockAPI(page); await page.goto('/'); await page.locator('[data-nav="events"]').click(); });

test('camera, type, date and text filters are combined and cleared', async ({page}) => {
  const form=page.locator('#event-filters');
  await form.getByRole('combobox', {name:'Kamera', exact:true}).selectOption('demo-1');
  await form.getByRole('combobox', {name:'Olay türü', exact:true}).selectOption('telefon');
  await form.getByLabel('Başlangıç').fill('2026-09-22T10:00');
  await form.getByLabel('Plaka, bölge veya açıklama').fill('kapı');
  const request=page.waitForRequest(r=>r.url().includes('/api/events?')&&r.url().includes('tur=telefon'));
  await form.getByRole('button',{name:'Filtrele',exact:true}).click();
  const params=new URL((await request).url()).searchParams;
  expect(params.get('kamera')).toBe('demo-1');
  expect(params.get('q')).toBe('kapı');
  expect(params.get('start')).toBeTruthy();
  await expect(form.getByRole('combobox', {name:'Olay türü', exact:true})).toHaveValue('telefon');
  await form.getByRole('button',{name:'Temizle',exact:true}).click();
  await expect(form.getByRole('combobox', {name:'Olay türü', exact:true})).toHaveValue('');
  await expect(form.getByLabel('Başlangıç')).toHaveValue('');
});

test('reversed dates keep the form and show a useful error', async ({page}) => {
  const form=page.locator('#event-filters');
  await form.getByLabel('Başlangıç').fill('2026-09-23T10:00');
  await form.getByLabel('Bitiş').fill('2026-09-22T10:00');
  await form.getByRole('button',{name:'Filtrele',exact:true}).click();
  await expect(form.getByRole('alert')).toContainText('Başlangıç');
});
