// 截图 / 录制脚本用的本机静态服务：只绑 127.0.0.1，端口由系统挑。
// root 是站点根（仓库根目录）；mounts 把网址前缀映射到别的目录，比如在 worktree 里跑时把 /runs/ 指到主检出的 runs/
// （runs/ 被 git 忽略，worktree 里没有），不用往 worktree 里放软链。
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.json': 'application/json', '.png': 'image/png',
  '.pgn': 'text/plain; charset=utf-8', '.txt': 'text/plain; charset=utf-8',
};

// → { port, close() }
// files 把单个网址精确映射到单个本机文件（录制脚本用：只供给命令行点名的棋谱，不连带它所在的目录）。
export async function serve(root, mounts = {}, files = {}) {
  const bases = Object.entries(mounts).sort((a, b) => b[0].length - a[0].length);
  const server = http.createServer(async (req, res) => {
    try {
      let rel = decodeURIComponent(new URL(req.url, 'http://x').pathname);
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
  await new Promise((ok, bad) => server.listen(0, '127.0.0.1', ok).on('error', bad));
  return { port: server.address().port, close: () => new Promise((ok) => server.close(ok)) };
}
