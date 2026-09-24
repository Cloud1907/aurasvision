const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');

async function player(fallback = 'camera-sub') {
  class Media {
    constructor() { this.listeners = {}; this.error = {code: 3}; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    get playbackRate() { return this._rate === undefined ? 1 : this._rate; }
    set playbackRate(value) { this._rate = value; }
  }
  const label = {textContent: 'tam çözünürlük'};
  const kbtn = {textContent: 'Alt akış'};
  const badge = {textContent: 'CANLI'};
  const tile = {dataset: {state: 'live'}, querySelector: () => badge};
  class VideoRTC {
    constructor() { this.dataset = {src: 'camera', fallbackSrc: fallback}; }
    oninit() { this.video = new Media(); }
    // .camview içinde iki AYRI öğe okunur: kalite etiketi ve tam-çözünürlük düğmesi.
    closest(selector) {
      if (selector === '.tile') return tile;
      return {querySelector: q => (q === '#cv-kalite' ? kbtn : label)};
    }
    set src(value) { this.nextSource = value; }
  }
  let Player;
  const context = vm.createContext({VideoRTC, HTMLMediaElement: Media,
    customElements: {get: () => null, define: (_, ctor) => { Player = ctor; }},
    tokq: () => '&token=test', console, toast: () => {}});
  const source = html.slice(html.indexOf('let PLAYER=null;'), html.indexOf('function duvarModu'))
    .replace('import("/vendor/video-rtc.js")', 'Promise.resolve({VideoRTC})');
  await vm.runInContext(source + '\nloadPlayer();', context);
  const el = new Player(); el.oninit();
  return {el, label, kbtn, badge, tile};
}

test('decode failure switches enlarged camera to its fallback once', async () => {
  const {el, label, tile} = await player();
  el.video.listeners.error?.();
  assert.equal(el.nextSource, '/api/stream?src=camera-sub&token=test');
  assert.equal(el.dataset.src, 'camera-sub');
  assert.equal(label.textContent, 'alt akış · çözücü yetmedi');
  assert.equal(tile.dataset.state, 'wait');
  el.nextSource = null;
  el.video.listeners.error();
  assert.equal(el.nextSource, null, 'fallback must not reconnect endlessly');
});

test('a camera without fallback never invents a source', async () => {
  const {el} = await player('');
  el.video.listeners.error?.();
  assert.equal(el.nextSource, undefined);
  assert.equal(el.dataset.src, 'camera');
});

test('healthy main stream keeps full resolution', async () => {
  const {el, label} = await player();
  el.video.error = null;
  el.video.listeners.error?.();
  assert.equal(el.nextSource, undefined);
  assert.equal(label.textContent, 'tam çözünürlük');
});

test('network errors keep the original source for normal reconnection', async () => {
  const {el} = await player();
  el.video.error = {code: 2};
  el.video.listeners.error?.();
  assert.equal(el.nextSource, undefined);
  assert.equal(el.dataset.fallbackSrc, 'camera-sub');
});

// Ölçüm 2026-09-24: substream anahtar kare aralığı 4,0 sn → akış açılırken tampon
// bir GOP kadar dolu geliyor. Yetişme tavanı o fazlalığı MAKUL sürede eritmeli,
// ama hedefe yakınken duvarı hızlandırmamalı.
test('a full keyframe interval behind live, catch-up uses the ceiling', async () => {
  const {el} = await player();
  el.video.playbackRate = 4;
  assert.equal(el.video.playbackRate, 1.5);
});

test('near the latency target playback stays calm', async () => {
  const {el} = await player();
  el.video.playbackRate = 1.2;
  assert.ok(el.video.playbackRate <= 1.05,
    'hedefin hemen üstünde gözle görülür hızlanma olmamalı');
  el.video.playbackRate = 1.0;
  assert.equal(el.video.playbackRate, 1);
});

test('an empty buffer never stops playback completely', async () => {
  const {el} = await player();
  el.video.playbackRate = 0;
  assert.equal(el.video.playbackRate, 0.9, 'ağır çekim tabanı korunmalı');
});

/* ---- kayıt arşivi oynatıcısı ---- */
function arsiv(segler) {
  const mkVideo = id => {
    const o = {id, _yuklu: null, readyState: 0, style: {}, currentTime: 0,
      playbackRate: 1, paused: false, srcSets: 0, _src: null, error: null,
      pause() { this.paused = true; }, play() { return Promise.resolve(); }};
    Object.defineProperty(o, 'src', {
      get() { return this._src; },
      set(v) { this._src = v; this.srcSets++; }});
    return o;
  };
  const v1 = mkVideo('v1'), v2 = mkVideo('v2');
  const rpp = {textContent: ''}, rsaat = {textContent: ''};
  const nodes = {'#recvid': v1, '#recvid2': v2, '#rpp': rpp, '#rsaat': rsaat};
  let timer = null;
  const context = vm.createContext({
    $: sel => nodes[sel] || null, toast: () => {}, tokq: () => '&token=test',
    setTimeout: fn => { timer = fn; return 1; }, clearTimeout: () => {}, Date, console});
  const bas = html.indexOf('let REC={segler');
  const src = html.slice(bas, html.indexOf('async function aramaYap'))
    + html.slice(html.indexOf('function recIndir(){'), html.indexOf('async function disaAktar'));
  // `let REC` sözcüksel bağdır, context üstünden görünmez → erişimci ile dışarı ver.
  vm.runInContext(src + '\nglobalThis.__t={get REC(){return REC;}};', context);
  context.__t.REC.segler = segler;
  context.__t.REC.v = v1; context.__t.REC.v2 = v2;
  return {context, v1, v2, REC: context.__t.REC, tick: () => timer && timer()};
}

const seg = (saat, path) => ({path, start_time: `2026-09-24 ${saat}`, duration: 60});
const saniye = s => {
  const [h, m, sn] = s.split(':').map(Number);
  return h * 3600 + m * 60 + sn;
};

test('seeking inside the playing segment does not reload the file', () => {
  const s1 = seg('10:00:00', 'kamera-201/1.mp4');
  const {context, v1} = arsiv([s1]);
  context.recOynat(saniye('10:00:05'));
  assert.equal(v1.srcSets, 1, 'segment bir kez açılır');
  assert.equal(v1._yuklu, s1.path);
  context.recOynat(saniye('10:00:25'));
  assert.equal(v1.srcSets, 1, 'aynı segment içinde atlamak dosyayı yeniden açmamalı');
  assert.equal(v1.currentTime, 25);
});

test('the next segment is opened on the standby player, not the visible one', () => {
  const s1 = seg('10:00:00', 'kamera-201/1.mp4'), s2 = seg('10:01:00', 'kamera-201/2.mp4');
  const {context, v1, v2, REC, tick} = arsiv([s1, s2]);
  context.recOynat(saniye('10:00:05'));
  tick();
  assert.equal(v2._src, '/media/rec/kamera-201/2.mp4?token=test');
  assert.equal(REC._bekSeg, s2);
  assert.equal(v1._yuklu, s1.path, 'ekrandaki oynatıcıya dokunulmamalı');
  assert.equal(v2.paused, true, 'yedek oynatıcı sesli/görüntülü oynamamalı');
});

test('a prepared next segment is shown by swapping, without reloading it', () => {
  const s1 = seg('10:00:00', 'kamera-201/1.mp4'), s2 = seg('10:01:00', 'kamera-201/2.mp4');
  const {context, v1, v2, REC, tick} = arsiv([s1, s2]);
  context.recOynat(saniye('10:00:05'));
  tick();
  const yuklemeler = v2.srcSets;
  v2.readyState = 2;                      // ilk kare çözüldü
  context.recSonraki();
  assert.equal(REC.v, v2, 'yedek oynatıcı ekrana alınmalı');
  assert.equal(v2.srcSets, yuklemeler, 'hazır segment yeniden yüklenmemeli');
  assert.equal(v2.style.opacity, '1');
  assert.equal(v1.style.opacity, '0');
  assert.equal(REC.aktif, s2);
});

test('an unprepared next segment still plays through the normal path', () => {
  const s1 = seg('10:00:00', 'kamera-201/1.mp4'), s2 = seg('10:01:00', 'kamera-201/2.mp4');
  const {context, v1, v2, REC} = arsiv([s1, s2]);
  context.recOynat(saniye('10:00:05'));
  context.recSonraki();                   // ön yükleme hiç koşmadı (tick yok)
  assert.equal(REC.v, v1, 'hazır olmayan yedeğe takas edilmemeli');
  assert.equal(v1._yuklu, s2.path);
  assert.equal(v1.srcSets, 2);
  assert.equal(v2.srcSets, 0);
});

test('failed decoder cannot be marked live by an advancing clock', () => {
  const badge = {textContent: 'CANLI'};
  const tile = {dataset: {state: 'live'}, getBoundingClientRect: () => ({top: 0, bottom: 100}), querySelector: () => badge};
  const el = {video: {currentTime: 4, error: {code: 3}}, closest: () => tile, wsState: 1};
  const context = vm.createContext({window: {}, document: {querySelectorAll: () => [el]},
    innerHeight: 800, WebSocket: {CLOSED: 3}, clearInterval() {}, setInterval() {}});
  vm.runInContext(html.slice(html.indexOf('function watchTiles(){'), html.indexOf('async function donanimKart')) + '\nwatchTiles();', context);
  assert.notEqual(tile.dataset.state, 'live');
  assert.notEqual(badge.textContent, 'CANLI');
});

test('panel camera connects even if optional system info was unavailable', async () => {
  const el = {dataset: {src: 'camera'}};
  let watched = false;
  const context = vm.createContext({SYS: {go2rtc: ''}, loadPlayer: async () => {},
    document: {querySelectorAll: () => [el]}, tokq: () => '',
    watchTiles: () => { watched = true; }});
  const start = html.indexOf('function mountStreams(){');
  const end = html.indexOf('function openCam(', start);
  vm.runInContext(html.slice(start, end) + '\nmountStreams();', context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(el.src, '/api/stream?src=camera');
  assert.equal(watched, true);
});

test('stalled main stream falls back without waiting for a decoder error', () => {
  const tile = {dataset: {state: 'wait'}, getBoundingClientRect: () => ({top: 0, bottom: 100}), querySelector: () => ({})};
  let fallbackCalls = 0, tick;
  const el = {video: {currentTime: 0, error: null}, closest: () => tile, wsState: 1,
    fallbackStream: () => { fallbackCalls++; return true; }};
  const context = vm.createContext({window: {}, document: {querySelectorAll: () => [el]},
    innerHeight: 800, WebSocket: {CLOSED: 3}, clearInterval() {}, setInterval(fn) { tick = fn; }});
  vm.runInContext(html.slice(html.indexOf('function watchTiles(){'), html.indexOf('async function donanimKart')) + '\nwatchTiles();', context);
  for(let i = 0; i < 6; i++)tick();
  assert.ok(fallbackCalls > 0, 'a stalled stream must try the configured fallback');
});
