import Icon from './Icon';
import ResourceState from './ResourceState';
import { kinds, time, updated, cameraName } from './panelData';
import SpotlightCard from '../react-bits/SpotlightCard';
import AnimatedList from '../react-bits/AnimatedList';

export default function PanelAlerts({ alarms, rows, bridge, onSelect }) {
  return <SpotlightCard className="ops-card ops-alerts" spotlightColor="rgba(53,100,217,.07)">
    <header className="ops-section-head"><div><span className="ops-eyebrow">İnceleme kuyruğu</span><h3>Bekleyen olaylar <span className="ops-badge">{alarms.error ? '—' : alarms.data?.length ?? '—'}</span></h3></div>
      <button className="ops-icon-button" onClick={alarms.retry} aria-label="Alarmları yenile"><Icon name="refresh" size={17}/></button></header>
    <ResourceState resource={alarms} empty={alarms.data?.length === 0} emptyText="Bekleyen uyarı yok">
      <AnimatedList items={alarms.data || []} itemKey={item => item.id} renderItem={a => <button className="ops-alert-row" onClick={() => onSelect(a)}>
        <span className={`ops-event-icon ${a.kind === 'fire_warning' ? 'danger' : 'warning'}`}><Icon name="alert"/></span>
        <span className="ops-row-copy"><strong>{kinds[a.kind] || 'Uyarı'} <span className="ops-inline-tag">İncele</span></strong><span>{a.label || a.ref || 'Ayrıntılar için açın'}</span><small>{cameraName(rows, a.camera_id)} · {time(a.time)}</small></span><Icon name="arrow" size={18}/>
      </button>}/>
    </ResourceState>
    <footer className="ops-card-footer"><span><i className="ops-dot"/> Son başarılı güncelleme {updated(alarms)}</span><button className="ops-link" onClick={() => bridge.go('events')}>Tüm olaylar <Icon name="arrow" size={14}/></button></footer>
  </SpotlightCard>;
}
