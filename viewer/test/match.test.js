import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { decodeText, moveNote, parsePgn } from '../lib/pgn.js';
import { cleanReason, fmtTokens, playerOf, resultText, scoresBefore, startMoveNumber, thinkTotals, totals } from '../lib/match.js';

test('棋手显示名：模型取冒号后小写并带深度，引擎照原名', () => {
  const g = { tags: { Red: 'claude:Opus', Black: 'engine:fsf:nodes=100', RedEffort: 'XHigh' } };
  assert.deepEqual(playerOf(g, 'w'), { name: 'opus', effort: 'xhigh', key: 'opus+XHigh' });
  assert.equal(playerOf(g, 'b').name, 'engine:fsf:nodes=100');
  assert.equal(playerOf({ tags: { White: 'codex:astra', WhiteEffort: 'max' } }, 'w').name, 'astra');
});

test('token 写法', () => {
  assert.deepEqual([0, 999, 1000, 3449, 9949, 9950, 38400, 999499, 999500, 1234567].map(fmtTokens),
    ['0', '999', '1k', '3.4k', '9.9k', '10k', '38k', '999k', '1M', '1.2M']);
});

test('累计思考 token 按半回合', () => {
  const notes = ['[%think 10]', '[%think 5]', '', '[%think 7]'].map((c) => moveNote({ comments: [c] }));
  const { think, has } = thinkTotals(notes);
  assert.deepEqual(think.w, [0, 10, 10, 10, 10]);
  assert.deepEqual(think.b, [0, 0, 5, 5, 12]);
  assert.deepEqual(has, { w: true, b: true });
});

test('版式极限造局：比分、回合数、结果文字', () => {
  const games = parsePgn(decodeText(readFileSync(new URL('./fixtures/layout-extreme-chess.pgn', import.meta.url))));
  assert.equal(games.length, 12);
  const last = games[10];
  const s = scoresBefore(games, 10);
  assert.equal(s['deepseek-v4-pro+xhigh'], 10);
  assert.equal(startMoveNumber(last), 121);
  assert.equal(resultText(last, false), '和棋 · 满 200 个半回合，判和');
});

test('结束原因去括注', () => {
  assert.equal(cleanReason('满 200 个半回合（研究设的上限），判和'), '满 200 个半回合，判和');
  assert.equal(cleanReason('将死'), '将死');
  assert.equal(cleanReason('超时 (by rule) 判负'), '超时判负');
  assert.equal(cleanReason(undefined), '');
});

test('总比分：按人累计、高分在前', () => {
  const E = { 'claude:opus': 'xhigh', 'codex:astra': 'max' };
  const g = (w, b, r) => ({ tags: { White: w, Black: b, WhiteEffort: E[w], BlackEffort: E[b] }, result: r });
  const t = totals([g('claude:opus', 'codex:astra', '0-1'), g('codex:astra', 'claude:opus', '1/2-1/2')]);
  assert.deepEqual(t.map((p) => [p.name, p.score]), [['astra', 1.5], ['opus', 0.5]]);
});
