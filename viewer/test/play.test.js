// 播放顺序与录制接口（docs/viewer.md「播放」）。
// 前半是 lib/play.js 的纯函数；后半用无头浏览器打开页面，调 window.viewer.next() 一格一格走完一盘单盘和几组连播，
// 核对 kind 顺序、hold（随 gap 等网址参数变）、播完标记、拖文件进页面、自动播放。
// 浏览器部分要 viewer/node_modules 里的 playwright-core 和它配套的 Chromium（或 VIEWER_CHROMIUM），没有就跳过。
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DEFAULTS, playOptions, sequence } from '../lib/play.js';
import { decodeText, parsePgn } from '../lib/pgn.js';
import { replay } from '../lib/replay.js';
import { serve } from '../serve.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FIX = '/viewer/test/fixtures/';

test('播放设置：默认值、自定、不合法回默认', () => {
  const o = playOptions(new URLSearchParams(''));
  assert.deepEqual(o, { ...DEFAULTS, openhold: DEFAULTS.gap, title: false });   // 标题画面默认不加；开局局面停得和每步一样久
  assert.equal(playOptions(new URLSearchParams('title=1')).title, true);
  assert.equal(playOptions(new URLSearchParams('title=0')).title, false);   // 旧写法仍表示关
  assert.equal(o.gap, 1.8);
  assert.equal(o.anim, 0.3);
  const p = playOptions(new URLSearchParams('gap=1.5&titlehold=0&resulthold=x&summaryhold=-1&title=0&anim=0'));
  assert.deepEqual(p, { gap: 1.5, openhold: 1.5, titlehold: 0, resulthold: DEFAULTS.resulthold, summaryhold: DEFAULTS.summaryhold, anim: 0, title: false });
  assert.equal(playOptions(new URLSearchParams('anim=-1')).anim, DEFAULTS.anim);
  // openhold 单独给就用它（0 也算），不合法时跟着 gap 走
  assert.equal(playOptions(new URLSearchParams('gap=1.5&openhold=0.5')).openhold, 0.5);
  assert.equal(playOptions(new URLSearchParams('openhold=0')).openhold, 0);
  for (const v of ['x', '-1', '', ' ']) assert.equal(playOptions(new URLSearchParams(`gap=2&openhold=${v}`)).openhold, 2, v);
});

test('播放顺序：单盘 title → move… → result → end(0)；多盘 end 停 summaryhold；没结果的盘没有 result', () => {
  const opt = { gap: 2, titlehold: 3, resulthold: 4, summaryhold: 5, title: true };
  const one = sequence([{ plies: 2, over: true }], opt);
  assert.deepEqual(one.map((f) => [f.kind, f.ply, f.hold]),
    [['title', 0, 3], ['move', 1, 2], ['move', 2, 2], ['result', 2, 4], ['end', null, 0]]);
  const two = sequence([{ plies: 1, over: false }, { plies: 0, over: true }], { ...opt, title: false });
  assert.deepEqual(two.map((f) => [f.kind, f.game, f.ply, f.hold]),
    [['move', 0, 0, 2], ['move', 0, 1, 2], ['move', 1, 0, 2], ['result', 1, 0, 4], ['end', null, null, 5]]);
});

test('播放顺序：openhold 只管每盘开局局面那格（每盘都管），标题画面、走子格不受影响', () => {
  const opt = { gap: 2, openhold: 0.5, titlehold: 3, resulthold: 4, summaryhold: 5, title: false, anim: 0.3 };
  const two = sequence([{ plies: 1, over: true }, { plies: 1, over: true }], opt);
  assert.deepEqual(two.map((f) => [f.kind, f.game, f.ply, f.hold, f.anim]), [
    ['move', 0, 0, 0.5, 0], ['move', 0, 1, 1.7, 0.3], ['result', 0, 1, 4, 0],
    ['move', 1, 0, 0.5, 0], ['move', 1, 1, 1.7, 0.3], ['result', 1, 1, 4, 0], ['end', null, null, 5, 0]]);
  const titled = sequence([{ plies: 1, over: false }], { ...opt, title: true });
  assert.deepEqual(titled.map((f) => [f.kind, f.hold]), [['title', 3], ['move', 1.7], ['end', 0]]);
});

