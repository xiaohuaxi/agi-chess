// 截图 / 录制脚本用的本机静态服务：只绑 127.0.0.1，端口由系统挑。
// root 是站点根（仓库根目录）；mounts 把网址前缀映射到别的目录（例如把 /runs/ 指向外部未入库的本地对局目录；
// 已入库的 192 盘正式对局 game.pgn 直接在仓内 runs/ 下，worktree 里也有）。
import http from 'node:http';
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
export { findExecutable, isExecutableFile, resolveBrowser, resolveChromium, resolveFfmpeg, resolveFfprobe } from './lib/bins.mjs';

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.json': 'application/json', '.jsonl': 'text/plain; charset=utf-8',
  '.png': 'image/png', '.pgn': 'text/plain; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.mp3': 'audio/mpeg',
};

const REDIRECT_PAGES = new Set(['catalog', 'series']);

// → { port, close() }
// files 把单个网址精确映射到单个本机文件（录制脚本用：只供给命令行点名的棋谱，不连带它所在的目录）。
export async function serve(root, mounts = {}, files = {}, port = 0, host = '127.0.0.1') {
  const bases = Object.entries(mounts).sort((a, b) => b[0].length - a[0].length);
  const allowedPrefixes = new Set(['/', '/viewer/']);
  for (const [prefix] of bases) {
    if (prefix.startsWith('/') && !prefix.startsWith('//') && prefix.endsWith('/')) {
      allowedPrefixes.add(prefix);
    }
  }
  const server = http.createServer(async (req, res) => {
    try {
      // 拒绝协议相对路径（如 //evil.com/...），避免 new URL(req.url, 'http://x') 将主机名解析掉并把路径折叠到根前缀
      if (!req.url || !req.url.startsWith('/') || req.url.startsWith('//')) {
        res.writeHead(404).end();
        return;
      }
      const urlObj = new URL(req.url, 'http://x');
      let rel = decodeURIComponent(urlObj.pathname);
      if (rel === '/favicon.ico') { res.writeHead(204).end(); return; }
      if (Object.hasOwn(files, rel)) {
        const body = await readFile(files[rel]);
        res.writeHead(200, { 'content-type': TYPES[path.extname(files[rel])] || 'application/octet-stream' }).end(body);
        return;
      }
      const origRel = rel;
      if (rel.endsWith('/')) rel += 'index.html';
      let base = root;
      let matchedMount = '/';
      for (const [prefix, dir] of bases) {
        if (rel.startsWith(prefix)) { base = dir; matchedMount = prefix; rel = rel.slice(prefix.length - 1); break; }
      }
      const file = path.resolve(base, '.' + rel);
      if (file !== base && !file.startsWith(base + path.sep)) { res.writeHead(403).end(); return; }
      try {
        const body = await readFile(file);
        res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' }).end(body);
      } catch (err) {
        // 本机开发服务兼容：仅当 readFile 报 ENOENT 且命中已知挂载前缀下的 /catalog/ 或 /series/ 时，构造安全同源 302
        if (err?.code === 'ENOENT' && origRel.startsWith('/') && !origRel.startsWith('//')) {
          const m = origRel.match(/^(\/(?:[^/]+\/)?)(catalog|series)\/$/);
          if (m && allowedPrefixes.has(m[1]) && REDIRECT_PAGES.has(m[2])) {
            const [, dirPrefix, name] = m;
            const candidates = [];
            if (dirPrefix === matchedMount || (matchedMount === '/' && dirPrefix === '/viewer/')) {
              const targetRel = dirPrefix === matchedMount ? `/${name}.html` : `/viewer/${name}.html`;
              const diskPath = path.resolve(base, '.' + targetRel);
              candidates.push([`${dirPrefix}${name}.html`, diskPath, base]);
            }
            if (dirPrefix === '/' && matchedMount === '/') {
              candidates.push([`/viewer/${name}.html`, path.resolve(root, 'viewer', `${name}.html`), root]);
            }
            for (const [locPath, diskPath, checkBase] of candidates) {
              if (!locPath.startsWith('/') || locPath.startsWith('//')) continue;
              const safe = diskPath === checkBase || diskPath.startsWith(checkBase + path.sep);
              if (safe && existsSync(diskPath)) {
                res.writeHead(302, { location: locPath + urlObj.search }).end();
                return;
              }
            }
          }
        }
        throw err;
      }
    } catch {
      res.writeHead(404).end();
    }
  });
  await new Promise((ok, bad) => server.listen(port, host, ok).on('error', bad));
  return { port: server.address().port, close: () => new Promise((ok) => server.close(ok)) };
}

export const SERVE_HELP = `用法：node viewer/serve.mjs [--port <端口>] [--bind <地址>]

在仓库根目录启动零依赖本机静态服务，供浏览器查看 viewer/ 与 runs/ 下的对局。
选项：
  -p, --port <端口>   监听端口（0–65535，0 为系统自动分配；默认 8765）
  -b, --bind <地址>   监听地址（默认 127.0.0.1）
  -h, --help          显示本说明
`;

export function parseServeCli(argv) {
  const { values, positionals } = parseArgs({
    args: argv,
    options: {
      port: { type: 'string', short: 'p' },
      bind: { type: 'string', short: 'b' },
      help: { type: 'boolean', short: 'h' },
    },
    strict: true,
    allowPositionals: true,
  });
  if (positionals.length) throw new Error(`多余的位置参数：${positionals.join(' ')}`);
  if (values.help) return { help: true };
  const rawPort = values.port === undefined ? '8765' : values.port.trim();
  if (!/^\d+$/.test(rawPort)) throw new Error(`--port 须为 0–65535 的整数，收到「${values.port}」`);
  const port = Number(rawPort);
  if (!Number.isInteger(port) || port < 0 || port > 65535) {
    throw new Error(`--port 超出范围（0–65535）：${values.port}`);
  }
  const host = (values.bind === undefined ? '127.0.0.1' : values.bind).trim();
  if (!host) throw new Error('--bind 不能为空');
  return { help: false, port, host };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  let cli;
  try {
    cli = parseServeCli(process.argv.slice(2));
  } catch (e) {
    console.error(`参数错误：${e.message}\n`);
    console.error(SERVE_HELP);
    process.exit(2);
  }
  if (cli.help) {
    process.stdout.write(SERVE_HELP);
    process.exit(0);
  }
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  try {
    const s = await serve(root, {}, {}, cli.port, cli.host);
    console.log(`Viewer listening at http://${cli.host}:${s.port}/viewer/`);
  } catch (e) {
    if (e?.code === 'EADDRINUSE') {
      console.error(`启动服务失败：端口 ${cli.port} 已被占用（可换 --port <端口>）`);
    } else {
      console.error(`启动服务失败：${e?.message || e}`);
    }
    process.exit(1);
  }
}
