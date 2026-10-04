// 录制脚本（viewer/record.mjs，docs/viewer.md「录屏：脚本出片」）。
// 前半不碰浏览器：命令行解析、秒数换帧数、服务只供给点名的文件、开工前的检查。
// 后半真出片：用自带样例、把停留时长调小，ffprobe 核对编码 H.264/High、yuv420p、30 帧恒定、1080×1440、+faststart，
// 时长 = 各格停留之和（误差 < 1 帧），换 gap 时长跟着变；默认带 AAC 音轨、时长与画面一致、每声起点落在棋子落地那一帧，
// --no-sound 出无声片。没有 playwright-core / 浏览器 / ffmpeg / ffprobe 时跳过。
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { accessSync, constants, mkdtempSync, openSync, readFileSync, readSync, closeSync, rmSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodeText, parsePgn } from '../lib/pgn.js';
import { replay } from '../lib/replay.js';
import { stepSound } from '../lib/sound.js';
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

test('命令行：停留时长透传、默认无标题 / --title 加 / --no-title 兼容、--set、不合法的报中文错', { skip: recSkip }, () => {
  const o = rec.parseCli(['a.pgn', 'b.pgn', '-o', 'x.mp4', '--gap', '1.5', '--resulthold', '0', '--set', 'layout=compact']);
  assert.deepEqual(o.inputs, ['a.pgn', 'b.pgn']);
  assert.deepEqual(o.params, { gap: '1.5', resulthold: '0', layout: 'compact' });   // 默认不带 title，页面默认无标题
  assert.deepEqual(rec.parseCli(['a', '-o', 'x.mp4', '--title']).params, { title: '1' });
  assert.deepEqual(rec.parseCli(['a', '-o', 'x.mp4', '--no-title']).params, {});
  assert.equal(o.aspect, '3:4');
  assert.equal(o.scale, 2);
  assert.deepEqual(rec.parseCli(['-h']), { help: true });
  assert.throws(() => rec.parseCli(['a', '-o', 'x.mp4', '--gap', '-1']), /--gap/);
  assert.throws(() => rec.parseCli(['a', '-o', 'x.mp4', '--gap', '']), /--gap/);
  assert.throws(() => rec.parseCli(['a', '-o', 'x.mp4', '--set', 'files=/etc/passwd']), /files/);
  assert.throws(() => rec.parseCli(['a', '-o', 'x.mp4', '--bogus']));
  assert.deepEqual(rec.parseCli(['a', '-o', 'x.mp4', '--anim', '0']).params, { anim: '0' });
  assert.throws(() => rec.parseCli(['a', '-o', 'x.mp4', '--anim', 'x']), /--anim/);
  assert.deepEqual(rec.parseCli(['a', '-o', 'x.mp4', '--openhold', '0.5']).params, { openhold: '0.5' });
  assert.throws(() => rec.parseCli(['a', '-o', 'x.mp4', '--openhold', '-1']), /--openhold/);
});

test('命令行：默认有声、--no-sound 关掉；--vol 是正的倍数', { skip: recSkip }, () => {
  const o = rec.parseCli(['a', '-o', 'x.mp4']);
  assert.equal(o.sound, true);
  assert.equal(o.vol, 1);
  assert.deepEqual(o.params, {});                                   // 声音选项不透传给页面
  assert.equal(rec.parseCli(['a', '-o', 'x.mp4', '--no-sound']).sound, false);
  assert.equal(rec.parseCli(['a', '-o', 'x.mp4', '--vol', '0.5']).vol, 0.5);
  for (const v of ['0', '-1', 'x', '']) assert.throws(() => rec.parseCli(['a', '-o', 'x.mp4', `--vol=${v}`]), /--vol/, v);
});

