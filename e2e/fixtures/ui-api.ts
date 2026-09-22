import type { Page } from '@playwright/test';

export const cameras = ['Ana giriş', 'Otopark', 'Depo A', 'Üretim alanı', 'Sevkiyat', 'Koridor'].map((name, i) => ({
  id: `demo-${i}`, name, source: 'rtsp://camera.invalid/stream', enabled: true,
  tasks: { count: i < 3, plate: i === 1, face: false, fire: false, record: true },
}));
export const eventTime = '2026-09-18T10:24:30+00:00';
export const alerts = [
  { id: 1, kind: 'intrusion', camera_id: 'demo-2', ref: 'Depo A', label: 'Sınırlı alana giriş', list_type: 'intrusion', time: eventTime },
  { id: 2, kind: 'plate', camera_id: 'demo-1', ref: 'TEST PLAKA', label: 'İzleme listesi eşleşmesi', list_type: 'blacklist', time: eventTime },
];
export const responses: Record<string, () => unknown> = {
  '/cameras': () => cameras,
  '/ben': () => ({ ad: 'Demo Operatör', rol: 'operator', kullanici_tanimli: true }),
  '/sysinfo': () => ({ go2rtc: '' }),
  '/status': () => ({ ok: true, bilesenler: [{ ad: 'Veritabanı', ok: true }, { ad: 'Analiz worker', ok: true, detay: '5/6 kamera işleniyor' }, { ad: 'Kayıt servisi', ok: true }, { ad: 'Arama dizini', ok: true, detay: 'henüz vektör yok (nesne görülünce başlar)' }] }),
  '/health': () => cameras.map((c, i) => ({ camera_id: c.id, fps: i === 4 ? 0 : 5,
    time: new Date().toISOString().replace('Z', '+00:00'), status: i === 4 ? 'error' : 'ok', detail: i === 4 ? 'Görüntü alınamıyor' : '' })),
  '/counts': () => ({ active: true, rows: cameras.slice(0, 3).map(c => ({ camera_id: c.id, in_count: 34, out_count: 18 })) }),
  '/capabilities': () => ({ fire: { available: false, enabled: false, reason: 'Yangın erken uyarısı pilot kapısı kapalı' } }),
  '/alerts': () => alerts,
  '/alerts/feed': () => ({ cursor: alerts.at(-1)?.id || 0, alerts: [], has_more: false }),
  '/alerts/rules': () => ({ revision: 0, rules: [
    { id: 'fire-demo', camera_id: 'demo-2', kind: 'fire', enabled: true, popup: true, sound: true, tone: 'urgent', cooldown: 60 },
    { id: 'intrusion-demo', camera_id: 'demo-2', kind: 'intrusion', enabled: true, popup: true, sound: false, tone: 'soft', cooldown: 60 },
  ] }),
  '/events': () => [1, 3, 2, 5, 4, 7].flatMap((hourTotal, hourIndex) =>
    Array.from({ length: hourTotal }, (_, eventIndex) => {
      const camera = cameras[(hourIndex + eventIndex) % cameras.length];
      return { camera_id: camera.id, type: ['count', 'plate', 'count', 'face', 'fire', 'count'][(hourIndex + eventIndex) % 6],
        detail: 'Temsili test olayı', time: new Date(new Date(eventTime).getTime() - (5 - hourIndex) * 60 * 60 * 1000 - eventIndex * 60000).toISOString(), ts_seconds: 12, frame_idx: 60 };
    })).reverse(),   // API gibi: en yeni önce (store.recent_events ORDER BY time DESC)
  '/events/summary': () => ({ hours: 24, cameras: cameras.map((c, i) => ({ camera_id: c.id, count: 34 + i * 12, count_events: 24, plate: 4, face: 0, fire: 0, alerts: i === 1 || i === 2 ? 1 : 0, last: eventTime })) }),
  '/recordings/stats': () => ({ enabled: true, total_bytes: 38 * 1024 ** 3, keep_days: 30,
    cameras: cameras.map((c, i) => ({ camera_id: c.id, segments: 30, bytes: (i + 1) * 256 * 1024 ** 2, oldest: eventTime, newest: new Date().toISOString() })) }),
};
export async function mockAPI(page: Page) {
  await page.addInitScript(() => sessionStorage.setItem('aurasvision-welcome-v1', 'done'));
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api', '');
    if (path === '/snapshot') return route.fulfill({ status: 503, json: { detail: 'Test: görüntü yok' } });
    const body = responses[path]?.() || (path.endsWith('/ack') ? { ok: true } : []);
    await route.fulfill({ status: 200, json: body });
  });
}
