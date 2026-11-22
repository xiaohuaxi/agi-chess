// 二期新增功能全套测试：
// 1. build-catalog.mjs --check 零漂移校验与 192 盘 / 番棋金标断言；
// 2. og-card.png 1200×628 尺寸校验；
// 3. 逐着引擎评分先手视角换算、最佳着（国象 SAN 含升变、中象四字记谱与 WXF）及 24 条实盘 ⚠ 通道告警无损分段；
// 4. /agi-chess/ 空根子路径下 index / series / catalog 三页互跳、返回状态保活、英文零 CJK 与手机窄屏零横向溢出。
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildCatalogObject, serializeCatalog } from '../build-catalog.mjs';
import { buildPages } from '../build-pages.mjs';
import { hasCjk } from '../lib/i18n.js';
import { formatStepEval, splitWarnings } from '../lib/panel.js';
import { decodeText, moveNote, parsePgn } from '../lib/pgn.js';
import { loadGamesWithAnalysis } from '../lib/replay.js';
import { resolveChromium, serve } from '../serve.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

test('build-catalog.mjs：内存重算与入库 catalog-data.json 逐字节一致，192 盘分类与番棋金标精确匹配', () => {
  const checkedIn = readFileSync(join(ROOT, 'viewer', 'lib', 'catalog-data.json'), 'utf8');
  assert.equal(serializeCatalog(), checkedIn, 'catalog-data.json 与现场重算不一致');

  const out = execFileSync(process.execPath, [join(ROOT, 'viewer', 'build-catalog.mjs'), '--check'], {
    cwd: ROOT,
    encoding: 'utf8',
  });
  assert.match(out, /Catalog check passed/);

  const data = buildCatalogObject();
  assert.deepEqual(data.counts, {
    total: 192,
    chess: 108,
    xiangqi: 84,
    h2h: 64,
    engine: 128,
    vsEngineOnly: 126,
    vsRandom: 2,
    analyzed: 191,
  });
  assert.equal(data.series.length, 12);
  assert.equal(data.exploratory.length, 8);
  assert.deepEqual(
    data.roundRobin.chess20261119.standings.map((s) => [s.shortLabel, s.pts, s.losses]),
    [['Neon xhigh', 6, 2], ['Astra 6.2 max', 5, 3], ['Carbon high', 1, 7]],
  );
  // 校验 carbon-high-vs-astra-max-20261119 按 PGN 头与颜色键正确聚合（未因摘要旧名 codex:astra 漏算）
  const ca = data.series.find((s) => s.id === 'carbon-vs-astra62-20261119');
  assert.deepEqual([ca.scoreA, ca.scoreB, ca.acplA, ca.acplB, ca.blundersA, ca.blundersB], [1, 3, 45.1, 35.8, 14, 8]);
});

test('og-card.png：PNG 签名有效且严格为 1200×628（1.91:1）', () => {
  const buf = readFileSync(join(ROOT, 'viewer', 'og-card.png'));
  assert.equal(buf.readUInt32BE(0), 0x89504e47);
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  assert.deepEqual([w, h], [1200, 628]);
});

