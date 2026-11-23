import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { decodeText, moveNote, parsePgn } from '../lib/pgn.js';
import { cleanReason, displayName, displayPlayer, fmtTokens, fullName, playerOf, resultText, scoresBefore, startMoveNumber, thinkTotals, totals } from '../lib/match.js';

test('棋手显示名：模型取冒号后小写并带深度，引擎照原名', () => {
  const g = { tags: { Red: 'claude:Opus', Black: 'engine:fsf:nodes=100', RedEffort: 'XHigh' } };
  assert.deepEqual(playerOf(g, 'w'), { name: 'opus', effort: 'xhigh', key: 'opus+XHigh' });
  assert.equal(playerOf(g, 'b').name, 'engine:fsf:nodes=100');
  assert.equal(playerOf({ tags: { White: 'codex:astra', WhiteEffort: 'max' } }, 'w').name, 'astra');
  const agyGame = { tags: { White: 'agy:gemini-4-neon', Black: 'agy:claude-opus-5-5', WhiteEffort: 'xhigh', BlackEffort: 'high' } };
  assert.deepEqual(playerOf(agyGame, 'w'), { name: 'gemini-4-neon', effort: 'xhigh', key: 'gemini-4-neon+xhigh' });
  assert.deepEqual(playerOf(agyGame, 'b'), { name: 'claude-opus-5-5', effort: 'high', key: 'claude-opus-5-5+high' });
});

test('标题画面全称：补厂商，认不出的照原名（agy 同时跑多家族模型，不映射固定厂商）', () => {
  const g = { tags: { White: 'codex:astra', Black: 'claude:opus', WhiteEffort: 'max' } };
  assert.deepEqual(fullName(g, 'w'), { name: 'GPT astra', effort: 'max' });
  assert.deepEqual(fullName(g, 'b'), { name: 'Claude opus', effort: '' });
  assert.equal(fullName({ tags: { Red: 'engine:fsf:nodes=100' } }, 'w').name, 'engine:fsf:nodes=100');
  assert.deepEqual(fullName(g, 'w', false), { name: 'astra', effort: 'max' });   // vendor=0
  const agyGame = { tags: { White: 'agy:gemini-4-neon', Black: 'agy:claude-opus-5-5', WhiteEffort: 'xhigh', BlackEffort: 'high' } };
  assert.deepEqual(fullName(agyGame, 'w'), { name: 'gemini-4-neon', effort: 'xhigh' });
  assert.deepEqual(fullName(agyGame, 'b'), { name: 'claude-opus-5-5', effort: 'high' });
  // 冒号后模型名本身已带厂商前缀时不再重复拼接（消除 GPT gpt-6.2-astra / Gemini gemini-4-argon-high）
  const dupGame = { tags: { White: 'codex:gpt-6.2-astra', Black: 'gemini:gemini-4-argon-high', WhiteEffort: 'max', BlackEffort: 'high' } };
  assert.deepEqual(fullName(dupGame, 'w'), { name: 'gpt-6.2-astra', effort: 'max' });
  assert.deepEqual(fullName(dupGame, 'b'), { name: 'gemini-4-argon-high', effort: 'high' });
  assert.deepEqual(playerOf(dupGame, 'w'), { name: 'gpt-6.2-astra', effort: 'max', key: 'gpt-6.2-astra+max' });
  const flashGame = { tags: { Red: 'gemini:gemini-3.8-flash-high', RedEffort: 'high' } };
  assert.deepEqual(fullName(flashGame, 'w'), { name: 'gemini-3.8-flash-high', effort: 'high' });
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
  const td = totals([g('claude:opus', 'codex:astra', '0-1'), g('codex:astra', 'claude:opus', '1/2-1/2')], null, { display: true, lang: 'en' });
  assert.deepEqual(td.map((p) => [p.name, p.score]), [['GPT Astra', 1.5], ['Claude Opus', 0.5]]);
});

test('统一对外显示名 displayName / displayPlayer：规范全仓模型、去重尾档位、agy 不臆断厂商、引擎与随机规范化', () => {
  const cases = [
    ['agy:gemini-4-neon', 'Gemini 4 Neon'],
    ['agy:gemini-4-carbon', 'Gemini 4 Carbon'],
    ['agy:claude-opus-5-5', 'Claude Opus 5.5 (agy)'],
    ['agy:claude-opus-5-5-high', 'Claude Opus 5.5 (agy)'],
    ['gemini:gemini-4-argon-high', 'Gemini 4 Argon'],
    ['gemini:gemini-3.8-flash-high', 'Gemini 3.8 Flash'],
    ['codex:gpt-6.2-astra', 'GPT-6.2 Astra'],
    ['claude:opus', 'Claude Opus'],
    ['codex:astra', 'GPT Astra'],
    ['codex:sol', 'GPT Sol'],
    ['deepseek:deepseek-reasoner', 'DeepSeek Reasoner'],
    ['deepseek:deepseek-v4-pro', 'DeepSeek V4 Pro'],
    ['openrouter:anthropic/claude-opus-5-5', 'Claude Opus 5.5'],
    ['engine:fsf:nodes=100', 'Fairy-Stockfish · nodes=100'],
    ['engine:fsf:depth=6', 'Fairy-Stockfish · depth=6'],
    ['engine:stockfish:elo=1900', 'Stockfish · elo=1900'],
    ['engine:sf:skill=5', 'Stockfish · skill=5'],
    ['engine:maia-1900', 'Maia 1900'],
    ['engine:maia-1100', 'Maia 1100'],
    ['gemini-4-neon', 'Gemini 4 Neon'],
    ['claude-opus-5-5-high', 'Claude Opus 5.5'],
    ['gpt-6.2-astra', 'GPT-6.2 Astra'],
    ['Claude-Dupont', 'Claude-Dupont'],
    ['Claude', 'Claude'],
    ['Gemini-Smith', 'Gemini-Smith'],
    ['GPT-Fan', 'GPT-Fan'],
    ['Grok-Player', 'Grok-Player'],
    ['Stockfish 16', 'Stockfish 16'],
    ['Magnus Carlsen', 'Magnus Carlsen'],
    ['胡荣华', '胡荣华'],
  ];
  for (const [raw, want] of cases) {
    assert.equal(displayName(raw, 'en'), want, raw);
    assert.equal(displayName(raw, 'zh'), want, raw);
  }
  assert.equal(displayName('random', 'en'), 'Random');
  assert.equal(displayName('random', 'zh'), '随机棋手');

  // 绝不修改 playerOf().key 与 effort；剥去重复 -high 后缀后与 effort 拼接不出现 -high +high
  const g = {
    tags: {
      White: 'gemini:gemini-4-argon-high',
      Black: 'agy:claude-opus-5-5-high',
      WhiteEffort: 'high',
      BlackEffort: 'high',
    },
  };
  assert.deepEqual(displayPlayer(g, 'w', { lang: 'en' }), { name: 'Gemini 4 Argon', effort: 'high', key: 'gemini-4-argon-high+high' });
  assert.deepEqual(displayPlayer(g, 'b', { lang: 'en' }), { name: 'Claude Opus 5.5 (agy)', effort: 'high', key: 'claude-opus-5-5-high+high' });
  // 显式 names= 覆盖优先于 displayName
  const names = new Map([['gemini:gemini-4-argon-high', 'Custom Argon']]);
  assert.equal(displayPlayer(g, 'w', { lang: 'en', names }).name, 'Custom Argon');
});
