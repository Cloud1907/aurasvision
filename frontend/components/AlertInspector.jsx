import { useEffect, useRef, useState } from 'react';
import Icon from './Icon';

export default function AlertInspector({ alert, cameraName, bridge, onClose, onAccepted }) {
  const dialog = useRef(null);
  const [error] = useState('');
  const alive = useRef(true);
  useEffect(() => {
    const previous = document.activeElement;
    dialog.current.showModal();
    return () => { alive.current = false; previous?.focus(); };
  }, []);
  return <dialog className="ops-inspector" ref={dialog} onCancel={onClose} aria-labelledby="inspection-title">
    <header><span className="ops-eyebrow">OLAY İNCELEME</span><button className="ops-icon-button" aria-label="İncelemeyi kapat" onClick={onClose}><Icon name="close"/></button></header>
    <div className="ops-inspector-body"><span className="ops-event-icon warning"><Icon name="alert" size={24}/></span><h2 id="inspection-title">{alert.ref || 'Yeni uyarı'}</h2><p>{alert.label}</p>
      <dl><div><dt>Kamera</dt><dd>{cameraName}</dd></div><div><dt>Olay zamanı</dt><dd>{window.AurasRuntime.parseTime(alert.time)?.toLocaleString('tr-TR') || 'Belirtilmedi'}</dd></div></dl>
      {alert.clip && <video className="ops-evidence" src={bridge.media(alert.clip)} controls autoPlay muted loop playsInline aria-label="Analiz klibi"/>}
      {alert.clip && <p className="ops-hint">Analiz klibi: kişi kutusu ve aşama (izle → ön uyarı → ALARM).</p>}
      <EvidenceImage path={alert.snapshot} bridge={bridge}/>
      <AnalysisTimeline detay={alert.detay} time={alert.time}/>
      {alert.kind === 'fire_warning' && <p className="ops-error">Sertifikalı yangın alarmının yerine geçmez.</p>}
      {error && <p className="ops-error" role="alert">{error}</p>}
    </div>
    <footer><button className="btn pri" onClick={() => bridge.record(alert.camera_id, alert.time)}><Icon name="play" size={16}/> Olay anına git</button><button className="btn" onClick={onClose}>Kapat</button><p>Alarm bir kayıttır; olay anını kayıttan izleyin.</p></footer>
  </dialog>;
}

const ASAMA_AD = { izle: 'İzlemeye alındı', on_uyari: 'ÖN UYARI', alarm: 'ALARM' };
const ASAMA_IM = { izle: '·', on_uyari: '?', alarm: '!' };
const SINIF_AD = { telefon: 'telefon kullanımı', sigara: 'sigara içme' };

/* Analiz zaman çizgisi: ne yakalandı, hangi anda ön uyarı, hangi anda alarm.
   Aşama zamanları alarm anına göre geriye saniyedir (bkz. src/davranis.py:_analiz);
   mutlak saat burada hesaplanır ki kayıt ekranındaki saatle karşılaştırılabilsin. */
function AnalysisTimeline({ detay, time }) {
  let a = null;
  try { a = typeof detay === 'string' ? JSON.parse(detay || 'null') : detay; } catch { a = null; }
  if (!a || !Array.isArray(a.asamalar) || !a.asamalar.length) return null;
  const t0 = window.AurasRuntime.parseTime(time)?.getTime();
  const saat = sn => t0 ? new Date(t0 - (+sn || 0) * 1000).toLocaleTimeString('tr-TR')
    : `alarmdan ${+sn || 0} sn önce`;
  const olcum = [];
  if (a.olcum?.alt_tur) olcum.push(`tanım: ${a.olcum.alt_tur}`);
  if (a.olcum?.dokunus != null) olcum.push(`${a.olcum.dokunus} ağız teması · ${a.olcum.onayli_dokunus || 0} tanesi sigara olarak doğrulandı`);
  return <section className="ops-analysis">
    <h3>Analiz · {SINIF_AD[a.sinif] || a.sinif || 'olay'} <span>güven %{Math.round((a.guven || 0) * 100)}</span></h3>
    <ol>{a.asamalar.map((s, i) => <li key={i} data-asama={s.durum}>
      <b aria-hidden="true">{ASAMA_IM[s.durum] || '·'}</b>
      <div><strong>{ASAMA_AD[s.durum] || s.durum}</strong><span>{s.not}</span></div>
      <time>{saat(s.once_sn)}</time></li>)}</ol>
    <p>doğrulama: {a.dogrulama === 'poz' ? 'yalnız poz (doğrulayıcı kutu yok)' : (a.dogrulama || '—')}
      {' · '}ön uyarıdan alarma {a.sure_sn || 0} sn · kişi {a.izlendi_sn || 0} sn izlendi · iz #{a.iz ?? '—'}
      {olcum.length ? ` · ${olcum.join(' · ')}` : ''}</p>
  </section>;
}

function EvidenceImage({ path, bridge }) {
  const [failed, setFailed] = useState(false), [loaded, setLoaded] = useState(false);
  if (!path || failed) return <div className="ops-evidence-empty"><Icon name="camera" size={28}/><strong>{failed ? 'Kanıt görüntüsü yüklenemedi' : 'Kanıt karesi bulunmuyor'}</strong><span>Olay anını kayıt arşivinde inceleyebilirsiniz.</span></div>;
  return <div>{!loaded && <p role="status">Kanıt görüntüsü yükleniyor…</p>}<img onLoad={() => setLoaded(true)} onError={() => setFailed(true)} className="ops-evidence" src={bridge.media(path)} alt="Olaya ait kanıt görüntüsü"/></div>;
}
