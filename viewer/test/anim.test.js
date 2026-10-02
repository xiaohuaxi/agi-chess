// 走子滑动动画（docs/viewer.md「棋盘·走子动画」）：无头浏览器里核对
// ——录制模式下 next() 兑现时动画停在起点，拨到一半时走的子正好在起止两格中间，走完落在落点、临时叠的子都收掉；
// 被吃的子动画期间还在、结束消失；王车易位车也滑；升变滑的是兵、结束是后；吃过路兵被吃的兵在旁边那格；
// 静态看某一格（game/ply）不带动画；非录制时连按 → 不丢步、不错位，最后停在对的局面上。
// 要 viewer/node_modules 里的 playwright-core 和它配套的 Chromium（或 VIEWER_CHROMIUM），没有就跳过。
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { serve } from '../serve.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FIX = '/viewer/test/fixtures/';

let pw = null;
try { pw = await import('playwright-core'); } catch { /* 没装开发依赖 */ }
let browser = null, skip = pw ? false : '没有 playwright-core（cd viewer && npm ci）';
if (pw) {
  try { browser = await pw.chromium.launch({ executablePath: process.env.VIEWER_CHROMIUM || undefined }); }
  catch (e) { skip = `起不来浏览器：${e.message.split('\n')[0]}`; }
}

async function withPage(query, fn, viewport = { width: 540, height: 720 }) {
  const server = await serve(ROOT);
  const page = await browser.newPage({ viewport });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  try {
    await page.goto(`http://127.0.0.1:${server.port}/viewer/?${query}`);
    await page.evaluate(() => window.viewer.ready);
    await fn(page);
    assert.deepEqual(errors, []);
  } finally {
    await page.close();
    await server.close();
  }
}

// 录制模式：走到第 ply 个半回合那格（前面有一格标题），返回那格的 next() 结果。
const toPly = (page, ply) => page.evaluate(async (n) => {
  let r;
  for (let i = 0; i <= n; i++) r = await window.viewer.next();
  return r;
}, ply);

// 把页面上所有动画拨到 t 毫秒（t 为 'end' 时走完并等两帧），再量各选择器对应元素的中心。
const probe = (page, t, sels) => page.evaluate(async ([t, sels]) => {
  if (t === 'end') {
    for (const a of document.getAnimations()) a.finish();
    await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
  } else for (const a of document.getAnimations()) { a.pause(); a.currentTime = t; }
  const c = (e) => { if (!e) return null; const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; };
  return {
    n: document.getAnimations().length,
    ...Object.fromEntries(Object.entries(sels).map(([k, s]) => [k, c(document.querySelector(s))])),
  };
}, [t, sels]);

const near = (a, b, tol = 1.5) => Math.abs(a[0] - b[0]) <= tol && Math.abs(a[1] - b[1]) <= tol;
const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];

// 国际象棋：临时叠上去的棋子画在 .pieces 的最后；格子用 cm-chessboard 棋盘层里带 data-square 的 rect 定位。
const sq = (s) => `#board-chess rect[data-square='${s}']`;
const top = '#board-chess g.pieces > g:last-child';
const playState = (page) => page.evaluate(() => document.getAnimations().map((a) => a.playState));

test('国际象棋：录制模式停在起点，拨到一半在两格正中，走完落定、叠的子收掉', { skip }, async () => {
  await withPage(`rec=1&files=${FIX}chess-sample.pgn`, async (page) => {
    const r = await toPly(page, 13);                       // 7. Nxe5：f3 → e5，吃兵
    assert.deepEqual(r, { kind: 'move', hold: 1.5, anim: 0.3, sound: 'capture' });
    assert.ok((await playState(page)).every((s) => s === 'paused'));
    const S = { mv: top, from: sq('f3'), to: sq('e5'), taken: "#board-chess g.pieces > g[data-piece='bp'][data-square='e5']" };
    const t0 = await probe(page, 0, S);
    assert.ok(near(t0.mv, t0.from), `起点 ${t0.mv} 应在 f3 ${t0.from}`);
    assert.ok(t0.taken, '被吃的兵动画期间还在');
    const th = await probe(page, 150, S);
    assert.ok(near(th.mv, mid(th.from, th.to)), `一半 ${th.mv} 应在 f3、e5 正中 ${mid(th.from, th.to)}`);
    const t1 = await probe(page, 'end', S);
    assert.equal(t1.taken, null, '走完被吃的兵消失');
    const left = await page.evaluate(() => ({
      pieces: document.querySelectorAll('#board-chess g.pieces > g').length,
      n: document.querySelectorAll("#board-chess g.pieces > g[data-square='e5']").length,
      e5: document.querySelector("#board-chess g.pieces > g[data-square='e5']").dataset.piece,
      opacity: getComputedStyle(document.querySelector("#board-chess g.pieces > g[data-square='e5']")).opacity,
    }));
    assert.deepEqual(left, { pieces: 30, n: 1, e5: 'wn', opacity: '1' });
  });
});

