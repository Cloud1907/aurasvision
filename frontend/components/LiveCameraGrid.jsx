import { useEffect, useRef, useState } from 'react';
import Icon from './Icon';
import { useResource } from '../hooks/useResource';

/* Karo katmanları (kullanıcı isteği 2026-09-23): kameranın üstünde hangi analizlerin
   açık olduğu, bekleyen alarm sayısı ve sayım çizgisi/ihlal/yangın alanı görünsün;
   her katman kapatılabilsin. Tercih tarayıcıda kalır. */
const KATMAN_KEY = 'aurasvision-panel-katman-v1';
const GOREV_AD = { count: 'Sayım', plate: 'Plaka', face: 'Yüz', fire: 'Yangın', telefon: 'Telefon', sigara: 'Sigara' };
const ALARM_AD = { intrusion: 'İhlal', plate: 'Plaka', face: 'Yüz', fire_warning: 'Yangın', telefon: 'Telefon', sigara: 'Sigara' };
const ZONE_COL = { line: '#22d3ee', zone: '#a78bfa', intrusion: '#f87171', fire: '#fb923c', firemask: '#6b7280' };

export function katmanOku() {
  const vars = { gorevler: true, alarmlar: true, cizgiler: true };
  try { return { ...vars, ...(JSON.parse(localStorage.getItem(KATMAN_KEY) || '{}')) }; } catch (e) { return vars; }
}

function ZoneOverlay({ zones }) {
  if (!zones || !zones.length) return null;
  return <svg className="zone-ov" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
    {zones.map((z, i) => {
      const pts = (z.points || []).map(p => `${(+p[0]).toFixed(4)},${(+p[1]).toFixed(4)}`).join(' ');
      if (!pts) return null;
      const c = ZONE_COL[z.kind] || ZONE_COL.line;
      return z.kind === 'line'
        ? <polyline key={i} points={pts} fill="none" stroke={c} strokeWidth="0.006"/>
        : <polygon key={i} points={pts} fill={c} fillOpacity="0.14" stroke={c} strokeWidth="0.005"/>;
    })}
  </svg>;
}

function KaroRozetleri({ camera, alarmlar, katman }) {
  const gorevler = Object.keys(GOREV_AD).filter(k => (camera.tasks || {})[k]);
  const bekleyen = alarmlar.filter(a => a.camera_id === camera.id);
  const turler = [...new Set(bekleyen.map(a => ALARM_AD[a.kind] || a.kind))];
  if (!(katman.gorevler && gorevler.length) && !(katman.alarmlar && bekleyen.length)) return null;
  return <span className="monitor-badges" aria-label="Kamera katmanları">
    {katman.alarmlar && bekleyen.length > 0 && <span className="monitor-alarm" title={`Bekleyen alarm: ${turler.join(', ')}`}>
      <Icon name="alert" size={11}/> {bekleyen.length} {turler.slice(0, 2).join(' · ')}</span>}
    {katman.gorevler && gorevler.map(k => <span key={k} className="monitor-task">{GOREV_AD[k]}</span>)}
  </span>;
}

function SnapshotCard({ camera, bridge, zones }) {
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
    {state === 'ready' && <ZoneOverlay zones={zones}/>}
  </div>;
}

function LiveCard({ camera, bridge, zones, alarmlar, katman }) {
  const live = bridge.live?.();
  return <button className="monitor-card tile" data-state="wait" onClick={() => bridge.openCamera(camera.id, camera.name)}>
    {live ? <div className="monitor-visual"><div className="skel"/><auras-stream data-src={camera.url_sub ? `${camera.id}-sub` : camera.id}/><span className="nosig"><Icon name="camera" size={18}/> Sinyal yok</span>{katman.cizgiler && <ZoneOverlay zones={zones}/>}</div> : <SnapshotCard camera={camera} bridge={bridge} zones={katman.cizgiler ? zones : null}/>}
    <KaroRozetleri camera={camera} alarmlar={alarmlar} katman={katman}/> 
    <span className="monitor-meta"><span><i/><strong>{camera.name}</strong></span><small>{live ? 'Canlı izleme' : 'Son görüntü'}</small></span>
  </button>;
}

export default function LiveCameraGrid({ cameras, bridge, alarms }) {
  const [expanded, setExpanded] = useState(false);
  const [katman, setKatman] = useState(katmanOku);
  const zonesAll = useResource(bridge, '/zones/all', 60000);
  const rows = cameras.data || [];
  const alarmlar = (alarms && alarms.data) || [];
  const katmanDegis = (k) => setKatman(prev => {
    const next = { ...prev, [k]: !prev[k] };
    try { localStorage.setItem(KATMAN_KEY, JSON.stringify(next)); } catch (e) { /* özel pencere */ }
    return next;
  });
  const visible = expanded ? rows : rows.slice(0, 4);
  // Oynatıcı bir kez bağlanır: kart başına çağrı N kez tam tarama demekti.
  useEffect(() => { if (bridge.live?.()) bridge.mountStreams?.(); }, [visible.length, bridge]);
  return <section className="live-monitoring" aria-label="Canlı kamera izleme">
    <header><div><span className="section-live-dot"/><h3>Canlı kamera izleme</h3><span>{rows.length} kamera</span></div>
      <span className="monitor-layers" role="group" aria-label="Karo katmanları">
        {[['gorevler', 'Görevler'], ['alarmlar', 'Alarmlar'], ['cizgiler', 'Çizgiler']].map(([k, ad]) =>
          <label key={k} className={`monitor-layer ${katman[k] ? 'on' : ''}`}><input type="checkbox" checked={!!katman[k]} onChange={() => katmanDegis(k)}/>{ad}</label>)}
      </span>
      {rows.length > 4 && <button className="ops-link" onClick={() => setExpanded(value => !value)}>{expanded ? 'Öncelikli kameralar' : 'Tüm kameraları göster'} <Icon name="arrow" size={14}/></button>}</header>
    {cameras.error ? <div className="monitor-state">Kamera listesi alınamadı. <button className="ops-link" onClick={cameras.retry}>Yeniden dene</button></div>
      : visible.length ? <div className="monitor-grid">{visible.map(camera => <LiveCard key={camera.id} camera={camera} bridge={bridge} zones={(zonesAll.data || {})[camera.id]} alarmlar={alarmlar} katman={katman}/>)}</div>
        : <div className="monitor-state">Henüz kamera tanımlanmadı.</div>}
  </section>;
}
