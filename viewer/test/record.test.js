// 录制脚本（viewer/record.mjs，docs/viewer.md「录屏：脚本出片」）。
// 前半不碰浏览器：命令行解析、秒数换帧数、服务只供给点名的文件、开工前的检查。
// 后半真出片：用自带样例、把停留时长调小，ffprobe 核对编码 H.264/High、yuv420p、30 帧恒定、1080×1440、+faststart，
// 时长 = 各格停留之和（误差 < 1 帧），换 gap 时长跟着变。没有 playwright-core / 浏览器 / ffmpeg / ffprobe 时跳过。
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { accessSync, constants, mkdtempSync, openSync, readFileSync, readSync, closeSync, rmSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodeText, parsePgn } from '../lib/pgn.js';
import { replay } from '../lib/replay.js';
import { serve } from '../serve.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FIX = join(ROOT, 'viewer', 'test', 'fixtures');
const TMP = mkdtempSync(join(tmpdir(), 'viewer-rec-test-'));

let rec = null, recSkip = false;
try { rec = await import('../record.mjs'); } catch (e) { recSkip = `没有 playwright-core（cd viewer && npm ci）：${e.message.split('\n')[0]}`; }

test('秒数换帧数：按累计时刻取整，总数 = round(总秒数 × 30)', { skip: recSkip }, () => {
  assert.deepEqual(rec.toFrames([3, 2.5, 4]), [90, 75, 120]);
  const f = rec.toFrames(Array(10).fill(0.11));                 // 每格 3.3 帧
  assert.equal(f.reduce((a, b) => a + b, 0), 33);
  assert.ok(f.every((n) => n === 3 || n === 4));
  assert.deepEqual(rec.toFrames([0.01, 0.01, 1]), [0, 1, 30]);   // 太短的格可能分到 0 帧，但总数不丢
});

test('命令行：停留时长透传、--no-title、--set、不合法的报中文错', { skip: recSkip }, () => {
  const o = rec.parseCli(['a.pgn', 'b.pgn', '-o', 'x.mp4', '--gap', '1.5', '--resulthold', '0', '--no-title', '--set', 'layout=compact']);
  assert.deepEqual(o.inputs, ['a.pgn', 'b.pgn']);
  assert.deepEqual(o.params, { gap: '1.5', resulthold: '0', title: '0', layout: 'compact' });
  assert.equal(o.aspect, '3:4');
  assert.equal(o.scale, 2);
  assert.deepEqual(rec.parseCli(['-h']), { help: true });
  assert.throws(() => rec.parseCli(['a', '-o', 'x.mp4', '--gap', '-1']), /--gap/);
  assert.throws(() => rec.parseCli(['a', '-o', 'x.mp4', '--gap', '']), /--gap/);
  assert.throws(() => rec.parseCli(['a', '-o', 'x.mp4', '--set', 'files=/etc/passwd']), /files/);
  assert.throws(() => rec.parseCli(['a', '-o', 'x.mp4', '--bogus']));
});

test('开工前检查：缺棋谱、输出不是 mp4、画幅不认识、ffmpeg 不在都直接报错', { skip: recSkip }, async () => {
  const pgn = join(FIX, 'xq-sample.pgn');
  const base = { inputs: [pgn], out: join(TMP, 'x.mp4'), params: {}, ffmpeg: '/bin/sh' };
  const bad = async (o, re) => assert.rejects(rec.record({ ...base, ...o }, () => {}), (e) => e instanceof rec.RecordError && re.test(e.message));
  await bad({ inputs: [join(TMP, 'nope.pgn')] }, /棋谱不存在/);
  await bad({ inputs: [TMP] }, /game\.pgn/);
  const junk = join(TMP, `junk-${Math.random().toString(36).slice(2)}.pgn`);
  writeFileSync(junk, '# 这不是棋谱\nhello world\n');
  await bad({ inputs: [pgn, junk] }, /没读到任何一盘有着法的棋.*junk-/);
  await bad({ out: join(TMP, 'x.mov') }, /\.mp4/);
  await bad({ out: join(TMP, 'no-dir', 'x.mp4') }, /输出目录不存在/);
  await bad({ aspect: '1:1' }, /画幅/);
  await bad({ ffmpeg: join(TMP, 'no-ffmpeg') }, /ffmpeg/);
});

test('服务：精确映射的文件照给，同目录别的文件和站点根都 404', async () => {
  const dir = join(TMP, `srv-${process.pid}-${Math.random().toString(36).slice(2)}`);
  mkdirSync(join(dir, 'www'), { recursive: true });
  writeFileSync(join(dir, 'a.pgn'), 'A');
  writeFileSync(join(dir, 'b.pgn'), 'B');
  const s = await serve(join(dir, 'www'), { '/viewer/': join(ROOT, 'viewer') }, { '/rec/1.pgn': join(dir, 'a.pgn') });
  try {
    const get = async (p) => { const r = await fetch(`http://127.0.0.1:${s.port}${p}`); return [r.status, r.ok ? await r.text() : null]; };
    assert.deepEqual(await get('/rec/1.pgn'), [200, 'A']);
    for (const p of ['/rec/2.pgn', '/rec/b.pgn', '/b.pgn', '/', '/AGENTS.md', '/rec/../b.pgn', '/viewer/../AGENTS.md']) {
      assert.equal((await get(p))[0], 404, p);
    }
    assert.equal((await get('/viewer/index.html'))[0], 200);
  } finally { await s.close(); }
});