test('逐着引擎评估换算与最佳着转换：实盘黄金断言、国象升变、杀棋符号与终局步去冗余', () => {
  const loadRun = (relDir) => {
    const pgn = decodeText(readFileSync(join(ROOT, relDir, 'game.pgn')));
    const ana = decodeText(readFileSync(join(ROOT, relDir, 'analysis.jsonl')));
    return loadGamesWithAnalysis([
      { name: `${relDir}/game.pgn`, text: pgn },
      { name: `${relDir}/analysis.jsonl`, text: ana },
    ])[0];
  };

  // 黄金断言 1：国象黑方走子恶手 20...Re8??（ply=40）
  const g1 = loadRun('runs/neon-xhigh-vs-carbon-high-20261119');
  const st40 = g1.rep.steps[39];
  assert.equal(st40.eval.best, 'f8g7');
  assert.equal(st40.eval.played_best, false);
  assert.deepEqual(formatStepEval(st40, false, 'en'), {
    scoreLabel: 'White eval',
    score: '+1.02 → +4.10',
    wpLabel: 'Win%',
    wp: '59.3% → 81.9%',
    bestLabel: 'Best',
    best: 'Kg7',
  });

  // 终局将死步（36.Qd8#，after="end +1", played_best=true）不重复渲染终局评分箭头
  assert.equal(formatStepEval(g1.rep.steps.at(-1), false, 'en'), null);

  // 黄金断言 2：中象红方走子恶手 5.车九平八??（ply=9）
  const g2 = loadRun('runs/carbon-vs-agy-opus-high-xq-20261114-3');
  const st9 = g2.rep.steps[8];
  assert.deepEqual(formatStepEval(st9, true, 'zh'), {
    scoreLabel: '红方评分',
    score: '0 → -469 cp',
    wpLabel: '白方胜率',
    wp: null,
    bestLabel: '最佳着',
    best: '车二进六',
  });
  assert.deepEqual(formatStepEval(st9, true, 'en'), {
    scoreLabel: 'Red eval',
    score: '0 → -469 cp',
    wpLabel: 'Win%',
    wp: null,
    bestLabel: 'Best',
    best: 'R2+6',
  });

  // 国象 5 字符升变最佳着转换（d7d8r -> d8=R#）
  const gProm = loadRun('runs/zc/maia-1900-s2-b');
  const st87 = gProm.rep.steps[86];
  assert.equal(st87.eval.best, 'd7d8r');
  assert.equal(formatStepEval(st87, false, 'en').best, 'd8=R#');

  // 杀棋分数先手固定视角符号翻转：黑走（side='b'），走前黑有 3 步杀 -> -M3，走后反被白 2 步杀 -> +M2
  const mateMock = formatStepEval({
    side: 'b',
    eval: { before: 'mate 3', after: 'mate -2', wp_before: 97.5, wp_after: 2.5, best: 'a8a1', played_best: false, bestSan: 'Ra1#' },
  }, false, 'en');
  assert.equal(mateMock.score, '-M3 → +M2');
  assert.equal(mateMock.wp, '2.5% → 97.5%');
  assert.equal(mateMock.best, 'Ra1#');
});

test('splitWarnings：全仓 24 条含 ⚠ 实盘评注 100% 识别且前后正常理由逐字无损还原', () => {
  const pgns = execFileSync('git', ['ls-files', '-z', 'runs/'], { cwd: ROOT, maxBuffer: 16 * 1024 * 1024 })
    .toString('utf8')
    .split('\0')
    .filter((f) => /^runs\/(?!quiz-).+\/game\.pgn$/.test(f))
    .sort();

  let hitMoves = 0, hitWarns = 0;
  for (const rel of pgns) {
    const [g] = parsePgn(decodeText(readFileSync(join(ROOT, rel))));
    g.moves.forEach((m, i) => {
      const txt = moveNote(m).text;
      if (!txt.includes('⚠')) return;
      hitMoves++;
      const segs = splitWarnings(txt);
      const warns = segs.filter((s) => s.warn);
      const bodies = segs.filter((s) => !s.warn);
      hitWarns += warns.length;
      assert.ok(warns.length >= 1, `${rel} ply=${i + 1} 未拆出通道告警`);
      assert.ok(bodies.length >= 1, `${rel} ply=${i + 1} 误吞正常理由`);
      assert.equal(segs.map((s) => s.text).join(' '), txt, `${rel} ply=${i + 1} 还原不一致`);
    });
  }
  assert.equal(hitMoves, 24);
  assert.equal(hitWarns, 27);

  // 未知 ⚠ 字符保持在普通正文中原样显示，绝不盲切
  assert.deepEqual(splitWarnings('注意 ⚠ 王翼空虚'), [{ warn: false, text: '注意 ⚠ 王翼空虚' }]);
});

// ---------------------------------------------------------------- 浏览器端到端（/agi-chess/ 空根子路径）
let pw = null;
try { pw = await import('playwright-core'); } catch { /* 未装开发依赖 */ }
let browser = null, skip = pw ? false : '没有 playwright-core（cd viewer && npm ci）';
if (pw) {
  try { browser = await pw.chromium.launch({ executablePath: resolveChromium(undefined, pw) }); }
  catch (e) { skip = `起不来浏览器：${e.message.split('\n')[0]}`; }
}
if (process.env.VIEWER_REQUIRE_BROWSER === '1' && skip) throw new Error(skip);

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

