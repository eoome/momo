const http = require('http');
const fs = require('fs');
const path = require('path');

const WEB_PORT = 80;
const API_TARGET = 'http://127.0.0.1:20011';
const STATIC_DIR = path.join(__dirname, 'publish', 'frontend');

const MIME = {
  '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css',
  '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.gif': 'image/gif', '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
  '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf',
};

function serveStatic(req, res) {
  let filePath = path.join(STATIC_DIR, req.url === '/' ? 'index.html' : req.url);
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    filePath = path.join(STATIC_DIR, 'index.html'); // SPA fallback
  }
  const ext = path.extname(filePath);
  res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
  fs.createReadStream(filePath).pipe(res);
}

function proxyAPI(req, res) {
  const url = new URL(req.url, API_TARGET);
  const opts = { hostname: url.hostname, port: url.port, path: url.pathname + url.search, method: req.method, headers: req.headers };
  const proxy = http.request(opts, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });
  proxy.on('error', () => { res.writeHead(502); res.end('Backend offline'); });
  req.pipe(proxy);
}

http.createServer((req, res) => {
  if (req.url.startsWith('/api') || req.url.startsWith('/swagger')) {
    proxyAPI(req, res);
  } else {
    serveStatic(req, res);
  }
}).listen(WEB_PORT, '0.0.0.0', () => {
  console.log(`前端: http://127.0.0.1:${WEB_PORT}`);
  console.log(`后端: ${API_TARGET}`);
});