test('声音时刻：和画面同一套累计帧数——响在动画帧之后那张静止画面的开头', { skip: recSkip }, () => {
  // 开局 1.8 秒；第 1 步 9 张动画帧（各 1/30）+ 静止 1.5；第 2 步没动画、停 1；结果格停 4
  const sec = [1.8, ...Array(9).fill(1 / 30), 1.5, 1, 4];
  const t = rec.cueTimes(sec, [[10, 'move'], [11, 'capture'], [12, 'end'], [13, 'end']]);
  assert.deepEqual(t.map((c) => c.sound), ['move', 'capture', 'end', 'end']);
  for (const [got, want] of [[t[0].t, 2.1], [t[1].t, 3.6], [t[2].t, 4.6], [t[3].t, 8.6]]) assert.ok(Math.abs(got - want) < 1e-9, `${got} ≠ ${want}`);
  // 秒数不是整帧时，时刻跟着帧数取整走（第 2 张从第 round(0.25×30)=8 帧起）
  assert.equal(rec.cueTimes([0.25, 1], [[1, 'move']])[0].t, 8 / 30);
});

test('混音：按时刻叠进全长音轨、乘增益，超出片尾截掉、叠爆削到 ±1', { skip: recSkip }, () => {
  const pcm = { move: new Float32Array([0.5, 0.5]), capture: new Float32Array([1, 1, 1]), end: new Float32Array([0.9]) };
  const out = rec.mixTrack([{ t: 0, sound: 'move' }, { t: 2 / rec.RATE, sound: 'capture' }], 4 / rec.RATE, pcm, 1);
  assert.equal(out.length, 4);
  const km = 10 ** (1.7 / 20), kc = 10 ** (-7.9 / 20);
  assert.ok(Math.abs(out[0] - 0.5 * km) < 1e-6 && Math.abs(out[1] - 0.5 * km) < 1e-6);
  assert.ok(Math.abs(out[2] - kc) < 1e-6 && Math.abs(out[3] - kc) < 1e-6);   // 第三个样本超出片长，截掉
  const loud = rec.mixTrack([{ t: 0, sound: 'end' }, { t: 0, sound: 'end' }], 1 / rec.RATE, pcm, 2);
  assert.equal(loud[0], 1);
  assert.equal(rec.mixTrack([], 0.5, pcm).length, rec.RATE / 2);
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

async function make(name, files, params, extra = {}) {
  const out = join(TMP, `${name}-${Math.random().toString(36).slice(2)}.mp4`);
  const r = await rec.record({ inputs: files.map((f) => join(FIX, f)), out, params, ffmpeg: FFMPEG, ...extra }, () => {});
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

const H = { title: '1', titlehold: '0.2', resulthold: '0.3' };   // 这几条带标题画面出片

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
  const m = await make('match', ['chess-sample.pgn', 'xq-sample.pgn'], { gap: '0.05', resulthold: '0.2', summaryhold: '0.5' });
  // 默认无标题：每盘开局一格 move（停 gap）+ N 步 + result；最后一格总比分。
  const want = counts.reduce((s, n) => s + (n + 1) * 0.05 + 0.2, 0) + 0.5;
  checkSpec(m.p, m.out, want);
  assert.equal(m.r.cells.at(-1).kind, 'end');
  assert.equal(m.r.cells.at(-1).hold, 0.5);
  // --openhold：每盘开局局面那格改停 0.3，别的格不变——两盘共长 2 × (0.3 − 0.05) 秒
  const o = await make('match-open', ['chess-sample.pgn', 'xq-sample.pgn'], { gap: '0.05', resulthold: '0.2', summaryhold: '0.5', openhold: '0.3' });
  checkSpec(o.p, o.out, want + 2 * (0.3 - 0.05));
  assert.equal(o.r.cells.filter((c) => c.kind === 'move' && c.anim === 0 && c.hold === 0.3).length, 2);
});

test('出片：走子动画算在 gap 之内——时长不变，每步多出 round(anim×30) 张动画帧', { skip }, async () => {
  const [n] = plies('anim-special.pgn');
  const a = await make('anim', ['anim-special.pgn'], { ...H, gap: '0.5', anim: '0.3' });
  checkSpec(a.p, a.out, 0.2 + n * 0.5);                      // 这盘没结果：title + n 步，没有 result 格
  assert.ok(a.r.cells.filter((c) => c.kind === 'move').every((c) => c.anim === 0.3 && Math.abs(c.hold - 0.2) < 1e-9));
  assert.equal(a.r.shots, 1 + n * (9 + 1));                  // 标题 1 张；每步 9 张动画帧 + 1 张静止
  const b = await make('anim0', ['anim-special.pgn'], { ...H, gap: '0.5', anim: '0' });
  checkSpec(b.p, b.out, 0.2 + n * 0.5);
  assert.equal(b.r.shots, 1 + n);
});

// 音轨：codec、采样率、声道、时长；没有音轨时返回 null。
function probeAudio(file) {
  const j = JSON.parse(execFileSync(FFPROBE, ['-v', 'error', '-select_streams', 'a', '-show_entries',
    'stream=codec_name,sample_rate,channels,duration', '-of', 'json', file]));
  return j.streams[0] || null;
}

// 解码音轨，找每声的起点（幅度超过 −40 dBFS、且之前静了 50 ms 以上）。
function onsets(file) {
  const raw = execFileSync(FFMPEG, ['-v', 'error', '-i', file, '-vn', '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'], { maxBuffer: 1 << 28 });
  const x = new Float32Array(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.length));
  const out = [];
  let last = -Infinity;
  for (let i = 0; i < x.length; i++) {
    if (Math.abs(x[i]) > 0.01) { if (i - last > 2400) out.push(i / 48000); last = i; }
  }
  return out;
}

