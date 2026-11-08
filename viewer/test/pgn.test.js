import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodeText, moveNote, parseComment, parsePgn, unwrap, wide } from '../lib/pgn.js';
import { loadGamesWithAnalysis } from '../lib/replay.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

test('标签、着法、评注、结果，一个文件多盘', () => {
  const text = `[Event "a \\"b\\" c"]
[White "x"]

1. e4 {开局} e5 2.Nf3 Nc6 1-0

[Event "second"]
1. d4 d5 *
`;
  const gs = parsePgn(text);
  assert.equal(gs.length, 2);
  assert.equal(gs[0].tags.Event, 'a "b" c');
  assert.deepEqual(gs[0].moves.map((m) => m.text), ['e4', 'e5', 'Nf3', 'Nc6']);
  assert.deepEqual(gs[0].moves[0].comments, ['开局']);
  assert.equal(gs[0].result, '1-0');
  assert.equal(gs[1].tags.Event, 'second');
  assert.deepEqual(gs[1].moves.map((m) => m.text), ['d4', 'd5']);
  assert.equal(gs[1].result, '*');
});

test('没有结果记号时靠下一盘的标签分盘', () => {
  const gs = parsePgn('[Event "a"]\n1. e4 e5\n[Event "b"]\n1. d4\n');
  assert.deepEqual(gs.map((g) => [g.tags.Event, g.moves.length, g.result]), [['a', 2, null], ['b', 1, null]]);
});

test('标注：后缀转 NAG，$n，单独的后缀', () => {
  const [g] = parsePgn('1. e4! e5?? 2. Nf3 $14 Nc6 !? 3. Bb5?! $2 *');
  assert.deepEqual(g.moves.map((m) => [m.text, m.nags]),
    [['e4', [1]], ['e5', [4]], ['Nf3', [14]], ['Nc6', [5]], ['Bb5', [6, 2]]]);
});

test('变着跳过，里面的评注和括号不干扰', () => {
  const [g] = parsePgn('1. e4 (1. d4 {不走) 这个} d5 (1... Nf6)) e5 ; 行尾评注 (\n2. Nf3 *');
  assert.deepEqual(g.moves.map((m) => m.text), ['e4', 'e5', 'Nf3']);
  assert.deepEqual(g.moves[1].comments, ['行尾评注 (']);
});

test('行首 % 转义行跳过；着法前的评注进 pre', () => {
  const [g] = parsePgn('%这行不要\n[Event "x"]\n{开局前} 1. e4 1/2-1/2');
  assert.deepEqual(g.pre, ['开局前']);
  assert.deepEqual(g.moves.map((m) => m.text), ['e4']);
  assert.equal(g.result, '1/2-1/2');
});

test('象棋：评注后的黑方着法带不带「N...」都认', () => {
  const a = parsePgn('1. 炮二平五 {理由} 马８进７ 2. 马二进三 {x} 2... 马２进３ 1-0')[0];
  assert.deepEqual(a.moves.map((m) => m.text), ['炮二平五', '马８进７', '马二进三', '马２进３']);
  const b = parsePgn('1. 炮二平五　马８进７\n2. 马二进三　马２进３ *')[0];   // 全角空格分隔
  assert.deepEqual(b.moves.map((m) => m.text), ['炮二平五', '马８进７', '马二进三', '马２进３']);
});

test('评注断行：两边都是全角字符不补空格，否则补一个', () => {
  assert.equal(unwrap('先出车控制\n肋道'), '先出车控制肋道');
  assert.equal(unwrap('先出车，\n再兑子'), '先出车，再兑子');
  assert.equal(unwrap('马在 e5\n很活跃'), '马在 e5 很活跃');
  assert.equal(unwrap('Nf3\nnext'), 'Nf3 next');
  assert.equal(unwrap('  a \n  b  \n'), 'a b');
  assert.ok(wide('中') && wide('，') && wide('１') && wide('　'));
  assert.ok(!wide('a') && !wide('…') && !wide('—'));
});

test('评注命令：已知的取数，未知的原样保留，剩下是理由', () => {
  const c = parseComment('[%emt 0:01:05] [%think 1631] [%out 1865] [%in 2] [%cacheread 0] [%cachewrite 1810] ' +
    '[%illegal 1] [%flagged 2] [%empty 1] [%dropped 0] [%clk 0:10:00] 红方炮二进四，[%think abc] 有两个威胁');
  assert.deepEqual(c.cmds, { emt: 65, think: 1631, out: 1865, in: 2, cacheread: 0, cachewrite: 1810,
                             illegal: 1, flagged: 2, empty: 1, dropped: 0 });
  assert.deepEqual(c.unknown, ['[%clk 0:10:00]', '[%think abc]']);
  assert.equal(c.text, '红方炮二进四， 有两个威胁');
  assert.deepEqual(parseComment('只有文字'), { cmds: {}, unknown: [], text: '只有文字' });
});

