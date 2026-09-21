import Icon from './Icon';

const WIDTH = 720;
const HEIGHT = 176;
const PAD = { left: 34, right: 12, top: 18, bottom: 28 };

function pathFor(rows, key, max) {
  const usableW = WIDTH - PAD.left - PAD.right;
  const usableH = HEIGHT - PAD.top - PAD.bottom;
  return rows.map((row, index) => {
    const x = PAD.left + (rows.length === 1 ? usableW / 2 : index / (rows.length - 1) * usableW);
    const y = PAD.top + usableH - Number(row[key] || 0) / max * usableH;
    return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}

function hour(value) {
  const date = new Date(String(value).replace(' ', 'T') + (String(value).includes('+') ? '' : 'Z'));
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
}

export default function PanelTrend({ trend }) {
  const rows = trend.data?.series || [];
  const maximum = Math.max(1, ...rows.flatMap(row => [Number(row.in_count || 0), Number(row.out_count || 0)]));
  const inTotal = rows.reduce((sum, row) => sum + Number(row.in_count || 0), 0);
  const outTotal = rows.reduce((sum, row) => sum + Number(row.out_count || 0), 0);
  return <section className="ops-trend" aria-label="24 saatlik geçiş eğilimi">
    <header className="ops-section-head"><div><span className="ops-eyebrow">Hareket ritmi</span><h3>24 saatlik geçiş eğilimi</h3></div>
      <div className="ops-trend-legend" aria-label="Toplamlar"><span className="in">Giriş <b>{inTotal.toLocaleString('tr-TR')}</b></span><span className="out">Çıkış <b>{outTotal.toLocaleString('tr-TR')}</b></span></div></header>
    {trend.error ? <div className="ops-trend-state ops-error" role="status"><Icon name="alert"/><span><strong>Trend verisi alınamadı</strong><small>Son 24 saatlik seri şu anda güncellenemiyor.</small></span><button onClick={trend.retry}>Yeniden dene</button></div>
      : trend.data === null ? <div className="ops-skeleton" role="status" aria-label="Trend yükleniyor"><i/><i/><i/></div>
      : rows.length === 0 ? <div className="ops-trend-state ops-empty"><Icon name="pulse"/><span><strong>Henüz çizgi geçişi yok</strong><small>İlk giriş veya çıkış olayı burada görünecek.</small></span></div>
      : <div className="ops-trend-chart"><svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Giriş ve çıkış sayılarının son 24 saatteki değişimi" preserveAspectRatio="none">
          <title>Son 24 saatte giriş ve çıkış eğilimi</title>
          {[0, .5, 1].map(level => <line className="grid" key={level} x1={PAD.left} x2={WIDTH - PAD.right} y1={PAD.top + level * (HEIGHT - PAD.top - PAD.bottom)} y2={PAD.top + level * (HEIGHT - PAD.top - PAD.bottom)}/>)}
          <path data-series="in" className="series in" d={pathFor(rows, 'in_count', maximum)}/>
          <path data-series="out" className="series out" d={pathFor(rows, 'out_count', maximum)}/>
          <text x="2" y={PAD.top + 4}>{maximum}</text><text x="16" y={HEIGHT - PAD.bottom + 4}>0</text>
          <text className="time" x={PAD.left} y={HEIGHT - 6}>{hour(rows[0].bucket)}</text>
          <text className="time end" x={WIDTH - PAD.right} y={HEIGHT - 6}>{hour(rows.at(-1).bucket)}</text>
        </svg></div>}
  </section>;
}
