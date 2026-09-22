import { useEffect, useRef, useState } from 'react';
import Icon from './Icon';

function SnapshotCard({ camera, bridge }) {
  const root = useRef(null);
  const [state, setState] = useState('waiting');
  useEffect(() => {
    const el = root.current;
    const ready = () => setState('ready');
    const failed = () => setState('error');
    el.addEventListener('snapshotready', ready);
    el.addEventListener('snapshoterror', failed);
    const stop = window.AurasRuntime.snapshots(el, bridge.snapshot, 5000);
    return () => {
      stop();
      el.removeEventListener('snapshotready', ready);
      el.removeEventListener('snapshoterror', failed);
    };
  }, [camera.id, bridge]);
  return <div className={`monitor-visual ${state}`} ref={root}>
    <img data-snapshot={camera.id} alt={`${camera.name} kamera görüntüsü`}/>
    {state !== 'ready' && <div className="monitor-empty"><Icon name="camera" size={28}/><span>{state === 'error' ? 'Görüntü alınamadı' : 'Görüntü bekleniyor'}</span></div>}
  </div>;
}

function LiveCard({ camera, bridge }) {
  const live = bridge.live?.();
  useEffect(() => {
    if (live) bridge.mountStreams?.();
  }, [live, camera.id, bridge]);
  return <button className="monitor-card tile" data-state="wait" onClick={() => bridge.openCamera(camera.id, camera.name)}>
    {live ? <div className="monitor-visual"><div className="skel"/><auras-stream data-src={camera.url_sub ? `${camera.id}-sub` : camera.id}/><span className="nosig"><Icon name="camera" size={18}/> Sinyal yok</span></div> : <SnapshotCard camera={camera} bridge={bridge}/>} 
    <span className="monitor-meta"><span><i/><strong>{camera.name}</strong></span><small>{live ? 'Canlı izleme' : 'Son görüntü'}</small></span>
  </button>;
}

export default function LiveCameraGrid({ cameras, bridge }) {
  const [expanded, setExpanded] = useState(false);
  const rows = cameras.data || [];
  const visible = expanded ? rows : rows.slice(0, 4);
  return <section className="live-monitoring" aria-label="Canlı kamera izleme">
    <header><div><span className="section-live-dot"/><h3>Canlı kamera izleme</h3><span>{rows.length} kamera</span></div>
      {rows.length > 4 && <button className="ops-link" onClick={() => setExpanded(value => !value)}>{expanded ? 'Öncelikli kameralar' : 'Tüm kameraları göster'} <Icon name="arrow" size={14}/></button>}</header>
    {cameras.error ? <div className="monitor-state">Kamera listesi alınamadı. <button className="ops-link" onClick={cameras.retry}>Yeniden dene</button></div>
      : visible.length ? <div className="monitor-grid">{visible.map(camera => <LiveCard key={camera.id} camera={camera} bridge={bridge}/>)}</div>
        : <div className="monitor-state">Henüz kamera tanımlanmadı.</div>}
  </section>;
}