test('播放顺序：走子动画算在 gap 之内——只有走子那几格有 anim，hold = gap − anim，anim 超过 gap 时截到 gap', () => {
  const opt = { gap: 2, titlehold: 3, resulthold: 4, summaryhold: 5, title: false, anim: 0.5 };
  const one = sequence([{ plies: 2, over: true }], opt);
  assert.deepEqual(one.map((f) => [f.kind, f.ply, f.hold, f.anim]),
    [['move', 0, 2, 0], ['move', 1, 1.5, 0.5], ['move', 2, 1.5, 0.5], ['result', 2, 4, 0], ['end', null, 0, 0]]);
  const short = sequence([{ plies: 1, over: false }], { ...opt, gap: 0.2 });
  assert.deepEqual(short.map((f) => [f.hold, f.anim]), [[0.2, 0], [0, 0.2], [0, 0]]);
});

test('播放顺序：每格响哪声——吃子格 capture、其余走子格 move、结果格 end，开局 / 标题 / 总比分不响', () => {
  const opt = { gap: 2, titlehold: 3, resulthold: 4, summaryhold: 5, title: true, anim: 0.3 };
  const one = sequence([{ plies: 3, over: true, captures: [false, true, false] }, { plies: 1, over: false }], opt);
  assert.deepEqual(one.map((f) => [f.kind, f.ply, f.sound]), [
    ['title', 0, null], ['move', 1, 'move'], ['move', 2, 'capture'], ['move', 3, 'move'], ['result', 3, 'end'],
    ['title', 0, null], ['move', 1, 'move'], ['end', null, null]]);   // 第二盘没给 captures、没结果：只有落子声
  const plain = sequence([{ plies: 1, over: true }], { ...opt, title: false });
  assert.deepEqual(plain.map((f) => f.sound), [null, 'move', 'end', null]);
});

// ---------------------------------------------------------------- 浏览器
const plies = (file) => parsePgn(decodeText(readFileSync(join(ROOT, FIX, file)))).map((g) => replay(g).steps.length);

// 不看实现，照方案手写的期望：[kind, hold, anim]。走子那几格先滑 anim 秒、再停 gap − anim，一格总长仍是 gap。
// openhold 是开局局面那格停多久，不给时同 gap。
function expected(counts, { gap = 1.8, openhold = gap, titlehold = 3, resulthold = 4, summaryhold = 5, title = false, anim = 0.3 } = {}) {
  const out = [];
  for (const n of counts) {
    out.push(title ? ['title', titlehold, 0] : ['move', openhold, 0]);
    for (let i = 0; i < n; i++) out.push(['move', gap - anim, anim]);
    out.push(['result', resulthold, 0]);                 // 样例每盘都有结果
  }
  out.push(['end', counts.length > 1 ? summaryhold : 0, 0]);
  return out;
}

let pw = null;
try { pw = await import('playwright-core'); } catch { /* 没装开发依赖 */ }
let browser = null, skip = pw ? false : '没有 playwright-core（cd viewer && npm ci）';
if (pw) {
  try { browser = await pw.chromium.launch({ executablePath: process.env.VIEWER_CHROMIUM || undefined }); }
  catch (e) { skip = `起不来浏览器：${e.message.split('\n')[0]}`; }
}

