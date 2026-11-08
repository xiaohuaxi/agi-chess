// 回归：读本机 runs/ 里全部已结束的对局，把 game.pgn 逐步走完。
// - 同时有 game.jsonl 时（作者本机）：每步坐标、将军与 game.jsonl 的 move / check 一致，步数与结果和 end 行一致；
//   每步读出的理由文字与导出端（python3 现场按 game.jsonl 算 records.move_meta）逐字一致，折行不丢、不多空格。
// - 只有入库的 game.pgn 而无 game.jsonl 时（公开克隆环境）：逐步走完 PGN 校验合法性、评注命令解析、终局标签与将死状态，
//   若同目录有 analysis.jsonl 则进一步核对每步坐标一致。
// 还在下的盘（没有 end 行或 Result 为 *）一律不读。导出不是本代码写法的盘跳过并计数、不算失败：game.pgn 缺失、比 game.jsonl 旧，
// 或与本代码现场导出的（runner.render_exports）不一致——对局可能在本检出之外刚结束，用的是那边的旧导出写法。
// 这样跳过的盘在输出里报数；要读它们，先用本检出的代码 `python3 -m agi_chess export <目录>` 重导。
// 对局目录：环境变量 VIEWER_RUNS 优先；worktree（.agents/worktrees/<名>）里默认用主检出的 runs/。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodeText, moveNote, parsePgn } from '../lib/pgn.js';
import { isXiangqi, replay } from '../lib/replay.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const RUNS = process.env.VIEWER_RUNS || join(ROOT.split('/.agents/worktrees/')[0], 'runs');

function* gameDirs(dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (!e.isDirectory()) continue;
    const d = join(dir, e.name);
    if (existsSync(join(d, 'game.jsonl')) || existsSync(join(d, 'game.pgn'))) yield d;
    yield* gameDirs(d);
  }
}

