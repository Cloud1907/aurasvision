/* UI yaşam döngüsü: GET iptali, görünürlük ve sınırlı kamera önizleme kuyruğu. */
(() => {
  let view = null;
  const aborted = () => new DOMException('Ekran değişti', 'AbortError');
  function begin(name, api, isActive) {
    view?.dispose();
    const controller = new AbortController(), cleanups = [];
    const ctx = {
      name, signal: controller.signal,
      current: () => view === ctx && !controller.signal.aborted && isActive(),
      check() { if (!ctx.current()) throw aborted(); },
      async get(path) {
        ctx.check();
        const value = await api(path, { signal: controller.signal });
        ctx.check();
        return value;
      },
      cleanup(fn) { cleanups.push(fn); },
      dispose() { controller.abort(); cleanups.splice(0).forEach(fn => fn()); }
    };
    view = ctx;
    return ctx;
  }
  function poll(fn, interval, enabled = () => true, immediate = true) {
    let stopped = false, busy = false, requested = false, timer;
    const tick = async () => {
      clearTimeout(timer);
      if (stopped) return;
      if (busy) { requested = true; return; }
      if (!document.hidden && enabled()) {
        busy = true;
        try { await fn(); } catch (e) {
          if (e.name !== 'AbortError') console.warn('UI yenileme başarısız:', e.message);
        } finally { busy = false; }
      }
      if (!stopped) timer = setTimeout(tick, requested ? 0 : interval);
      requested = false;
    };
    const visibility = () => { if (!document.hidden) tick(); };
    document.addEventListener('visibilitychange', visibility);
    if (immediate) tick(); else timer = setTimeout(tick, interval);
    const stop = () => { stopped = true; clearTimeout(timer); document.removeEventListener('visibilitychange', visibility); };
    stop.refresh = tick;
    return stop;
  }
  function visibleSnapshot(img, state) {
    const rect = img.getBoundingClientRect();
    return rect.bottom > 0 && rect.top < innerHeight && rect.width > 0 &&
      (!state.failures.has(img) || state.failures.get(img) < Date.now()) &&
      (!state.due.has(img) || state.due.get(img) < Date.now());
  }
  async function snapshotImage(img, response, state) {
    if (!response.ok) throw new Error('Görüntü alınamadı');
    const blob = await response.blob();
    state.controller.signal.throwIfAborted();
    if (!img.isConnected) return;
    const url = URL.createObjectURL(blob);
    if (state.urls.has(img)) URL.revokeObjectURL(state.urls.get(img));
    state.urls.set(img, url); img.src = url;
    await img.decode();
    state.controller.signal.throwIfAborted();
    img.classList.add('loaded', 'yuklendi');
    img.dataset.updated = new Date().toISOString();
    img.dispatchEvent(new CustomEvent('snapshotready', { bubbles: true }));
    state.failures.delete(img);
  }
  async function fetchSnapshot(img, state) {
    const request = new AbortController(), cancel = () => request.abort();
    state.controller.signal.addEventListener('abort', cancel, { once: true });
    const timeout = setTimeout(cancel, 6500);
    try {
      const response = await fetch(state.makeUrl(img.dataset.snapshot), { signal: request.signal });
      await snapshotImage(img, response, state);
    } catch (e) {
      if (!state.controller.signal.aborted) {
        state.failures.set(img, Date.now() + 30000);
        img.classList.remove('loaded', 'yuklendi');
        img.dispatchEvent(new CustomEvent('snapshoterror', { bubbles: true }));
      }
    } finally {
      clearTimeout(timeout);
      state.controller.signal.removeEventListener('abort', cancel);
    }
  }
  async function snapshotWorker(queue, state) {
    while (queue.length && !state.controller.signal.aborted && !document.hidden) {
      const img = queue.shift();
      if (img.isConnected && visibleSnapshot(img, state)) { state.due.set(img, Date.now() + state.interval); await fetchSnapshot(img, state); }
    }
  }
  function observeSnapshots(root, refresh) {
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting && !entry.target.dataset.updated)) refresh();
    });
    root.querySelectorAll('img[data-snapshot]').forEach(img => observer.observe(img));
    return () => observer.disconnect();
  }
  function snapshots(root, makeUrl, interval = 10000) {
    const state = { controller: new AbortController(), failures: new WeakMap(), due: new WeakMap(), urls: new Map(), makeUrl, interval };
    const refresh = async () => {
      const queue = [...root.querySelectorAll('img[data-snapshot]')].filter(img => visibleSnapshot(img, state));
      await Promise.all([snapshotWorker(queue, state), snapshotWorker(queue, state)]);
    };
    const stop = poll(refresh, interval);
    const disconnect = observeSnapshots(root, stop.refresh);
    return () => {
      stop(); disconnect(); state.controller.abort();
      state.urls.forEach(url => URL.revokeObjectURL(url)); state.urls.clear();
    };
  }
  function parseTime(value) {
    if (!value) return null;
    const text = String(value).replace(' ', 'T');
    const date = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(text.slice(10)) ? text : text + 'Z');
    return Number.isNaN(date.getTime()) ? null : date;
  }
  function health(row) {
    const time = parseTime(row?.time);
    if (!time || Date.now() - time.getTime() > 30000) return { state: 'idle', label: 'Analiz bilgisi güncel değil' };
    if (row.status === 'error' || row.status === 'degraded') return { state: 'error', label: 'Analiz sorunu' };
    return Number(row.fps) > 0 ? { state: 'ok', label: 'Analiz çalışıyor' } : { state: 'idle', label: 'Analiz bekliyor' };
  }
  window.AurasRuntime = { begin, poll, snapshots, parseTime, health };
})();
