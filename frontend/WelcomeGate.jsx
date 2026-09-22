import { useEffect, useMemo, useRef, useState } from 'react';
import Icon from './components/Icon';
import DomeGallery from './components/DomeGallery';

// Kubbe karoları: web/assets/kapi altındaki yerel görseller (köken: KAYNAK.md).
// Dış ağa istek atılmaz; internetsiz kurulumda da görünür.
const TILE_COUNT = 20;

export default function WelcomeGate({ onEnter }) {
  const [leaving, setLeaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const loginRef = useRef(null);
  useEffect(() => { loginRef.current?.focus(); }, []);
  const images = useMemo(() => Array.from({ length: TILE_COUNT }, (_, i) => ({
    src: `/static/assets/kapi/kapi-${String(i + 1).padStart(2, '0')}.webp`,
    alt: '',
  })), []);

  const enter = () => {
    if (busy) return;
    setBusy(true); setLeaving(true);
    setTimeout(onEnter, 330);
  };

  return <section className={`welcome-gate${leaving ? ' leaving' : ''}`} aria-labelledby="welcome-title">
    <div className="welcome-visual">
      <div className="welcome-dome-pro" aria-hidden="true">
        <DomeGallery images={images} interactive={false} fit={1.05} fitBasis="max"
          minRadius={520} maxRadius={1500} padFactor={0} overlayBlurColor="#070a10"
          maxVerticalRotationDeg={5} dragSensitivity={18} dragDampening={0.8} segments={26}
          autoRotateDegPerSec={0.55}
          grayscale={false} imageBorderRadius="14px" openedImageBorderRadius="14px"/>
      </div>
      <div className="welcome-scrim" aria-hidden="true"/>
      <span className="welcome-drag-hint" aria-hidden="true"><i/>SÜRÜKLEYİN</span>
      <div className="welcome-brand"><span className="welcome-brand-mark"><Icon name="live" size={22}/></span><span>AURASVISION<small>GÖRÜNTÜ ANALİTİĞİ</small></span></div>
      <div className="welcome-hero"><span className="welcome-kicker"><i/> Akıllı operasyon merkezi</span>
        <h1>Saatlerce ekran yok.<em>Görüntünün arkası var.</em></h1>
        <p>Kameraları sistem izler, anlamlı olanı ayıklar ve bir şey olduğunda sizi çağırır.</p></div>
    </div>
    <div className="welcome-auth"><div className="welcome-auth-card">
      <span className="welcome-auth-eyebrow">Güvenli çalışma alanı</span>
      <h2 id="welcome-title">Operasyon merkezine hoş geldiniz.</h2>
      <p>Sahanızda ne olduğunu görmek ve olayları yönetmek için devam edin.</p>
      <button ref={loginRef} className="welcome-login-button" type="button" disabled={busy} onClick={enter}><span>{busy ? 'Panel hazırlanıyor' : 'Giriş yap'}</span><span aria-hidden="true">→</span></button>
      <div className="welcome-trust"><i/><span>Yerel sistem · Güvenli oturum · Kesintisiz izleme</span></div>
    </div></div>
  </section>;
}
