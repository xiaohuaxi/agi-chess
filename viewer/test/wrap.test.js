// 评注折行往返：导出端（llmchess，python3 现场生成）写进 game.pgn 的理由文字，经本页分词器读回来要逐字一致。
// 重点是「中文 空格 中文」：导出端永不在这种空格处断行，否则按「换行两边都是全角字符不补空格」读回来会少一个空格
// （docs/viewer.md「中文折行」）。本机没有 python3 或 llmchess 依赖时跳过。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { moveNote, parsePgn } from '../lib/pgn.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

// 随机拼 200 条理由（固定种子）：中文词、英文词、着法、全角标点，词间随机加或不加空格；两种棋各导一盘，每步一条理由。
const PY = `
import json, random
from llmchess import chess_ as C, records, xiangqi as X
rng = random.Random(7)
zh = ['红方', '中炮', '过河', '黑方', '必须', '马上', '应对', '中卒', '丢掉', '被动', '先手', '兑子', '控制', '肋道']
en = ['Nf3', 'e5', 'h2e2', 'the', 'centre', 'is', 'open', 'x']
punct = ['，', '。', '：', '；', '、', '……', '——', '…']   # 「…」「—」是 A 宽度：在它们后面断行读回会多空格
def reason():
    out = ''
    for _ in range(rng.randint(3, 60)):
        w = rng.choice(zh * 3 + en + punct)
        out += (' ' if out and rng.random() < 0.5 else '') + w
    return out
def meta(n):
    return {i: {'emt': 1, 'think': 5, 'why': reason()} for i in range(1, n + 1)}
cfg = {'tag': 't', 'players': {'w': 'claude:opus', 'b': 'claude:opus'}}
end = {'winner': None, 'reason': 'x'}
res = {}
for name, G, moves in (('chess', C, ['g1f3', 'g8f6', 'f3g1', 'f6g8'] * 25),
                       ('xiangqi', X, ['h0g2', 'h9g7', 'g2h0', 'g7h9'] * 25)):
    st = G.start()
    for mv in moves:
        G.push(st, mv)
    m = meta(len(moves))
    res[name] = {'pgn': G.exports(st, cfg, end, [], m)['game.pgn'],
                 'why': [' '.join(records.comment_text(m[i + 1]['why']).split()) for i in range(len(moves))]}
print(json.dumps(res, ensure_ascii=False))
`;

const py = spawnSync('python3', ['-c', PY], { cwd: ROOT, encoding: 'utf8', maxBuffer: 1 << 26 });
const skip = py.status === 0 ? false : `python3 导出失败：${(py.stderr || py.error || '').toString().slice(-300)}`;
const data = skip ? {} : JSON.parse(py.stdout);

for (const kind of ['chess', 'xiangqi']) {
  test(`折行往返：${kind} 理由文字逐字一致（含「中文 空格 中文」）`, { skip }, () => {
    const { pgn, why } = data[kind];
    assert.ok(why.some((w) => /[一-鿿] [一-鿿]/.test(w)), '样例里要有「中文 空格 中文」');
    const [g] = parsePgn(pgn);
    assert.equal(g.moves.length, why.length);
    g.moves.forEach((m, i) => {
      const { cmds, text } = moveNote(m);
      assert.equal(cmds.think, 5);
      assert.equal(text, why[i], `第 ${i + 1} 步`);
    });
  });
}
