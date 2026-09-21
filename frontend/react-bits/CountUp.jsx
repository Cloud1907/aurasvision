import { animate, useMotionValue, useInView } from 'motion/react';
import { useEffect, useRef } from 'react';
// React Bits CountUp: hedef değere kesin sürede ulaşır, Türkçe biçim kullanır.
export default function CountUp({ to, from = 0, duration = 0.45, separator = '' }) {
  const ref = useRef(null);
  const value = useMotionValue(from);
  const visible = useInView(ref, { once: true });
  useEffect(() => {
    const format = n => Intl.NumberFormat('tr-TR', { useGrouping: !!separator, maximumFractionDigits: 0 }).format(n);
    const unsubscribe = value.on('change', n => { if (ref.current) ref.current.textContent = format(n); });
    if (!visible) return unsubscribe;
    const controls = animate(value, to, { duration, ease: 'easeOut', onComplete: () => {
      if (ref.current) ref.current.textContent = format(to);
    } });
    return () => { controls.stop(); unsubscribe(); };
  }, [to, duration, separator, visible, value]);
  return <span ref={ref}>{from}</span>;
}
