// 确定性 GitHub Pages 静态站点打包脚本（零外部依赖）。
// 用法：node viewer/build-pages.mjs [输出目录]（默认输出到仓库根下 _site/）。
// 把阅读器静态资源平铺到站点根，并仅从 git ls-files runs/ 拷入已跟踪的 game.pgn 与 analysis.jsonl。
import { execFileSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const VIEWER = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(VIEWER, '..');
const DEFAULT_OUT = path.join(ROOT, '_site');

const VIEWER_FILES = ['index.html', 'series.html', 'catalog.html', '404.html', 'og-card.png', 'app.css', 'pages.css', 'app.js', 'series.js', 'catalog.js'];
const VIEWER_DIRS = ['lib', 'vendor'];
const FORBIDDEN_NAMES = new Set(['node_modules', 'test', 'package.json', 'package-lock.json']);
const PAGES_BASE_URL = 'https://xiaohuaxi.github.io/agi-chess/';
const REDIRECT_PAGES = [
  { dir: 'catalog', target: 'catalog.html', title: 'All Games Catalog · agi-chess', label: 'All Games Catalog (全部对局目录)' },
  { dir: 'series', target: 'series.html', title: 'No-Engine Series Board · agi-chess', label: 'No-Engine Series Board (无引擎对阵总览)' },
];

function makeRedirectHtml({ target, title, label }) {
  const rel = `../${target}`;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
<link rel="canonical" href="${PAGES_BASE_URL}${target}">
<meta http-equiv="refresh" content="0; url=${rel}">
<style>
  html, body { margin: 0; min-height: 100vh; background: #262421; color: #ece8e1;
    font-family: -apple-system, system-ui, "PingFang SC", "Noto Sans CJK SC", sans-serif;
    display: flex; align-items: center; justify-content: center; padding: 24px; box-sizing: border-box; }
  p { margin: 0; font-size: 14px; color: #9d968c; }
  a { color: #e8a33d; }
</style>
<script>location.replace('${rel}' + location.search + location.hash);</script>
</head>
<body>
<p>Redirecting to <a id="redirect-link" href="${rel}">${label}</a>…</p>
<script>document.getElementById('redirect-link').href = '${rel}' + location.search + location.hash;</script>
</body>
</html>
`;
}

function isForbiddenEntry(name) {
  return FORBIDDEN_NAMES.has(name) || /\.mjs$/i.test(name) || /\.py$/i.test(name) || /^package.*\.json$/i.test(name);
}

function copyTreeFiltered(srcDir, dstDir) {
  mkdirSync(dstDir, { recursive: true });
  for (const ent of readdirSync(srcDir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    if (isForbiddenEntry(ent.name) || ent.name === '.DS_Store') continue;
    const s = path.join(srcDir, ent.name);
    const d = path.join(dstDir, ent.name);
    if (ent.isDirectory()) copyTreeFiltered(s, d);
    else if (ent.isFile()) copyFileSync(s, d);
  }
}

function measureDir(dir) {
  let files = 0, bytes = 0;
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      const sub = measureDir(full);
      files += sub.files;
      bytes += sub.bytes;
    } else if (ent.isFile()) {
      files += 1;
      bytes += statSync(full).size;
    }
  }
  return { files, bytes };
}

export function buildPages(targetDir = DEFAULT_OUT) {
  const outDir = path.resolve(targetDir);
  const inRepo = outDir === ROOT || outDir.startsWith(ROOT + path.sep);
  const containsRepo = path.dirname(outDir) === outDir || ROOT.startsWith(outDir + path.sep);
  if ((inRepo && outDir !== DEFAULT_OUT) || containsRepo) {
    throw new Error(`拒绝覆盖受保护目录：${outDir}`);
  }
  rmSync(outDir, { recursive: true, force: true });
  mkdirSync(outDir, { recursive: true });
  writeFileSync(path.join(outDir, '.nojekyll'), '');

  for (const f of VIEWER_FILES) {
    const src = path.join(VIEWER, f);
    if (!existsSync(src)) throw new Error(`缺少阅读器静态文件：${src}`);
    copyFileSync(src, path.join(outDir, f));
  }
  for (const d of VIEWER_DIRS) {
    copyTreeFiltered(path.join(VIEWER, d), path.join(outDir, d));
  }
  for (const spec of REDIRECT_PAGES) {
    const dir = path.join(outDir, spec.dir);
    mkdirSync(dir, { recursive: true });
    writeFileSync(path.join(dir, 'index.html'), makeRedirectHtml(spec), 'utf8');
  }
  copyFileSync(path.join(ROOT, 'LICENSE'), path.join(outDir, 'LICENSE'));

  const tracked = execFileSync('git', ['ls-files', '-z', 'runs/'], { cwd: ROOT, maxBuffer: 16 * 1024 * 1024 })
    .toString('utf8')
    .split('\0')
    .filter(Boolean)
    .sort();

  let pgnCount = 0, analysisCount = 0;
  for (const rel of tracked) {
    if (/^runs\/quiz-/.test(rel)) continue;
    const isPgn = /^runs\/.+\/game\.pgn$/.test(rel);
    const isAna = /^runs\/.+\/analysis\.jsonl$/.test(rel);
    if (!isPgn && !isAna) continue;
    const dst = path.join(outDir, rel);
    mkdirSync(path.dirname(dst), { recursive: true });
    copyFileSync(path.join(ROOT, rel), dst);
    if (isPgn) pgnCount++;
    else analysisCount++;
  }

  const { files: totalFiles, bytes: totalBytes } = measureDir(outDir);
  return { outDir, pgnCount, analysisCount, totalFiles, totalBytes };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const arg = process.argv[2];
  const res = buildPages(arg ? path.resolve(arg) : path.join(ROOT, '_site'));
  const mb = (res.totalBytes / (1024 * 1024)).toFixed(2);
  console.log(`Built Pages site at ${res.outDir}: ${res.totalFiles} files (${mb} MiB), ${res.pgnCount} game.pgn, ${res.analysisCount} analysis.jsonl`);
}
