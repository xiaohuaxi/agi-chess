// 走子音效（docs/viewer.md「走子音效」）。
// 前半是 lib/sound.js 的纯函数；后半用无头浏览器：录制模式下 next() 给的 sound 和棋谱里的吃子逐步对得上，
// 看棋谱时默认不读、不放声音，sound=1 时手工单步和自动播放各响对的声、落在动画结束那一刻。
// 浏览器部分要 viewer/node_modules 里的 playwright-core 和它配套的 Chromium（或 VIEWER_CHROMIUM），没有就跳过。
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SOUNDS, linear, soundOptions, stepSound } from '../lib/sound.js';
import { decodeText, parsePgn } from '../lib/pgn.js';
import { replay } from '../lib/replay.js';
import { resolveChromium, serve } from '../serve.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FIX = '/viewer/test/fixtures/';
const games = (file) => parsePgn(decodeText(readFileSync(join(ROOT, FIX, file)))).map((g) => replay(g));

test('每步响哪声：吃子 capture，否则 move（将军不另配声）', () => {
  assert.equal(stepSound({ capture: 'p', check: false }), 'capture');
  assert.equal(stepSound({ capture: null, check: true }), 'move');
  assert.equal(stepSound({ capture: 'n', check: true }), 'capture');
  // 样例里真有吃子：国际象棋 7. Nxe5、象棋第 7 步炮吃卒
  assert.equal(stepSound(games('chess-sample.pgn')[0].steps[12]), 'capture');
  assert.equal(stepSound(games('xq-sample.pgn')[0].steps[6]), 'capture');
});

test('音量：三种声音的增益照方案的量级——吃子比落子响、终局最响；vol 是整体倍数', () => {
  assert.deepEqual(Object.keys(SOUNDS).sort(), ['capture', 'end', 'move']);
  assert.ok(Math.abs(linear('move') - 10 ** (1.7 / 20)) < 1e-12);
  assert.ok(Math.abs(linear('capture', 0.5) - 0.5 * 10 ** (-7.9 / 20)) < 1e-12);
  // 原始单声响度 −32.7 / −20.6 / −25.2 LUFS 加上增益：吃子比落子高 2–3 dB，终局比吃子再高 3–6 dB
  const loud = { move: -32.7 + SOUNDS.move.gain, capture: -20.6 + SOUNDS.capture.gain, end: -25.2 + SOUNDS.end.gain };
  const d1 = loud.capture - loud.move, d2 = loud.end - loud.capture;
  assert.ok(d1 >= 2 && d1 <= 3, `吃子比落子高 ${d1} dB`);
  assert.ok(d2 >= 3 && d2 <= 6, `终局比吃子高 ${d2} dB`);
  assert.ok(Math.abs(-12.2 + SOUNDS.move.gain + 10) <= 1, '落子峰值约 −10 dBFS');
});

test('网址参数：默认静音，sound=1 打开；vol 不合法时为 1', () => {
  const o = (q) => soundOptions(new URLSearchParams(q));
  assert.deepEqual(o(''), { on: false, vol: 1 });
  assert.deepEqual(o('sound=1&vol=0.5'), { on: true, vol: 0.5 });
  assert.deepEqual(o('sound=0&vol=2'), { on: false, vol: 2 });
  for (const v of ['0', '-1', 'x', '']) assert.equal(o(`vol=${v}`).vol, 1, v);
});

// ---------------------------------------------------------------- 浏览器
let pw = null;
try { pw = await import('playwright-core'); } catch { /* 没装开发依赖 */ }
let browser = null, skip = pw ? false : '没有 playwright-core（cd viewer && npm ci）';
if (pw) {
  try {
    browser = await pw.chromium.launch({
      executablePath: resolveChromium(undefined, pw), args: ['--autoplay-policy=no-user-gesture-required'],
    });
  } catch (e) { skip = `起不来浏览器：${e.message.split('\n')[0]}`; }
}

// 在页面脚本之前装好探针：记下每次放声（buffer 时长 → 哪声，延迟几秒）和解码好了几个声音文件。
const SPY = () => {
  window.__rings = [];
  window.__decoded = 0;
  const start = AudioBufferSourceNode.prototype.start;
  AudioBufferSourceNode.prototype.start = function (when = 0, ...rest) {
    window.__rings.push({ dur: this.buffer.duration, delay: when - this.context.currentTime });
    return start.call(this, when, ...rest);
  };
  const decode = BaseAudioContext.prototype.decodeAudioData;
  BaseAudioContext.prototype.decodeAudioData = function (...a) {
    return decode.apply(this, a).then((b) => { window.__decoded++; return b; });
  };
};

