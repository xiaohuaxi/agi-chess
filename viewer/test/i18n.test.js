// 英文界面（docs/viewer.md「英文界面」）：lib/i18n.js 的对照表、结束原因与显示名覆盖，象棋 WXF 记法，
// 加上无头浏览器里 lang=en 的画面上没有中文（象棋棋子的汉字和棋谱里的理由文字除外）、默认仍是中文、names= 生效。
// 浏览器部分要 viewer/node_modules 里的 playwright-core 和它配套的 Chromium（或 VIEWER_CHROMIUM），没有就跳过。
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TEXT, hasCjk, langOf, parseNames, reasonEn } from '../lib/i18n.js';
import { cleanReason, fullName, playerOf, resultText, totals } from '../lib/match.js';
import { fmtSeconds, moveRows, nagLabel, noteItems } from '../lib/panel.js';
import { moveNote, parsePgn, decodeText } from '../lib/pgn.js';
import { replay } from '../lib/replay.js';
import { START_FEN, digit, makeMove, parseFen, sqXY, wxfMove } from '../lib/xiangqi.js';
import { parseCli } from '../record.mjs';
import { resolveChromium, serve } from '../serve.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FIX = '/viewer/test/fixtures/';

// 对照表里的一项（字符串、函数、数组、对象）展开成所有会显示的字符串；函数用造的参数调一次。
function strings(v) {
  if (typeof v === 'string') return [v];
  if (typeof v === 'function') return [v(2, 4, 'opus', 'astra')];
  if (Array.isArray(v)) return v.flatMap(strings);
  if (v && typeof v === 'object') return Object.values(v).flatMap(strings);
  return [];
}

function shape(v) {
  if (Array.isArray(v)) return v.map(shape);
  if (typeof v === 'function') return 'fn';
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, shape(x)]));
  return typeof v;
}

test('对照表：中英两份键一一对应，英文里没有中文，中文是原来的写法', () => {
  assert.deepEqual(shape(TEXT.en), shape(TEXT.zh));
  for (const [k, v] of Object.entries(TEXT.en)) {
    for (const s of strings(v)) assert.equal(hasCjk(s), false, `${k}：${s}`);
  }
  const z = TEXT.zh;
  assert.equal(z.gameOf(2, 4), '第 2 局 · 共 4 局');
  assert.equal(z.finalScore(4), '总比分 · 共 4 局');
  assert.deepEqual([z.won, z.check, z.thinking, z.vs], ['胜', '将军', '思考', '对']);
  const e = TEXT.en;
  assert.equal(e.gameOf(2, 4), 'Game 2 of 4');
  assert.equal(e.finalScore(4), 'Final score · 4 games');
});

test('语言参数：lang=en 英文，其余（不给、写错）都是中文', () => {
  const q = (s) => langOf(new URLSearchParams(s));
  assert.deepEqual([q(''), q('lang=en'), q('lang=EN'), q('lang=fr'), q('lang=')], ['zh', 'en', 'en', 'zh', 'zh']);
});

