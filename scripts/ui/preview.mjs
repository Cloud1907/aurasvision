// Yalnız statik UI önizlemesi. Kamera, DB veya model başlatmaz.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';

const root = resolve('web');
const demo = process.argv.includes('--demo');
const fixtures = demo ? (await import('../../e2e/fixtures/ui-api.ts')).responses : null;
const port = demo ? 8768 : 8767;
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.json': 'application/json',
  '.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg' };
createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname.startsWith('/api/')) {
    const response = fixtures?.[url.pathname.slice(4)];
    if (demo && req.method !== 'GET') {
      res.writeHead(405, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ detail: 'Tasarım önizlemesi salt okunur.' }));
    }
    if (response) {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      return res.end(JSON.stringify(response()));
    }
    res.writeHead(503, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ detail: 'Statik önizleme: canlı API bağlı değil.' }));
  }
  const requested = url.pathname === '/' ? 'index.html' :
    url.pathname === '/m' ? 'mobil.html' : url.pathname.replace(/^\/static\//, '').replace(/^\//, '');
  const file = resolve(root, requested);
  if (!file.startsWith(root + sep)) { res.writeHead(403); return res.end(); }
  try {
    let body = await readFile(file);
    if (demo && extname(file) === '.html') body = body.toString().replace(/<body([^>]*)>/, '$&<aside style="position:relative;padding:7px 16px;background:#eceef1;color:#50545b;text-align:center;font:11px monospace;letter-spacing:.08em;border-top:1px solid #d5d9df">TASARIM ÖNİZLEMESİ · TEMSİLİ VERİLER · CANLI KAMERA BAĞLI DEĞİL</aside>');
    res.writeHead(200, { 'Content-Type': types[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(body);
  } catch { res.writeHead(404); res.end('Not found'); }
}).listen(port, '127.0.0.1', () => console.info(`UI preview: http://127.0.0.1:${port}${demo ? ' (temsili veriler)' : ''}`));
