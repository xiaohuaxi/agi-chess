import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parsePgn } from '../lib/pgn.js';
import { replay } from '../lib/replay.js';
import { START_FEN, inCheck, makeMove, parseFen, parseMove, toFen } from '../lib/xiangqi.js';

const fixture = (name) => new URL('./fixtures/' + name, import.meta.url);
const readJson = (name) => JSON.parse(readFileSync(fixture(name), 'utf8'));

test('FEN 往返', () => {
  assert.equal(toFen(parseFen(START_FEN)), START_FEN.split(' ').slice(0, 2).join(' '));
  assert.equal(toFen(parseFen('rheakaehr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RHEAKAEHR b')),
    'rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR b');
});

// 导出端（pgn_move）写出的每个局面的全部合法着法 → 解析回同一坐标；走完的将军与 pyffish 一致
test('记谱往返：多路兵、同线多子、仕相同线、随机局面', () => {
  const data = readJson('xq-roundtrip.json');
  let n = 0, checks = 0;
  for (const { fen, moves } of data) {
    const pos = parseFen(fen);
    for (const [iccs, text, check] of moves) {
      const mv = parseMove(pos, text);
      assert.equal(mv.iccs, iccs, `${fen} ${text}`);
      n++;
      if (check === null) continue;               // 造的局面本身不合法（对方已被将），只测记谱
      const after = makeMove(pos, iccs);
      assert.equal(inCheck(after, after.turn), check, `${fen} ${iccs} 将军`);
      checks += check;
    }
  }
  assert.ok(n > 3000 && checks > 50, `${n} 步，${checks} 步将军`);
});

test('容错：繁体、半角数字、汉字与全角数字混用', () => {
  const pos = parseFen(START_FEN);
  for (const t of ['炮二平五', '砲二平五', '炮2平5', '炮２平５']) assert.equal(parseMove(pos, t).iccs, 'h2e2', t);
  assert.equal(parseMove(pos, '傌二進三').iccs, 'h0g2');
  assert.equal(parseMove(pos, '俥一進一').iccs, 'i0i1');
  assert.equal(parseMove(pos, '帥五進一').iccs, 'e0e1');
  const black = makeMove(pos, 'h2e2');
  for (const t of ['马８进７', '馬8進7', '马八进七']) assert.equal(parseMove(black, t).iccs, 'h9g7', t);
  assert.equal(parseMove(black, '包２平５').iccs, 'b7e7');
  // 同线两车，繁体「後」
  const rr = parseFen('3k5/9/9/9/9/R8/9/9/9/R3K4 w');
  assert.equal(parseMove(rr, '後車平八').iccs, 'a0b0');
  assert.equal(parseMove(rr, '前车进一').iccs, 'a4a5');
});

test('认不出或有歧义时报错', () => {
  const pos = parseFen(START_FEN);
  for (const t of ['炮二平', 'h2e2', '车二进一', '兵五退一', '前炮平五', '马二平三']) {
    assert.throws(() => parseMove(pos, t), Error, t);
  }
  // 同线两车不写前后
  assert.throws(() => parseMove(parseFen('3k5/9/9/9/9/R8/9/9/9/R3K4 w'), '车九进一'), /歧义/);
});

test('将军：车、炮（炮架）、马（马腿）、兵、照面', () => {
  const chk = (fen) => { const p = parseFen(fen); return inCheck(p, p.turn); };
  assert.equal(chk('4k4/9/9/9/9/9/9/9/9/4R1K2 b'), true);            // 车
  assert.equal(chk('4k4/9/9/9/4p4/9/9/9/9/4R1K2 b'), false);         // 车被挡
  assert.equal(chk('4k4/9/9/9/4p4/9/9/9/9/4C1K2 b'), true);          // 炮有架
  assert.equal(chk('4k4/9/9/9/9/9/9/9/9/4C1K2 b'), false);           // 炮无架
  assert.equal(chk('4k4/9/5N3/9/9/9/9/9/9/6K2 b'), true);            // 马 f7 将 e9
  assert.equal(chk('4k4/5p3/5N3/9/9/9/9/9/9/6K2 b'), false);         // 马腿 f8 被塞
  assert.equal(chk('4k4/4P4/9/9/9/9/9/9/9/6K2 b'), true);            // 兵正面
  assert.equal(chk('3Pk4/9/9/9/9/9/9/9/9/6K2 b'), true);             // 兵侧面
  assert.equal(chk('4k4/9/9/9/9/9/9/9/9/4K4 b'), true);              // 照面
  assert.equal(chk('4k4/9/9/9/9/9/9/9/4p4/4K4 w'), true);            // 黑卒将红帅
  assert.equal(chk('4k4/9/9/9/9/9/9/9/9/3pK4 w'), true);
  assert.equal(chk('4k4/4p4/9/9/9/9/9/9/9/4K4 w'), false);           // 卒不能后退吃
});

// 本机对局截的一盘（runs/b3max-xq/fsf-nodes100-s2-w），逐步坐标与将军同 game.jsonl
test('象棋样例整盘走完', () => {
  const [g] = parsePgn(readFileSync(fixture('xq-sample.pgn'), 'utf8'));
  const exp = readJson('xq-sample.json');
  const r = replay(g);
  assert.equal(r.kind, 'xiangqi');
  assert.equal(r.error, null);
  assert.deepEqual(r.steps.map((s) => [s.move, s.check]), exp.moves);
  assert.equal(g.tags.RedEffort, 'max');
  assert.equal(g.result, '1-0');
});

test('国际象棋样例整盘走完', () => {
  const [g] = parsePgn(readFileSync(fixture('chess-sample.pgn'), 'utf8'));
  const exp = readJson('chess-sample.json');
  const r = replay(g);
  assert.equal(r.kind, 'chess');
  assert.equal(r.error, null);
  assert.deepEqual(r.steps.map((s) => [s.move, s.check]), exp.moves);
  assert.ok(r.steps.at(-1).san.endsWith('#'));
});

test('国际象棋走不下去时停在那步并给原因', () => {
  const [g] = parsePgn('1. e4 e5 2. Ke3 *');
  const r = replay(g);
  assert.equal(r.steps.length, 2);
  assert.equal(r.error.ply, 3);
});
