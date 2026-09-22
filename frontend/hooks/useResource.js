import { useEffect, useRef, useState, useCallback } from 'react';

export function useResource(bridge, path, interval = 15000) {
  const [state, setState] = useState({ data: null, error: '', updated: null, loading: true });
  const [revision, setRevision] = useState(0);
  const retry = useCallback(() => {
    setState(prev => ({ ...prev, error: '', loading: true }));
    setRevision(n => n + 1);
  }, []);
  const last = useRef('');
  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    const stop = window.AurasRuntime.poll(async () => {
      try {
        const data = await bridge.api(path, { signal: controller.signal });
        if (!current) return;
        const json = JSON.stringify(data);
        const unchanged = json === last.current;
        last.current = json;
        setState(prev => ({ data: unchanged && prev.data !== null ? prev.data : data, error: '', updated: Date.now(), loading: false }));
      } catch (e) {
        if (current && e.name !== 'AbortError') setState(prev => ({ ...prev, error: e.message, loading: false }));
      }
    }, interval);
    return () => { current = false; controller.abort(); stop(); };
  }, [bridge, path, interval, revision]);
  return { ...state, retry };
}

export function useMotionAllowed() {
  const [allowed, setAllowed] = useState(false);
  useEffect(() => {
    const query = matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setAllowed(!query.matches && !document.hidden);
    update(); query.addEventListener('change', update);
    document.addEventListener('visibilitychange', update);
    return () => { query.removeEventListener('change', update); document.removeEventListener('visibilitychange', update); };
  }, []);
  return allowed;
}
