import { useEffect, useRef, useState } from 'react';
import Icon from './Icon';
import { time } from './panelData';
import DotGrid from '../react-bits/DotGrid';
import StarBorder from '../react-bits/StarBorder';
import FadeContent from '../react-bits/FadeContent';

function Preview({ camera, bridge }) {
  const root = useRef(null);
  const [image, setImage] = useState({ state: 'waiting', updated: null });
  useEffect(() => {
    const el = root.current;
    const ready = e => setImage({ state: 'ready', updated: e.target.dataset.updated });
    const failed = () => setImage({ state: 'error', updated: null });
    el.addEventListener('snapshotready', ready); el.addEventListener('snapshoterror', failed);
    const stop = window.AurasRuntime.snapshots(el, bridge.snapshot, 10000);
    return () => { stop(); el.removeEventListener('snapshotready', ready); el.removeEventListener('snapshoterror', failed); };
  }, [camera.id, bridge]);
  return <div className={`camera-preview ${image.state}`} ref={root}>
    <img data-snapshot={camera.id} alt={`${camera.name} son kamera karesi`}/>
    {image.state !== 'ready' && <div className="camera-placeholder"><DotGrid/><div className="camera-empty-icon"><Icon name="camera" size={32}/></div>
      <strong>{image.state === 'error' ? 'Görüntü alınamadı' : 'Görüntü bekleniyor'}</strong><span>{image.state === 'error' ? 'Kamera bağlantısını kontrol edin. Otomatik yeniden denenecek.' : 'Kameradan en son kare isteniyor.'}</span>
    </div>}
    <div className="camera-hud"><span data-testid="preview-mode"><i/>{({ ready: 'SON KARE', error: 'GÖRÜNTÜ YOK', waiting: 'BAĞLANIYOR' })[image.state]}</span><span>{image.updated ? time(image.updated) : '—'}</span></div>
  </div>;
}
export default function CameraStage({ cameras, bridge, camera, onCamera }) {
  const rows = cameras.data || [];
  return <section className="camera-stage" aria-label="Seçili kamera görüntüsü">
    <header><div className="camera-stage-label"><span className="ops-eyebrow">Kamera</span><h3>{camera?.name || 'Kamera çalışma alanı'}</h3></div><span className="camera-preview-type">Son görüntü</span></header>
    {camera ? <FadeContent key={camera.id}><Preview camera={camera} bridge={bridge}/></FadeContent> : <div className="camera-preview camera-placeholder"><Icon name="camera" size={42}/><strong>{cameras.error ? 'Kamera listesi alınamadı' : 'Kamera bekleniyor'}</strong><button className="ops-link" onClick={cameras.retry}>Yeniden dene</button></div>}
    <footer><span><Icon name="pulse" size={15}/> Önizleme 10 saniyede bir yenilenir</span><StarBorder color="#c8e2ff" backgroundColor="var(--action)" borderColor="var(--action)" disabled={!camera} onClick={() => bridge.openCamera(camera.id, camera.name)}><Icon name="play" size={14}/> Canlı akışı aç <Icon name="arrow" size={14}/></StarBorder></footer>
    {rows.length > 8 && <label className="camera-picker"><span>Kameraya git</span><select aria-label="Kameraya git" value={camera?.id || ''} onChange={event => onCamera(event.target.value)}>{rows.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>}
    <div className="camera-tabs" role="tablist" aria-label="Kamera seçimi">{rows.map((c, i) => <button key={c.id} role="tab" tabIndex={c.id === camera?.id ? 0 : -1} onKeyDown={e => selectByKey(e, i, rows, onCamera)} aria-selected={c.id === camera?.id} onClick={() => onCamera(c.id)}><span>{String(i + 1).padStart(2, '0')}</span><Icon name="camera" size={16}/><strong>{c.name}</strong><i/></button>)}</div>
  </section>;
}

function selectByKey(event, index, rows, onCamera) {
  const next = { ArrowRight: (index + 1) % rows.length, ArrowLeft: (index - 1 + rows.length) % rows.length, Home: 0, End: rows.length - 1 }[event.key];
  if (next === undefined) return;
  event.preventDefault(); onCamera(rows[next].id);
  event.currentTarget.parentElement.children[next].focus();
}
