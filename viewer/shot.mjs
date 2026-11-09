// 静态截图：起本机服务，无头打开 index.html 的若干格画面，各截一张 2 倍图（540×720 → 1080×1440）。
// 用法：node viewer/shot.mjs <输出目录> [--runs <目录>] [--measure] [--size 宽x高] <名字>=<网址参数> ...
//   例：node viewer/shot.mjs /tmp/shots --runs ~/repos/agi-chess/runs chess-open='files=/runs/g1-c-opus-sol/game.pgn&ply=0'
//   --runs 把网址 /runs/ 映射到给定目录（供查看外部未入库的本地对局目录；已入库对局直接在仓内 runs/ 下）；--measure 另存 <名字>.json：页面里实测的各块尺寸。
//   --size 换视口（默认 540x720，宽版截图用如 1440x900）；网址参数里没写 layout= 时补 layout=compact。
// 浏览器：优先用 VIEWER_CHROMIUM，其次用 playwright-core 配套的缓存浏览器，再从 PATH 与常见系统路径查找 Chromium / Chrome。
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { resolveChromium, serve } from './serve.mjs';

export const HELP = `用法：node viewer/shot.mjs <输出目录> [--runs <目录>] [--measure] [--size 宽x高] <名字>=<网址参数> ...

选项：
  --runs <目录>   把网址 /runs/ 映射到给定目录
  --measure       另存 <名字>.json：页面里实测的各块尺寸
  --size <宽x高>  视口尺寸（默认 540x720，截图按 2x 导出为 1080x1440）
  -h, --help      显示本说明
`;

export function parseShotCli(argv) {
  const args = [...argv];
  if (args.includes('-h') || args.includes('--help')) return { help: true };
  if (!args.length) throw new Error('缺少 <输出目录> 与 <名字>=<网址参数>');
  const out = args.shift();
  if (out.startsWith('-')) throw new Error(`第一个参数须为 <输出目录>，收到选项：${out}`);
  let runs = null, measure = false, size = [540, 720];
  const shots = [];
  while (args.length) {
    const a = args.shift();
    if (a === '--runs') {
      const v = args.shift();
      if (!v) throw new Error('--runs 缺少目录参数');
      runs = path.resolve(v);
    } else if (a === '--measure') {
      measure = true;
    } else if (a === '--size') {
      const v = args.shift();
      if (!v || !/^\d+x\d+$/.test(v)) throw new Error(`--size 格式须为 宽x高（如 540x720）：${v ?? ''}`);
      size = v.split('x').map(Number);
      if (size[0] <= 0 || size[1] <= 0) throw new Error(`--size 宽高须大于 0：${v}`);
    } else if (a.startsWith('-')) {
      throw new Error(`不认识的选项：${a}`);
    } else {
      const i = a.indexOf('=');
      if (i <= 0) throw new Error(`截图项格式须为 <名字>=<网址参数>：${a}`);
      shots.push([a.slice(0, i), a.slice(i + 1)]);
    }
  }
  if (!shots.length) throw new Error('至少给出一项 <名字>=<网址参数>');
  return { out, runs, measure, size, shots };
}

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
  const title = document.querySelector('#title');
  if (shown(title)) {
    const cs = getComputedStyle(title), area = document.querySelector('#board-area').getBoundingClientRect();
    item('#title', '#title', title, { padTop: cs.paddingTop, padBottom: cs.paddingBottom,
      areaTop: area.top, areaBottom: area.bottom });
    for (const sel of ['.t-head', '.t-row', '.t-row .name', '.t-row .effort', '.t-vs']) {
      for (const e of title.querySelectorAll(sel)) item('#title', sel, e);
    }
  }
  return { viewport: [innerWidth, innerHeight], blocks, texts };
}

async function main() {
  let o;
  try {
    o = parseShotCli(process.argv.slice(2));
  } catch (e) {
    console.error(`参数不对：${e.message}\n`);
    console.error(HELP);
    process.exit(2);
  }
  if (o.help) {
    process.stdout.write(HELP);
    return;
  }
  let chromium;
  try {
    ({ chromium } = await import('playwright-core'));
  } catch (e) {
    console.error(`未安装 playwright-core，请先执行：cd viewer && npm ci --ignore-scripts（${e.message.split('\n')[0]}）`);
    process.exit(1);
  }
  const { out, runs, measure, size, shots } = o;
  const server = await serve(root, runs ? { '/runs/': runs } : {});
  let browser;
  try {
    browser = await chromium.launch({ executablePath: resolveChromium(undefined, { chromium }) });
  } catch (e) {
    await server.close();
    console.error(`起不来浏览器：${e.message.split('\n')[0]}（用环境变量 VIEWER_CHROMIUM 指到 Chromium / Chrome）`);
    process.exit(1);
  }
  mkdirSync(out, { recursive: true });
  let failed = 0;
  try {
    const ctx = await browser.newContext({ viewport: { width: size[0], height: size[1] }, deviceScaleFactor: 2 });
    for (const [name, query] of shots) {
      const page = await ctx.newPage();
      page.on('pageerror', (e) => console.error(name, 'pageerror', e.message));
      await page.goto(`http://127.0.0.1:${server.port}/viewer/?${/(^|&)layout=/.test(query) ? '' : 'layout=compact&'}${query}`);
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
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
