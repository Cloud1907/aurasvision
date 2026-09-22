import { useId, useMemo, useState } from 'react';
import { cameraName } from './panelData';

// Olay türleri sabit sırada: renk varlığa bağlıdır, sıralamaya değil.
export const TYPES = [
  { key: 'count', label: 'Geçiş', tone: 'one', field: 'count_events' },
  { key: 'plate', label: 'Plaka', tone: 'two', field: 'plate' },
  { key: 'face', label: 'Yüz', tone: 'three', field: 'face' },
  { key: 'fire', label: 'Yangın', tone: 'four', field: 'fire' },
];
const STEPS = [15, 30, 60, 180, 360, 720, 1440].map(minutes => minutes * 60000);
const BOX = { w: 640, h: 190, l: 30, r: 12, t: 18, b: 24 };
const PLOT = { w: BOX.w - BOX.l - BOX.r, h: BOX.h - BOX.t - BOX.b };
const SLOT_LIMIT = 12;
const SUMMARY_CAP = 20000;

const clock = ms => new Date(ms).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
const stepLabel = step => step >= 1440 * 60000 ? '1 gün' : step >= 3600000 ? `${step / 3600000} saat` : `${step / 60000} dk`;
const parse = value => window.AurasRuntime.parseTime(value)?.getTime();
const tr = value => value.toLocaleString('tr-TR');

// Olayları eşit zaman dilimlerine böler; dilim genişliği en fazla 12 dilim olacak şekilde seçilir.
function bucketize(events) {
  const valid = (events || []).map(event => ({ type: event.type, ms: parse(event.time) }))
    .filter(event => Number.isFinite(event.ms) && TYPES.some(type => type.key === event.type));
  if (!valid.length) return { buckets: [], step: 0, live: false };
  const times = valid.map(event => event.ms);
  const oldest = Math.min(...times), newest = Math.max(...times);
  const step = STEPS.find(size => (newest - oldest) / size < SLOT_LIMIT) || STEPS.at(-1);
  const first = Math.floor(oldest / step) * step;
  const buckets = [];
  for (let ms = first; ms <= newest; ms += step) buckets.push({ ms, total: 0, count: 0, plate: 0, face: 0, fire: 0 });
  for (const event of valid) {
    const bucket = buckets[Math.floor((event.ms - first) / step)];
    bucket[event.type] += 1; bucket.total += 1;
  }
  const visible = buckets.slice(-SLOT_LIMIT);
  return { buckets: visible, step, live: Math.floor(Date.now() / step) * step === visible.at(-1).ms };
}

function typeShares(events) {
  const counts = new Map(TYPES.map(type => [type.key, 0]));
  for (const event of events || []) if (counts.has(event.type)) counts.set(event.type, counts.get(event.type) + 1);
  const total = [...counts.values()].reduce((sum, value) => sum + value, 0);
  return { total, rows: TYPES.map(type => ({ ...type, value: counts.get(type.key) })) };
}

function cameraLoad(summary, cameras) {
  const rows = (summary?.cameras || []).map(row => ({
    id: row.camera_id, name: cameraName(cameras || [], row.camera_id),
    value: TYPES.reduce((sum, type) => sum + Number(row[type.field] || 0), 0),
  })).filter(row => row.value > 0).sort((a, b) => b.value - a.value).slice(0, 6);
  const scanned = (summary?.cameras || []).reduce((sum, row) => sum + Number(row.count || 0), 0);
  return { rows, max: rows[0]?.value || 0, saturated: scanned >= SUMMARY_CAP };
}

// Noktalar arasında yumuşak geçiş: orta noktadan kontrol edilen kübik eğri.
function curve(points) {
  if (points.length === 1) return `M${points[0].x} ${points[0].y}`;
  return points.slice(1).reduce((path, point, index) => {
    const prev = points[index], mid = (prev.x + point.x) / 2;
    return `${path} C${mid} ${prev.y} ${mid} ${point.y} ${point.x} ${point.y}`;
  }, `M${points[0].x} ${points[0].y}`);
}

// Dilimleri çizim koordinatlarına çevirir; bileşen yalnız boyar.
function layout(buckets) {
  const max = Math.max(4, Math.ceil(Math.max(...buckets.map(row => row.total)) / 4) * 4);
  const slot = buckets.length > 1 ? PLOT.w / (buckets.length - 1) : 0;
  const points = buckets.map((row, index) => ({
    x: BOX.l + (buckets.length === 1 ? PLOT.w / 2 : slot * index),
    y: BOX.t + PLOT.h - (row.total / max) * PLOT.h, row,
  }));
  const peak = points.reduce((best, point) => point.row.total > best.row.total ? point : best, points[0]);
  const path = curve(points);
  const floor = BOX.t + PLOT.h;
  const area = `${path} L${points.at(-1).x} ${floor} L${points[0].x} ${floor} Z`;
  const labels = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
  return { max, slot, points, peak, path, area, labels };
}

