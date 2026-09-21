import Icon from './Icon';
import { updated } from './panelData';
import StarBorder from '../react-bits/StarBorder';

function cameraStatus(health) {
  if (health.error) return { label: 'Platform çalışıyor · kamera durumu alınamadı', tone: 'idle' };
  if (health.data === null) return { label: 'Platform çalışıyor · kamera durumu bekleniyor', tone: 'idle' };
  const issues = health.data.filter(row => window.AurasRuntime.health(row).state !== 'ok').length;
  if (issues) return { label: `Platform çalışıyor · ${issues} kamera incelenmeli`, tone: 'idle' };
  return { label: 'Platform ve kameralar sağlıklı', tone: 'ok' };
}

function systemStatus(status, health) {
  const parts = status.data?.bilesenler || [];
  if (status.error) return { label: 'Sistem bilgisi alınamadı', tone: 'idle' };
  if (!parts.length) return { label: 'Sistem kontrol ediliyor', tone: 'idle' };
  if (!parts.every(part => part.ok)) return { label: 'Sistem incelenmeli', tone: 'idle' };
  return cameraStatus(health);
}

export default function CommandHeader({ status, health, bridge }) {
  const { label, tone } = systemStatus(status, health);
  return <header className="command-header"><div><h2>Görüntü merkezi</h2><p>Kameralar, olaylar ve sistem durumu.</p></div>
    <div className="command-actions"><button className={`command-system ${tone}`} onClick={() => bridge.go('sys')}><i/><span>{label}<small>Son kontrol {updated(status)}</small></span><Icon name="arrow" size={14}/></button>
      <StarBorder color="#c8e2ff" backgroundColor="var(--action)" borderColor="var(--action)" onClick={() => bridge.go('live')}><Icon name="grid" size={16}/> Kamera duvarı <Icon name="arrow" size={16}/></StarBorder></div>
  </header>;
}
