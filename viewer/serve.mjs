// 截图 / 录制脚本用的本机静态服务：只绑 127.0.0.1，端口由系统挑。
// root 是站点根（仓库根目录）；mounts 把网址前缀映射到别的目录（例如把 /runs/ 指向外部未入库的本地对局目录；
// 已入库的 171 盘正式对局 game.pgn 直接在仓内 runs/ 下，worktree 里也有）。
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
export { findExecutable, resolveChromium, resolveFfmpeg, resolveFfprobe } from './lib/bins.mjs';

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.json': 'application/json', '.jsonl': 'text/plain; charset=utf-8',
  '.png': 'image/png', '.pgn': 'text/plain; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.mp3': 'audio/mpeg',
};

// → { port, close() }
// files 把单个网址精确映射到单个本机文件（录制脚本用：只供给命令行点名的棋谱，不连带它所在的目录）。
export async function serve(root, mounts = {}, files = {}, port = 0, host = '127.0.0.1') {
  const bases = Object.entries(mounts).sort((a, b) => b[0].length - a[0].length);
  const server = http.createServer(async (req, res) => {
    try {
      let rel = decodeURIComponent(new URL(req.url, 'http://x').pathname);
      if (rel === '/favicon.ico') { res.writeHead(204).end(); return; }
      if (Object.hasOwn(files, rel)) {
        const body = await readFile(files[rel]);
        res.writeHead(200, { 'content-type': TYPES[path.extname(files[rel])] || 'application/octet-stream' }).end(body);
        return;
      }
      if (rel.endsWith('/')) rel += 'index.html';
      let base = root;
      for (const [prefix, dir] of bases) {
        if (rel.startsWith(prefix)) { base = dir; rel = rel.slice(prefix.length - 1); break; }
      }
      const file = path.resolve(base, '.' + rel);
      if (file !== base && !file.startsWith(base + path.sep)) { res.writeHead(403).end(); return; }
      const body = await readFile(file);
      res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' }).end(body);
    } catch {
      res.writeHead(404).end();
    }
  });
  await new Promise((ok, bad) => server.listen(port, host, ok).on('error', bad));
  return { port: server.address().port, close: () => new Promise((ok) => server.close(ok)) };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({
    args: process.argv.slice(2),
    options: {
      port: { type: 'string', short: 'p', default: '8765' },
      bind: { type: 'string', short: 'b', default: '127.0.0.1' },
    },
    strict: false,
  });
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const host = String(values.bind || '127.0.0.1');
  const port = Number(values.port) || 8765;
  const s = await serve(root, {}, {}, port, host);
  console.log(`Viewer listening at http://${host}:${s.port}/viewer/`);
}
