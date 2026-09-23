import Icon from './Icon';
import { cameraName } from './panelData';

const eventNames = { count: 'Geçiş', plate: 'Plaka', face: 'Yüz', fire: 'Yangın erken uyarısı' };

function Metric({ icon, label, value, hint, tone = '' }) {
  return <div className={`ops-metric ops-kpi ${tone}`}>
    <span className="ops-metric-label"><Icon name={icon} size={17}/>{label}</span>
    <strong className="ops-metric-value">{value}</strong>
    <span className="ops-caption">{hint}</span>
  </div>;
}

export default function PanelMetrics({ cameras, status, alarms, events, archive }) {
  const parts = status.data?.bilesenler || [];
  const worker = parts.find(part => part.ad === 'Analiz worker');
  const issue = parts.find(part => !part.ok);
  const workerValue = status.error || !status.data ? '—' : worker ? (worker.ok ? 'Çalışıyor' : 'İncelenmeli') : (issue ? 'İncelenmeli' : 'Doğrulanamadı');
  const workerHint = status.error ? 'Durum alınamadı' : worker ? (worker.detay || (worker.ok ? 'Analiz hattı sağlıklı' : 'Analiz hattı incelenmeli')) : (issue ? `${issue.ad} incelenmeli` : 'Analiz worker durumu bulunamadı');

  // Kabul/onay akışı kaldırıldı: metrik son 24 saatin alarm sayısıdır
  const esik = Date.now() - 24 * 3600000;
  const pending = alarms.data ? alarms.data.filter(a => (window.AurasRuntime.parseTime(a.time)?.getTime() || 0) >= esik).length : undefined;
  const pendingValue = alarms.error || pending === undefined ? '—' : pending.toLocaleString('tr-TR');
  const pendingHint = alarms.error ? 'Güncellenemedi' : pending === undefined ? 'Alarm listesi yükleniyor' : 'Son 24 saatte üretilen alarm';
  const latest = events.data?.[0];
  const latestDate = window.AurasRuntime.parseTime(latest?.time);
  const latestValue = events.error || !events.data ? '—' : latest
    ? latestDate?.toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) || '—' : 'Yok';
  const latestHint = events.error ? 'Olay akışı alınamadı' : latest
    ? `${eventNames[latest.type] || 'Olay'} · ${cameraName(cameras.data || [], latest.camera_id)}` : 'Henüz olay kaydedilmedi';

  const all = cameras.data || [];
  const recordable = all.filter(camera => camera.enabled !== false && camera.tasks?.record !== false);
  const stats = archive.data;
  let recordValue = '—', recordHint = 'Kayıt durumu alınıyor';
  if (archive.error || cameras.error) recordHint = 'Kayıt kapsamı doğrulanamadı';
  else if (stats && cameras.data) {
    if (stats.enabled === false) { recordValue = 'Kapalı'; recordHint = 'Kayıt servisi etkin değil'; }
    else if (stats.enabled !== true) recordHint = 'Kayıt servisinin durumu bilinmiyor';
    else if (!recordable.length) { recordValue = 'Kapalı'; recordHint = 'Kayıt görevi açık kamera yok'; }
    else {
      const newest = new Map((stats.cameras || []).map(row => [row.camera_id, window.AurasRuntime.parseTime(row.newest)]));
      const timestamps = recordable.map(camera => newest.get(camera.id));
      if (timestamps.every(value => !value)) recordHint = 'Son kayıt zamanı doğrulanamadı';
      else {
        const active = timestamps.filter(value => {
          const age = value ? Date.now() - value.getTime() : Infinity;
          return age >= 0 && age < 300000;
        }).length;
        recordValue = `${active}/${recordable.length}`;
        recordHint = 'Son 5 dakikada kayıt üreten';
      }
    }
  }

  return <div className="ops-metrics" aria-label="Operasyon göstergeleri">
    <Metric icon="camera" label="Analiz hattı" value={workerValue} hint={workerHint} tone={worker?.ok === false ? 'warning' : ''}/>
    <Metric icon="alert" label="Alarm · son 24 saat" value={pendingValue} hint={pendingHint} tone={pending > 0 ? 'warning' : ''}/>
    <Metric icon="clock" label="Son olay" value={latestValue} hint={latestHint}/>
    <Metric icon="disk" label="Kayıt kapsamı" value={recordValue} hint={recordHint}/>
  </div>;
}
