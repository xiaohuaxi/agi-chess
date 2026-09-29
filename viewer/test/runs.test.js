// 回归：读本机 runs/ 里全部已结束（game.jsonl 有 end 行）的对局，把 game.pgn 逐步走完，
// 每步坐标、将军与 game.jsonl 的 move / check 一致，步数与结果和 end 行一致；每步读出的理由文字与导出端
// （python3 现场按 game.jsonl 算 records.move_meta）逐字一致，折行不丢、不多空格。本机没有 runs/ 时跳过。
// 对局目录：环境变量 VIEWER_RUNS 优先；worktree（.agents/worktrees/<名>）里默认用主检出的 runs/。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodeText, moveNote, parsePgn } from '../lib/pgn.js';
import { replay } from '../lib/replay.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const RUNS = process.env.VIEWER_RUNS || join(ROOT.split('/.agents/worktrees/')[0], 'runs');

function* gameDirs(dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (!e.isDirectory()) continue;
    const d = join(dir, e.name);
    if (existsSync(join(d, 'game.jsonl'))) yield d;
    yield* gameDirs(d);
  }
}

function finished() {
  const out = [];
  for (const d of gameDirs(RUNS)) {
    const rows = readFileSync(join(d, 'game.jsonl'), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
    const end = rows.find((r) => r.type === 'end');
    if (!end) continue;                                 // 还在下的盘不碰
    const cfg = rows.find((r) => r.type === 'config').cfg;
    const moves = rows.filter((r) => r.type === 'move').sort((a, b) => a.ply - b.ply);
    out.push({ dir: d, game: cfg.game, end, moves });
  }
  return out;
}

const RESULT = { w: '1-0', b: '0-1' };

// 导出端眼里每步的理由文字：{目录: {半回合号: 文字}}（空白压成一个空格，和 parseComment 的 text 同一口径）。
// python3 跑不起来时为 null，只跳过这一项核对。
const PY_WHY = `
import json, sys
from llmchess import records
out = {}
for d in json.load(sys.stdin):
    meta = records.move_meta(records.read(d + '/game.jsonl'))
    out[d] = {p: ' '.join(records.comment_text(m.get('why') or '').split()) for p, m in meta.items()}
print(json.dumps(out, ensure_ascii=False))
`;

function reasons(dirs) {
  const py = spawnSync('python3', ['-c', PY_WHY], { cwd: ROOT, input: JSON.stringify(dirs), encoding: 'utf8', maxBuffer: 1 << 28 });
  return py.status === 0 ? JSON.parse(py.stdout) : null;
}

function check(rec) {
  const games = parsePgn(decodeText(readFileSync(join(rec.dir, 'game.pgn'))));
  assert.equal(games.length, 1, rec.dir);
  const [g] = games;
  const r = replay(g);
  assert.equal(r.kind, rec.game === 'xiangqi' ? 'xiangqi' : 'chess', rec.dir);
  assert.equal(r.error, null, `${rec.dir} ${JSON.stringify(r.error)}`);
  assert.equal(r.steps.length, rec.moves.length, rec.dir);
  r.steps.forEach((s, i) => {
    const m = rec.moves[i];
    if (s.move !== m.move || s.check !== Boolean(m.check)) {
      assert.fail(`${rec.dir} 第 ${i + 1} 步：读出 ${s.text} → ${s.move} 将军 ${s.check}，记录 ${m.move} 将军 ${m.check}`);
    }
    const note = moveNote(g.moves[i]);                  // 我们导出的评注命令都认得
    assert.deepEqual(note.unknown, [], `${rec.dir} 第 ${i + 1} 步评注`);
    assert.ok(!note.text.includes('[%'), `${rec.dir} 第 ${i + 1} 步评注`);
    if (WHY) assert.equal(note.text, WHY[rec.dir][i + 1] || '', `${rec.dir} 第 ${i + 1} 步理由文字`);
  });
  assert.deepEqual(r.steps.map((s) => s.move), rec.end.moves, rec.dir);
  assert.equal(g.result, RESULT[rec.end.end.winner] || '1/2-1/2', rec.dir);
  if (rec.end.end.reason === '将死') assert.equal(r.steps.at(-1).check, true, rec.dir);
  return { plies: r.steps.length, checks: r.steps.filter((s) => s.check).length };
}

const have = existsSync(RUNS);
const recs = have ? finished() : [];
const WHY = have ? reasons(recs.map((r) => r.dir)) : null;

for (const kind of ['xiangqi', 'chess']) {
  test(`runs 回归：${kind} 已结束对局逐步与 game.jsonl 一致`, { skip: have ? false : `没有 ${RUNS}` }, (t) => {
    const mine = recs.filter((r) => r.game === kind);
    assert.ok(mine.length > 0, '没有已结束的对局');
    let plies = 0, checks = 0;
    for (const rec of mine) {
      const s = check(rec);
      plies += s.plies;
      checks += s.checks;
    }
    t.diagnostic(`${kind}：${mine.length} 盘，${plies} 步，其中将军 ${checks} 步，不一致 0`);
  });
}

test('runs 回归：国际象棋样例 g1-c-opus-sol', { skip: existsSync(join(RUNS, 'g1-c-opus-sol')) ? false : '没有这盘' }, () => {
  const rec = recs.find((r) => r.dir === join(RUNS, 'g1-c-opus-sol'));
  assert.ok(rec, 'g1-c-opus-sol 没结束');
  const s = check(rec);
  assert.equal(s.plies, 95);
});
