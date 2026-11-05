// 真正的裁决文案 → 两种棋的 PGN 导出 → 阅读器结果；只 mock 引擎评分，不调用模型或引擎。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { parsePgn } from '../lib/pgn.js';
import { reasonEn } from '../lib/i18n.js';
import { resultText } from '../lib/match.js';

const root = fileURLToPath(new URL('../../', import.meta.url));
const available = spawnSync('python3', ['-c', 'import chess, pyffish'], { encoding: 'utf8' });
test('上限裁决：真实文案与 PGN 往返涵盖两棋种、双方走子、正负评分与零分', {
  skip: available.status === 0 ? false : 'python3 缺少规则库',
}, () => {
  const py = spawnSync('python3', ['-c', `
import json
from unittest.mock import patch
from llmchess import analyze, chess_ as C, xiangqi as X
out = []
for kind, G, move in [('chess', C, 'e2e4'), ('xiangqi', X, 'h2e2')]:
    for black in [False, True]:
        st = G.start()
        if black:
            G.push(st, move)
        for score in [('mate', 3), ('mate', -2), ('mate', 0), ('cp', 350), ('cp', -300), ('cp', 299), ('cp', -299), ('cp', 0)]:
            with patch('llmchess.analyze.Analyser') as mocked:
                eng = mocked.return_value.__enter__.return_value
                eng.evaluate.return_value = (score, 16, None)
                eng.id = 'fixture'
                end = analyze.adjudicate(G, kind, st, 300, 200)
            cfg = {'tag': 'fixture', 'players': {'w': 'Alpha', 'b': 'Beta'}}
            out.append({'kind': kind, 'black': black, 'score': score, 'winner': end['winner'],
                        'reason': end['reason'], 'pgn': G.exports(st, cfg, end, [], {})['game.pgn']})
print(json.dumps(out))
`], { cwd: root, encoding: 'utf8' });
  assert.equal(py.status, 0, py.stderr);
  const data = JSON.parse(py.stdout);
  assert.equal(data.length, 32);
  for (const row of data) {
    const [g] = parsePgn(row.pgn);
    assert.equal(g.tags.Termination, row.reason);
    const side = row.winner === 'b' ? 'Black' : row.kind === 'chess' ? 'White' : 'Red';
    const [kind, score] = row.score;
    const whiteScore = row.black ? -score : score;
    const signed = `${whiteScore >= 0 ? '+' : ''}${whiteScore}`;
    const expected = kind === 'mate' ? `${side} wins (mate in ${Math.abs(score)})`
      : row.winner ? `${side} wins (+${Math.abs(score)} cp ≥ 300)`
      : `draw (${row.kind === 'chess' ? 'White' : 'Red'} ${signed} cp; gap < 300)`;
    assert.equal(reasonEn(g.tags.Termination), `Engine adjudication at 200 plies: ${expected}`, row.reason);
    assert.equal(g.result, row.winner === 'w' ? '1-0' : row.winner === 'b' ? '0-1' : '1/2-1/2');
    assert.equal(resultText(g, row.kind === 'xiangqi', 'en'),
      `${row.winner ? `${side} wins` : 'Draw'} · Engine adjudication at 200 plies: ${expected}`);
  }
});
