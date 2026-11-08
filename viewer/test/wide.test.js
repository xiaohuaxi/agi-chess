// 宽版（docs/viewer.md「版式」）：lib/panel.js 的纯函数，加上无头浏览器里的版式自动切换、键盘单步 / 首尾 / 换盘、
// 点着法跳步、按钮播放暂停、评注面板的标签与标注。
// 浏览器部分要 viewer/node_modules 里的 playwright-core 和它配套的 Chromium（或 VIEWER_CHROMIUM），没有就跳过。
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fmtSeconds, moveRows, nagLabel, noteItems } from '../lib/panel.js';
import { decodeText, moveNote, parsePgn } from '../lib/pgn.js';
import { replay } from '../lib/replay.js';
import { resolveChromium, serve } from '../serve.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FIX = '/viewer/test/fixtures/';

test('标注、用时、评注数字的中文写法', () => {
  assert.deepEqual([1, 2, 3, 4, 5, 6, 10].map(nagLabel), ['! 好棋', '? 错着', '!! 妙着', '?? 大错', '!? 有意思', '?! 可疑', '$10']);
  assert.deepEqual([5, 76, 3723.25].map(fmtSeconds), ['5 秒', '1 分 16 秒', '1 时 2 分 3.3 秒']);
  const n = moveNote({ comments: ['[%emt 0:01:02] [%think 12345] [%illegal 2] [%clk 0:10:00] 理由'] });
  assert.deepEqual(noteItems(n).map((x) => [x.label, x.value]), [['用时', '1 分 2 秒'], ['思考 token', '12,345'], ['非法重选', '2']]);
});

test('着法列表按回合成行，黑方先走时第一行红 / 白空着，带标注后缀', () => {
  const [g] = parsePgn('[FEN "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"]\n1... e5?! 2. Nf3! Nc6 *');
  const rep = replay(g);
  assert.deepEqual(moveRows(rep.steps, g.moves, 'b', 1, false), [
    { no: 1, w: null, b: { ply: 1, text: 'e5?!' } },
    { no: 2, w: { ply: 2, text: 'Nf3!' }, b: { ply: 3, text: 'Nc6' } },
  ]);
});

// ---------------------------------------------------------------- 浏览器
const plies = (file) => parsePgn(decodeText(readFileSync(join(ROOT, FIX, file)))).map((g) => replay(g).steps.length);

let pw = null;
try { pw = await import('playwright-core'); } catch { /* 没装开发依赖 */ }
let browser = null, skip = pw ? false : '没有 playwright-core（cd viewer && npm ci）';
if (pw) {
  try { browser = await pw.chromium.launch({ executablePath: resolveChromium(undefined, pw) }); }
  catch (e) { skip = `起不来浏览器：${e.message.split('\n')[0]}`; }
}