test('结束原因：导出端写的每一种都有英文，认不出的中文不显示，英文照原样', () => {
  const cases = {
    '将死': 'Checkmate', '困毙': 'Stalemate', '逼和，判和': 'Stalemate', '双方子力都不足以将死，判和': 'Insufficient material',
    '七十五回合没有吃子和兵的走动，判和': '75-move rule', '同一局面出现五次，判和': 'Fivefold repetition',
    '同一局面出现三次，程序替棋手申诉，判和': 'Threefold repetition', '五十回合没有吃子和兵的走动，程序替棋手申诉，判和': '50-move rule',
    '一百个半回合没有吃子，判和': 'No capture in 100 plies', '长将，判负': 'Perpetual check', '长捉，判负': 'Perpetual chase',
    '满 200 个半回合（研究设的上限），判和': 'Move limit (200 plies)', '红方连续 3 次给出非法着法，判负': '3 illegal moves in a row',
    '白方连续 4 次给出非法着法，判负': '4 illegal moves in a row',
  };
  for (const [zh, en] of Object.entries(cases)) assert.equal(reasonEn(zh), en, zh);
  assert.equal(reasonEn('超时判负'), '');
  assert.equal(reasonEn('Time forfeit'), 'Time forfeit');
  assert.equal(reasonEn(undefined), '');
  // 默认（中文）照旧去括注
  assert.equal(cleanReason('满 200 个半回合（研究设的上限），判和'), '满 200 个半回合，判和');
  assert.equal(cleanReason('满 200 个半回合（研究设的上限），判和', 'en'), 'Move limit (200 plies)');
  const g = (r, why) => ({ tags: { Red: 'claude:opus', Result: r, Termination: why } });
  assert.equal(resultText(g('1-0', '将死'), true), '红方胜 · 将死');
  assert.equal(resultText(g('1-0', '将死'), true, 'en'), 'Red wins · Checkmate');
  assert.equal(resultText(g('1-0', '将死'), false, 'en'), 'White wins · Checkmate');
  assert.equal(resultText(g('0-1', '超时判负'), false, 'en'), 'Black wins');
  assert.equal(resultText(g('1/2-1/2', '逼和，判和'), false, 'en'), 'Draw · Stalemate');
});

test('宽版标签：标注、用时、评注数字有英文，默认仍是中文', () => {
  assert.equal(nagLabel(4), '?? 大错');
  assert.deepEqual([1, 2, 3, 4, 5, 6, 10].map((n) => nagLabel(n, 'en')),
    ['! Good move', '? Mistake', '!! Brilliant move', '?? Blunder', '!? Interesting move', '?! Dubious move', '$10']);
  assert.deepEqual([5, 76, 3723.25].map((s) => fmtSeconds(s, 'en')), ['5s', '1m 16s', '1h 2m 3.3s']);
  assert.equal(fmtSeconds(76), '1 分 16 秒');
  const n = moveNote({ comments: ['[%emt 0:01:02] [%think 12345] [%illegal 2] [%dropped 0] 理由'] });
  assert.deepEqual(noteItems(n, 'en').map((x) => [x.label, x.value]),
    [['Time', '1m 2s'], ['Thinking tokens', '12,345'], ['Illegal retries', '2'], ['Thinking dropped', '0']]);
  assert.deepEqual(noteItems(n).map((x) => x.label), ['用时', '思考 token', '非法重选', '去掉的思考段']);
});

test('显示名覆盖：按原名或简称、不分大小写；比分仍按原名归属；标题全称不再补厂商', () => {
  const names = parseNames('claude:opus=Claude Opus 4.x, ASTRA = GPT-5 astra ,bad,=x,y=');
  assert.deepEqual([...names], [['claude:opus', 'Claude Opus 4.x'], ['astra', 'GPT-5 astra']]);
  const g = { tags: { White: 'claude:opus', Black: 'codex:astra', WhiteEffort: 'max', BlackEffort: 'max' }, result: '0-1' };
  assert.deepEqual(playerOf(g, 'w', names), { name: 'Claude Opus 4.x', effort: 'max', key: 'opus+max' });
  assert.deepEqual(playerOf(g, 'b', names), { name: 'GPT-5 astra', effort: 'max', key: 'astra+max' });
  assert.deepEqual(playerOf(g, 'w'), { name: 'opus', effort: 'max', key: 'opus+max' });            // 不给就不变
  assert.deepEqual(fullName(g, 'w', true, names), { name: 'Claude Opus 4.x', effort: 'max' });
  assert.deepEqual(fullName(g, 'w', true), { name: 'Claude opus', effort: 'max' });
  assert.deepEqual(fullName({ tags: { White: 'engine:x' } }, 'w', true, names), { name: 'engine:x', effort: '' });
  const swap = { tags: { White: 'codex:astra', Black: 'claude:opus', WhiteEffort: 'max', BlackEffort: 'max' }, result: '1/2-1/2' };
  assert.deepEqual(totals([g, swap], names).map((p) => [p.name, p.score]), [['GPT-5 astra', 1.5], ['Claude Opus 4.x', 0.5]]);
  assert.equal(parseNames(null).size, 0);
});