// ---------------------------------------------------------------- 真出片
const FFMPEG = process.env.VIEWER_FFMPEG || '/opt/homebrew/bin/ffmpeg';
const FFPROBE = process.env.VIEWER_FFPROBE || join(dirname(FFMPEG), 'ffprobe');
let skip = recSkip;
if (!skip) {
  try { accessSync(FFMPEG, constants.X_OK); accessSync(FFPROBE, constants.X_OK); } catch { skip = `没有 ffmpeg / ffprobe（${FFMPEG}）`; }
}
if (!skip) {
  const pw = await import('playwright-core');
  try { await (await pw.chromium.launch({ executablePath: process.env.VIEWER_CHROMIUM || undefined })).close(); }
  catch (e) { skip = `起不来浏览器：${e.message.split('\n')[0]}`; }
}

const plies = (file) => parsePgn(decodeText(readFileSync(join(FIX, file)))).map((g) => replay(g).steps.length);

function probe(file) {
  const j = JSON.parse(execFileSync(FFPROBE, ['-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries',
    'stream=codec_name,profile,pix_fmt,width,height,r_frame_rate,avg_frame_rate,nb_read_frames,color_range,color_space:format=duration',
    '-of', 'json', file]));
  const pts = execFileSync(FFPROBE, ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'frame=pts_time', '-of', 'csv=p=0', file])
    .toString().trim().split('\n').map((l) => parseFloat(l));   // 首行可能带多余的逗号
  return { ...j.streams[0], duration: Number(j.format.duration), pts };
}

// moov 在 mdat 前面（+faststart）。
function moovFirst(file) {
  const fd = openSync(file, 'r');
  try {
    const buf = Buffer.alloc(8);
    for (let pos = 0; ;) {
      if (readSync(fd, buf, 0, 8, pos) < 8) return false;
      const type = buf.toString('latin1', 4, 8);
      if (type === 'moov') return true;
      if (type === 'mdat') return false;
      pos += buf.readUInt32BE(0);
    }
  } finally { closeSync(fd); }
}

async function make(name, files, params) {
  const out = join(TMP, `${name}-${Math.random().toString(36).slice(2)}.mp4`);
  const r = await rec.record({ inputs: files.map((f) => join(FIX, f)), out, params, ffmpeg: FFMPEG }, () => {});
  return { r, p: probe(out), out };
}

function checkSpec(p, out, seconds) {
  assert.equal(p.codec_name, 'h264');
  assert.equal(p.profile, 'High');
  assert.equal(p.pix_fmt, 'yuv420p');
  assert.equal(p.color_range, 'tv');
  assert.equal(p.color_space, 'bt709');
  assert.deepEqual([p.width, p.height], [1080, 1440]);
  assert.equal(p.r_frame_rate, '30/1');
  assert.equal(p.avg_frame_rate, '30/1');
  assert.ok(Math.abs(p.duration - seconds) < 1 / 30, `时长 ${p.duration}，应为 ${seconds}`);
  assert.equal(Number(p.nb_read_frames), Math.round(seconds * 30));
  for (let i = 1; i < p.pts.length; i++) assert.ok(Math.abs(p.pts[i] - p.pts[i - 1] - 1 / 30) < 1e-4, `第 ${i} 帧间隔不是 1/30`);
  assert.ok(moovFirst(out), '没有 +faststart');
}

const H = { titlehold: '0.2', resulthold: '0.3' };

test('出片：两种棋 3:4、编码与时长对，换 gap 时长跟着变', { skip }, async () => {
  const [nx] = plies('xq-sample.pgn');
  const [nc] = plies('chess-sample.pgn');
  const a = await make('xq-a', ['xq-sample.pgn'], { ...H, gap: '0.1' });
  checkSpec(a.p, a.out, 0.2 + nx * 0.1 + 0.3);
  assert.deepEqual(a.r.cells.map((c) => c.kind), ['title', ...Array(nx).fill('move'), 'result', 'end']);
  const b = await make('xq-b', ['xq-sample.pgn'], { ...H, gap: '0.2' });
  checkSpec(b.p, b.out, 0.2 + nx * 0.2 + 0.3);
  assert.ok(Math.abs(b.p.duration - a.p.duration - nx * 0.1) < 1 / 30);
  const c = await make('chess', ['chess-sample.pgn'], { ...H, gap: '0.1' });
  checkSpec(c.p, c.out, 0.2 + nc * 0.1 + 0.3);
});

test('出片：两个文件连播、不要标题，末尾总比分停 summaryhold', { skip }, async () => {
  const counts = ['chess-sample.pgn', 'xq-sample.pgn'].flatMap(plies);
  const m = await make('match', ['chess-sample.pgn', 'xq-sample.pgn'], { gap: '0.05', resulthold: '0.2', summaryhold: '0.5', title: '0' });
  // title=0：每盘开局一格 move（停 gap）+ N 步 + result；最后一格总比分。
  const want = counts.reduce((s, n) => s + (n + 1) * 0.05 + 0.2, 0) + 0.5;
  checkSpec(m.p, m.out, want);
  assert.equal(m.r.cells.at(-1).kind, 'end');
  assert.equal(m.r.cells.at(-1).hold, 0.5);
});

// 放在文件末尾：顶层 await 之后才登记的测试，要在它们之后收临时目录。
after(() => rmSync(TMP, { recursive: true, force: true }));