test('评注跨行的命令和中文理由能还原', () => {
  const [g] = parsePgn(`1. 马七进六 { [%emt 0:09:08] [%think 54726]
[%illegal 1] **思路：**黑卒进到 c5，和我的 c4 兵顶头相对。我先走兵七进一吃卒，黑方大概率象5进3
回吃，结果是兵卒相换。所以兑兵是积极又稳妥
的选择。 } *`);
  const n = moveNote(g.moves[0]);
  assert.deepEqual(n.cmds, { emt: 548, think: 54726, illegal: 1 });
  assert.equal(n.text, '**思路：**黑卒进到 c5，和我的 c4 兵顶头相对。我先走兵七进一吃卒，黑方大概率象5进3 回吃，' +
    '结果是兵卒相换。所以兑兵是积极又稳妥的选择。');
});

test('解码：UTF-8 优先，失败回退 gb18030（GBK）', () => {
  const utf8 = new TextEncoder().encode('﻿[Event "炮二平五"]');
  assert.equal(decodeText(utf8), '[Event "炮二平五"]');
  // 「炮二平五」的 GBK 编码
  const gbk = new Uint8Array([0xc5, 0xda, 0xb6, 0xfe, 0xc6, 0xbd, 0xce, 0xe5]);
  assert.equal(decodeText(gbk), '炮二平五');
});

test('analysis.jsonl 叠加：国际象棋仅用 lichess 口径，中国象棋仅用 cls 口径，不跨口径混用', () => {
  const cPgn = readFileSync(join(ROOT, 'runs/g7-c-opus-astra-1/game.pgn'), 'utf-8');
  const cAna = readFileSync(join(ROOT, 'runs/g7-c-opus-astra-1/analysis.jsonl'), 'utf-8');
  const [cg] = loadGamesWithAnalysis([
    { name: '/runs/g7-c-opus-astra-1/game.pgn', text: cPgn },
    { name: '/runs/g7-c-opus-astra-1/analysis.jsonl', text: cAna },
  ]);
  // 半回合 47：cls=blunder, lichess=Mistake -> 应标 ? (NAG 2) 而非 ?? (NAG 4)
  assert.deepEqual(cg.game.moves[46].nags, [2]);
  // 半回合 68、71：cls=mistake, lichess=Blunder -> 应标 ?? (NAG 4) 而非 ? (NAG 2)
  assert.deepEqual(cg.game.moves[67].nags, [4]);
  assert.deepEqual(cg.game.moves[70].nags, [4]);
  // lichess=null 而 cls=mistake 的半回合（如半回合 28）不应跨口径标上 NAG
  assert.deepEqual(cg.game.moves[27].nags, []);

  // 中国象棋：使用 cls 口径，且拖放排序 analysis 在 game.pgn 前面时仍能正确关联
  const xPgn = readFileSync(join(ROOT, 'runs/g1-x-opus-sol/game.pgn'), 'utf-8');
  const xAna = readFileSync(join(ROOT, 'runs/g1-x-opus-sol/analysis.jsonl'), 'utf-8');
  const [xg] = loadGamesWithAnalysis([
    { name: 'analysis.jsonl', text: xAna },
    { name: 'game.pgn', text: xPgn },
  ]);
  assert.deepEqual(xg.game.moves[8].nags, [4]); // ply 9 blunder
  assert.deepEqual(xg.game.moves[9].nags, [4]); // ply 10 blunder
});

test('analysis.jsonl 校验：着法或局面不匹配、孤立分析、多盘 PGN 歧义均显式报错', () => {
  const pgn = '[Event "x"]\n\n1. e4 e5 *\n';
  const badMove = JSON.stringify({
    ply: 1, move: 'a7a6', fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', lichess: 'Blunder',
  });
  const badFen = JSON.stringify({
    ply: 1, move: 'e2e4', fen: 'WRONG POSITION', lichess: 'Blunder',
  });
  const badCastlingFen = JSON.stringify({
    ply: 1, move: 'e2e4', fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1', lichess: 'Blunder',
  });
  const goodRow = JSON.stringify({
    ply: 1, move: 'e2e4', fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', lichess: 'Blunder',
  });
  assert.throws(() => loadGamesWithAnalysis([pgn, badMove]), /不匹配/);
  assert.throws(() => loadGamesWithAnalysis([pgn, badFen]), /不匹配/);
  assert.throws(() => loadGamesWithAnalysis([pgn, badCastlingFen]), /不匹配/);
  assert.throws(() => loadGamesWithAnalysis([goodRow]), /只有分析文件/);
  const multiPgn = '[Event "a"]\n\n1. e4 e5 *\n\n[Event "b"]\n\n1. d4 d5 *\n';
  assert.throws(() => loadGamesWithAnalysis([multiPgn, goodRow]), /多盘棋谱存在歧义/);

  // 以花括号评注开头的合法 PGN（无论是否带 .pgn 文件名）均不应被误判为 JSONL
  const commentFirstPgn = '{Opening comment}\n1. e4 e5 *\n';
  const [g1] = loadGamesWithAnalysis([commentFirstPgn]);
  assert.deepEqual(g1.game.pre, ['Opening comment']);
  assert.deepEqual(g1.game.moves.map((m) => m.text), ['e4', 'e5']);
  const [g2] = loadGamesWithAnalysis([{ name: 'game.pgn', text: '{"jsonLikeComment": 1}\n1. e4 e5 *\n' }]);
  assert.deepEqual(g2.game.moves.map((m) => m.text), ['e4', 'e5']);
});