test('国际象棋：长易位车也滑、吃过路兵被吃的兵在旁边那格、升变滑的是兵', { skip }, async () => {
  await withPage(`rec=1&files=${FIX}anim-special.pgn`, async (page) => {
    // 3. exf6（吃过路兵）：e5 → f6，被吃的是 f5 上的黑兵
    await toPly(page, 5);
    const ep = await probe(page, 150, { taken: "#board-chess g.pieces > g[data-piece='bp'][data-square='f5']" });
    assert.ok(ep.taken, '吃过路兵：动画期间 f5 的黑兵还在');
    assert.equal((await probe(page, 'end', { taken: "#board-chess g.pieces > g[data-piece='bp'][data-square='f5']" })).taken, null);
    // 5. gxh8=Q：滑的是白兵，结束后 h8 是白后
    await page.evaluate(async () => { for (let i = 0; i < 4; i++) await window.viewer.next(); });
    const pr = await page.evaluate(() => document.querySelector('#board-chess g.pieces > g:last-child').dataset.piece);
    assert.equal(pr, 'wp');
    await probe(page, 'end', {});
    assert.equal(await page.evaluate(() => document.querySelector("#board-chess g.pieces > g[data-square='h8']").dataset.piece), 'wq');
    // 6... O-O-O：王 e8 → c8，车 a8 → d8，两枚都滑（叠上去的子记着起点格）
    await page.evaluate(async () => { for (let i = 0; i < 3; i++) await window.viewer.next(); });
    const piece = (p, s) => `#board-chess g.pieces > g[data-piece='${p}'][data-square='${s}']`;
    const S = { k: piece('bk', 'e8'), r: piece('br', 'a8'), a8: sq('a8'), c8: sq('c8'), d8: sq('d8'), e8: sq('e8') };
    // 棋子图不一定在格子里上下居中（车矮），所以按「起点位置 + 两格中心连线的一半」比
    const z = await probe(page, 0, S);
    const h = await probe(page, 150, S);
    const half = (p, a, b) => [p[0] + (b[0] - a[0]) / 2, p[1] + (b[1] - a[1]) / 2];
    assert.ok(near(z.k, z.e8, 3) && near(z.r, z.a8, 3), '起点在 e8、a8');
    assert.ok(near(h.k, half(z.k, h.e8, h.c8)), `王一半 ${h.k}`);
    assert.ok(near(h.r, half(z.r, h.a8, h.d8)), `车一半 ${h.r}`);
    const e = await probe(page, 'end', { ...S, kc: piece('bk', 'c8'), rd: piece('br', 'd8') });
    assert.equal(e.k, null);
    assert.equal(e.r, null);
    assert.ok(near(e.kc, e.c8, 3) && near(e.rd, e.d8, 3), '走完王在 c8、车在 d8');
    assert.equal(await page.evaluate(() => document.querySelectorAll('#board-chess g.pieces > g').length), 29);   // 吃了三个子
  });
});

