// 手机端响应式布局、手动翻步深链接、语言切换、可见错误页，以及 GitHub Pages 子路径（/agi-chess/）打包产物端到端测试。
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildPages } from '../build-pages.mjs';
import { hasCjk } from '../lib/i18n.js';
import { resolveChromium, serve } from '../serve.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FIX = '/viewer/test/fixtures/';

let pw = null;
try { pw = await import('playwright-core'); } catch { /* 没装开发依赖 */ }
let browser = null, skip = pw ? false : '没有 playwright-core（cd viewer && npm ci）';
if (pw) {
  try { browser = await pw.chromium.launch({ executablePath: resolveChromium(undefined, pw) }); }
  catch (e) { skip = `起不来浏览器：${e.message.split('\n')[0]}`; }
}
if (process.env.VIEWER_REQUIRE_BROWSER === '1' && skip) throw new Error(skip);

async function withMobilePage(query, viewport, fn, serverOpts = { root: ROOT, mounts: {} }) {
  const server = await serve(serverOpts.root, serverOpts.mounts);
  const ctx = await browser.newContext({
    viewport,
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const prefix = serverOpts.prefix ?? '/viewer/';
  try {
    await page.goto(`http://127.0.0.1:${server.port}${prefix}${query ? `?${query}` : ''}`);
    await fn(page, server.port);
    assert.deepEqual(errors, []);
  } finally {
    await ctx.close();
    await server.close();
  }
}

test('手机屏（360/375/390）：国象与中象代表局零横向溢出、棋盘完整、点按翻步、恶手与理由可见、纵向可滚', { skip }, async () => {
  // 1) 国际象棋 375×667（并复查 360×640）
  await withMobilePage('lang=en&files=/runs/neon-xhigh-vs-carbon-high-20261119&ply=39', { width: 375, height: 667 }, async (page) => {
    await page.evaluate(() => window.viewer.ready);
    const m0 = await page.evaluate(() => {
      const st = document.getElementById('stage');
      const board = document.getElementById('board-chess').getBoundingClientRect();
      const ctrl = document.getElementById('s-ctrl').getBoundingClientRect();
      const head = document.getElementById('s-head').getBoundingClientRect();
      const note = document.getElementById('s-note').getBoundingClientRect();
      const moves = document.getElementById('s-moves').getBoundingClientRect();
      const nextBtn = document.querySelector('#s-ctrl [data-act="next"]').getBoundingClientRect();
      const pill = document.querySelector('#s-head .nav-pill').getBoundingClientRect();
      const subOverflow = ['#bar-top', '#board-area', '#bar-bottom', '#side', '#s-ctrl', '#s-head', '#s-note', '#s-moves']
        .filter((s) => { const e = document.querySelector(s); return e && e.scrollWidth > e.clientWidth + 1; });
      return {
        isMobile: st.classList.contains('mobile'),
        scrollCls: document.documentElement.classList.contains('mobile-scroll'),
        docScrollW: document.documentElement.scrollWidth,
        innerW: window.innerWidth,
        docScrollH: document.documentElement.scrollHeight,
        innerH: window.innerHeight,
        boardW: board.width,
        boardH: board.height,
        boardRight: board.right,
        btnH: nextBtn.height,
        pillH: pill.height,
        orderOk: board.bottom <= ctrl.top + 20 && ctrl.bottom <= head.top + 2 && head.bottom <= note.top + 2 && note.bottom <= moves.top + 2,
        keysHidden: getComputedStyle(document.getElementById('s-keys')).display === 'none',
        players: [...document.querySelectorAll('.bar .name')].map((e) => e.textContent),
        subOverflow,
      };
    });
    assert.equal(m0.isMobile, true);
    assert.equal(m0.scrollCls, true);
    assert.ok(m0.docScrollW <= m0.innerW, `scrollWidth ${m0.docScrollW} > innerWidth ${m0.innerW}`);
    assert.deepEqual(m0.subOverflow, []);
    assert.ok(m0.boardW >= 350 && m0.boardRight <= m0.innerW + 0.5);
    assert.ok(Math.abs(m0.boardW - m0.boardH) < 1);
    assert.ok(m0.btnH >= 40, `button height ${m0.btnH} < 40`);
    assert.ok(m0.pillH >= 36, `nav-pill height ${m0.pillH} < 36`);
    assert.equal(m0.orderOk, true);
    assert.equal(m0.keysHidden, true);
    assert.deepEqual(m0.players, ['Gemini 4 Carbon', 'Gemini 4 Neon']);
    assert.ok(m0.docScrollH > m0.innerH);

    // 触控点按「下一步」推进到 ply=40（20... Re8?? Blunder）
    await page.tap('#s-ctrl [data-act="next"]');
    await page.waitForFunction(() => Number(document.querySelector('#s-moves .cur')?.dataset.ply) === 40);
    const step40 = await page.evaluate(() => ({
      nags: [...document.querySelectorAll('#s-note .nag.bad')].map((e) => e.textContent),
      why: document.querySelector('#s-note .why')?.textContent || '',
    }));
    assert.deepEqual(step40.nags, ['?? Blunder']);
    assert.match(step40.why, /Re8/);

    // 页面纵向可滚动，且切换 360px 窄屏仍零横向溢出
    await page.evaluate(() => window.scrollTo(0, 180));
    assert.ok((await page.evaluate(() => window.scrollY)) > 0);
    await page.setViewportSize({ width: 360, height: 640 });
    await page.waitForFunction(() => window.innerWidth === 360);
    const w360 = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    assert.ok(w360[0] <= w360[1], `360px overflow: ${w360[0]} > ${w360[1]}`);
  });

  // 2) 中国象棋 390×844（重点核查 #board-xq 不再按 458px 撑破窄视口，且 360px 下同样不溢出）
  await withMobilePage('files=/runs/carbon-vs-agy-opus-high-xq-20261114-3&ply=9', { width: 390, height: 844 }, async (page) => {
    await page.evaluate(() => window.viewer.ready);
    const xq = await page.evaluate(() => {
      const b = document.getElementById('board-xq').getBoundingClientRect();
      return {
        isMobile: document.getElementById('stage').classList.contains('mobile'),
        docScrollW: document.documentElement.scrollWidth,
        innerW: window.innerWidth,
        boardW: b.width,
        boardH: b.height,
        boardLeft: b.left,
        boardRight: b.right,
        nags: [...document.querySelectorAll('#s-note .nag.bad')].map((e) => e.textContent),
        whyLen: (document.querySelector('#s-note .why')?.textContent || '').length,
        players: [...document.querySelectorAll('.bar .name')].map((e) => e.textContent),
      };
    });
    assert.equal(xq.isMobile, true);
    assert.ok(xq.docScrollW <= xq.innerW, `XQ 390 overflow: ${xq.docScrollW} > ${xq.innerW}`);
    assert.ok(xq.boardW > 340 && xq.boardLeft >= 6 && xq.boardRight <= xq.innerW - 6);
    assert.ok(xq.boardH > xq.boardW);
    assert.deepEqual(xq.nags, ['?? 大错']);
    assert.ok(xq.whyLen > 20);
    assert.deepEqual(xq.players, ['Gemini 4 Carbon', 'Claude Opus 5.5 (agy)']);

    // 着法框整行对齐：可见高度固定 8 行（8 * 34 = 272px）且与 scrollTop 均为单行高度整数倍，无半行腰斩
    const movesAlign = await page.evaluate(() => {
      const box = document.getElementById('s-moves');
      const rowH = box.querySelector('.r')?.offsetHeight || 0;
      return { clientH: box.clientHeight, scrollTop: box.scrollTop, rowH };
    });
    assert.ok(movesAlign.rowH > 0 && movesAlign.clientH === 8 * movesAlign.rowH && movesAlign.scrollTop % movesAlign.rowH === 0);

    await page.setViewportSize({ width: 360, height: 640 });
    await page.waitForFunction(() => window.innerWidth === 360);
    const xq360 = await page.evaluate(() => ({
      scrollW: document.documentElement.scrollWidth,
      innerW: window.innerWidth,
      boardRight: document.getElementById('board-xq').getBoundingClientRect().right,
    }));
    assert.ok(xq360.scrollW <= xq360.innerW && xq360.boardRight <= xq360.innerW + 0.5);
  });

  // 3) 手机空白首页 375×667：6 张精选对局卡片排在桌面拖放说明之前，首屏无需下滚完整可见
  await withMobilePage('lang=en', { width: 375, height: 667 }, async (page) => {
    await page.evaluate(() => window.viewer.ready);
    const home = await page.evaluate(() => {
      const samples = document.querySelector('#hint .h-samples').getBoundingClientRect();
      const msg = document.querySelector('#hint .h-msg').getBoundingClientRect();
      const links = [...document.querySelectorAll('#hint .h-link')].map((e) => e.getBoundingClientRect());
      const pill = document.querySelector('#hint .nav-pill').getBoundingClientRect();
      return {
        samplesTop: samples.top,
        samplesBottom: samples.bottom,
        msgTop: msg.top,
        count: links.length,
        lastLinkBottom: links.at(-1)?.bottom ?? Infinity,
        innerH: window.innerHeight,
        pillH: pill.height,
      };
    });
    assert.equal(home.count, 6);
    assert.ok(home.samplesBottom <= home.msgTop + 1, `samples (${home.samplesBottom}) should precede msg (${home.msgTop})`);
    assert.ok(home.lastLinkBottom <= home.innerH, `6th sample bottom ${home.lastLinkBottom} > innerHeight ${home.innerH}`);
    assert.ok(home.pillH >= 36, `home nav-pill height ${home.pillH} < 36`);
  });
});

test('深链接 replaceState、autoplay 切语言不丢当前步、本地拖拽不改 URL、错误页单语显示且保留 dataset.error', { skip }, async () => {
  // 0) autoplay=1 未经手动翻步直接切语言：移除 autoplay 并精准停在当前正在看的盘号与 ply
  const two = `files=${FIX}chess-sample.pgn,${FIX}xq-sample.pgn`;
  await withMobilePage(`${two}&autoplay=1&openhold=0.05&anim=0&gap=5`, { width: 390, height: 844 }, async (page) => {
    await page.evaluate(() => window.viewer.ready);
    await page.waitForFunction(() => Number(document.querySelector('#s-moves .cur')?.dataset.ply) === 1, null, { timeout: 3000 });
    await Promise.all([
      page.waitForNavigation(),
      page.click('#s-head a.lang-switch'),
    ]);
    await page.evaluate(() => window.viewer.ready);
    const autoSwitched = await page.evaluate(() => {
      const q = new URL(location.href).searchParams;
      return {
        lang: document.documentElement.lang,
        hasAutoplay: q.has('autoplay'),
        game: q.get('game'),
        ply: q.get('ply'),
        curPly: Number(document.querySelector('#s-moves .cur')?.dataset.ply),
        playText: document.getElementById('s-play').textContent,
      };
    });
    assert.deepEqual(autoSwitched, {
      lang: 'en',
      hasAutoplay: false,
      game: '1',
      ply: '1',
      curPly: 1,
      playText: 'Play',
    });
  });

  // 1) 多盘手动翻步更新 game/ply 并移除 autoplay；回到开局移除 ply；中英切换保留 files/game/ply
  await withMobilePage(`${two}&autoplay=1&gap=5`, { width: 390, height: 844 }, async (page) => {
    await page.evaluate(() => window.viewer.ready);
    await page.tap('#s-ctrl [data-act="next"]');
    await page.waitForFunction(() => {
      const q = new URL(location.href).searchParams;
      return q.get('game') === '1' && q.get('ply') === '1' && !q.has('autoplay');
    }, null, { timeout: 3000 });

    // 切到第 2 局并走 2 步，点 EN 切英文仍保留第 2 局第 2 步
    await page.selectOption('#s-game', '1');
    await page.tap('#s-ctrl [data-act="next"]');
    await page.tap('#s-ctrl [data-act="next"]');
    await page.waitForFunction(() => {
      const q = new URL(location.href).searchParams;
      return q.get('game') === '2' && q.get('ply') === '2';
    }, null, { timeout: 3000 });

    await Promise.all([
      page.waitForNavigation(),
      page.click('#s-head a.lang-switch'),
    ]);
    await page.evaluate(() => window.viewer.ready);
    const afterEn = await page.evaluate(() => {
      const q = new URL(location.href).searchParams;
      return {
        lang: document.documentElement.lang,
        game: q.get('game'),
        ply: q.get('ply'),
        files: q.get('files'),
        curPly: Number(document.querySelector('#s-moves .cur')?.dataset.ply),
      };
    });
    assert.deepEqual(afterEn, {
      lang: 'en',
      game: '2',
      ply: '2',
      files: `${FIX}chess-sample.pgn,${FIX}xq-sample.pgn`,
      curPly: 2,
    });

    // 点中文切回默认语言（删掉 lang，保留 game 与 ply）
    await Promise.all([
      page.waitForNavigation(),
      page.click('#s-head a.lang-switch'),
    ]);
    await page.evaluate(() => window.viewer.ready);
    const afterZh = await page.evaluate(() => {
      const q = new URL(location.href).searchParams;
      return { hasLang: q.has('lang'), game: q.get('game'), ply: q.get('ply') };
    });
    assert.deepEqual(afterZh, { hasLang: false, game: '2', ply: '2' });

    // 点本盘开头 ply=0 时删掉 ply 参数
    await page.tap('#s-ctrl [data-act="first"]');
    await page.waitForFunction(() => !new URL(location.href).searchParams.has('ply'), null, { timeout: 3000 });

    // 本地拖拽文件后 hasUrlFiles=false：隐藏重载导航链接且翻步不再调用 replaceState
    const urlBeforeDrop = page.url();
    const pgn = '[White "claude:opus"]\n[Black "codex:astra"]\n\n1. e4 e5 2. Nf3 Nc6 1/2-1/2\n';
    const dt = await page.evaluateHandle((t) => { const d = new DataTransfer(); d.items.add(new File([t], 'local.pgn')); return d; }, pgn);
    await page.dispatchEvent('body', 'drop', { dataTransfer: dt });
    await page.waitForFunction(() => document.querySelectorAll('#s-moves [data-ply]').length === 5);
    await page.tap('#s-ctrl [data-act="next"]');
    await new Promise((ok) => setTimeout(ok, 250));
    assert.equal(page.url(), urlBeforeDrop);
    assert.equal(await page.evaluate(() => document.querySelectorAll('#s-head .s-nav').length), 0);
  });

  // 2) 错误路径 ?files=/runs/missing（中文）与 ?files=/runs/does-not-exist&lang=en（英文零 CJK）
  await withMobilePage('files=/runs/missing-not-exist', { width: 375, height: 667 }, async (page) => {
    await assert.rejects(page.evaluate(() => window.viewer.ready));
    const errUi = await page.evaluate(() => ({
      dataError: document.body.dataset.error || '',
      hasErrorCard: !!document.querySelector('#hint .h-error'),
      title: document.querySelector('#hint .e-title')?.textContent || '',
      hint: document.querySelector('#hint .e-hint')?.textContent || '',
      hasHomeLink: !!document.querySelector('#hint .e-home'),
      samplesCount: document.querySelectorAll('#hint .h-link').length,
      scrollW: document.documentElement.scrollWidth,
      innerW: window.innerWidth,
    }));
    assert.match(errUi.dataError, /读不到棋谱 .*404/);
    assert.equal(errUi.hasErrorCard, true);
    assert.equal(errUi.title, '无法加载棋谱');
    assert.equal(errUi.hint, '请检查网址中的 ?files= 棋谱路径，或直接打开下方精选对局。');
    assert.equal(errUi.hasHomeLink, true);
    assert.equal(errUi.samplesCount, 6);
    assert.ok(errUi.scrollW <= errUi.innerW);
  });

  await withMobilePage('files=/runs/does-not-exist&lang=en', { width: 375, height: 667 }, async (page) => {
    await assert.rejects(page.evaluate(() => window.viewer.ready));
    const errEn = await page.evaluate(() => {
      const texts = [];
      const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = w.nextNode(); n; n = w.nextNode()) {
        const e = n.parentElement;
        if (!n.textContent.trim() || !e || e.closest('.lang-switch, script')) continue;
        if (!e.getClientRects().length) continue;
        texts.push(n.textContent.trim());
      }
      texts.push(document.title);
      return {
        dataError: document.body.dataset.error || '',
        title: document.querySelector('#hint .e-title')?.textContent || '',
        detail: document.querySelector('#hint .e-detail')?.textContent || '',
        hint: document.querySelector('#hint .e-hint')?.textContent || '',
        texts,
      };
    });
    assert.match(errEn.dataError, /Failed to load .*404/);
    assert.equal(errEn.title, 'Failed to load game record');
    assert.match(errEn.detail, /^Failed to load \/runs\/does-not-exist\/game\.pgn: 404$/);
    assert.equal(errEn.hint, 'Check the ?files= path in the URL, or open a featured game below.');
    assert.deepEqual(errEn.texts.filter((t) => hasCjk(t)), []);
  });
});

test('build-pages.mjs：静态产物完整性、过滤 *.mjs/*.py/package*.json 与仓内受保护目录拦截', () => {
  for (const forbidden of [
    ROOT,
    dirname(ROOT),
    join(ROOT, 'runs'),
    join(ROOT, 'docs'),
    join(ROOT, 'viewer'),
    join(ROOT, '.git'),
    join(ROOT, '_site', 'nested'),
  ]) {
    assert.throws(() => buildPages(forbidden), /拒绝覆盖受保护目录/);
  }

  const tmp = mkdtempSync(join(tmpdir(), 'viewer-pages-fs-'));
  const siteDir = join(tmp, '_site');
  try {
    const built = buildPages(siteDir);
    assert.equal(built.pgnCount, 192);
    assert.equal(built.analysisCount, 191);
    assert.equal(existsSync(join(siteDir, '.nojekyll')), true);
    assert.equal(existsSync(join(siteDir, 'series.html')), true);
    assert.equal(existsSync(join(siteDir, 'catalog.html')), true);
    assert.equal(existsSync(join(siteDir, 'series', 'index.html')), true);
    assert.equal(existsSync(join(siteDir, 'catalog', 'index.html')), true);
    assert.equal(existsSync(join(siteDir, 'pages.css')), true);
    assert.equal(existsSync(join(siteDir, 'lib', 'catalog-data.json')), true);
    assert.equal(existsSync(join(siteDir, 'catalog-meta.json')), false);
    assert.equal(existsSync(join(siteDir, '404.html')), true);
    assert.equal(existsSync(join(siteDir, 'og-card.png')), true);
    assert.equal(existsSync(join(siteDir, 'LICENSE')), true);
    assert.equal(existsSync(join(siteDir, 'vendor', 'chess.js', 'LICENSE')), true);
    assert.equal(existsSync(join(siteDir, 'vendor', 'cm-chessboard', 'LICENSE')), true);
    assert.equal(existsSync(join(siteDir, 'vendor', 'cburnett-pieces', 'SOURCE.md')), true);
    assert.equal(existsSync(join(siteDir, 'vendor', 'cburnett-pieces', 'build_sprite.py')), false);
    assert.equal(existsSync(join(siteDir, 'vendor', 'sounds', 'SOURCE.md')), true);
    assert.equal(existsSync(join(siteDir, 'node_modules')), false);
    assert.equal(existsSync(join(siteDir, 'test')), false);

    // 递归确认不含任何 .mjs、.py、package*.json、quiz-*、summary.*、judged.jsonl
    const bad = [];
    const scan = (d) => {
      for (const e of readdirSync(d, { withFileTypes: true })) {
        const p = join(d, e.name);
        if (e.isDirectory()) {
          if (e.name.startsWith('quiz-')) bad.push(p);
          scan(p);
        } else if (
          /\.(mjs|py)$/i.test(e.name)
          || /^package.*\.json$/i.test(e.name)
          || /summary\./i.test(e.name)
          || e.name === 'judged.jsonl'
        ) {
          bad.push(p);
        }
      }
    };
    scan(siteDir);
    assert.deepEqual(bad, []);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('/agi-chess/ 子路径端到端加载（空根 /runs/ 404）', { skip }, async () => {
  const tmp = mkdtempSync(join(tmpdir(), 'viewer-pages-e2e-'));
  const emptyRoot = join(tmp, 'empty-root');
  const siteDir = join(tmp, '_site');
  mkdirSync(emptyRoot, { recursive: true });
  try {
    buildPages(siteDir);

    // 在空根目录下仅挂载 /agi-chess/ → siteDir（根路径 /runs/... 必 404），端到端验证子路径自适应
    await withMobilePage(
      'lang=en',
      { width: 390, height: 844 },
      async (page, port) => {
        await page.evaluate(() => window.viewer.ready);
        // 确认根 /runs/... 确实是 404
        const rootStatus = await page.evaluate(async () => (await fetch('/runs/neon-xhigh-vs-carbon-high-20261119/game.pgn')).status);
        assert.equal(rootStatus, 404);

        const homeLinks = await page.evaluate(() => [...document.querySelectorAll('#hint .h-link')].map((a) => a.getAttribute('href')));
        assert.equal(homeLinks.length, 6);

        // 1) 国象代表局 + analysis.jsonl ?? Blunder 徽章
        await page.goto(`http://127.0.0.1:${port}/agi-chess/?lang=en&files=/runs/neon-xhigh-vs-carbon-high-20261119&ply=40`);
        await page.evaluate(() => window.viewer.ready);
        assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('#s-note .nag.bad')].map((e) => e.textContent)), ['?? Blunder']);

        // 2) 中象代表局 + analysis.jsonl ?? Blunder 徽章
        await page.goto(`http://127.0.0.1:${port}/agi-chess/?lang=en&files=/runs/carbon-vs-agy-opus-high-xq-20261114-3&ply=9`);
        await page.evaluate(() => window.viewer.ready);
        assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('#s-note .nag.bad')].map((e) => e.textContent)), ['?? Blunder']);

        // 3) 嵌套批次目录 runs/zc/maia-1900-s1-w（不带前导斜杠也能按 SITE_ROOT 正常加载）
        await page.goto(`http://127.0.0.1:${port}/agi-chess/?lang=en&files=runs/zc/maia-1900-s1-w&ply=10`);
        await page.evaluate(() => window.viewer.ready);
        const zc = await page.evaluate(() => ({
          curPly: Number(document.querySelector('#s-moves .cur')?.dataset.ply),
          badCount: document.querySelectorAll('#s-moves .m.bad').length,
        }));
        assert.equal(zc.curPly, 10);
        assert.ok(zc.badCount > 0);

        // 4) /agi-chess/catalog/ 与 /agi-chess/series/ 尾斜杠静态重定向（保留 query 与 hash）
        await page.goto(`http://127.0.0.1:${port}/agi-chess/catalog/?q=neon&lang=en#h1`);
        await page.waitForFunction(() => location.pathname === '/agi-chess/catalog.html');
        await page.evaluate(() => window.pageReady);
        assert.deepEqual(await page.evaluate(() => ({
          pathname: location.pathname,
          q: new URLSearchParams(location.search).get('q'),
          lang: new URLSearchParams(location.search).get('lang'),
          hash: location.hash,
          rows: document.querySelectorAll('.cat-row').length,
        })), { pathname: '/agi-chess/catalog.html', q: 'neon', lang: 'en', hash: '#h1', rows: 8 });

        await page.goto(`http://127.0.0.1:${port}/agi-chess/series/?variant=xiangqi&lang=en#h2`);
        await page.waitForFunction(() => location.pathname === '/agi-chess/series.html');
        await page.evaluate(() => window.pageReady);
        assert.deepEqual(await page.evaluate(() => ({
          pathname: location.pathname,
          variant: new URLSearchParams(location.search).get('variant'),
          lang: new URLSearchParams(location.search).get('lang'),
          hash: location.hash,
          activeVar: document.querySelector('.seg-btn.active')?.dataset.variant,
        })), { pathname: '/agi-chess/series.html', variant: 'xiangqi', lang: 'en', hash: '#h2', activeVar: 'xiangqi' });

        // 5) 404.html 三页入口（无相对路径，?lang=en 自动沿用，含 /ladder/ 引导）
        await page.goto(`http://127.0.0.1:${port}/agi-chess/404.html`);
        const p404Zh = await page.evaluate(() => ({
          hrefs: ['#link-home', '#link-series', '#link-catalog'].map((s) => document.querySelector(s)?.getAttribute('href')),
          text: document.body.textContent,
        }));
        assert.deepEqual(p404Zh.hrefs, ['/agi-chess/', '/agi-chess/series.html', '/agi-chess/catalog.html']);
        assert.match(p404Zh.text, /\/ladder\//);

        await page.goto(`http://127.0.0.1:${port}/agi-chess/404.html?lang=en`);
        const p404En = await page.evaluate(() => ({
          lang: document.documentElement.lang,
          hrefs: ['#link-home', '#link-series', '#link-catalog'].map((s) => document.querySelector(s)?.getAttribute('href')),
        }));
        assert.deepEqual(p404En, {
          lang: 'en',
          hrefs: ['/agi-chess/?lang=en', '/agi-chess/series.html?lang=en', '/agi-chess/catalog.html?lang=en'],
        });
      },
      { root: emptyRoot, mounts: { '/agi-chess/': siteDir }, prefix: '/agi-chess/' },
    );
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

after(() => browser?.close());