async function withPage(query, fn) {
  const server = await serve(ROOT);
  const page = await browser.newPage({ viewport: { width: 540, height: 720 } });
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

// 调 next() 走到 end 为止（多给几格余量防死循环），返回 [kind, hold, anim] 列表。
// 不去拨动画进度：下一格开始时页面自己把上一段直接结束。
async function walk(page) {
  return page.evaluate(async () => {
    const out = [];
    for (let i = 0; i < 2000; i++) {
      const r = await window.viewer.next();
      out.push([r.kind, r.hold, r.anim]);
      if (r.kind === 'end') break;
    }
    return out;
  });
}

test('录制接口：单盘默认参数（默认没有标题画面）', { skip }, async () => {
  await withPage(`rec=1&files=${FIX}chess-sample.pgn`, async (page) => {
    const res = await page.evaluate(() => ({
      sprite: !!document.getElementById('cm-chessboard-sprite'), fonts: document.fonts.status,
      done: window.viewer.done, title: !document.getElementById('title').hidden,
    }));
    assert.deepEqual(res, { sprite: true, fonts: 'loaded', done: false, title: false });   // ready 时第一格（开局局面）已画好
    assert.deepEqual(await walk(page), expected(plies('chess-sample.pgn')));
    assert.equal(await page.evaluate(() => document.body.dataset.done), '1');
    assert.deepEqual(await page.evaluate(() => window.viewer.next()), { kind: 'end', hold: 0, anim: 0, sound: null });
  });
});

test('录制接口：单盘自定时长、title=1 有标题画面，result 那格才出横幅', { skip }, async () => {
  await withPage(`rec=1&title=1&gap=1.5&titlehold=2&resulthold=6&files=${FIX}xq-sample.pgn`, async (page) => {
    assert.equal(await page.evaluate(() => !document.getElementById('title').hidden), true);   // ready 时第一格（标题）已画好
    const n = plies('xq-sample.pgn')[0];
    const seen = await page.evaluate(async (n) => {
      const banner = () => !document.getElementById('banner').hidden;
      const out = [];
      for (let i = 0; i < n + 3; i++) { const r = await window.viewer.next(); out.push([r.kind, r.hold, r.anim, banner()]); }
      return out;
    }, n);
    const want = expected([n], { title: true, gap: 1.5, titlehold: 2, resulthold: 6 }).map(([k, h, a]) => [k, h, a, k === 'result' || k === 'end']);
    assert.deepEqual(seen, want);
  });
});

test('录制接口：连播（一个文件多盘 + 多个文件、两种棋），title=0，end 画总比分', { skip }, async () => {
  const files = ['layout-extreme-chess.pgn', 'xq-sample.pgn'];
  await withPage(`rec=1&title=0&gap=0.5&resulthold=1&summaryhold=7&files=${files.map((f) => FIX + f).join(',')}`, async (page) => {
    const counts = files.flatMap(plies);
    assert.equal(counts.length, 13);
    assert.deepEqual(await walk(page), expected(counts, { title: false, gap: 0.5, resulthold: 1, summaryhold: 7 }));
    const end = await page.evaluate(() => ({
      summary: document.getElementById('stage').classList.contains('summary'),
      kind: document.querySelector('#summary .s-kind').textContent, done: window.viewer.done,
    }));
    assert.deepEqual(end, { summary: true, kind: '国际象棋 / 中国象棋', done: true });
  });
});

test('录制接口：连播 openhold=0.2，每盘开局局面那格都停 0.2，其余照 gap', { skip }, async () => {
  const files = ['chess-sample.pgn', 'xq-sample.pgn'];
  await withPage(`rec=1&gap=0.5&openhold=0.2&files=${files.map((f) => FIX + f).join(',')}`, async (page) => {
    assert.deepEqual(await walk(page), expected(files.flatMap(plies), { gap: 0.5, openhold: 0.2 }));
  });
});

test('拖文件进页面：换成拖进来的棋谱、从头播（title=1 时照样有标题）', { skip }, async () => {
  await withPage(`rec=1&title=1&files=${FIX}chess-sample.pgn`, async (page) => {
    await page.evaluate(() => window.viewer.next());
    const texts = ['xq-sample.pgn', 'chess-sample.pgn'].map((f) => readFileSync(join(ROOT, FIX, f), 'utf8'));
    const dt = await page.evaluateHandle(([a, b]) => {
      const dt = new DataTransfer();
      dt.items.add(new File([a], 'b.pgn'));          // 按文件名排序：a.pgn（国际象棋）在前
      dt.items.add(new File([b], 'a.pgn'));
      return dt;
    }, texts);
    await page.dispatchEvent('body', 'drop', { dataTransfer: dt });
    await page.waitForFunction(() => document.querySelector('#title .t-head')?.textContent === '第 1 局 · 共 2 局');
    assert.deepEqual(await walk(page), expected([...plies('chess-sample.pgn'), ...plies('xq-sample.pgn')], { title: true }));
  });
});

test('拖文件进页面：默认没有标题画面', { skip }, async () => {
  await withPage(`rec=1&files=${FIX}chess-sample.pgn`, async (page) => {
    await page.evaluate(() => window.viewer.next());
    const text = readFileSync(join(ROOT, FIX, 'xq-sample.pgn'), 'utf8');
    const dt = await page.evaluateHandle((a) => {
      const dt = new DataTransfer();
      dt.items.add(new File([a], 'a.pgn'));
      return dt;
    }, text);
    await page.dispatchEvent('body', 'drop', { dataTransfer: dt });
    await page.waitForFunction(() => document.getElementById('stage').classList.contains('xq'));   // 换成象棋、第一格已画
    assert.deepEqual(await walk(page), expected(plies('xq-sample.pgn')));
    assert.equal(await page.evaluate(() => document.getElementById('title').hidden), true);
  });
});

test('自动播放：按 gap 等参数一格格播完，置播完标记', { skip }, async () => {
  await withPage(`autoplay=1&gap=0.01&titlehold=0.01&resulthold=0.01&summaryhold=0.01&files=${FIX}xq-sample.pgn,${FIX}chess-sample.pgn`,
    async (page) => {
      await page.waitForFunction(() => document.body.dataset.done === '1', null, { timeout: 20000 });
      assert.equal(await page.evaluate(() => document.getElementById('stage').classList.contains('summary')), true);
    });
});

after(() => browser?.close());