test('中国象棋：拨到一半在两点正中，被吃的子垫在下面、走完消失', { skip }, async () => {
  await withPage(`rec=1&files=${FIX}xq-sample.pgn`, async (page) => {
    await page.evaluate(async () => { for (let i = 0; i < 7; i++) await window.viewer.next(); });
    const r = await page.evaluate(() => window.viewer.next());   // 第 7 步：c4 → c5 吃卒
    assert.deepEqual(r, { kind: 'move', hold: 1.5, anim: 0.3, sound: 'capture' });
    const S = { mv: '.xq-pieces > g:last-child', under: '.xq-pieces > g:first-child' };
    const t0 = await probe(page, 0, S);
    const th = await probe(page, 150, S);
    const count = await page.evaluate(() => document.querySelectorAll('.xq-pieces > g').length);
    const t1 = await probe(page, 'end', S);
    assert.ok(!near(t0.mv, t1.mv), '起点和落点不同');
    assert.ok(near(th.mv, mid(t0.mv, t1.mv)), `一半 ${th.mv} 应在正中 ${mid(t0.mv, t1.mv)}`);
    assert.ok(near(t0.under, t1.mv), '被吃的子垫在落点');
    const after = await page.evaluate(() => document.querySelectorAll('.xq-pieces > g').length);
    assert.equal(count - after, 1, '走完被吃的子收掉');
    assert.equal(after, 31);
  });
});

test('静态看某一格不带动画；anim=0 时 next() 的 anim 为 0、hold = gap', { skip }, async () => {
  await withPage(`files=${FIX}xq-sample.pgn&ply=7`, async (page) => {
    assert.equal(await page.evaluate(() => document.getAnimations().length), 0);
  });
  await withPage(`rec=1&anim=0&gap=1&files=${FIX}chess-sample.pgn`, async (page) => {
    assert.deepEqual(await toPly(page, 3), { kind: 'move', hold: 1, anim: 0, sound: 'move' });
    assert.equal(await page.evaluate(() => document.getAnimations().length), 0);
  });
});

test('手工单步（宽版）：往前一步会滑、连按不丢步不错位；往回直接画', { skip }, async () => {
  await withPage(`layout=wide&anim=0.3&files=${FIX}chess-sample.pgn&ply=0`, async (page) => {
    await page.keyboard.press('ArrowRight');
    await page.waitForFunction(() => document.getAnimations().length > 0);
    assert.ok((await playState(page)).includes('running'));
    for (let i = 0; i < 12; i++) await page.keyboard.press('ArrowRight');   // 连按，不等动画
    await page.waitForFunction(() => document.querySelector('#s-moves .cur')?.dataset.ply === '13'
      && document.getAnimations().length === 0, null, { timeout: 5000 });
    const s = await page.evaluate(() => ({
      cur: document.querySelector('#s-moves .cur').dataset.ply,
      pieces: [...document.querySelectorAll('#board-chess g.pieces > g')].map((g) => g.dataset.square + g.dataset.piece).sort().join(' '),
    }));
    assert.equal(s.cur, '13');
    // 与静态直接画第 13 步的棋子一一对上
    const server = await serve(ROOT);
    const p2 = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    try {
      await p2.goto(`http://127.0.0.1:${server.port}/viewer/?layout=wide&files=${FIX}chess-sample.pgn&ply=13`);
      await p2.evaluate(() => window.viewer.ready);
      const want = await p2.evaluate(() => [...document.querySelectorAll('#board-chess g.pieces > g')]
        .map((g) => g.dataset.square + g.dataset.piece).sort().join(' '));
      assert.equal(s.pieces, want);
    } finally { await p2.close(); await server.close(); }
    await page.keyboard.press('ArrowLeft');
    await page.waitForFunction(() => document.querySelector('#s-moves .cur')?.dataset.ply === '12');
    assert.equal(await page.evaluate(() => document.getAnimations().length), 0);
  }, { width: 1440, height: 900 });
});

test('自动播放：每步有滑动，一格总长仍按 gap 走完', { skip }, async () => {
  await withPage(`autoplay=1&gap=0.4&anim=0.3&titlehold=0.05&resulthold=0.05&files=${FIX}anim-special.pgn`, async (page) => {
    await page.waitForFunction(() => document.getAnimations().some((a) => a.playState === 'running'), null, { timeout: 5000 });
    const t0 = Date.now();
    await page.waitForFunction(() => document.body.dataset.done === '1', null, { timeout: 20000 });
    const ms = Date.now() - t0;
    // 13 步 × 0.4 秒 ≈ 5.2 秒（加上每格画面的开销）；动画若另外加时长会到 9 秒以上
    assert.ok(ms > 4000 && ms < 8500, `播完用了 ${ms} 毫秒`);
  });
});

after(() => browser?.close());
