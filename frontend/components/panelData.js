export const kinds = { intrusion: 'Alan ihlali', plate: 'Plaka eşleşmesi', face: 'Yüz eşleşmesi', fire_warning: 'Yangın erken uyarısı' };
export const time = value => window.AurasRuntime.parseTime(value)?.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) || '—';
export const updated = resource => resource.updated ? time(new Date(resource.updated).toISOString()) : '—';
export const cameraName = (rows, id) => rows.find(c => c.id === id)?.name || id || 'Kamera belirtilmedi';
