import { useState } from 'react';
import Icon from './Icon';
import ResourceState from './ResourceState';
import { kinds, time, updated, cameraName } from './panelData';
import SpotlightCard from '../react-bits/SpotlightCard';
import AnimatedList from '../react-bits/AnimatedList';
import QueueProgress from './QueueProgress';

export default function PanelAlerts({ alarms, rows, bridge, onSelect }) {
  const [filter, setFilter] = useState('all');
  const all = alarms.data || [];
  const critical = all.filter(alert => alert.kind === 'fire_warning' || alert.kind === 'intrusion' || alert.list_type === 'blacklist');
  const visible = filter === 'critical' ? critical : all;
  return <SpotlightCard className="ops-card ops-alerts" spotlightColor="rgba(53,100,217,.07)">
    <header className="ops-section-head"><div><span className="ops-eyebrow">İNCELEME KUYRUĞU</span><h3>Aktif alarmlar <span className="ops-badge">{alarms.error ? '—' : all.length}</span></h3></div>
      <button className={`ops-icon-button${alarms.loading ? ' is-loading' : ''}`} onClick={alarms.retry} disabled={alarms.loading} aria-label="Alarmları yenile" aria-busy={alarms.loading}><Icon name="refresh" size={17}/></button></header>
    <div className="alert-filters" role="group" aria-label="Alarm filtresi"><button aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>Tümü <span>{all.length}</span></button><button aria-pressed={filter === 'critical'} onClick={() => setFilter('critical')}>Kritik <span>{critical.length}</span></button></div>
    {alarms.loading ? <QueueProgress hasPreviousData={alarms.data !== null}/> : <ResourceState resource={alarms} empty={visible.length === 0} emptyText={filter === 'critical' ? 'Kritik alarm yok' : 'Bekleyen uyarı yok'}>
      <AnimatedList items={visible} itemKey={item => item.id} renderItem={a => <button className="ops-alert-row" onClick={() => onSelect(a)}>
        <span className={`ops-event-icon ${a.kind === 'fire_warning' ? 'danger' : 'warning'}`}><Icon name="alert"/></span>
        <span className="ops-row-copy"><strong>{kinds[a.kind] || 'Uyarı'} <span className="ops-inline-tag">İncele</span></strong><span>{a.label || a.ref || 'Ayrıntılar için açın'}</span><small>{cameraName(rows, a.camera_id)} · {time(a.time)}</small></span><Icon name="arrow" size={18}/>
      </button>}/>
    </ResourceState>}
    <footer className="ops-card-footer"><span><i className="ops-dot"/> Son başarılı güncelleme {updated(alarms)}</span><button className="ops-link" onClick={() => bridge.go('events')}>Tüm olaylar <Icon name="arrow" size={14}/></button></footer>
  </SpotlightCard>;
}