async function withPage(query, viewport, fn) {
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

const WIDE = { width: 1440, height: 900 };
const layout = (page) => page.evaluate(() => document.getElementById('stage').className.split(' ').filter((c) => c === 'wide' || c === 'compact').join());
// 右栏现在高亮的是第几盘、第几个半回合（等到画完为止）
async function at(page, gi, ply) {
  await page.waitForFunction(([gi, ply]) => {
    const c = document.querySelector('#s-moves .cur');
    const sel = document.getElementById('s-game');
    return c && Number(c.dataset.ply) === ply && (!sel || Number(sel.value) === gi);
  }, [gi, ply], { timeout: 5000 });
}

test('版式：按窗口宽度自动选，layout= 强制，rec=1 恒为窄版，窗口改大小时跟着切', { skip }, async () => {
  const q = `files=${FIX}chess-sample.pgn`;
  await withPage(q, WIDE, async (page) => {
    assert.equal(await layout(page), 'wide');
    await page.setViewportSize({ width: 540, height: 720 });
    await page.waitForFunction(() => document.getElementById('stage').classList.contains('compact'));
    assert.equal(await page.evaluate(() => getComputedStyle(document.getElementById('side')).display), 'none');
  });
  await withPage(q, { width: 540, height: 720 }, async (page) => assert.equal(await layout(page), 'compact'));
  await withPage(`layout=compact&${q}`, WIDE, async (page) => assert.equal(await layout(page), 'compact'));
  await withPage(`rec=1&layout=wide&${q}`, WIDE, async (page) => assert.equal(await layout(page), 'compact'));
  await withPage(`layout=wide&${q}`, { width: 800, height: 700 }, async (page) => assert.equal(await layout(page), 'wide'));
});

test('键盘：单步、连按、首尾、跨盘、换盘', { skip }, async () => {
  const [n1] = plies('chess-sample.pgn');
  await withPage(`layout=wide&files=${FIX}chess-sample.pgn,${FIX}xq-sample.pgn&game=1&ply=0`, WIDE, async (page) => {
    await at(page, 0, 0);
    await page.keyboard.press('ArrowRight');
    await at(page, 0, 1);
    for (let i = 0; i < 4; i++) await page.keyboard.press('ArrowRight');   // 连按不等画完也不丢步
    await at(page, 0, 5);
    await page.keyboard.press('ArrowLeft');
    await at(page, 0, 4);
    await page.keyboard.press('End');
    await at(page, 0, n1);
    assert.equal(await page.evaluate(() => document.getElementById('banner').hidden), false);   // 走到底带终局横幅
    await page.keyboard.press('ArrowRight');                                // 本盘到底再往后：下一盘开局
    await at(page, 1, 0);
    assert.equal(await page.evaluate(() => document.querySelector('#s-head span').textContent), '中国象棋');
    await page.keyboard.press('ArrowLeft');                                 // 再退回上一盘的最后一步
    await at(page, 0, n1);
    await page.keyboard.press('Home');
    await at(page, 0, 0);
    await page.keyboard.press('PageDown');
    await at(page, 1, 0);
    await page.keyboard.press('PageUp');
    await at(page, 0, 0);
    await page.selectOption('#s-game', '1');                               // 下拉框换盘
    await at(page, 1, 0);
  });
});

test('黑方回合号：中国象棋不带省略号（「4. 卒３进１」），国际象棋照标准写「1...」', { skip }, async () => {
  const look = (page) => page.evaluate(() => ({
    head: document.querySelector('#s-note .n-head').firstChild.textContent,
    bar: document.querySelector('#bar-top .mv').textContent,
  }));
  await withPage(`layout=wide&files=${FIX}xq-sample.pgn&ply=6`, WIDE, async (page) => {
    const x = await look(page);
    assert.match(x.head, /^3\. \S/);
    assert.match(x.bar, /^3\. \S/);
  });
  await withPage(`layout=wide&files=${FIX}chess-sample.pgn&ply=2`, WIDE, async (page) => {
    assert.deepEqual(await look(page), { head: '1... e5', bar: '1... e5' });
  });
});

test('点着法跳步，按钮与空格播放 / 暂停，评注面板带中文标签', { skip }, async () => {
  await withPage(`layout=wide&gap=0.05&files=${FIX}xq-sample.pgn`, WIDE, async (page) => {
    await page.click('#s-moves [data-ply="7"]');
    await at(page, 0, 7);
    const note = await page.evaluate(() => ({
      head: document.querySelector('#s-note .n-head').textContent,
      labels: [...document.querySelectorAll('#s-note dt')].map((e) => e.textContent),
      why: document.querySelector('#s-note .why')?.textContent.length > 0,
      bar: document.querySelector('#bar-bottom .mv').textContent,
    }));
    assert.match(note.head, /^4\. 兵七进一/);
    assert.deepEqual(note.labels, ['用时', '思考 token', '输出 token', '输入 token', '缓存读', '缓存写']);
    assert.equal(note.why, true);
    assert.equal(note.bar, '4. 兵七进一');                                  // 棋盘和棋手条跟着跳
    await page.click('#s-play');
    await page.waitForFunction(() => document.getElementById('s-play').textContent === '暂停');
    await page.waitForFunction(() => Number(document.querySelector('#s-moves .cur')?.dataset.ply) >= 9);   // 从跳到的那步往下播
    await page.keyboard.press('Space');
    await page.waitForFunction(() => document.getElementById('s-play').textContent === '播放');
    const p = await page.evaluate(() => document.querySelector('#s-moves .cur').dataset.ply);
    await new Promise((ok) => setTimeout(ok, 300));
    assert.equal(await page.evaluate(() => document.querySelector('#s-moves .cur').dataset.ply), p);   // 真停了
    await page.keyboard.press('ArrowRight');                               // 播放中按方向键：停下并走一步（这里已停，直接走）
    await at(page, 0, Number(p) + 1);
  });
});

test('评注面板：标注、将军、非法重选、不认识的命令', { skip }, async () => {
  await withPage('layout=wide&autoplay=0', WIDE, async (page) => {
    const pgn = '[White "claude:opus"]\n[Black "codex:astra"]\n[WhiteEffort "xhigh"]\n\n'
      + '1. e4! { [%think 10] [%illegal 2] [%clk 0:01:00] 走中心 } 1... e5?? 2. Qh5 Nc6 3. Bc4 Nf6?? 4. Qxf7# 1-0\n';
    const dt = await page.evaluateHandle((t) => { const d = new DataTransfer(); d.items.add(new File([t], 'x.pgn')); return d; }, pgn);
    await page.dispatchEvent('body', 'drop', { dataTransfer: dt });
    await page.waitForFunction(() => document.querySelector('#s-moves [data-ply="7"]'));
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('#s-moves .m.bad, #s-moves .m.good')]
      .map((e) => [e.textContent, e.className])), [['e4!', 'm good'], ['e5??', 'm bad'], ['Nf6??', 'm bad']]);
    assert.equal(await page.evaluate(() => document.querySelector('#s-players').textContent),
      'Claude opus思考深度 xhighGPT astra结果：白方胜');
    await page.keyboard.press('ArrowRight');
    await at(page, 0, 1);
    const n1 = await page.evaluate(() => ({
      nags: [...document.querySelectorAll('#s-note .nag')].map((e) => e.textContent),
      warn: [...document.querySelectorAll('#s-note dd.warn')].map((e) => e.textContent),
      raw: document.querySelector('#s-note .raw').textContent, why: document.querySelector('#s-note .why').textContent,
    }));
    assert.deepEqual(n1, { nags: ['! 好棋'], warn: ['2'], raw: '[%clk 0:01:00]', why: '走中心' });
    await page.keyboard.press('End');
    await at(page, 0, 7);
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('#s-note .nag')].map((e) => e.textContent)), ['将军']);
    assert.match(await page.evaluate(() => document.getElementById('s-note').textContent), /终局白方胜/);
  });
});

after(() => browser?.close());
