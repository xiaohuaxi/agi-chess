// 真实用户场景覆盖专项测试（S1–S8）：
// 基于 build-pages.mjs 生成的真实 _site/（挂载 /agi-chess/ 子路径与 / 根域），用真实 Chromium 端到端检验核心用户旅程。
import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, extname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildPages } from '../build-pages.mjs';
import { hasCjk } from '../lib/i18n.js';
import { displayName } from '../lib/match.js';
import { decodeText, parsePgn } from '../lib/pgn.js';
import { replay } from '../lib/replay.js';
import { resolveChromium, serve } from '../serve.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

let pw = null;
try { pw = await import('playwright-core'); } catch { /* 未装开发依赖 */ }
let browser = null, skip = pw ? false : '没有 playwright-core（cd viewer && npm ci）';
if (pw) {
  try { browser = await pw.chromium.launch({ executablePath: resolveChromium(undefined, pw) }); }
  catch (e) { skip = `起不来浏览器：${e.message.split('\n')[0]}`; }
}
if (process.env.VIEWER_REQUIRE_BROWSER === '1' && skip) throw new Error(skip);

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.json': 'application/json',
  '.jsonl': 'text/plain; charset=utf-8', '.png': 'image/png', '.pgn': 'text/plain; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8', '.mp3': 'audio/mpeg',
};

// 模拟 GitHub Pages 行为：/agi-chess/ 静态站，缺失路径返回真实 HTTP 404 + _site/404.html
async function servePagesSubpath(siteDir, prefix = '/agi-chess/') {
  const notFoundHtml = readFileSync(join(siteDir, '404.html'));
  const server = http.createServer((req, res) => {
    const urlObj = new URL(req.url, 'http://127.0.0.1');
    const pathname = decodeURIComponent(urlObj.pathname);
    if (pathname === '/favicon.ico') { res.writeHead(204).end(); return; }
    if (!pathname.startsWith(prefix)) {
      res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' }).end('Not Found');
      return;
    }
    let rel = pathname.slice(prefix.length);
    if (!rel || rel.endsWith('/')) rel += 'index.html';
    const full = resolve(siteDir, rel);
    if (full !== siteDir && !full.startsWith(siteDir + sep)) {
      res.writeHead(403).end();
      return;
    }
    if (existsSync(full)) {
      try {
        const body = readFileSync(full);
        res.writeHead(200, { 'content-type': MIME[extname(full)] || 'application/octet-stream' }).end(body);
        return;
      } catch { /* fall through to 404 */ }
    }
    res.writeHead(404, { 'content-type': 'text/html; charset=utf-8' }).end(notFoundHtml);
  });
  await new Promise((ok, bad) => server.listen(0, '127.0.0.1', ok).on('error', bad));
  return { port: server.address().port, close: () => new Promise((ok) => server.close(ok)) };
}

function attachHealthMonitors(page, { allowResponse = () => false, allowConsoleError = () => false } = {}) {
  const pageErrors = [];
  const consoleErrors = [];
  const badResponses = [];
  page.on('pageerror', (e) => pageErrors.push(String(e?.message || e)));
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    if (!allowConsoleError(text)) consoleErrors.push(text);
  });
  page.on('response', (res) => {
    if (res.status() < 400) return;
    const info = { status: res.status(), url: res.url() };
    if (!allowResponse(info)) badResponses.push(`${info.status} ${info.url}`);
  });
  return {
    assertClean(label) {
      assert.deepEqual(pageErrors, [], `${label} pageerror`);
      assert.deepEqual(consoleErrors, [], `${label} console.error`);
      assert.deepEqual(badResponses, [], `${label} unexpected >=400`);
    },
  };
}

async function collectUiTexts(page) {
  return page.evaluate(() => {
    const out = [];
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const e = n.parentElement;
      if (!n.textContent.trim() || !e || e.closest('.xq-piece, .xq-file, #s-note .why, #s-note .raw, .lang-switch, script')) continue;
      if (!e.getClientRects().length) continue;
      out.push(n.textContent.trim());
    }
    for (const e of document.querySelectorAll('input[placeholder], [aria-label], [title], option')) {
      if (e.placeholder) out.push(e.placeholder);
      const al = e.getAttribute('aria-label');
      if (al) out.push(al);
      if (e.title) out.push(e.title);
      if (e.tagName === 'OPTION') out.push(e.textContent.trim());
    }
    out.push(document.title);
    return out;
  });
}

let tmpDir = null;
let siteDir = null;
let pagesServer = null;
let rootServer = null;
let pagesBase = '';
let rootBase = '';

before(async () => {
  tmpDir = mkdtempSync(join(tmpdir(), 'viewer-scenarios-'));
  siteDir = join(tmpDir, '_site');
  buildPages(siteDir);
  pagesServer = await servePagesSubpath(siteDir, '/agi-chess/');
  rootServer = await serve(siteDir);
  pagesBase = `http://127.0.0.1:${pagesServer.port}/agi-chess/`;
  rootBase = `http://127.0.0.1:${rootServer.port}/`;
});

after(async () => {
  await browser?.close();
  await pagesServer?.close();
  await rootServer?.close();
  if (tmpDir) rmSync(tmpDir, { recursive: true, force: true });
});

