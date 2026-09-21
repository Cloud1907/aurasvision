import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';

const result = await build({ entryPoints: ['frontend/main.jsx'], bundle: true, minify: true,
  outfile: 'web/dist/auras-ui.js', format: 'iife', target: ['es2020'], jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"' },
  loader: { '.woff2': 'file', '.woff': 'file' }, publicPath: '/static/dist',
  assetNames: 'fonts/[name]-[hash]', metafile: true, legalComments: 'linked' });
await writeFile('web/dist/react-bits-LICENSE.txt', await readFile('frontend/react-bits/LICENSE.md'));
await writeFile('web/dist/manrope-LICENSE.txt', await readFile('node_modules/@fontsource-variable/manrope/LICENSE'));
await writeFile('web/dist/ibm-plex-mono-LICENSE.txt', await readFile('node_modules/@fontsource/ibm-plex-mono/LICENSE'));
console.info(JSON.stringify(Object.fromEntries(Object.entries(result.metafile.outputs)
  .filter(([name]) => /\.(js|css)$/.test(name)).map(([name, data]) => [name, data.bytes])), null, 2));
