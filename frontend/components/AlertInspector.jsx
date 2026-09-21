import { useEffect, useRef, useState } from 'react';
import Icon from './Icon';

export default function AlertInspector({ alert, cameraName, bridge, onClose, onAccepted }) {
  const dialog = useRef(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const alive = useRef(true);
  useEffect(() => {
    const previous = document.activeElement;
    dialog.current.showModal();
    return () => { alive.current = false; previous?.focus(); };
  }, []);
  const accept = async () => {
    setBusy(true); setError('');
    try {
      // Mutation yaşam döngüsü ekranın GET iptalinden bağımsızdır.
      await bridge.api(`/alerts/${alert.id}/ack`, { method: 'POST' });
      if (alive.current) onAccepted();
    } catch (e) { if (alive.current) { setError(e.message); setBusy(false); } }
  };
  return <dialog className="ops-inspector" ref={dialog} onCancel={onClose} aria-labelledby="inspection-title">
    <header><span className="ops-eyebrow">OLAY İNCELEME</span><button className="ops-icon-button" aria-label="İncelemeyi kapat" onClick={onClose}><Icon name="close"/></button></header>
    <div className="ops-inspector-body"><span className="ops-event-icon warning"><Icon name="alert" size={24}/></span><h2 id="inspection-title">{alert.ref || 'Yeni uyarı'}</h2><p>{alert.label}</p>
      <dl><div><dt>Kamera</dt><dd>{cameraName}</dd></div><div><dt>Olay zamanı</dt><dd>{window.AurasRuntime.parseTime(alert.time)?.toLocaleString('tr-TR') || 'Belirtilmedi'}</dd></div><div><dt>Durum</dt><dd>Operatör incelemesi bekliyor</dd></div></dl>
      <EvidenceImage path={alert.snapshot} bridge={bridge}/>
      {alert.kind === 'fire_warning' && <p className="ops-error">Sertifikalı yangın alarmının yerine geçmez.</p>}
      {error && <p className="ops-error" role="alert">{error}</p>}
    </div>
    <footer><button className="btn pri" onClick={() => bridge.record(alert.camera_id, alert.time)}><Icon name="play" size={16}/> Olay anına git</button><button className="btn" disabled={busy} onClick={accept}>{busy ? 'Kaydediliyor…' : 'Gördüm, kabul et'}</button><p>Önce olay anını inceleyin. Kabul, uyarıyı gördüğünüzü kaydeder; sorunun çözüldüğü anlamına gelmez.</p></footer>
  </dialog>;
}

function EvidenceImage({ path, bridge }) {
  const [failed, setFailed] = useState(false), [loaded, setLoaded] = useState(false);
  if (!path || failed) return <div className="ops-evidence-empty"><Icon name="camera" size={28}/><strong>{failed ? 'Kanıt görüntüsü yüklenemedi' : 'Kanıt karesi bulunmuyor'}</strong><span>Olay anını kayıt arşivinde inceleyebilirsiniz.</span></div>;
  return <div>{!loaded && <p role="status">Kanıt görüntüsü yükleniyor…</p>}<img onLoad={() => setLoaded(true)} onError={() => setFailed(true)} className="ops-evidence" src={bridge.media(path)} alt="Olaya ait kanıt görüntüsü"/></div>;
}