// ---------------------------------------------------------------- WXF
// 测试这边照字面把导出端写的中文记谱换成 WXF（只换字，前后中 / 编号看这条线上有几个同种子），和从坐标算的逐步对上。
const LET = { 车: 'R', 马: 'H', 炮: 'C', 相: 'E', 象: 'E', 仕: 'A', 士: 'A', 帅: 'K', 将: 'K', 兵: 'P', 卒: 'P' };
const OPS = { 进: '+', 退: '-', 平: '.' };
function translit(pos, iccs, text) {
  const cs = Array.from(text);
  let head;
  if (LET[cs[0]]) head = LET[cs[0]] + digit(cs[1]);
  else {
    const [x, y] = sqXY(iccs.slice(0, 2)), p = pos.board[y * 9 + x];
    const onFile = pos.board.filter((q, i) => q === p && i % 9 === x).length;
    const at = '一二三四五'.indexOf(cs[0]);
    head = LET[cs[1]] + (at >= 0 ? 'abcde'[at] : onFile === 2 ? { 前: '+', 后: '-' }[cs[0]] : { 前: 'a', 中: 'b', 后: 'c' }[cs[0]]);
  }
  return head + OPS[cs[2]] + digit(cs[3]);
}

test('WXF：导出端每个局面的全部合法着法逐字对上、互不相同', () => {
  const data = JSON.parse(readFileSync(new URL('./fixtures/xq-roundtrip.json', import.meta.url), 'utf8'));
  let n = 0, tandem = 0;
  for (const { fen, moves } of data) {
    const pos = parseFen(fen), seen = new Set();
    for (const [iccs, text] of moves) {
      const w = wxfMove(pos, iccs);
      assert.equal(w, translit(pos, iccs, text), `${fen} ${iccs} ${text}`);
      assert.ok(!seen.has(w), `${fen} 重复 ${w}`);
      seen.add(w);
      n++;
      tandem += !LET[Array.from(text)[0]];
    }
  }
  assert.ok(n > 3000 && tandem > 300, `${n} 步，其中前后中 / 编号 ${tandem} 步`);
});

test('WXF：常见写法与同线多子', () => {
  const pos = parseFen(START_FEN);
  assert.deepEqual(['h2e2', 'h0g2', 'i0i1', 'e0e1', 'd0e1', 'c0e2'].map((m) => wxfMove(pos, m)),
    ['C2.5', 'H2+3', 'R1+1', 'K5+1', 'A6+5', 'E7+5']);
  const b = makeMove(pos, 'h2e2');
  assert.deepEqual(['h9g7', 'b7e7', 'h7h0'].map((m) => wxfMove(b, m)), ['H8+7', 'C2.5', 'C8+7']);
  const rr = parseFen('3k5/9/9/9/9/R8/9/9/9/R3K4 w');           // 同线两车：前 +、后 -
  assert.deepEqual([wxfMove(rr, 'a4a5'), wxfMove(rr, 'a0b0')], ['R++1', 'R-.8']);
  const cc = parseFen('4k4/9/1c7/1c7/9/9/9/9/9/4K4 b');          // 黑方同线两炮
  assert.deepEqual([wxfMove(cc, 'b6b5'), wxfMove(cc, 'b7a7')], ['C++1', 'C-.1']);
  const p3 = parseFen('3k5/9/9/4P4/4P4/4P4/9/9/9/3K5 w');        // 同线三兵：从前往后 a b c
  assert.deepEqual([wxfMove(p3, 'e6e7'), wxfMove(p3, 'e5d5')], ['Pa+1', 'Pb.6']);
  // xqbase 例局：四线、六线各两兵一起编号（四线前兵 a … 六线后兵 d），五线单兵照常写
  const pp = parseFen('4k4/9/9/3PPP3/3P1P3/9/9/9/9/4K4 w');
  assert.deepEqual(['f6f7', 'f5g5', 'd6d7', 'd5c5', 'e6e7'].map((m) => wxfMove(pp, m)), ['Pa+1', 'Pb.3', 'Pc+1', 'Pd.7', 'P5+1']);
});