function finished() {
  const out = [];
  for (const d of gameDirs(RUNS)) {
    const jsonl = join(d, 'game.jsonl');
    const pgn = join(d, 'game.pgn');
    if (!existsSync(jsonl)) {
      const [g] = parsePgn(decodeText(readFileSync(pgn)));
      if (!g || !g.result || g.result === '*' || g.tags.Result === '*') continue;
      out.push({ dir: d, game: isXiangqi(g) ? 'xiangqi' : 'chess', end: null, moves: null, stale: null });
      continue;
    }
    const rows = readFileSync(jsonl, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
    const end = rows.find((r) => r.type === 'end');
    if (!end) continue;                                 // 还在下的盘不碰
    const cfg = rows.find((r) => r.type === 'config').cfg;
    const moves = rows.filter((r) => r.type === 'move').sort((a, b) => a.ply - b.ply);
    const stale = !existsSync(pgn) ? '导出缺失'
      : statSync(pgn).mtimeMs < statSync(jsonl).mtimeMs ? '导出比记录旧' : null;
    out.push({ dir: d, game: cfg.game, end, moves, stale });
  }
  return out;
}

const RESULT = { w: '1-0', b: '0-1' };

// 导出端眼里的每一盘：{目录: {why: {半回合号: 文字}, current: 盘上 game.pgn 是否与本代码现场导出的一致}}
// （理由文字空白压成一个空格，和 parseComment 的 text 同一口径）。python3 跑不起来时为 null，只跳过这两项核对。
const PY_WHY = `
import json, re, sys
from agi_chess import cli, records, runner
out = {}
for d in json.load(sys.stdin):
    meta = records.move_meta(records.read(d + '/game.jsonl'))
    cfg = records.read(d + '/game.jsonl')[0]['cfg']
    fresh = runner.render_exports(runner.load(cli.game_module(cfg['game']), d))['game.pgn']
    with open(d + '/game.pgn', encoding='utf-8') as f:
        current = re.sub(r'^\\[Event "(?:llm|agi)-chess ', '[Event "agi-chess ', f.read(), count=1, flags=re.M) == fresh
    out[d] = {'why': {p: ' '.join(records.comment_text(m.get('why') or '').split()) for p, m in meta.items()},
              'current': current}
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
  assert.deepEqual(g.errors, [], rec.dir);
  const r = replay(g);
  assert.equal(r.kind, rec.game === 'xiangqi' ? 'xiangqi' : 'chess', rec.dir);
  assert.equal(r.error, null, `${rec.dir} ${JSON.stringify(r.error)}`);
  assert.equal(r.steps.length, g.moves.length, rec.dir);
  if (rec.moves) {
    assert.equal(r.steps.length, rec.moves.length, rec.dir);
  } else {
    assert.ok(r.steps.length > 0, rec.dir);
    assert.ok(['1-0', '0-1', '1/2-1/2'].includes(g.result), rec.dir);
    assert.equal(g.tags.Result, g.result, rec.dir);
    assert.ok(g.tags.Termination, rec.dir);
    if (g.tags.Termination === '将死') assert.equal(r.steps.at(-1).check, true, rec.dir);
    const an = join(rec.dir, 'analysis.jsonl');
    if (existsSync(an)) {
      const arows = readFileSync(an, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
      assert.deepEqual(r.steps.map((s) => s.move), arows.map((a) => a.move), rec.dir);
    }
  }
  r.steps.forEach((s, i) => {
    if (rec.moves) {
      const m = rec.moves[i];
      if (s.move !== m.move || s.check !== Boolean(m.check)) {
        assert.fail(`${rec.dir} 第 ${i + 1} 步：读出 ${s.text} → ${s.move} 将军 ${s.check}，记录 ${m.move} 将军 ${m.check}`);
      }
    }
    const note = moveNote(g.moves[i]);                  // 我们导出的评注命令都认得
    assert.deepEqual(note.unknown, [], `${rec.dir} 第 ${i + 1} 步评注`);
    assert.ok(!note.text.includes('[%'), `${rec.dir} 第 ${i + 1} 步评注`);
    if (rec.moves && WHY) assert.equal(note.text, WHY[rec.dir].why[i + 1] || '', `${rec.dir} 第 ${i + 1} 步理由文字`);
  });
  if (rec.end) {
    assert.deepEqual(r.steps.map((s) => s.move), rec.end.moves, rec.dir);
    assert.equal(g.result, RESULT[rec.end.end.winner] || '1/2-1/2', rec.dir);
    if (rec.end.end.reason === '将死') assert.equal(r.steps.at(-1).check, true, rec.dir);
  }
  return { plies: r.steps.length, checks: r.steps.filter((s) => s.check).length };
}

const have = existsSync(RUNS);
const recs = have ? finished() : [];
const jsonlDirs = have ? recs.filter((r) => !r.stale && r.end).map((r) => r.dir) : [];
const WHY = jsonlDirs.length ? reasons(jsonlDirs) : null;
if (WHY) for (const r of recs) if (!r.stale && r.end && !WHY[r.dir].current) r.stale = '不是本代码的导出写法';

for (const kind of ['xiangqi', 'chess']) {
  test(`runs 回归：${kind} 已结束对局逐步与 game.jsonl 一致`, { skip: have ? false : `没有 ${RUNS}` }, (t) => {
    const all = recs.filter((r) => r.game === kind);
    const mine = all.filter((r) => !r.stale);
    const why = {};
    for (const r of all) if (r.stale) why[r.stale] = (why[r.stale] || 0) + 1;
    const skipped = Object.entries(why).map(([k, n]) => `${k} ${n}`).join('、');
    if (skipped) t.diagnostic(`${kind}：跳过 ${all.length - mine.length} 盘（${skipped}），先用本检出重导才读`);
    assert.ok(mine.length > 0, '没有可读的已结束对局');
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
  assert.ok(!rec.stale, `g1-c-opus-sol ${rec.stale}，先重导`);
  const s = check(rec);
  assert.equal(s.plies, 95);
  const sPgnOnly = check({ dir: rec.dir, game: rec.game, end: null, moves: null, stale: null });
  assert.equal(sPgnOnly.plies, 95);
});
