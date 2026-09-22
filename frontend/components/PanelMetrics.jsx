import Icon from './Icon';
import SpotlightCard from '../react-bits/SpotlightCard';
import SplitFlapText from '../react-bits/SplitFlapText';

function Metric({ icon, label, value, resource, hint, tone = '' }) {
  const valid = resource.data !== null && !resource.error;
  const display = !valid ? '—' : typeof value === 'number' ? value.toLocaleString('tr-TR') : value;
  return <SpotlightCard className={`ops-metric ${tone} ${resource.error ? "is-stale" : ""}`} spotlightColor="rgba(53,100,217,.06)">
    <div className="ops-metric-label"><Icon name={icon} size={17}/>{label}</div>
    <div className="ops-metric-value"><SplitFlapText value={display}/></div>
    <span className="ops-caption">{resource.error ? 'Güncellenemedi · yeniden deneyin' : hint}</span>
  </SpotlightCard>;
}
export default function PanelMetrics({ cameras, health, alarms, totals }) {
  const healthy = (health.data || []).filter(h => window.AurasRuntime.health(h).state === 'ok').length;
  const total = (totals.data?.cameras || []).reduce((n, r) => n + Number(r.count || 0), 0);
  const critical = (alarms.data || []).filter(alert => alert.kind === 'fire_warning' || alert.kind === 'intrusion' || alert.list_type === 'blacklist').length;
  return <div className="ops-metrics">
    <Metric icon="camera" label="Kameralar çevrimiçi" value={`${healthy}/${cameras.data?.length || 0}`} resource={cameras} hint="Son sağlık kontrolü"/>
    <Metric icon="grid" label="Bugünkü olaylar" value={total} resource={totals} hint="Son 24 saatte kaydedildi"/>
    <Metric icon="alert" label="Aktif alarmlar" value={alarms.data?.length || 0} resource={alarms} tone="warning" hint="Operatör incelemesi bekliyor"/>
    <Metric icon="alert" label="Kritik alarmlar" value={critical} resource={alarms} tone="danger" hint="Öncelikli müdahale"/>
  </div>;
}
