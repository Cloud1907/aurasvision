import { useEffect, useRef, useState } from 'react';
import { createAurora } from './aurora/renderer';

// React Bits shader'ı; native WebGL2, en fazla 30fps, görünürlük ve hareket guard'ı.
export default function Aurora({ motion }) {
  const ref = useRef(null), active = useRef(motion);
  const [ready, setReady] = useState(false);
  active.current = motion;
  useEffect(() => {
    if (!motion) return;
    let renderer;
    try { renderer = createAurora(ref.current); } catch (error) { console.warn(error.message); }
    if (!renderer) return;
    setReady(true);
    let timer, visible = true, lost = false;
    const canvas = ref.current;
    const contextLost = () => { lost = true; clearTimeout(timer); setReady(false); };
    canvas.addEventListener('webglcontextlost', contextLost);
    const frame = () => {
      clearTimeout(timer);
      if (lost || !active.current || !visible || document.hidden) return;
      renderer.draw(performance.now()); timer = setTimeout(frame, 34);
    };
    const observer = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; frame(); });
    observer.observe(ref.current); frame();
    return () => { clearTimeout(timer); observer.disconnect(); canvas.removeEventListener('webglcontextlost', contextLost); renderer.dispose(); setReady(false); };
  }, [motion]);
  return <div className={`rb-aurora ${ready ? 'ready' : 'fallback'}`} aria-hidden="true"><canvas ref={ref}/></div>;
}
