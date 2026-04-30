const http = require('http');
const fs = require('fs');
const path = require('path');
const port = 8080;
const distDir = path.join(__dirname, 'dist');

const mimeTypes = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.json': 'application/json',
  '.ico': 'image/x-icon'
};

const server = http.createServer((req, res) => {
  let filePath = path.join(distDir, req.url.split('?')[0]);
  
  // Default to index.html
  if (req.url === '/' || req.url === '/index.html') {
    filePath = path.join(distDir, 'index.html');
  }
  
  // If path is a directory, serve index.html
  if (fs.existsSync(filePath) && fs.statSync(filePath).isDirectory()) {
    filePath = path.join(filePath, 'index.html');
  }
  
  // If file not found, serve index.html (for SPA routing)
  if (!fs.existsSync(filePath)) {
    filePath = path.join(distDir, 'index.html');
  }
  
  const ext = path.extname(filePath).toLowerCase();
  const contentType = mimeTypes[ext] || 'application/octet-stream';
  
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end('Not found');
      return;
    }
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(data);
  });
});

server.listen(port, () => {
  console.log(`\n========================================`);
  console.log(`  Server running at http://localhost:${port}`);
  console.log(`  Press Ctrl+C to stop`);
  console.log(`========================================\n`);
  console.log(`Opening browser...`);
  
  // Auto open browser
  const { exec } = require('child_process');
  exec(`start http://localhost:${port}`);
});