test('WXF：样例棋谱逐步算出，着法列表英文时换成 WXF', () => {
  const [g] = parsePgn(decodeText(readFileSync(new URL('./fixtures/xq-sample.pgn', import.meta.url))));
  const rep = replay(g);
  assert.ok(rep.steps.every((s) => /^[KAEHRCP][1-9+\-a-e][+\-.][1-9]$/.test(s.wxf)), rep.steps.map((s) => s.wxf).join(' '));
  assert.equal(rep.steps[0].wxf, 'H8+7');                                   // 马八进七
  const rows = moveRows(rep.steps, g.moves, 'w', 1, true, true);
  assert.equal(rows[0].w.text, 'H8+7');
  assert.equal(moveRows(rep.steps, g.moves, 'w', 1, true)[0].w.text, '马八进七');
});

test('录制脚本：--set lang=en 与 names= 原样透传', () => {
  const o = parseCli(['a', '-o', 'x.mp4', '--set', 'lang=en', '--set', 'names=claude:opus=Claude Opus,codex:astra=GPT astra']);
  assert.deepEqual(o.params, { lang: 'en', names: 'claude:opus=Claude Opus,codex:astra=GPT astra' });
});

// ---------------------------------------------------------------- 浏览器
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

// 画面上看得见的文字（象棋棋子上的字、棋盘边的路数——全角数字，另有一条专门核对——、宽版评注里的理由与原样列出的命令除外），
// 连同按钮提示、下拉框选项、页面标题。
const visible = (page) => page.evaluate(() => {
  const out = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const e = n.parentElement;
    if (!n.textContent.trim() || !e || e.closest('.xq-piece, .xq-file, #s-note .why, #s-note .raw, option, script')) continue;
    if (!e.getClientRects().length) continue;
    out.push(n.textContent.trim());
  }
  for (const e of document.querySelectorAll('[title], option')) out.push(e.title || e.textContent);
  out.push(document.title);
  return out;
});
const noCjk = (texts, where) => assert.deepEqual(texts.filter((t) => /[　-〿㐀-鿿＀-￯]/.test(t)), [], where);

const NARROW = { width: 540, height: 720 }, WIDE = { width: 1440, height: 900 };
const BOTH = `files=${FIX}chess-sample.pgn,${FIX}xq-sample.pgn`;

test('英文界面：窄版各格画面（中局、将军、终局横幅、总比分、标题画面）没有中文', { skip }, async () => {
  for (const q of [`${BOTH}&game=1&ply=12`, `${BOTH}&game=1&ply=end`, `${BOTH}&game=2&ply=7`, `${BOTH}&game=2&ply=end`,
    `${BOTH}&summary=1`, `files=${FIX}layout-extreme-chess.pgn&game=11&ply=end`, `files=${FIX}layout-extreme-xq.pgn&game=11&ply=end`]) {
    await withPage(`layout=compact&lang=en&${q}`, NARROW, async (page) => {
      noCjk(await visible(page), q);
      assert.equal(await page.evaluate(() => document.documentElement.lang), 'en');
    });
  }
  await withPage(`layout=compact&lang=en&${BOTH}&game=2&ply=end`, NARROW, async (page) => {
    assert.deepEqual(await page.evaluate(() => [document.getElementById('strip').textContent,
      document.querySelector('#banner .b-head').textContent]), ['Game 2 of 2', 'Red wins · Checkmate']);
    // 象棋棋盘：红方路数换成数字，河界不画；棋子还是汉字
    assert.equal(await page.evaluate(() => document.querySelectorAll('.xq-river').length), 0);
    assert.equal(await page.evaluate(() => [...document.querySelectorAll('.xq-file')].map((e) => e.textContent).join('')),
      '１９２８３７４６５５６４７３８２９１');   // 每路上下各一个：黑方 1–9、红方 9–1
    assert.ok(await page.evaluate(() => [...document.querySelectorAll('.xq-glyph')].some((e) => e.textContent === '帥')));
  });
  // 录制模式：标题画面（每盘开头）、走子格的着法文字
  await withPage(`rec=1&title=1&lang=en&${BOTH}`, NARROW, async (page) => {
    assert.equal((await page.evaluate(() => window.viewer.next())).kind, 'title');
    noCjk(await visible(page), 'title');
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('#title > div')].map((e) => e.textContent)),
      ['Game 1 of 2', 'Claude opus+high', 'vs', 'engine:maia-1100']);
  });
});