function Grid({ max }) {
  return [0, 1, 2, 3].map(index => {
    const y = BOX.t + (PLOT.h / 3) * index;
    return <g key={index}><line className="ts-grid" x1={BOX.l} x2={BOX.w - BOX.r} y1={y} y2={y}/>
      <text className="ts-axis" x={BOX.l - 6} y={y + 3} textAnchor="end">{Math.round(max - (max / 3) * index)}</text></g>;
  });
}

function AxisLabels({ geo }) {
  const last = geo.labels.length - 1;
  return geo.labels.map((index, position) => <text key={index} className="ts-axis" y={BOX.h - 6}
    x={position === 0 ? BOX.l : position === last ? BOX.w - BOX.r : geo.points[index].x}
    textAnchor={position === 0 ? 'start' : position === last ? 'end' : 'middle'}>{clock(geo.points[index].row.ms)}</text>);
}

function Tooltip({ point, ongoing }) {
  const below = point.y < BOX.t + PLOT.h * 0.42;
  return <div className={`ts-tip${below ? ' is-below' : ''}`} role="status"
    style={{ left: `${(point.x / BOX.w) * 100}%`, top: `${(point.y / BOX.h) * 100}%` }}>
    <strong>{point.row.total}</strong><span>{clock(point.row.ms)}{ongoing ? ' · sürüyor' : ''}</span>
    <ul>{TYPES.filter(type => point.row[type.key]).map(type => <li key={type.key} className={`tone-${type.tone}`}><i/><span>{type.label}</span><b>{point.row[type.key]}</b></li>)}</ul>
  </div>;
}

function DataTable({ buckets }) {
  return <table className="analytics-table"><caption>Zaman dilimlerine göre olay sayıları</caption>
    <thead><tr><th>Dilim</th><th>Toplam</th>{TYPES.map(type => <th key={type.key}>{type.label}</th>)}</tr></thead>
    <tbody>{buckets.map(row => <tr key={row.ms}><th>{clock(row.ms)}</th><td>{row.total}</td>{TYPES.map(type => <td key={type.key}>{row[type.key]}</td>)}</tr>)}</tbody></table>;
}

function TimeSeries({ buckets, live, step }) {
  const [active, setActive] = useState(null);
  const gradient = useId();
  const geo = useMemo(() => layout(buckets), [buckets]);
  const move = delta => setActive(value => Math.min(geo.points.length - 1, Math.max(0, (value ?? 0) + delta)));
  const onKey = event => {
    const action = { ArrowRight: () => move(1), ArrowLeft: () => move(-1), Escape: () => setActive(null) }[event.key];
    if (action) { event.preventDefault(); action(); }
  };
  const current = active === null ? null : geo.points[active];
  const hitWidth = Math.max(geo.slot, 24);
  return <div className="ts-wrap" onMouseLeave={() => setActive(null)}>
    <svg className="ts-svg" viewBox={`0 0 ${BOX.w} ${BOX.h}`} role="img" tabIndex={0} onKeyDown={onKey} onBlur={() => setActive(null)}
      aria-label={`Zaman dilimlerine göre olay yoğunluğu; ${buckets.length} dilim, dilim genişliği ${stepLabel(step)}. Ok tuşlarıyla dilimler arasında gezinin.`}>
      <defs><linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop offset="0" className="ts-fill-top"/><stop offset="1" className="ts-fill-bottom"/></linearGradient></defs>
      <Grid max={geo.max}/>
      {live && <rect className="ts-live" x={geo.points.at(-1).x - geo.slot / 2} y={BOX.t} width={geo.slot / 2 + BOX.r} height={PLOT.h}/>}
      <path className="ts-area" d={geo.area} fill={`url(#${gradient})`}/>
      <path className="ts-line" d={geo.path}/>
      {current && <line className="ts-cursor" x1={current.x} x2={current.x} y1={BOX.t} y2={BOX.t + PLOT.h}/>}
      {geo.points.map((point, index) => <circle key={point.row.ms} className={`ts-dot${active === index ? ' is-active' : ''}`} cx={point.x} cy={point.y} r={active === index ? 5.5 : 4}/>)}
      <text className="ts-peak" x={geo.peak.x} y={geo.peak.y - 10} textAnchor="middle">{geo.peak.row.total}</text>
      <AxisLabels geo={geo}/>
      {geo.points.map((point, index) => <rect key={`hit-${point.row.ms}`} className="ts-hit" x={point.x - hitWidth / 2} y={0} width={hitWidth} height={BOX.h}
        onMouseEnter={() => setActive(index)}><title>{`${clock(point.row.ms)} · ${point.row.total} olay`}</title></rect>)}
    </svg>
    {current && <Tooltip point={current} ongoing={live && active === geo.points.length - 1}/>}
    <DataTable buckets={buckets}/>
  </div>;
}

