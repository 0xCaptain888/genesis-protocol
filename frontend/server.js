/**
 * Genesis Protocol — Production Server
 * Serves static frontend + proxies OKX API to avoid CORS.
 */
import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST = path.join(__dirname, 'dist');
const PORT = process.env.PORT || 3000;

const MIME = {
  '.html': 'text/html',
  '.js':   'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
};

/** Proxy a request to an external HTTPS host. */
function proxyTo(targetHost, pathRewrite, req, res) {
  const url = new URL(req.url, `http://localhost`);
  const targetPath = url.pathname.replace(pathRewrite.from, pathRewrite.to) + url.search;
  const opts = {
    hostname: targetHost,
    port: 443,
    path: targetPath,
    method: req.method,
    headers: {
      'User-Agent': 'genesis-protocol/1.0',
      'Accept': 'application/json',
    },
    timeout: 15000,
  };
  const proxyReq = https.request(opts, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, {
      'Content-Type': proxyRes.headers['content-type'] || 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Cache-Control': 'public, max-age=5',
    });
    proxyRes.pipe(res);
  });
  proxyReq.on('error', (e) => {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'proxy_error', detail: e.message }));
  });
  proxyReq.end();
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost`);

  // CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    });
    return res.end();
  }

  // API proxies
  if (url.pathname.startsWith('/okx-api/')) {
    return proxyTo('www.okx.com', { from: /^\/okx-api/, to: '' }, req, res);
  }
  if (url.pathname.startsWith('/okx-web3/')) {
    return proxyTo('web3.okx.com', { from: /^\/okx-web3/, to: '' }, req, res);
  }
  if (url.pathname.startsWith('/cg-api/')) {
    return proxyTo('api.coingecko.com', { from: /^\/cg-api/, to: '' }, req, res);
  }

  // Static files
  let filePath = path.join(DIST, url.pathname === '/' ? 'index.html' : url.pathname);
  if (!fs.existsSync(filePath)) filePath = path.join(DIST, 'index.html'); // SPA fallback

  const ext = path.extname(filePath);
  const contentType = MIME[ext] || 'application/octet-stream';

  try {
    const data = fs.readFileSync(filePath);
    res.writeHead(200, {
      'Content-Type': contentType,
      'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=86400',
    });
    res.end(data);
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not Found');
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Genesis Protocol running on http://localhost:${PORT}`);
});
