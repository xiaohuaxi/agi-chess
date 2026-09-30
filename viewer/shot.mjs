// 静态截图：起本机服务，无头打开 index.html 的若干格画面，各截一张 2 倍图（540×720 → 1080×1440）。
// 用法：node viewer/shot.mjs <输出目录> [--runs <目录>] [--measure] <名字>=<网址参数> ...
//   例：node viewer/shot.mjs /tmp/shots --runs ~/repos/llm-chess/runs chess-open='files=/runs/g1-c-opus-sol/game.pgn&ply=0'
//   --runs 把网址 /runs/ 映射到给定目录（worktree 里没有 runs/）；--measure 另存 <名字>.json：页面里实测的各块尺寸。
// 浏览器：playwright-core 锁在 1.58.2，默认用它配套的缓存 chromium-1208；缓存里没有时用 VIEWER_CHROMIUM 指到可执行文件。
import { chromium } from 'playwright-core';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { serve } from './serve.mjs';

const args = process.argv.slice(2);
const out = args.shift();
if (!out) { console.error('usage: node viewer/shot.mjs <out-dir> [--runs DIR] [--measure] name=query ...'); process.exit(2); }
let runs = null, measure = false;
const shots = [];
while (args.length) {
  const a = args.shift();
  if (a === '--runs') runs = path.resolve(args.shift());
  else if (a === '--measure') measure = true;
  else { const i = a.indexOf('='); shots.push([a.slice(0, i), a.slice(i + 1)]); }
}
mkdirSync(out, { recursive: true });
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

// 在页面里量：各块的实际矩形、每行文字的字号 / 行高 / 实际高度，可能挤的元素的内容宽度与可用宽度。
function measurePage() {
  const r = (e) => { const b = e.getBoundingClientRect(); return { top: b.top, height: b.height, left: b.left, width: b.width }; };
  const font = (e) => { const s = getComputedStyle(e); return { size: s.fontSize, lh: s.lineHeight, weight: s.fontWeight }; };
  const shown = (e) => e && !e.hidden && getComputedStyle(e).display !== 'none';
  const blocks = ['#stage', '#strip', '#bar-top', '#board-area', '#bar-bottom', '#board-chess', '#board-xq', '#banner', '#summary']
    .map((s) => [s, document.querySelector(s)]).filter(([, e]) => shown(e)).map(([s, e]) => ({ sel: s, ...r(e) }));
  const texts = [];
  const item = (where, sel, e, extra = {}) => texts.push({ where, sel, text: e.textContent, ...font(e), ...r(e),
    scrollWidth: e.scrollWidth, clientWidth: e.clientWidth, ...extra });
  for (const bar of ['#bar-top', '#bar-bottom']) {
    const b = document.querySelector(bar);
    if (!shown(b)) continue;
    for (const sel of ['.row1', '.row2', '.disc', '.name', '.effort', '.score', '.win', '.move', '.mv', '.tag', '.think', '.delta']) {
      for (const e of b.querySelectorAll(sel)) item(bar, sel, e);
    }
    const row1 = b.querySelector('.row1'), row2 = b.querySelector('.row2');
    const cs = getComputedStyle(b);
    texts.push({ where: bar, sel: '(padding)', padTop: cs.paddingTop, padBottom: cs.paddingBottom, padLeft: cs.paddingLeft,
      padRight: cs.paddingRight, gap: cs.rowGap, contentTop: row1.getBoundingClientRect().top - b.getBoundingClientRect().top,
      contentBottom: b.getBoundingClientRect().bottom - row2.getBoundingClientRect().bottom });
  }
  const strip = document.querySelector('#strip');
  if (shown(strip)) item('#strip', '#strip', strip);
  const banner = document.querySelector('#banner');
  if (shown(banner)) {
    const cs = getComputedStyle(banner);
    item('#banner', '#banner', banner, { split: banner.classList.contains('split'), bg: cs.backgroundColor, padTop: cs.paddingTop,
      padLeft: cs.paddingLeft, padRight: cs.paddingRight });
    for (const sel of ['.b-head', '.b-head .res', '.b-head .why', '.b-name', '.b-name .name', '.b-name .effort']) {
      for (const e of banner.querySelectorAll(sel)) item('#banner', sel, e);
    }
  }
  const sum = document.querySelector('#summary');
  if (shown(sum)) {
    for (const sel of ['.s-kind', '.s-title', '.s-row', '.s-row .name', '.s-row .effort', '.s-row .score']) {
      for (const e of sum.querySelectorAll(sel)) item('#summary', sel, e);
    }
  }
  return { viewport: [innerWidth, innerHeight], blocks, texts };
}

const server = await serve(root, runs ? { '/runs/': runs } : {});
const browser = await chromium.launch({ executablePath: process.env.VIEWER_CHROMIUM || undefined });
let failed = 0;
try {
  const ctx = await browser.newContext({ viewport: { width: 540, height: 720 }, deviceScaleFactor: 2 });
  for (const [name, query] of shots) {
    const page = await ctx.newPage();
    page.on('pageerror', (e) => console.error(name, 'pageerror', e.message));
    await page.goto(`http://127.0.0.1:${server.port}/viewer/?layout=compact&${query}`);
    try {
      await page.evaluate(() => window.viewer.ready);
    } catch (e) {
      console.error(name, 'ready failed:', e.message);
      failed++;
      await page.close();
      continue;
    }
    const file = path.join(out, `${name}.png`);
    await page.screenshot({ path: file });
    if (measure) writeFileSync(path.join(out, `${name}.json`), JSON.stringify(await page.evaluate(measurePage), null, 1));
    console.log(file);
    await page.close();
  }
} finally {
  await browser.close();
  await server.close();
}
process.exit(failed ? 1 : 0);