test('S1：X 访客冷开深链（360×740 手机 + 1280×800 桌面）与翻步刷新保位、中英互切', { skip }, async () => {
  const mobCtx = await browser.newContext({
    viewport: { width: 360, height: 740 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  const deskCtx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const mobPage = await mobCtx.newPage();
  const deskPage = await deskCtx.newPage();
  const mobHealth = attachHealthMonitors(mobPage);
  const deskHealth = attachHealthMonitors(deskPage);

  try {
    await mobPage.goto(`${pagesBase}?files=runs/neon-xhigh-vs-carbon-high-20261119&ply=40&lang=en`);
    await mobPage.evaluate(() => window.viewer.ready);
    await new Promise((ok) => setTimeout(ok, 350)); // 确认未自动播放

    const snap40 = await mobPage.evaluate(() => ({
      curPly: Number(document.querySelector('#s-moves .cur')?.dataset.ply),
      head: document.querySelector('#s-note .n-head')?.textContent || '',
      nags: [...document.querySelectorAll('#s-note .nag.bad')].map((e) => e.textContent),
      who: document.querySelector('#s-note .who')?.textContent || '',
      evalText: document.querySelector('#s-note .n-eval')?.textContent || '',
      players: [...document.querySelectorAll('.bar .name')].map((e) => e.textContent),
      playBtn: document.getElementById('s-play')?.textContent || '',
      homeHref: document.querySelector('#s-head .home-link')?.getAttribute('href') || '',
      effMargin: getComputedStyle(document.querySelector('#bar-bottom .effort')).marginLeft,
    }));
    assert.equal(snap40.curPly, 40);
    assert.match(snap40.head, /^20\.\.\. Re8/);
    assert.deepEqual(snap40.nags, ['?? Blunder']);
    assert.equal(snap40.who, 'Gemini 4 Carbon +high');
    assert.equal(snap40.effMargin, '5px');
    assert.deepEqual(snap40.players, ['Gemini 4 Carbon', 'Gemini 4 Neon']);
    assert.match(snap40.evalText, /White eval \+1\.02 → \+4\.10/);
    assert.match(snap40.evalText, /White win% 59\.3% → 81\.9%/);
    assert.match(snap40.evalText, /Best Kg7/);
    assert.equal(snap40.playBtn, 'Play');
    assert.equal(snap40.homeHref, '/agi-chess/?lang=en');
    assert.deepEqual((await collectUiTexts(mobPage)).filter(hasCjk), [], 'S1 mobile EN CJK');

    // 点下一步 → URL 更新为 ply=41
    await mobPage.tap('#s-ctrl [data-act="next"]');
    await mobPage.waitForFunction(() => new URL(location.href).searchParams.get('ply') === '41', null, { timeout: 4000 });
    const mobAt41 = await mobPage.evaluate(() => ({
      url: location.href,
      curPly: Number(document.querySelector('#s-moves .cur')?.dataset.ply),
      moveHead: document.querySelector('#s-note .n-head')?.firstChild?.textContent || '',
    }));
    assert.equal(mobAt41.curPly, 41);

    // 复制 URL 在全新桌面上下文打开，确认落地 ply=41 且步号、局面、英文一致
    await deskPage.goto(mobAt41.url);
    await deskPage.evaluate(() => window.viewer.ready);
    const deskAt41 = await deskPage.evaluate(() => ({
      lang: document.documentElement.lang,
      curPly: Number(document.querySelector('#s-moves .cur')?.dataset.ply),
      moveHead: document.querySelector('#s-note .n-head')?.firstChild?.textContent || '',
      evalText: document.querySelector('#s-note .n-eval')?.textContent || '',
      effMargin: getComputedStyle(document.querySelector('#bar-bottom .effort')).marginLeft,
    }));
    assert.equal(deskAt41.lang, 'en');
    assert.equal(deskAt41.curPly, 41);
    assert.equal(deskAt41.moveHead, mobAt41.moveHead);
    assert.match(deskAt41.evalText, /White win%/);
    assert.equal(deskAt41.effMargin, '5px');
    assert.deepEqual((await collectUiTexts(deskPage)).filter(hasCjk), [], 'S1 desktop EN CJK');

    // 中英来回切换保留 files 与 ply=41，评估标签在 White win% ↔ 白方胜率 正确切换
    await Promise.all([deskPage.waitForNavigation(), deskPage.click('#s-head a.lang-switch')]);
    await deskPage.evaluate(() => window.viewer.ready);
    const deskZh = await deskPage.evaluate(() => {
      const q = new URL(location.href).searchParams;
      return {
        lang: document.documentElement.lang,
        files: q.get('files'),
        ply: q.get('ply'),
        evalText: document.querySelector('#s-note .n-eval')?.textContent || '',
      };
    });
    assert.equal(deskZh.lang, 'zh-CN');
    assert.equal(deskZh.files, 'runs/neon-xhigh-vs-carbon-high-20261119');
    assert.equal(deskZh.ply, '41');
    assert.match(deskZh.evalText, /白方胜率/);

    await Promise.all([deskPage.waitForNavigation(), deskPage.click('#s-head a.lang-switch')]);
    await deskPage.evaluate(() => window.viewer.ready);
    const deskEnAgain = await deskPage.evaluate(() => {
      const q = new URL(location.href).searchParams;
      return {
        lang: document.documentElement.lang,
        files: q.get('files'),
        ply: q.get('ply'),
        evalText: document.querySelector('#s-note .n-eval')?.textContent || '',
      };
    });
    assert.equal(deskEnAgain.lang, 'en');
    assert.equal(deskEnAgain.files, 'runs/neon-xhigh-vs-carbon-high-20261119');
    assert.equal(deskEnAgain.ply, '41');
    assert.match(deskEnAgain.evalText, /White win%/);

    // 顶栏 Home 链回英文首页且精选卡第 3 张写 Gemini 4 Carbon
    await Promise.all([deskPage.waitForNavigation(), deskPage.click('#s-head .home-link')]);
    await deskPage.evaluate(() => window.viewer.ready);
    const home = await deskPage.evaluate(() => ({
      lang: document.documentElement.lang,
      empty: document.getElementById('stage').classList.contains('empty'),
      card3: document.querySelectorAll('#hint .h-link .h-name')[2]?.textContent || '',
    }));
    assert.deepEqual(home, {
      lang: 'en',
      empty: true,
      card3: 'Xiangqi · Claude Opus 5.5 (agy) vs Gemini 4 Carbon',
    });

    mobHealth.assertClean('S1-mobile');
    deskHealth.assertClean('S1-desktop');
  } finally {
    await mobCtx.close();
    await deskCtx.close();
  }
});

test('S2：榜单名复制搜目录、空态恢复、三页往返保态与切语言保 hash', { skip }, async () => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  const health = attachHealthMonitors(page);

  try {
    // 1) series.html?lang=en → 切 Xiangqi → ▶ Play Series → 下拉切 G2 → 返回 series.html?variant=xiangqi&lang=en
    await page.goto(`${pagesBase}series.html?lang=en`);
    await page.evaluate(() => window.pageReady);
    await page.click('button.seg-btn[data-variant="xiangqi"]');
    await Promise.all([page.waitForNavigation(), page.click('.s-card a.btn-play')]);
    await page.evaluate(() => window.viewer.ready);
    await page.selectOption('#s-game', '1');
    await page.waitForFunction(() => document.getElementById('strip')?.textContent === 'Game 2 of 4');
    await Promise.all([page.waitForNavigation(), page.click('#s-head .back-link')]);
    await page.evaluate(() => window.pageReady);
    const backSeries = await page.evaluate(() => {
      const q = new URL(location.href).searchParams;
      return {
        pathname: location.pathname,
        variant: q.get('variant'),
        lang: q.get('lang'),
        activeSeg: document.querySelector('.seg-btn.active')?.dataset.variant,
      };
    });
    assert.deepEqual(backSeries, {
      pathname: '/agi-chess/series.html',
      variant: 'xiangqi',
      lang: 'en',
      activeSeg: 'xiangqi',
    });

    // 2) catalog.html?lang=en：Series Board 覆盖名搜索 100% 命中 + 空态恢复 + 筛选进单局原位返回
    await page.goto(`${pagesBase}catalog.html?lang=en`);
    await page.evaluate(() => window.pageReady);

    await page.fill('#cat-q', 'Claude Opus 5.5 (CLI)');
    const cliHits = await page.evaluate(() => [...document.querySelectorAll('.cat-row')].map((r) => r.dataset.dir));
    assert.ok(cliHits.length >= 20 && cliHits.includes('runs/g7-c-opus-astra-1'), `CLI alias hits=${cliHits.length}`);

    await page.fill('#cat-q', 'GPT-6 Astra');
    const astra6Hits = await page.evaluate(() => [...document.querySelectorAll('.cat-row')].map((r) => r.dataset.dir));
    assert.ok(astra6Hits.length >= 20 && astra6Hits.includes('runs/g7-c-opus-astra-1'), `GPT-6 Astra hits=${astra6Hits.length}`);

    await page.fill('#cat-q', 'Claude Opus 5.5 (agy) +high');
    const agyHits = await page.evaluate(() => document.querySelectorAll('.cat-row').length);
    assert.equal(agyHits, 12);

    await page.fill('#cat-q', 'agy Opus');
    assert.equal(await page.evaluate(() => document.querySelectorAll('.cat-row').length), 12);

    await page.fill('#cat-q', 'zzznomatch999');
    const emptyState = await page.evaluate(() => ({
      rows: document.querySelectorAll('.cat-row').length,
      emptyText: document.querySelector('.empty-box p')?.textContent || '',
    }));
    assert.deepEqual(emptyState, { rows: 0, emptyText: 'No games match the current filters.' });

    await page.fill('#cat-q', '');
    assert.equal(await page.evaluate(() => document.querySelectorAll('.cat-row').length), 192);

    // 筛选 Xiangqi + Model vs Model → 点第一局 → 返回保留筛选与英文
    await page.click('.filter-row .pill-group:nth-child(1) .f-pill[data-val="xiangqi"]');
    await page.click('.filter-row .pill-group:nth-child(2) .f-pill[data-val="h2h"]');
    const beforeEnter = await page.evaluate(() => document.querySelectorAll('.cat-row').length);
    assert.ok(beforeEnter > 0 && beforeEnter < 84);
    await Promise.all([page.waitForNavigation(), page.click('.cat-row')]);
    await page.evaluate(() => window.viewer.ready);
    await Promise.all([page.waitForNavigation(), page.click('#s-head .back-link')]);
    await page.evaluate(() => window.pageReady);
    const backCat = await page.evaluate(() => {
      const q = new URL(location.href).searchParams;
      return {
        variant: q.get('variant'),
        cat: q.get('cat'),
        lang: q.get('lang'),
        rows: document.querySelectorAll('.cat-row').length,
      };
    });
    assert.deepEqual(backCat, { variant: 'xiangqi', cat: 'h2h', lang: 'en', rows: beforeEnter });

    // 3) 同页切语言保留 location.hash
    await page.goto(`${pagesBase}catalog.html?q=neon#app`);
    await page.evaluate(() => window.pageReady);
    await Promise.all([page.waitForNavigation(), page.click('#top-header a.lang-switch')]);
    await page.evaluate(() => window.pageReady);
    assert.deepEqual(await page.evaluate(() => ({
      pathname: location.pathname,
      q: new URL(location.href).searchParams.get('q'),
      lang: new URL(location.href).searchParams.get('lang'),
      hash: location.hash,
    })), { pathname: '/agi-chess/catalog.html', q: 'neon', lang: 'en', hash: '#app' });

    await page.goto(`${pagesBase}series.html?variant=xiangqi#s1`);
    await page.evaluate(() => window.pageReady);
    await Promise.all([page.waitForNavigation(), page.click('#top-header a.lang-switch')]);
    await page.evaluate(() => window.pageReady);
    assert.deepEqual(await page.evaluate(() => ({
      pathname: location.pathname,
      variant: new URL(location.href).searchParams.get('variant'),
      lang: new URL(location.href).searchParams.get('lang'),
      hash: location.hash,
    })), { pathname: '/agi-chess/series.html', variant: 'xiangqi', lang: 'en', hash: '#s1' });

    health.assertClean('S2');
  } finally {
    await ctx.close();
  }
});

test('S3：尾斜杠重定向、保 query+hash 与浏览器后退链（/agi-chess/ 与 / 根域）', { skip }, async () => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  const health = attachHealthMonitors(page);

  try {
    // 1) /agi-chess/ 下：先停首页，再跳尾斜杠重定向页 → 改 2 次筛选 → 进单局 → goBack 2 次不卡死
    await page.goto(`${pagesBase}?lang=en`);
    await page.evaluate(() => window.viewer.ready);

    await page.goto(`${pagesBase}catalog/?q=neon&lang=en#app`);
    await page.waitForFunction(() => location.pathname === '/agi-chess/catalog.html');
    await page.evaluate(() => window.pageReady);
    assert.deepEqual(await page.evaluate(() => ({
      q: new URL(location.href).searchParams.get('q'),
      lang: new URL(location.href).searchParams.get('lang'),
      hash: location.hash,
      rows: document.querySelectorAll('.cat-row').length,
    })), { q: 'neon', lang: 'en', hash: '#app', rows: 8 });

    // 改 2 次筛选后进单局
    await page.click('.filter-row .pill-group:nth-child(1) .f-pill[data-val="chess"]');
    await page.selectOption('.sort-select', 'longest');
    await Promise.all([page.waitForNavigation(), page.click('.cat-row')]);
    await page.evaluate(() => window.viewer.ready);

    // goBack #1：回到 catalog.html 且筛选与 #app 保留
    await page.goBack();
    await page.waitForFunction(() => location.pathname === '/agi-chess/catalog.html');
    await page.evaluate(() => window.pageReady);
    assert.deepEqual(await page.evaluate(() => {
      const q = new URL(location.href).searchParams;
      return { variant: q.get('variant'), q: q.get('q'), sort: q.get('sort'), lang: q.get('lang'), hash: location.hash };
    }), { variant: 'chess', q: 'neon', sort: 'longest', lang: 'en', hash: '#app' });

    // goBack #2：越过 location.replace 重定向页直接回到首页，不被卡死
    await page.goBack();
    await page.waitForFunction(() => location.pathname === '/agi-chess/' && !location.search.includes('files='));
    await page.evaluate(() => window.viewer.ready);
    assert.equal(await page.evaluate(() => document.getElementById('stage').classList.contains('empty')), true);

    // 2) /agi-chess/series/ 尾斜杠重定向保留 variant/lang/hash
    await page.goto(`${pagesBase}series/?variant=xiangqi&lang=en#s1`);
    await page.waitForFunction(() => location.pathname === '/agi-chess/series.html');
    await page.evaluate(() => window.pageReady);
    assert.deepEqual(await page.evaluate(() => ({
      variant: new URL(location.href).searchParams.get('variant'),
      lang: new URL(location.href).searchParams.get('lang'),
      hash: location.hash,
      activeSeg: document.querySelector('.seg-btn.active')?.dataset.variant,
    })), { variant: 'xiangqi', lang: 'en', hash: '#s1', activeSeg: 'xiangqi' });

    // 3) 根域 / 下的 /catalog/?q=neon#top
    await page.goto(`${rootBase}catalog/?q=neon#top`);
    await page.waitForFunction(() => location.pathname === '/catalog.html');
    await page.evaluate(() => window.pageReady);
    assert.deepEqual(await page.evaluate(() => ({
      pathname: location.pathname,
      q: new URL(location.href).searchParams.get('q'),
      hash: location.hash,
      rows: document.querySelectorAll('.cat-row').length,
    })), { pathname: '/catalog.html', q: 'neon', hash: '#top', rows: 8 });

    // 4) serve.mjs 安全收紧验证：协议相对与未知前缀尾斜杠不可触发 302
    const localDev = await serve(ROOT);
    try {
      const bad1 = await fetch(`http://127.0.0.1:${localDev.port}//evil.com/catalog/`, { redirect: 'manual' });
      const bad2 = await fetch(`http://127.0.0.1:${localDev.port}/unknown/catalog/`, { redirect: 'manual' });
      assert.equal(bad1.status, 404);
      assert.equal(bad2.status, 404);
    } finally {
      await localDev.close();
    }

    health.assertClean('S3');
  } finally {
    await ctx.close();
  }
});

test('S4：手机竖屏 ↔ 横屏（>900px）旋转与 150+ 半回合长局单步交互', { skip }, async () => {
  const ctx = await browser.newContext({
    viewport: { width: 375, height: 667 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  const page = await ctx.newPage();
  const health = attachHealthMonitors(page);

  try {
    // runs/argon-high-self-20261019 共 158 半回合
    await page.goto(`${pagesBase}?files=runs/argon-high-self-20261019`);
    await page.evaluate(() => window.viewer.ready);
    const totalPlies = await page.evaluate(() => document.querySelectorAll('#s-moves [data-ply]').length - 1);
    assert.ok(totalPlies >= 150, `expected >=150 plies, got ${totalPlies}`);

    // 竖屏点后段第 140 步
    await page.click('#s-moves [data-ply="140"]');
    await page.waitForFunction(() => Number(document.querySelector('#s-moves .cur')?.dataset.ply) === 140);
    const readState = () => page.evaluate(() => ({
      mode: document.getElementById('stage').classList.contains('wide') ? 'wide' : 'mobile',
      curPly: Number(document.querySelector('#s-moves .cur')?.dataset.ply),
      curText: document.querySelector('#s-moves .cur')?.textContent || '',
      noteHead: document.querySelector('#s-note .n-head')?.textContent || '',
      noteWhy: document.querySelector('#s-note .why')?.textContent || '',
      overflow: document.documentElement.scrollWidth > window.innerWidth,
    }));
    const portrait1 = await readState();
    assert.equal(portrait1.mode, 'mobile');
    assert.equal(portrait1.curPly, 140);
    assert.equal(portrait1.overflow, false);

    // 切 960×450 横屏（宽版）
    await page.setViewportSize({ width: 960, height: 450 });
    await page.waitForFunction(() => document.getElementById('stage').classList.contains('wide'));
    const landscape = await readState();
    assert.equal(landscape.mode, 'wide');
    assert.equal(landscape.curPly, 140);
    assert.equal(landscape.curText, portrait1.curText);
    assert.equal(landscape.noteHead, portrait1.noteHead);
    assert.equal(landscape.noteWhy, portrait1.noteWhy);
    assert.equal(landscape.overflow, false);

    // 切回 375×667 竖屏并单步 +1
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForFunction(() => document.getElementById('stage').classList.contains('mobile'));
    const portrait2 = await readState();
    assert.equal(portrait2.mode, 'mobile');
    assert.equal(portrait2.curPly, 140);
    assert.equal(portrait2.curText, portrait1.curText);
    assert.equal(portrait2.noteHead, portrait1.noteHead);
    assert.equal(portrait2.overflow, false);

    await page.tap('#s-ctrl [data-act="next"]');
    await page.waitForFunction(() => Number(document.querySelector('#s-moves .cur')?.dataset.ply) === 141);
    const afterNext = await readState();
    assert.equal(afterNext.curPly, 141);
    assert.equal(afterNext.overflow, false);

    health.assertClean('S4');
  } finally {
    await ctx.close();
  }
});

test('S5：特殊归档局（唯一无分析局 + 重试告警局 + 随机/引擎局）', { skip }, async () => {
  const catalog = JSON.parse(readFileSync(join(siteDir, 'lib', 'catalog-data.json'), 'utf8'));
  const randomGame = catalog.games.find((g) => g.subcat === 'random');
  const fsfGame = catalog.games.find((g) => g.w.raw.startsWith('engine:fsf:') || g.b.raw.startsWith('engine:fsf:'));
  assert.ok(randomGame && fsfGame);

  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  // 唯一无分析局允许同目录可选 analysis.jsonl 404
  const health = attachHealthMonitors(page, {
    allowResponse: (r) => r.status === 404 && r.url.endsWith('/runs/gemini38-flash-high-clean-20261015/analysis.jsonl'),
    allowConsoleError: (t) => /404/.test(t) && /Failed to load resource/i.test(t),
  });

  try {
    // 1) 唯一无分析局 runs/gemini38-flash-high-clean-20261015 跳至末步 104：零报错、无虚构 .n-eval
    await page.goto(`${pagesBase}?files=runs/gemini38-flash-high-clean-20261015&ply=end`);
    await page.evaluate(() => window.viewer.ready);
    const unana = await page.evaluate(() => ({
      curPly: Number(document.querySelector('#s-moves .cur')?.dataset.ply),
      hasEval: !!document.querySelector('#s-note .n-eval'),
      bannerHidden: document.getElementById('banner').hidden,
    }));
    assert.deepEqual(unana, { curPly: 104, hasEval: false, bannerHidden: false });

    // 2) 切到有分析中象局 ply=9（5. 车九平八??）：中文 车二进六 / 英文 R2+6
    await page.goto(`${pagesBase}?files=runs/carbon-vs-agy-opus-high-xq-20261114-3&ply=9`);
    await page.evaluate(() => window.viewer.ready);
    assert.match(await page.evaluate(() => document.querySelector('#s-note .n-eval')?.textContent || ''), /车二进六/);
    await page.goto(`${pagesBase}?files=runs/carbon-vs-agy-opus-high-xq-20261114-3&ply=9&lang=en`);
    await page.evaluate(() => window.viewer.ready);
    assert.match(await page.evaluate(() => document.querySelector('#s-note .n-eval')?.textContent || ''), /R2\+6/);

    // 3) 重试告警局 ply=70：.why-warn 与 .why-body 分段可见、棋盘实际落子 Rf6
    await page.goto(`${pagesBase}?files=runs/neon-xhigh-vs-carbon-high-20261119-2&ply=70&lang=en`);
    await page.evaluate(() => window.viewer.ready);
    const warn70 = await page.evaluate(() => ({
      warnVisible: [...document.querySelectorAll('#s-note .why-warn')].some((e) => e.getBoundingClientRect().height > 0),
      bodyVisible: [...document.querySelectorAll('#s-note .why-body')].some((e) => e.getBoundingClientRect().height > 0),
      head: document.querySelector('#s-note .n-head')?.firstChild?.textContent || '',
      f6Piece: document.querySelector('#board-chess .pieces [data-square="f6"]')?.getAttribute('data-piece') || '',
    }));
    assert.equal(warn70.warnVisible, true);
    assert.equal(warn70.bodyVisible, true);
    assert.match(warn70.head, /35\.\.\. Rf6/);
    assert.equal(warn70.f6Piece, 'br');

    // 4) vs Random：中文「随机棋手」↔ 英文「Random」
    await page.goto(`${pagesBase}?files=${randomGame.dir}`);
    await page.evaluate(() => window.viewer.ready);
    assert.ok((await page.evaluate(() => [...document.querySelectorAll('.bar .name')].map((e) => e.textContent))).includes('随机棋手'));
    await page.goto(`${pagesBase}?files=${randomGame.dir}&lang=en`);
    await page.evaluate(() => window.viewer.ready);
    assert.ok((await page.evaluate(() => [...document.querySelectorAll('.bar .name')].map((e) => e.textContent))).includes('Random'));

    // 5) 引擎局：Fairy-Stockfish · ... 与 Maia 1900
    await page.goto(`${pagesBase}?files=${fsfGame.dir}&lang=en`);
    await page.evaluate(() => window.viewer.ready);
    assert.ok((await page.evaluate(() => [...document.querySelectorAll('.bar .name')].map((e) => e.textContent))).some((t) => /^Fairy-Stockfish · /.test(t)));

    await page.goto(`${pagesBase}?files=runs/zc/maia-1900-s1-w&lang=en`);
    await page.evaluate(() => window.viewer.ready);
    assert.ok((await page.evaluate(() => [...document.querySelectorAll('.bar .name')].map((e) => e.textContent))).includes('Maia 1900'));

    health.assertClean('S5');
  } finally {
    await ctx.close();
  }
});

test('S6：真实 HTTP 404 恢复 + 非法 files 容错 + 错配文件拖入现场恢复', { skip }, async () => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  const pageErrors = [];
  page.on('pageerror', (e) => pageErrors.push(String(e?.message || e)));

  try {
    // 1) 真实 HTTP 404（_site/404.html）：三个入口分别跳到 200 的英文首页、Series Board、All Games (192)
    const missingUrl = `${pagesBase}ladder/missing?lang=en`;
    const r404 = await page.goto(missingUrl);
    assert.equal(r404.status(), 404);

    const [homeRes] = await Promise.all([page.waitForNavigation(), page.click('#link-home')]);
    assert.equal(homeRes.status(), 200);
    await page.evaluate(() => window.viewer.ready);
    assert.equal(await page.evaluate(() => document.documentElement.lang), 'en');

    await page.goto(missingUrl);
    const [serRes] = await Promise.all([page.waitForNavigation(), page.click('#link-series')]);
    assert.equal(serRes.status(), 200);
    await page.evaluate(() => window.pageReady);
    assert.equal(await page.evaluate(() => document.documentElement.lang), 'en');

    await page.goto(missingUrl);
    const [catRes] = await Promise.all([page.waitForNavigation(), page.click('#link-catalog')]);
    assert.equal(catRes.status(), 200);
    await page.evaluate(() => window.pageReady);
    assert.equal(await page.evaluate(() => document.querySelectorAll('.cat-row').length), 192);

    // 2) 非法 files 容错：单语可见错误卡 + 有效返回链接 + 零未捕获异常
    await page.goto(`${pagesBase}?files=runs/not-exist-999&lang=en`);
    await assert.rejects(page.evaluate(() => window.viewer.ready));
    const errInfo = await page.evaluate(() => ({
      visible: !!document.querySelector('#hint .h-error'),
      title: document.querySelector('#hint .e-title')?.textContent || '',
      homeHref: document.querySelector('#hint .e-home')?.getAttribute('href') || '',
    }));
    assert.equal(errInfo.visible, true);
    assert.equal(errInfo.title, 'Failed to load game record');
    assert.equal(errInfo.homeHref, '/agi-chess/?lang=en');
    assert.deepEqual((await collectUiTexts(page)).filter(hasCjk), [], 'S6 error page EN CJK');

    const [backHomeRes] = await Promise.all([page.waitForNavigation(), page.click('#hint .e-home')]);
    assert.equal(backHomeRes.status(), 200);
    await page.evaluate(() => window.viewer.ready);

    // 3) 错配文件拖入不崩溃 → 同页重新拖入匹配文件无需刷新即恢复评分与评注
    await page.goto(`${pagesBase}?lang=en&autoplay=0`);
    await page.evaluate(() => window.viewer.ready);

    const pgnA = readFileSync(join(siteDir, 'runs/neon-xhigh-vs-carbon-high-20261119/game.pgn'), 'utf8');
    const anaA = readFileSync(join(siteDir, 'runs/neon-xhigh-vs-carbon-high-20261119/analysis.jsonl'), 'utf8');
    const anaWrong = readFileSync(join(siteDir, 'runs/neon-xhigh-vs-astra-max-20261119-4/analysis.jsonl'), 'utf8');

    const dropFiles = async (items) => {
      const dt = await page.evaluateHandle((arr) => {
        const d = new DataTransfer();
        for (const [name, text] of arr) d.items.add(new File([text], name));
        return d;
      }, items);
      await page.dispatchEvent('body', 'drop', { dataTransfer: dt });
    };

    await dropFiles([['game.pgn', pgnA], ['analysis.jsonl', anaWrong]]);
    await page.waitForFunction(() => !!document.querySelector('#hint .h-error'));
    assert.equal(await page.evaluate(() => document.getElementById('stage').classList.contains('error')), true);

    // 同一页面不刷新，重新拖入匹配的 game.pgn + analysis.jsonl
    await dropFiles([['game.pgn', pgnA], ['analysis.jsonl', anaA]]);
    await page.waitForFunction(() => !document.getElementById('stage').classList.contains('error') && document.querySelectorAll('#s-moves .m.bad').length > 0);
    assert.equal(await page.evaluate(() => document.body.dataset.error), undefined);
    await page.click('#s-moves [data-ply="40"]');
    await page.waitForFunction(() => Number(document.querySelector('#s-moves .cur')?.dataset.ply) === 40);
    const recovered = await page.evaluate(() => ({
      nags: [...document.querySelectorAll('#s-note .nag.bad')].map((e) => e.textContent),
      evalText: document.querySelector('#s-note .n-eval')?.textContent || '',
      whyLen: (document.querySelector('#s-note .why')?.textContent || '').length,
    }));
    assert.deepEqual(recovered.nags, ['?? Blunder']);
    assert.match(recovered.evalText, /\+1\.02 → \+4\.10/);
    assert.match(recovered.evalText, /Best Kg7/);
    assert.ok(recovered.whyLen > 40);

    assert.deepEqual(pageErrors, [], 'S6 pageerror');
  } finally {
    await ctx.close();
  }
});

test('S7：移动端视觉防裁切与几何硬断言（360×740 & 375×667）及 404 三按钮排布', { skip }, async () => {
  for (const vp of [{ width: 360, height: 740 }, { width: 375, height: 667 }]) {
    const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    const health = attachHealthMonitors(page);
    try {
      // 1) catalog.html 中英文 placeholder 用 Canvas 2D measureText 硬断言完全不截断 + 零溢出
      for (const lang of ['zh', 'en']) {
        await page.goto(`${pagesBase}catalog.html${lang === 'en' ? '?lang=en' : ''}`);
        await page.evaluate(() => window.pageReady);
        const m = await page.evaluate(() => {
          const inp = document.getElementById('cat-q');
          const cs = getComputedStyle(inp);
          const canvas = document.createElement('canvas');
          const c2d = canvas.getContext('2d');
          c2d.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
          const textW = c2d.measureText(inp.placeholder).width;
          const contentW = inp.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
          return {
            placeholder: inp.placeholder,
            textW,
            contentW,
            overflow: document.documentElement.scrollWidth > window.innerWidth,
          };
        });
        assert.ok(m.textW <= m.contentW, `${vp.width} ${lang} placeholder "${m.placeholder}" truncated: ${m.textW.toFixed(1)} > ${m.contentW.toFixed(1)}`);
        assert.equal(m.overflow, false, `catalog ${vp.width} ${lang} overflow`);
      }

      // 2) series.html 零横向溢出
      await page.goto(`${pagesBase}series.html?lang=en`);
      await page.evaluate(() => window.pageReady);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false, `series ${vp.width} overflow`);

      // 3) 阅读器（长名 Claude Opus 5.5 (agy) +high）：零溢出、#s-moves 整行对齐、棋盘与翻步栏无重叠、棋手条不溢出
      await page.goto(`${pagesBase}?files=runs/carbon-vs-agy-opus-high-xq-20261114-3&ply=9`);
      await page.evaluate(() => window.viewer.ready);
      const r = await page.evaluate(() => {
        const moves = document.getElementById('s-moves');
        const rowH = moves.querySelector('.r')?.offsetHeight || 0;
        const board = document.getElementById('board-area').getBoundingClientRect();
        const ctrl = document.getElementById('s-ctrl').getBoundingClientRect();
        const bot = document.getElementById('bar-bottom');
        const botRect = bot.getBoundingClientRect();
        const effRect = bot.querySelector('.effort')?.getBoundingClientRect();
        return {
          overflow: document.documentElement.scrollWidth > window.innerWidth,
          rowH,
          movesClientH: moves.clientHeight,
          movesScrollTop: moves.scrollTop,
          boardBottom: board.bottom,
          ctrlTop: ctrl.top,
          botName: bot.querySelector('.name')?.textContent || '',
          botScrollW: bot.scrollWidth,
          botClientW: bot.clientWidth,
          effRight: effRect ? effRect.right : 0,
          botRight: botRect.right,
        };
      });
      assert.equal(r.overflow, false, `reader ${vp.width} overflow`);
      assert.ok(r.rowH > 0 && r.movesClientH === 8 * r.rowH && r.movesScrollTop % r.rowH === 0, `moves align ${vp.width}: ${JSON.stringify(r)}`);
      assert.ok(r.boardBottom <= r.ctrlTop + 1, `board overlaps ctrl ${vp.width}`);
      assert.ok(r.botScrollW <= r.botClientW + 1, `longname bar overflow ${vp.width}`);
      assert.ok(r.effRight <= r.botRight + 0.5, `effort clips right ${vp.width}`);

      // 4) 手机 404.html 零溢出且三按钮高度 >= 40px
      await page.goto(`${pagesBase}404.html?lang=en`);
      const m404 = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > window.innerWidth,
        heights: [...document.querySelectorAll('.actions a.btn')].map((a) => a.getBoundingClientRect().height),
      }));
      assert.equal(m404.overflow, false, `404 ${vp.width} overflow`);
      assert.ok(m404.heights.length === 3 && m404.heights.every((h) => h >= 40), `404 btn heights: ${m404.heights}`);

      health.assertClean(`S7-${vp.width}`);
    } finally {
      await ctx.close();
    }
  }

  // 5) 桌面 1280×800 下 404.html 三按钮整齐排在同一行
  const deskCtx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const deskPage = await deskCtx.newPage();
  const deskHealth = attachHealthMonitors(deskPage);
  try {
    await deskPage.goto(`${pagesBase}404.html`);
    const tops = await deskPage.evaluate(() => [...document.querySelectorAll('.actions a.btn')].map((a) => Math.round(a.getBoundingClientRect().top)));
    assert.equal(tops.length, 3);
    assert.equal(new Set(tops).size, 1, `desktop 404 buttons wrapped: tops=${JSON.stringify(tops)}`);
    deskHealth.assertClean('S7-desktop-404');
  } finally {
    await deskCtx.close();
  }
});

