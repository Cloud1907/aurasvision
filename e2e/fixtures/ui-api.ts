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
  '/status': () => ({ bilesenler: [{ ad: 'Veritabanı', ok: true }, { ad: 'Analiz worker', ok: true }, { ad: 'Kayıt', ok: true }] }),
  '/health': () => cameras.map((c, i) => ({ camera_id: c.id, fps: i === 4 ? 0 : 5,
    time: new Date().toISOString().replace('Z', '+00:00'), status: i === 4 ? 'error' : 'ok', detail: i === 4 ? 'Görüntü alınamıyor' : '' })),
  '/counts': () => ({ active: true, rows: cameras.slice(0, 3).map(c => ({ camera_id: c.id, in_count: 34, out_count: 18 })) }),
  '/capabilities': () => ({ fire: { available: false, enabled: false, reason: 'Yangın erken uyarısı pilot kapısı kapalı' } }),
  '/alerts': () => alerts,
  '/events': () => cameras.map((c, i) => ({ camera_id: c.id, type: i === 1 ? 'plate' : 'count',
    detail: 'Temsili test olayı', time: eventTime, ts_seconds: 12, frame_idx: 60 })),
  '/events/summary': () => ({ cameras: cameras.map((c, i) => ({ camera_id: c.id, count: 34 + i * 12, count_events: 24, plate: 4, last: eventTime })) }),
  '/events/trend': () => ({ hours: 24, bucket_minutes: 15, series: [
    { bucket: '2026-09-18T08:00:00+00:00', in_count: 4, out_count: 2 },
    { bucket: '2026-09-18T10:00:00+00:00', in_count: 7, out_count: 5 },
    { bucket: '2026-09-18T12:00:00+00:00', in_count: 3, out_count: 6 },
  ] }),
  '/recordings/stats': () => ({ total_bytes: 38 * 1024 ** 3, keep_days: 30,
    cameras: cameras.map(c => ({ camera_id: c.id, segments: 30, oldest: eventTime })) }),
};
export async function mockAPI(page: Page) {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api', '');
    if (path === '/snapshot') return route.fulfill({ status: 503, json: { detail: 'Test: görüntü yok' } });
    const body = responses[path]?.() || (path.endsWith('/ack') ? { ok: true } : []);
    await route.fulfill({ status: 200, json: body });
  });
}
