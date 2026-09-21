import Icon from './Icon';
import ResourceState from './ResourceState';
import SpotlightCard from '../react-bits/SpotlightCard';

function CameraRow({ camera, health, bridge }) {
  const stale = { state: 'idle', label: 'Sağlık bilgisi güncellenemedi' };
  const status = health.error ? stale : window.AurasRuntime.health((health.data || []).find(r => r.camera_id === camera.id));
  return <button className="ops-camera-row" onClick={() => bridge.openCamera(camera.id, camera.name)}>
    <span className="ops-camera-icon"><Icon name="camera" size={19}/></span><span><strong>{camera.name}</strong><small>{status.label}</small></span><i className={`ops-health-dot ${status.state}`}/>
  </button>;
}
export default function PanelCameras({ cameras, health, bridge }) {
  const rank = c => ({ error: 0, idle: 1, ok: 2 }[window.AurasRuntime.health((health.data || []).find(h => h.camera_id === c.id)).state]);
  const rows = [...(cameras.data || [])].sort((a, b) => rank(a) - rank(b));
  const issues = rows.filter(c => rank(c) < 2).length;
  return <SpotlightCard className="ops-card" spotlightColor="rgba(53,100,217,.05)">
    <header className="ops-section-head"><div><span className="ops-eyebrow">Bağlantı durumu</span><h3>Kameralar</h3>{issues > 0 && !health.error && <span className="ops-caption">{issues} nokta incelenmeli</span>}</div><Icon name="camera" size={19}/></header>
    <ResourceState resource={cameras} empty={!rows.length} emptyText="İlk kameranızı ekleyin">
      {health.error && <div className="ops-error">Sağlık bilgisi alınamadı. <button onClick={health.retry}>Yeniden dene</button></div>}
      <div className="ops-camera-list">{rows.slice(0, 6).map(c => <CameraRow camera={c} health={health} bridge={bridge} key={c.id}/>)}</div>
    </ResourceState>
    <footer className="ops-card-footer"><span>{rows.length} tanımlı kamera</span><button className="ops-link" onClick={() => bridge.go('cams')}>Yönet <Icon name="arrow" size={14}/></button></footer>
  </SpotlightCard>;
}
