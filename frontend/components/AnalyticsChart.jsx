import { useEffect, useMemo, useRef } from 'react';

const label = { count: 'Geçiş', plate: 'Plaka', face: 'Yüz', fire: 'Yangın', intrusion: 'İhlal', telefon: 'Telefon', sigara: 'Sigara' };
const chartColors = ['var(--chart-one)', 'var(--chart-two)', 'var(--chart-three)', 'var(--chart-four)'];

function curve(ctx, points) {
  if (points.length === 1) { ctx.lineTo(points[0].x, points[0].y); return; }
  for (let index = 0; index < points.length - 1; index += 1) {
    const point = points[index], next = points[index + 1];
    const middle = (point.x + next.x) / 2;
    ctx.bezierCurveTo(middle, point.y, middle, next.y, next.x, next.y);
  }
}

function draw(canvas, values) {
  const box = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(box.width * ratio));
  canvas.height = Math.max(1, Math.round(box.height * ratio));
  const ctx = canvas.getContext('2d');
  ctx.scale(ratio, ratio);
  const width = box.width, height = box.height, left = 34, right = 14, top = 18, bottom = 28;
  const plotW = width - left - right, plotH = height - top - bottom;
  const styles = getComputedStyle(canvas);
  const line = styles.getPropertyValue('--chart-line').trim() || '#6294ff';
  const grid = styles.getPropertyValue('--chart-grid').trim() || '#ffffff1c';
  const text = styles.getPropertyValue('--chart-text').trim() || '#9aa4b2';
  ctx.clearRect(0, 0, width, height);
  ctx.font = '10px IBM Plex Mono'; ctx.fillStyle = text; ctx.strokeStyle = grid; ctx.lineWidth = 1;
  const rawMax = Math.max(4, ...values.map(value => value.total));
  const max = Math.ceil(rawMax / 4) * 4;
  for (let index = 0; index <= 3; index += 1) {
    const y = top + (plotH / 3) * index;
    ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(width - right, y); ctx.stroke();
    ctx.fillText(String(Math.round(max - (max / 3) * index)), 4, y + 3);
  }
  if (!values.length) return;
  const points = values.map((value, index) => ({
    x: left + (values.length === 1 ? plotW / 2 : (plotW / (values.length - 1)) * index),
    y: top + plotH - (value.total / max) * plotH,
  }));
  const fill = ctx.createLinearGradient(0, top, 0, top + plotH);
  fill.addColorStop(0, `${line}66`); fill.addColorStop(.55, `${line}22`); fill.addColorStop(1, `${line}00`);
  ctx.beginPath(); ctx.moveTo(points[0].x, top + plotH); ctx.lineTo(points[0].x, points[0].y);
  curve(ctx, points);
  ctx.lineTo(points.at(-1).x, top + plotH); ctx.closePath(); ctx.fillStyle = fill; ctx.fill();
  ctx.save(); ctx.strokeStyle = line; ctx.lineWidth = 3; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  ctx.shadowColor = line; ctx.shadowBlur = 14; ctx.beginPath(); ctx.moveTo(points[0].x, points[0].y); curve(ctx, points); ctx.stroke(); ctx.restore();
  points.forEach(point => {
    ctx.fillStyle = line; ctx.beginPath(); ctx.arc(point.x, point.y, 3.5, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = getComputedStyle(canvas).getPropertyValue('--glass-core').trim() || '#151922'; ctx.lineWidth = 2; ctx.stroke();
  });
  ctx.fillStyle = text;
  const indexes = [...new Set([0, Math.floor((values.length - 1) / 2), values.length - 1])];
  indexes.forEach((index, position) => {
    const point = points[index], labelText = values[index].hour;
    const measured = ctx.measureText(labelText).width;
    const x = position === 0 ? left : position === indexes.length - 1 ? width - right - measured : point.x - measured / 2;
    ctx.fillText(labelText, x, height - 7);
  });
}

export default function AnalyticsChart({ events }) {
  const canvas = useRef(null);
  const { series, types } = useMemo(() => {
    const buckets = new Map(), counts = new Map();
    for (const event of events.data || []) {
      const date = window.AurasRuntime.parseTime(event.time);
      if (!date) continue;
      date.setMinutes(0, 0, 0);
      const key = date.toISOString();
      buckets.set(key, (buckets.get(key) || 0) + 1);
      counts.set(event.type, (counts.get(event.type) || 0) + 1);
    }
    const rows = [...buckets].sort(([a], [b]) => a.localeCompare(b)).slice(-12).map(([key, total]) => ({
      hour: new Date(key).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }), total,
    }));
    return { series: rows, types: [...counts].sort((a, b) => b[1] - a[1]).slice(0, 4) };
  }, [events.data]);
  useEffect(() => {
    const el = canvas.current;
    const render = () => draw(el, series);
    render();
    const observer = new ResizeObserver(render); observer.observe(el);
    return () => observer.disconnect();
  }, [series]);
  const total = types.reduce((sum, [, count]) => sum + count, 0);
  const peak = series.reduce((best, row) => row.total > (best?.total || 0) ? row : best, null);
  let angle = 0;
  const donut = types.length ? `conic-gradient(${types.map(([, count], index) => {
    const start = angle; angle += count / total * 360;
    return `${chartColors[index]} ${start}deg ${angle}deg`;
  }).join(',')})` : 'conic-gradient(var(--line) 0deg 360deg)';
  const heatMax = Math.max(1, ...series.map(row => row.total));
  return <section className="analytics-panel">
    <header><div><span className="ops-eyebrow">CANLI ANALİTİK</span><h3>Olay analizi</h3></div><div className="analytics-summary"><span><strong>{total}</strong> toplam olay</span><span><strong>{peak?.hour || '—'}</strong> yoğun saat</span></div></header>
    <div className="analytics-grid"><div className="analytics-plot"><div className="analytics-subhead"><strong>Saatlik yoğunluk</strong><span className="analytics-live"><i/> Son 12 zaman dilimi</span></div><canvas ref={canvas} role="img" aria-label="Saatlere göre olay yoğunluğu alan grafiği"/>
      <div className="analytics-heat" aria-label="Zaman dilimlerine göre yoğunluk izi">{series.map((row, index) => <span key={`${row.hour}-${index}`} title={`${row.hour}: ${row.total} olay`} style={{ '--heat': .16 + row.total / heatMax * .84 }}/>)}</div></div>
      <div className="analytics-breakdown"><div className="analytics-subhead"><strong>Olay dağılımı</strong><span>Türlere göre</span></div>
        <div className="analytics-donut-wrap"><div className="analytics-donut" style={{ background: donut }}><span><strong>{total}</strong><small>OLAY</small></span></div></div>
        <div className="analytics-legend-rich">{types.length ? types.map(([type, count], index) => <div key={type}><i style={{ background: chartColors[index] }}/><span>{label[type] || type}</span><strong>{Math.round(count / total * 100)}%</strong><small>{count}</small></div>) : <span className="analytics-empty">Grafik için olay bekleniyor</span>}</div></div></div>
  </section>;
}