test('出片：默认带音轨——AAC 48k 单声道、时长同画面；每声起点对上棋子落地那一帧；--no-sound 没有音轨', { skip }, async () => {
  const [rep] = parsePgn(decodeText(readFileSync(join(FIX, 'xq-sample.pgn')))).map((g) => replay(g));
  const n = rep.steps.length;
  const a = await make('snd', ['xq-sample.pgn'], { gap: '0.5', anim: '0.3', resulthold: '0.8' });
  const seconds = 0.5 + n * 0.5 + 0.8;
  checkSpec(a.p, a.out, seconds);
  const au = probeAudio(a.out);
  assert.deepEqual([au.codec_name, au.sample_rate, au.channels], ['aac', '48000', 1]);
  assert.ok(Math.abs(Number(au.duration) - seconds) < 1 / 30, `音轨时长 ${au.duration}，应为 ${seconds}`);
  // 哪几声：每步 capture / move，最后终局
  assert.deepEqual(a.r.sounds.map((c) => c.sound), [...rep.steps.map(stepSound), 'end']);
  // 什么时候：第 k 步落地在 0.5（开局格）+ (k − 1) × 0.5 + 0.3；终局在 0.5 + n × 0.5
  const want = [...rep.steps.map((_, k) => 0.5 + k * 0.5 + 0.3), 0.5 + n * 0.5];
  a.r.sounds.forEach((c, i) => assert.ok(Math.abs(c.t - want[i]) < 1e-9, `第 ${i + 1} 声在 ${c.t}，应为 ${want[i]}`));
  // 成片里真的在那儿：解码出的起点比该响的时刻晚一点点，是素材开头自带的静音——落子 / 吃子约 8–11 ms，
  // 终局声（一串碰撞声）约 30–40 ms，都不到一帧多
  const on = onsets(a.out);
  assert.equal(on.length, want.length);
  on.forEach((t, i) => {
    const late = i < n ? 0.015 : 0.045;
    assert.ok(t - want[i] >= -0.002 && t - want[i] < late, `第 ${i + 1} 声起点 ${t}，应在 ${want[i]}`);
  });
  const b = await make('mute', ['xq-sample.pgn'], { gap: '0.5', anim: '0.3', resulthold: '0.8' }, { sound: false });
  checkSpec(b.p, b.out, seconds);
  assert.equal(probeAudio(b.out), null);
  assert.deepEqual(b.r.sounds, []);
});

// 放在文件末尾：顶层 await 之后才登记的测试，要在它们之后收临时目录。
after(() => rmSync(TMP, { recursive: true, force: true }));
