import Icon from './Icon';
import { updated } from './panelData';
import FadeContent from '../react-bits/FadeContent';
import DotGrid from '../react-bits/DotGrid';
import Noise from '../react-bits/Noise';
import StarBorder from '../react-bits/StarBorder';

function SystemStatus({ status, bridge }) {
  const parts = status.data?.bilesenler || [];
  const issues = parts.filter(s => !s.ok);
  let label = 'Kontrol ediliyor';
  if (status.data) label = issues.length ? `${issues.length} bileşen incelenmeli` : 'Bileşenler çalışıyor';
  if (status.error) label = 'Bağlantı sorunu';
  if (status.data && !parts.length) label = 'Durum bilgisi yok';
  const ok = parts.length > 0 && !issues.length && !status.error;
  return <div className="ops-system-tile">
    <div className="ops-system-symbol"><Icon name="pulse" size={28}/></div>
    <span className="ops-eyebrow">SİSTEM DURUMU</span><strong>{label}</strong>
    <span className={`ops-status ${ok ? 'ok' : 'idle'}`}><i/>Son kontrol {updated(status)}</span>
    <button className="ops-link" onClick={() => bridge.go('sys')}>Sistem ayrıntıları <Icon name="arrow" size={15}/></button>
  </div>;
}

export default function PanelHero({ status, bridge }) {
  return <FadeContent><section className="ops-hero"><DotGrid/><Noise patternAlpha={9}/>
    <div className="ops-hero-copy">
      <div className="ops-eyebrow"><span className="ops-mark"/> SAHAYA GENEL BAKIŞ</div>
      <h2>Kontrol sizde.<br/><span>Her an, her noktada.</span></h2>
      <p>Kameralarınız, dikkat bekleyen olaylarınız ve kayıtlarınız.<br className="ops-desktop"/> Günün tamamı için tek çalışma alanı.</p>
      <div className="ops-hero-actions">
        <StarBorder color="#94b5ff" backgroundColor="#2458d8" borderColor="#2458d8" onClick={() => bridge.go('live')}>
          <Icon name="play" size={16}/> Canlı izlemeye geç <Icon name="arrow" size={16}/>
        </StarBorder>
        <button className="ops-link" onClick={() => bridge.go('rec')}>Kayıtları incele <Icon name="arrow" size={15}/></button>
      </div>
    </div><SystemStatus status={status} bridge={bridge}/>
  </section></FadeContent>;
}