function Ring({ shares, fireNote }) {
  const radius = 44, circumference = 2 * Math.PI * radius, gap = 2;
  let offset = 0;
  const segments = shares.rows.filter(row => row.value > 0).map(row => {
    const length = (row.value / shares.total) * circumference, drawn = Math.max(length - gap, 0);
    const segment = { ...row, dash: `${drawn} ${circumference - drawn}`, offset: -offset };
    offset += length; return segment;
  });
  return <div className="ring-wrap">
    <svg className="ring-svg" viewBox="0 0 110 110" role="img" aria-label={`Olay dağılımı: ${shares.rows.map(row => `${row.label} ${row.value}`).join(', ')}`}>
      <circle className="ring-track" cx="55" cy="55" r={radius}/>
      {segments.map(segment => <circle key={segment.key} className={`ring-seg tone-${segment.tone}`} cx="55" cy="55" r={radius}
        strokeDasharray={segment.dash} strokeDashoffset={segment.offset} transform="rotate(-90 55 55)"><title>{`${segment.label}: ${segment.value}`}</title></circle>)}
      <text className="ring-total" x="55" y="53" textAnchor="middle">{tr(shares.total)}</text>
      <text className="ring-caption" x="55" y="67" textAnchor="middle">olay</text>
    </svg>
    <ul className="ring-legend">{shares.rows.map(row => <li key={row.key} className={`tone-${row.tone}${row.value ? '' : ' is-empty'}`}>
      <i/><span>{row.label}</span>
      {row.key === 'fire' && fireNote ? <small>{fireNote}</small> : <><strong>{shares.total ? Math.round((row.value / shares.total) * 100) : 0}%</strong><small>{row.value}</small></>}
    </li>)}</ul>
  </div>;
}

function CameraBars({ load }) {
  if (!load.rows.length) return <p className="analytics-empty">Kamera özeti için olay bekleniyor</p>;
  return <ol className="cam-bars" aria-label="Kameralara göre son 24 saatin olay sayısı">
    {load.rows.map(row => <li key={row.id}><span>{row.name}</span>
      <i style={{ '--w': `${(row.value / load.max) * 100}%` }} title={`${row.name}: ${row.value}`}><b/></i>
      <strong>{tr(row.value)}</strong></li>)}
  </ol>;
}

function fireStatus(capabilities) {
  const fire = capabilities?.data?.fire;
  if (!fire || fire.available) return null;
  return fire.enabled === false ? 'Yangın analizi etkin değil' : fire.reason || 'Kullanılamıyor';
}

export default function AnalyticsChart({ events, cameras, totals, capabilities }) {
  const titleId = useId();
  const model = useMemo(() => ({
    series: bucketize(events.data), shares: typeShares(events.data), load: cameraLoad(totals.data, cameras.data),
  }), [events.data, totals.data, cameras.data]);
  const fireNote = fireStatus(capabilities);
  const peak = model.series.buckets.reduce((best, row) => row.total > (best?.total || 0) ? row : best, null);
  return <section className="analytics-panel analytics-band" aria-labelledby={titleId}>
    <header><div><span className="ops-eyebrow">CANLI ANALİTİK</span><h3 id={titleId}>Olay analizi</h3></div>
      <div className="analytics-summary"><span><strong>{tr(model.shares.total)}</strong> toplam olay</span>
        <span><strong>{peak ? clock(peak.ms) : '—'}</strong> yoğun dilim</span><span><strong>{model.load.rows.length}</strong> aktif kamera</span></div></header>
    {!model.series.buckets.length ? <p className="analytics-empty">Henüz analiz olayı kaydedilmedi.</p> : <div className="analytics-grid">
      <div className="analytics-plot"><div className="analytics-subhead"><strong>Olay yoğunluğu</strong><span>{model.series.buckets.length} dilim · {stepLabel(model.series.step)} aralık</span></div>
        <TimeSeries buckets={model.series.buckets} live={model.series.live} step={model.series.step}/></div>
      <div className="analytics-breakdown"><div className="analytics-subhead"><strong>Olay dağılımı</strong><span>Türlere göre</span></div>
        <Ring shares={model.shares} fireNote={fireNote}/></div>
      <div className="analytics-cameras"><div className="analytics-subhead"><strong>Kamera bazlı</strong><span>Son 24 saat</span></div>
        <CameraBars load={model.load}/>
        {model.load.saturated && <p className="analytics-scope">Son 20.000 olay tarandı; sayılar alt sınırdır.</p>}</div>
    </div>}
  </section>;
}