test('英文界面：宽版右栏的标签、按钮、快捷键、下拉框没有中文；象棋着法写 WXF', { skip }, async () => {
  for (const q of [`${BOTH}&game=1&ply=12`, `${BOTH}&game=2&ply=end`, `${BOTH}&game=2&ply=0`]) {
    await withPage(`layout=wide&lang=en&${q}`, WIDE, async (page) => noCjk(await visible(page), q));
  }
  await withPage(`layout=wide&lang=en&${BOTH}&game=2&ply=1`, WIDE, async (page) => {
    const x = await page.evaluate(() => ({
      head: document.querySelector('#s-note .n-head').firstChild.textContent,
      first: document.querySelector('#s-moves [data-ply="1"]').textContent,
      bar: document.querySelector('#bar-bottom .mv').textContent,
      play: document.getElementById('s-play').textContent,
    }));
    assert.deepEqual(x, { head: '1. H8+7', first: 'H8+7', bar: '1. H8+7', play: 'Play' });
  });
});

test('默认（不给 lang）仍是中文界面；names= 覆盖棋手条、横幅、标题画面与总比分', { skip }, async () => {
  await withPage(`layout=compact&${BOTH}&game=2&ply=end`, NARROW, async (page) => {
    assert.deepEqual(await page.evaluate(() => [document.documentElement.lang, document.title, document.getElementById('strip').textContent,
      document.querySelector('#banner .b-head').textContent, document.getElementById('s-play').textContent]),
    ['zh-CN', '棋谱阅读器', '第 2 局 · 共 2 局', '红方胜 · 将死', '播放']);
    assert.match(await page.evaluate(() => document.querySelector('#bar-bottom .mv').textContent), /^\d+\. [一-鿿]/);   // 中文记谱
    assert.equal(await page.evaluate(() => document.querySelectorAll('.xq-river').length), 4);
  });
  const names = encodeURIComponent('claude:opus=Claude Opus 4.x,engine:maia-1100=Maia 1100');
  await withPage(`rec=1&title=1&lang=en&names=${names}&${BOTH}`, NARROW, async (page) => {
    await page.evaluate(() => window.viewer.next());
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('#title .t-row .name')].map((e) => e.textContent)),
      ['Claude Opus 4.x', 'Maia 1100']);
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('.bar .name')].map((e) => e.textContent)),
      ['Maia 1100', 'Claude Opus 4.x']);
    let r;
    do r = await page.evaluate(() => window.viewer.next()); while (r.kind !== 'result');
    assert.equal(await page.evaluate(() => document.querySelector('#banner .b-name .name').textContent), 'Claude Opus 4.x');
    do r = await page.evaluate(() => window.viewer.next()); while (r.kind !== 'end');
    const rows = await page.evaluate(() => [...document.querySelectorAll('#summary .s-row')].map((e) => e.textContent));
    assert.ok(rows.includes('Claude Opus 4.x+high1') && rows.includes('Maia 11000'), rows.join(' | '));
  });
});

after(() => browser?.close());