async function withPage(query, fn) {
  const server = await serve(ROOT);
  const page = await browser.newPage({ viewport: { width: 540, height: 720 } });
  const errors = [], fetched = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'warning' || m.type() === 'error') errors.push(m.text()); });
  page.on('request', (r) => { if (r.url().includes('/vendor/sounds/')) fetched.push(r.url().split('/').pop()); });
  await page.addInitScript(SPY);
  try {
    await page.goto(`http://127.0.0.1:${server.port}/viewer/?${query}`);
    await page.evaluate(() => window.viewer.ready);
    await fn(page, fetched);
    assert.deepEqual(errors, []);
  } finally {
    await page.close();
    await server.close();
  }
}

// 页面里放出来的各声按 buffer 时长认回名字（三个文件约 0.11 / 0.24 / 0.61 秒）。
const nameOf = (dur) => (dur < 0.17 ? 'move' : dur < 0.4 ? 'capture' : 'end');
const expectSounds = (reps) => reps.flatMap((r) => r.steps.map(stepSound));

test('录制模式：next() 的 sound 逐格对得上棋谱的吃子，结果格 end，其余 null；页面自己不出声', { skip }, async () => {
  const reps = [...games('chess-sample.pgn'), ...games('xq-sample.pgn')];
  await withPage(`rec=1&sound=1&files=${FIX}chess-sample.pgn,${FIX}xq-sample.pgn`, async (page, fetched) => {
    const cells = await page.evaluate(async () => {
      const out = [];
      for (let i = 0; i < 1000; i++) { const r = await window.viewer.next(); out.push([r.kind, r.sound]); if (r.kind === 'end') break; }
      return out;
    });
    const want = reps.flatMap((r) => [['move', null], ...r.steps.map((s) => ['move', stepSound(s)]), ['result', 'end']]);
    want.push(['end', null]);
    assert.deepEqual(cells, want);
    assert.ok(cells.some(([, s]) => s === 'capture'));
    assert.deepEqual(fetched, []);                                   // 录制时声音由脚本混，页面不读声音文件
    assert.equal(await page.evaluate(() => window.__rings.length), 0);
  });
});

test('看棋谱：默认不读声音文件、不出声', { skip }, async () => {
  await withPage(`layout=compact&gap=0.05&anim=0.02&files=${FIX}xq-sample.pgn`, async (page, fetched) => {
    await page.evaluate(async () => {
      window.viewer.play();
      while (!window.viewer.done) await new Promise((ok) => setTimeout(ok, 50));
    });
    assert.deepEqual(fetched, []);
    assert.equal(await page.evaluate(() => window.__rings.length), 0);
  });
});

test('sound=1：自动播放每步响对的声、延迟等于 anim，最后终局声；手工往前一步也响', { skip }, async () => {
  const reps = games('xq-sample.pgn');
  await withPage(`layout=compact&sound=1&vol=0.5&gap=0.06&anim=0.04&files=${FIX}xq-sample.pgn`, async (page, fetched) => {
    await page.waitForFunction(() => window.__decoded === 3);
    assert.deepEqual(fetched.sort(), ['capture.mp3', 'end.mp3', 'move.mp3']);
    const rings = await page.evaluate(async () => {
      window.viewer.play();
      while (!window.viewer.done) await new Promise((ok) => setTimeout(ok, 50));
      return window.__rings;
    });
    assert.deepEqual(rings.map((r) => nameOf(r.dur)), [...expectSounds(reps), 'end']);
    const steps = rings.slice(0, -1);
    assert.ok(steps.every((r) => Math.abs(r.delay - 0.04) < 0.01), `走子声的延迟：${steps.map((r) => r.delay.toFixed(3))}`);
    assert.ok(Math.abs(rings.at(-1).delay) < 0.01);                  // 终局声在横幅出现时立刻响
    // 手工：回到开头（不响），往前两步各响一声，第 7 步（炮吃卒）是吃子声
    await page.evaluate(() => { window.__rings = []; });
    await page.keyboard.press('Home');
    for (let i = 0; i < 7; i++) await page.keyboard.press('ArrowRight');
    await page.waitForFunction(() => window.__rings.length >= 7);
    assert.deepEqual((await page.evaluate(() => window.__rings)).map((r) => nameOf(r.dur)), expectSounds(reps).slice(0, 7));
  });
});

after(() => browser?.close());
