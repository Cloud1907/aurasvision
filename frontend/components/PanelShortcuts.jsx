import Icon from './Icon';
import GlassIcons from '../react-bits/GlassIcons';
export default function PanelShortcuts({ bridge }) {
  return <section className="ops-card ops-shortcuts"><header className="ops-section-head"><h3>Hızlı erişim</h3><Icon name="grid" size={18}/></header>
    <GlassIcons items={[
      { icon: <Icon name="camera"/>, color: '#286caf', label: 'Kameralar', onClick: () => bridge.go('cams') },
      { icon: <Icon name="clock"/>, color: '#587b9a', label: 'Kayıtlar', onClick: () => bridge.go('rec') },
      { icon: <Icon name="search"/>, color: '#5e8782', label: 'Arama', onClick: () => bridge.go('arama') },
    ]}/>
  </section>;
}
export function ArchiveSummary({ archive, bridge }) {
  let label = 'Arşiv bilgisi alınıyor';
  if (archive.data) label = `${((archive.data.total_bytes || 0) / 1024 ** 3).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} GB · ${archive.data.keep_days || '—'} gün saklama`;
  if (archive.error) label = 'Bilgi alınamadı';
  return <section className="ops-archive"><span className="ops-archive-icon"><Icon name="disk" size={23}/></span><div><strong>Kayıt arşivi</strong><span>{label}</span></div><button className="ops-icon-button" aria-label="Kayıt arşivini aç" onClick={() => bridge.go('rec')}><Icon name="arrow" size={18}/></button></section>;
}