test('S8：_site/ 192 盘全量健康体检、384 席命名净度与静态产物许可合规校验', async () => {
  const catRes = await fetch(`${pagesBase}lib/catalog-data.json`);
  assert.equal(catRes.status, 200);
  const catalog = await catRes.json();
  assert.equal(catalog.games.length, 192);
  assert.equal(catalog.games.filter((g) => g.variant === 'chess').length, 108);
  assert.equal(catalog.games.filter((g) => g.variant === 'xiangqi').length, 84);

  let analyzedOk = 0;
  let seatCount = 0;

  for (const g of catalog.games) {
    const pgnRes = await fetch(`${pagesBase}${g.dir}/game.pgn`);
    assert.equal(pgnRes.status, 200, `${g.dir}/game.pgn status`);
    const parsed = parsePgn(decodeText(new Uint8Array(await pgnRes.arrayBuffer())));
    assert.equal(parsed.length, 1, `${g.dir} single game`);
    const rep = replay(parsed[0]);
    assert.equal(rep.error, null, `${g.dir} replay error: ${JSON.stringify(rep.error)}`);
    assert.equal(rep.steps.length, g.plies, `${g.dir} plies mismatch`);
    assert.equal(parsed[0].result ?? parsed[0].tags.Result, g.result, `${g.dir} result mismatch`);

    for (const side of ['w', 'b']) {
      seatCount++;
      const s = g[side];
      assert.equal(displayName(s.raw, 'en'), s.labelEn, `${g.dir} ${side} labelEn`);
      assert.equal(displayName(s.raw, 'zh'), s.labelZh, `${g.dir} ${side} labelZh`);
      const full = s.effort ? `${s.labelEn} +${s.effort}` : s.labelEn;
      assert.doesNotMatch(full, /^(GPT|Gemini|Claude|DeepSeek)\s+\1/i, `dup prefix: ${full}`);
      assert.doesNotMatch(full, /-(?:minimal|low|medium|high|xhigh|max)\s*\+/i, `dup effort: ${full}`);
      assert.doesNotMatch(full, /\b(?:Claude opus|GPT astra|GPT sol)\b/, `lowercase alias: ${full}`);
    }

    if (g.analyzed) {
      const anaRes = await fetch(`${pagesBase}${g.dir}/analysis.jsonl`);
      assert.equal(anaRes.status, 200, `${g.dir}/analysis.jsonl status`);
      const lines = (await anaRes.text()).trim().split(/\r?\n/).filter(Boolean);
      assert.equal(lines.length, g.plies, `${g.dir} analysis line count`);
      analyzedOk++;
    }
  }
  assert.equal(seatCount, 384);
  assert.equal(analyzedOk, 191);

  // _site/ 零 quiz-* 泄漏，且根 LICENSE 与所有 vendor LICENSE/SOURCE.md 全部存在
  const leakedQuiz = [];
  const walk = (dir) => {
    for (const ent of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, ent.name);
      if (ent.name.startsWith('quiz-')) leakedQuiz.push(p);
      if (ent.isDirectory()) walk(p);
    }
  };
  walk(siteDir);
  assert.deepEqual(leakedQuiz, []);
  for (const rel of [
    'LICENSE',
    'vendor/chess.js/LICENSE',
    'vendor/cm-chessboard/LICENSE',
    'vendor/cburnett-pieces/SOURCE.md',
    'vendor/sounds/SOURCE.md',
  ]) {
    assert.equal(existsSync(join(siteDir, rel)), true, `missing ${rel}`);
  }
});
