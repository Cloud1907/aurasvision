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
    get playbackRate() { return 1; }
    set playbackRate(value) {}
  }
  const label = {textContent: 'tam çözünürlük'};
  const badge = {textContent: 'CANLI'};
  const tile = {dataset: {state: 'live'}, querySelector: () => badge};
  class VideoRTC {
    constructor() { this.dataset = {src: 'camera', fallbackSrc: fallback}; }
    oninit() { this.video = new Media(); }
    closest(selector) { return selector === '.tile' ? tile : {querySelector: () => label}; }
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
  return {el, label, badge, tile};
}

test('decode failure switches enlarged camera to its fallback once', async () => {
  const {el, label, tile} = await player();
  el.video.listeners.error?.();
  assert.equal(el.nextSource, '/api/stream?src=camera-sub&token=test');
  assert.equal(el.dataset.src, 'camera-sub');
  assert.equal(label.textContent, 'uyumlu akış');
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