async function checkNoOverflow(page, label) {
  const ov = await page.evaluate(() => {
    const bad = [];
    if (document.documentElement.scrollWidth > window.innerWidth) {
      bad.push(`doc:${document.documentElement.scrollWidth}>${window.innerWidth}`);
    }
    for (const e of document.querySelectorAll('#top-header, #app > *, #app .s-card, #app .cat-row')) {
      if (e.scrollWidth > e.clientWidth + 1) {
        bad.push(`${e.tagName}.${e.className}:${e.scrollWidth}>${e.clientWidth}`);
      }
    }
    return bad.slice(0, 5);
  });
  assert.deepEqual(ov, [], `${label} 横向溢出: ${ov.join(', ')}`);
}

test('/agi-chess/ 子路径三页全链路：英文零 CJK、手机窄屏零溢出、引擎评分/告警块渲染、翻步与切语言保留返回上下文', { skip }, async () => {
  const tmp = mkdtempSync(join(tmpdir(), 'viewer-p2-e2e-'));
  const emptyRoot = join(tmp, 'empty');
  const siteDir = join(tmp, '_site');
  mkdirSync(emptyRoot, { recursive: true });
  buildPages(siteDir);

  const server = await serve(emptyRoot, { '/agi-chess/': siteDir });
  const ctx = await browser.newContext({ viewport: { width: 375, height: 667 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));

  try {
    const base = `http://127.0.0.1:${server.port}/agi-chess/`;

    // 1) 新首页 index.html?lang=en（<h1> 品牌标题 + 三页顶栏 + 375×667 首屏 6 代表局完整可见 + 零 CJK）
    await page.goto(`${base}?lang=en`);
    await page.evaluate(() => window.viewer.ready);
    const homeInfo = await page.evaluate(() => ({
      h1Text: document.querySelector('#hint h1.h-brand')?.textContent || '',
      navCount: document.querySelectorAll('#hint .h-topbar .nav-pill').length,
      lastLinkBottom: [...document.querySelectorAll('#hint .h-link')].at(-1)?.getBoundingClientRect().bottom ?? Infinity,
    }));
    assert.equal(homeInfo.h1Text, 'agi-chess · Game Viewer');
    assert.equal(homeInfo.navCount, 4);
    assert.ok(homeInfo.lastLinkBottom <= 667, `lastLinkBottom ${homeInfo.lastLinkBottom} > 667`);
    assert.deepEqual((await collectUiTexts(page)).filter(hasCjk), []);
    await checkNoOverflow(page, 'home-375');

    // 2) series.html?lang=en（国象 + 展开 <details> + 切中象 + 展开 <details> 全部零 CJK 零溢出，且单局胶囊显示 W/L/D）
    await page.goto(`${base}series.html?lang=en`);
    await page.evaluate(() => window.pageReady);
    assert.equal(await page.evaluate(() => document.querySelector('meta[property="og:image"]')?.content.endsWith('/og-card.png')), true);
    const secondCardRes = await page.evaluate(() => [...document.querySelectorAll('.s-card')[1].querySelectorAll('.g-pill .g-res')].map((e) => e.textContent));
    assert.deepEqual(secondCardRes, ['W', 'W', 'L', 'L']);
    await page.click('details.exp-details > summary');
    assert.deepEqual((await collectUiTexts(page)).filter(hasCjk), [], 'series-chess-en CJK');
    await checkNoOverflow(page, 'series-chess-375');

    await page.click('button.seg-btn[data-variant="xiangqi"]');
    await page.click('details.exp-details > summary');
    assert.deepEqual((await collectUiTexts(page)).filter(hasCjk), [], 'series-xq-en CJK');
    await checkNoOverflow(page, 'series-xq-375');

    // 切回国象，验证点击 .btn-play 连播整组（带多盘 files= 与 autoplay=1），再返回验证恶手胶囊
    await page.click('button.seg-btn[data-variant="chess"]');
    await Promise.all([
      page.waitForNavigation(),
      page.click('.s-card a.btn-play'),
    ]);
    await page.evaluate(() => window.viewer.ready);
    const playSeriesState = await page.evaluate(() => {
      const q = new URL(location.href).searchParams;
      return {
        filesCount: (q.get('files') || '').split(',').filter(Boolean).length,
        autoplay: q.get('autoplay'),
        backText: document.querySelector('#s-head .back-link')?.textContent || '',
      };
    });
    assert.equal(playSeriesState.filesCount, 4);
    assert.equal(playSeriesState.autoplay, '1');
    assert.equal(playSeriesState.backText, '← Series Board');

    await Promise.all([
      page.waitForNavigation(),
      page.click('#s-head .back-link'),
    ]);
    await page.evaluate(() => window.pageReady);

    // 点 G1 · 20...Re8?? 恶手胶囊进入读谱页（不带 autoplay=1，精准停在 ply=40，显示引擎评分 + 最佳着 + ← Series Board）
    await Promise.all([
      page.waitForNavigation(),
      page.click('a.b-pill'),
    ]);
    await page.evaluate(() => window.viewer.ready);
    const readerFromSeries = await page.evaluate(() => ({
      search: location.search,
      curPly: Number(document.querySelector('#s-moves .cur')?.dataset.ply),
      evalText: document.querySelector('#s-note .n-eval')?.textContent || '',
      backText: document.querySelector('#s-head .back-link')?.textContent || '',
      firstSpan: document.querySelector('#s-head span')?.textContent || '',
    }));
    assert.ok(!readerFromSeries.search.includes('autoplay='), readerFromSeries.search);
    assert.equal(readerFromSeries.curPly, 40);
    assert.match(readerFromSeries.evalText, /\+1\.02 → \+4\.10/);
    assert.match(readerFromSeries.evalText, /59\.3% → 81\.9%/);
    assert.match(readerFromSeries.evalText, /Kg7/);
    assert.equal(readerFromSeries.backText, '← Series Board');
    assert.equal(readerFromSeries.firstSpan, 'Chess');
    assert.deepEqual((await collectUiTexts(page)).filter(hasCjk), [], 'reader-eval-en CJK');

    // 手动翻步触发 replaceState 后仍保留 ← Series Board；切换中文后变为 ← 对阵榜；点击成功返回 series.html
    await page.tap('#s-ctrl [data-act="next"]');
    await page.waitForFunction(() => new URL(location.href).searchParams.get('ply') === '41');
    await new Promise((ok) => setTimeout(ok, 220));
    assert.equal(await page.evaluate(() => document.querySelector('#s-head .back-link')?.textContent), '← Series Board');

    await Promise.all([
      page.waitForNavigation(),
      page.click('#s-head a.lang-switch'),
    ]);
    await page.evaluate(() => window.viewer.ready);
    assert.equal(await page.evaluate(() => document.querySelector('#s-head .back-link')?.textContent), '← 对阵榜');

    await Promise.all([
      page.waitForNavigation(),
      page.click('#s-head .back-link'),
    ]);
    await page.evaluate(() => window.pageReady);
    assert.match(page.url(), /\/agi-chess\/series\.html$/);
    const zhSecondCardRes = await page.evaluate(() => [...document.querySelectorAll('.s-card')[1].querySelectorAll('.g-pill .g-res')].map((e) => e.textContent));
    assert.deepEqual(zhSecondCardRes, ['胜', '胜', '负', '负']);

    // 3) 从锚点卡一键跳入 catalog.html?batch=zc，再测 catalog.html?lang=en 全量筛选、关键词搜索、排序与返回目录
    await Promise.all([
      page.waitForNavigation(),
      page.click('.anchor-card a.btn-outline'),
    ]);
    await page.evaluate(() => window.pageReady);
    assert.equal(await page.evaluate(() => document.querySelectorAll('.cat-row').length), 30);

    await page.goto(`${base}catalog.html?lang=en`);
    await page.evaluate(() => window.pageReady);
    assert.equal(await page.evaluate(() => document.querySelectorAll('.cat-row').length), 192);
    assert.deepEqual((await collectUiTexts(page)).filter(hasCjk), [], 'catalog-en CJK');
    await checkNoOverflow(page, 'catalog-375');

    // 关键词搜索 maia-1900 过滤并重置
    await page.fill('.search-input', 'maia-1900');
    assert.equal(await page.evaluate(() => document.querySelectorAll('.cat-row').length), 30);
    assert.match(page.url(), /q=maia-1900/);
    await page.click('.clear-btn');
    assert.equal(await page.evaluate(() => document.querySelectorAll('.cat-row').length), 192);

    // 筛选模型互弈 (64) + 快捷胶囊 Neon (8) + 排序步数最多
    await page.click('.filter-row .pill-group:nth-child(2) .f-pill[data-val="h2h"]');
    assert.equal(await page.evaluate(() => document.querySelectorAll('.cat-row').length), 64);
    await page.click('.model-pill[data-val="neon"]');
    assert.equal(await page.evaluate(() => document.querySelectorAll('.cat-row').length), 8);
    await page.selectOption('.sort-select', 'longest');
    const firstDir = await page.evaluate(() => document.querySelector('.cat-row')?.dataset.dir);
    assert.equal(firstDir, 'runs/neon-xhigh-vs-carbon-high-20261119-4');

    // 点击进入该局并验证 ← Catalog 返回保留筛选状态
    await Promise.all([
      page.waitForNavigation(),
      page.click('.cat-row'),
    ]);
    await page.evaluate(() => window.viewer.ready);
    assert.equal(await page.evaluate(() => document.querySelector('#s-head .back-link')?.textContent), '← Catalog');

    await Promise.all([
      page.waitForNavigation(),
      page.click('#s-head .back-link'),
    ]);
    await page.evaluate(() => window.pageReady);
    assert.equal(await page.evaluate(() => document.querySelectorAll('.cat-row').length), 8);
    assert.match(page.url(), /cat=h2h/);
    assert.match(page.url(), /model=neon/);

    // 4) 宽屏首页顶栏与 series.html 顶栏胶囊像素对齐，以及实盘 ⚠ 告警分段渲染核验（neon-xhigh-vs-carbon-high-20261119-2 ply=70）
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${base}?lang=en`);
    await page.evaluate(() => window.viewer.ready);
    const homeNavRects = await page.evaluate(() => ({
      brandLeft: Math.round(document.querySelector('#hint .h-top-brand').getBoundingClientRect().left),
      firstTabLeft: Math.round(document.querySelector('#hint .h-topbar .nav-pill').getBoundingClientRect().left),
      langRight: Math.round(document.querySelector('#hint .h-topbar .lang-switch').getBoundingClientRect().right),
    }));
    await page.goto(`${base}series.html?lang=en`);
    await page.evaluate(() => window.pageReady);
    const seriesNavRects = await page.evaluate(() => ({
      brandLeft: Math.round(document.querySelector('#top-header .p-brand').getBoundingClientRect().left),
      firstTabLeft: Math.round(document.querySelector('#top-header .nav-pill').getBoundingClientRect().left),
      langRight: Math.round(document.querySelector('#top-header .lang-switch').getBoundingClientRect().right),
    }));
    assert.deepEqual(homeNavRects, seriesNavRects);

    await page.goto(`${base}?lang=en&files=runs/neon-xhigh-vs-carbon-high-20261119-2&ply=70`);
    await page.evaluate(() => window.viewer.ready);
    const warnDom = await page.evaluate(() => ({
      warns: document.querySelectorAll('#s-note .why-warn').length,
      bodies: document.querySelectorAll('#s-note .why-body').length,
    }));
    assert.deepEqual(warnDom, { warns: 1, bodies: 2 });
    assert.deepEqual((await collectUiTexts(page)).filter(hasCjk), [], 'warn-ply70-en CJK');

    assert.deepEqual(errors, []);
  } finally {
    await ctx.close();
    await server.close();
    rmSync(tmp, { recursive: true, force: true });
  }
});

after(() => browser?.close());
