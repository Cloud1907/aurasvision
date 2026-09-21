import Icon from './Icon';
import ResourceState from './ResourceState';
import { time, cameraName } from './panelData';
import SpotlightCard from '../react-bits/SpotlightCard';
const labels = { count: 'Çizgi geçişi', plate: 'Plaka okuma', fire: 'Yangın erken uyarısı' };
export default function PanelActivity({ events, rows, bridge }) {
  return <SpotlightCard className="ops-card" spotlightColor="rgba(53,100,217,.05)">
    <header className="ops-section-head"><div><span className="ops-eyebrow">Son hareketler</span><h3>Olay akışı</h3></div><span className="ops-caption">En son 5 olay</span></header>
    <ResourceState resource={events} empty={events.data?.length === 0} emptyText="Henüz olay kaydedilmedi">
      <div className="ops-activity">{(events.data || []).slice(0, 5).map((e, i) => <button className="ops-activity-row" key={`${e.time}-${e.camera_id}-${i}`} onClick={() => bridge.record(e.camera_id, e.time)}>
        <span className="ops-time">{time(e.time)}</span><span className="ops-activity-dot"/><span><strong>{cameraName(rows, e.camera_id)}</strong><small>{e.detail || labels[e.type] || 'Yeni olay'}</small></span><Icon name="arrow" size={15}/>
      </button>)}</div>
    </ResourceState>
  </SpotlightCard>;
}
