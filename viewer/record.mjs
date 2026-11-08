// 录屏：脚本驱动页面一格一格截图，ffmpeg 拼成 mp4（docs/viewer.md「录屏：脚本出片」）；
// 默认带走子音效：按 next() 给的 sound 在棋子落地那一刻混一声，作为 AAC 音轨（docs/viewer.md「走子音效」）。
// 用法见 HELP（node viewer/record.mjs --help）。也可 import { record } 在测试里直接调。
import { spawn } from 'node:child_process';
import { accessSync, constants, existsSync, linkSync, mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { isExecutableFile, resolveChromium, resolveFfmpeg, serve } from './serve.mjs';
import { decodeText, parsePgn } from './lib/pgn.js';
import { replay } from './lib/replay.js';
import { SOUNDS, linear } from './lib/sound.js';

export const FPS = 30;
export const RATE = 48000;   // 音轨采样率
// 画幅 → 页面视口（CSS 像素）；实际像素再乘 scale（默认 2）。
export const ASPECTS = { '3:4': [540, 720], '9:16': [540, 960], '16:9': [960, 540] };
const VIEWER = path.dirname(fileURLToPath(import.meta.url));
const HOLDS = ['gap', 'openhold', 'titlehold', 'resulthold', 'summaryhold', 'anim'];   // 秒数选项，原样透传成同名网址参数
const STEP_TIMEOUT = 30_000;   // 页面画一格的上限；超了多半是页面卡住

const HELP = `用法：node viewer/record.mjs [选项] <棋谱> [<棋谱> …] -o <输出.mp4>

把棋谱按页面的录制模式（rec=1）一格一格截图，拼成 H.264 mp4（30 帧恒定、yuv420p、+faststart）。
默认带走子音效（AAC 音轨）：落子 / 吃子声响在棋子落地那一刻，终局横幅出现时再响一声。
棋谱可以是任意本机路径（绝对、相对都行）；给目录时取其中的 game.pgn（如 runs/<tag>）。
多个棋谱按给出的顺序连播，末尾加一格总比分。

选项：
  -o, --out <文件>         输出 mp4 路径（必填；目录须已存在，默认不覆盖已存在文件，先写临时文件再改名）
  -f, --force              允许覆盖已存在的输出 mp4 文件
  --gap <秒>               每步停多久（页面默认 1.8）
  --openhold <秒>          每盘开局局面（第一步之前）停多久（页面默认同 gap）；视频开头想快点动起来就调短，
                           如 0.5；加了 --title 时开局那格换成标题画面，这项不起作用
  --titlehold <秒>         标题画面停多久（页面默认 3；配 --title 才有用）
  --resulthold <秒>        终局横幅停多久（页面默认 4）
  --summaryhold <秒>       多盘时总比分停多久（页面默认 5）
  --anim <秒>              走子滑动多久（页面默认 0.3，0 关掉）；算在 gap 之内，不拉长视频：
                           每步一格总长仍是 gap（先滑 anim 秒，再停 gap − anim 秒）
  --vol <倍数>             音效整体音量倍数（默认 1；0.5 约轻 6 dB，2 约响 6 dB）
  --no-sound               不要音效，出无声视频（没有音轨）
  --title                  加标题画面（网址参数 title=1）；默认不加
  --no-title               不加标题画面（默认就是这样，留着兼容旧命令）
  --aspect <比例>          3:4（默认，1080×1440）、9:16（1080×1920）、16:9（1920×1080）
  --scale <倍数>           像素倍数，默认 2（视口 540×720 出 1080×1440）
  --set <名=值>            再透传一个网址参数给页面（可多次），如 --set layout=compact；
                           --set vendor=0 标题画面名字前不补厂商（「GPT astra」→「astra」）
                           --set lang=en 英文界面；--set 'names=claude:opus=Claude Opus,codex:astra=GPT astra'
                           覆盖棋手显示名（棋谱里的名字=显示名，逗号分隔；值里有空格要加引号）。参数名写错不报错，出片后抽帧核对
  --chromium <路径>        浏览器可执行文件；默认环境变量 VIEWER_CHROMIUM，再查 playwright-core 缓存及 PATH 中的 Chromium / Chrome
  --ffmpeg <路径>          ffmpeg；默认环境变量 VIEWER_FFMPEG，再从 PATH 及常见路径查找 ffmpeg
  -h, --help               显示本说明

没给的停留时长用页面的默认值；各格停多久由页面决定，脚本只照 next() 返回的 anim 与 hold 办。
例：node viewer/record.mjs ~/repos/agi-chess/runs/g1-c-opus-sol -o /tmp/g1.mp4 --gap 1.5
`;

// 用户能看懂的错误：main 只打印 message，不打堆栈。
export class RecordError extends Error {}

// 命令行 → 选项对象（出错抛 RecordError）。
export function parseCli(argv) {
  const { values, positionals } = parseArgs({
    args: argv, allowPositionals: true, strict: true,
    options: {
      out: { type: 'string', short: 'o' }, force: { type: 'boolean', short: 'f' },
      help: { type: 'boolean', short: 'h' }, title: { type: 'boolean' }, 'no-title': { type: 'boolean' },
      aspect: { type: 'string' }, scale: { type: 'string' }, set: { type: 'string', multiple: true },
      chromium: { type: 'string' }, ffmpeg: { type: 'string' }, vol: { type: 'string' }, 'no-sound': { type: 'boolean' },
      ...Object.fromEntries(HOLDS.map((k) => [k, { type: 'string' }])),
    },
  });
  if (values.help) return { help: true };
  const params = {};
  for (const k of HOLDS) {
    if (values[k] === undefined) continue;
    const v = Number(values[k]);
    if (values[k].trim() === '' || !Number.isFinite(v) || v < 0) throw new RecordError(`--${k} 要给不小于 0 的秒数，收到「${values[k]}」`);
    params[k] = values[k];
  }
  if (values.title) params.title = '1';   // 默认不加标题；--no-title 等同默认，不传参数
  for (const kv of values.set || []) {
    const i = kv.indexOf('=');
    if (i <= 0) throw new RecordError(`--set 要写成 名=值，收到「${kv}」`);
    const k = kv.slice(0, i);
    if (k === 'rec' || k === 'files') throw new RecordError(`--set 不能改 ${k}，它由脚本自己给`);
    params[k] = kv.slice(i + 1);
  }
  const scale = values.scale === undefined ? 2 : Number(values.scale);
  if (values.scale?.trim() === '' || !(scale > 0) || !Number.isFinite(scale)) {
    throw new RecordError(`--scale 要给正数，收到「${values.scale}」`);
  }
  const vol = values.vol === undefined ? 1 : Number(values.vol);
  if (values.vol?.trim() === '' || !(vol > 0) || !Number.isFinite(vol)) throw new RecordError(`--vol 要给正数（音量倍数），收到「${values.vol}」；不要声音用 --no-sound`);
  return {
    inputs: positionals, out: values.out, force: !!values.force, params, aspect: values.aspect || '3:4', scale,
    chromium: values.chromium, ffmpeg: values.ffmpeg, sound: !values['no-sound'], vol,
  };
}

// 开工前把能查的都查完：失败只是白跑一趟，不留半截东西。
function preflight(o) {
  if (!o.inputs?.length) throw new RecordError('没给棋谱文件（--help 看用法）');
  if (!o.out) throw new RecordError('没给输出路径：加 -o <文件.mp4>');
  if (!o.out.toLowerCase().endsWith('.mp4')) throw new RecordError(`输出要是 .mp4 文件，收到「${o.out}」`);
  const out = path.resolve(o.out);
  if (!existsSync(path.dirname(out))) throw new RecordError(`输出目录不存在：${path.dirname(out)}`);
  if (existsSync(out) && !o.force) throw new RecordError(`输出文件已存在：${out}（换个路径，或加 --force 覆盖）`);
  const view = ASPECTS[o.aspect || '3:4'];
  if (!view) throw new RecordError(`不认识的画幅「${o.aspect}」，可选 ${Object.keys(ASPECTS).join('、')}`);
  const inputs = o.inputs.map((p) => {
    let f = path.resolve(p);
    if (!existsSync(f)) throw new RecordError(`棋谱不存在：${p}`);
    if (statSync(f).isDirectory()) {
      f = path.join(f, 'game.pgn');
      if (!existsSync(f)) throw new RecordError(`目录里没有 game.pgn：${p}`);
    }
    // 解析宽松，给个不是棋谱的文件也会读出一盘空棋、照样出一段只有标题和终局的片：这里先挡掉。
    let moves = 0;
    try {
      moves = parsePgn(decodeText(readFileSync(f))).reduce((m, g) => Math.max(m, replay(g).steps.length), 0);
    } catch { /* 读不了或解析炸了，都按没读到着法报 */ }
    if (!moves) throw new RecordError(`棋谱里没读到任何一盘有着法的棋（不是棋谱文件？）：${p}`);
    return f;
  });
  let ffmpeg;
  try {
    ffmpeg = resolveFfmpeg(o.ffmpeg);
  } catch {
    throw new RecordError(`找不到可执行的 ffmpeg：${o.ffmpeg || process.env.VIEWER_FFMPEG}（请安装 ffmpeg 或用 --ffmpeg / 环境变量 VIEWER_FFMPEG 指定）`);
  }
  if (!isExecutableFile(ffmpeg)) {
    throw new RecordError(`找不到可执行的 ffmpeg：${ffmpeg}（请安装 ffmpeg 或用 --ffmpeg / 环境变量 VIEWER_FFMPEG 指定）`);
  }
  const explicitChromium = (o.chromium || process.env.VIEWER_CHROMIUM || '').trim();
  let explicitChromiumPath;
  if (explicitChromium) {
    try {
      explicitChromiumPath = resolveChromium(o.chromium);
    } catch {
      throw new RecordError(`浏览器不存在或不可执行：${explicitChromium}`);
    }
    if (!explicitChromiumPath || !isExecutableFile(explicitChromiumPath)) {
      throw new RecordError(`浏览器不存在或不可执行：${explicitChromium}`);
    }
  }
  const scale = o.scale ?? 2;
  if (!(scale > 0) || !Number.isFinite(scale)) throw new RecordError(`--scale 要给有限正数，收到「${o.scale}」`);
  const size = [Math.round(view[0] * scale), Math.round(view[1] * scale)];
  if (size.some((n) => n % 2)) throw new RecordError(`出片尺寸 ${size.join('×')} 有奇数边，yuv420p 编不了；换个 --scale`);
  return { out, view, scale, size, inputs, ffmpeg, explicitChromiumPath };
}

function withTimeout(p, ms, what) {
  let t;
  return Promise.race([p, new Promise((_, bad) => { t = setTimeout(() => bad(new RecordError(`${what}超过 ${ms / 1000} 秒没完成，页面可能卡住了`)), ms); })])
    .finally(() => clearTimeout(t));
}

// 各格的秒数 → 帧数。按累计时刻取整再相减，总帧数 = round(总秒数 × 30)，误差不随格数累积。
export function toFrames(seconds, fps = FPS) {
  let acc = 0, prev = 0;
  return seconds.map((s) => { acc += s * fps; const end = Math.round(acc); const n = end - prev; prev = end; return n; });
}

// 每声的时刻（秒）：seconds 是各张截图的秒数，cues 是 [第几张截图开始响, 哪声]（可以等于张数，即片尾）。
// 和画面用同一套累计帧数：第 i 张从第 sum(toFrames(seconds)[0..i-1]) 帧开始，声音就从那一帧的时刻起。
export function cueTimes(seconds, cues, fps = FPS) {
  const counts = toFrames(seconds, fps);
  const start = [0];
  for (const c of counts) start.push(start.at(-1) + c);
  return cues.map(([at, sound]) => ({ t: start[Math.min(at, counts.length)] / fps, sound }));
}

// 把各声按时刻叠成一条单声道音轨（32 位浮点，RATE 采样率），长 seconds 秒。pcm[sound] 是解码好的样本，
// 每声乘 linear(sound, vol)；超出片长的尾巴截掉，叠爆了的削到 ±1（默认音量下各声峰值都在 −5 dBFS 以下，碰不到）。
export function mixTrack(times, seconds, pcm, vol = 1) {
  const out = new Float32Array(Math.round(seconds * RATE));
  for (const { t, sound } of times) {
    const src = pcm[sound], k = linear(sound, vol);
    const at = Math.round(t * RATE);
    for (let i = 0; i < src.length && at + i < out.length; i++) out[at + i] += src[i] * k;
  }
  for (let i = 0; i < out.length; i++) out[i] = Math.max(-1, Math.min(1, out[i]));
  return out;
}

// 正在跑的子资源（浏览器、服务、ffmpeg、临时目录），收到中断信号时由 main 统一收掉。
const live = new Set();

function runFfmpeg(bin, args) {
  return new Promise((ok, bad) => {
    const child = spawn(bin, args, { stdio: ['ignore', 'ignore', 'pipe'] });
    const kill = () => child.kill('SIGKILL');
    live.add(kill);
    let err = '';
    child.stderr.on('data', (d) => { err = (err + d).slice(-4000); });
    child.on('error', (e) => { live.delete(kill); bad(new RecordError(`ffmpeg 起不来：${e.message}`)); });
    child.on('close', (code, sig) => {
      live.delete(kill);
      if (code === 0) ok();
      else bad(new RecordError(`ffmpeg 失败（${sig || '退出码 ' + code}）：${err.trim().split('\n').slice(-5).join('\n')}`));
    });
  });
}

/**
 * 录一段视频。o：{ inputs, out, params, aspect, scale, chromium, ffmpeg }，log 为进度输出（默认 stderr）。
 * o.sound 为 false 时出无声视频（默认 true），o.vol 是音效整体音量倍数（默认 1）。
 * → { out, seconds, frames, shots, cells: [{kind, hold, anim, sound}], sounds: [{t, sound}]（无声时为空）, ms }
 */
export async function record(o, log = (s) => process.stderr.write(s + '\n')) {
  const t0 = Date.now();
  const cfg = preflight(o);
  const tmp = mkdtempSync(path.join(tmpdir(), 'viewer-rec-'));
  const dropTmp = () => rmSync(tmp, { recursive: true, force: true });
  live.add(dropTmp);
  const www = path.join(tmp, 'www'), shots = path.join(tmp, 'frames');
  mkdirSync(www); mkdirSync(shots);
  const tmpOut = path.join(path.dirname(cfg.out), `.${path.basename(cfg.out)}.${process.pid}.tmp.mp4`);
  const dropOut = () => rmSync(tmpOut, { force: true });
  live.add(dropOut);
  let server = null, browser = null;
  const closeServer = () => server?.close(), closeBrowser = () => browser?.close();
  try {
    // 站点根是空目录：只供给 /viewer/ 和命令行点名的棋谱，别的一概 404。
    const files = Object.fromEntries(cfg.inputs.map((f, i) => [`/rec/${i + 1}.pgn`, f]));
    server = await serve(www, { '/viewer/': VIEWER }, files);
    live.add(closeServer);
    let chromium;
    try {
      ({ chromium } = await import('playwright-core'));
    } catch (e) {
      throw new RecordError(`未安装 playwright-core，请先执行：cd viewer && npm ci --ignore-scripts（${e.message.split('\n')[0]}）`);
    }
    try {
      const chromiumPath = cfg.explicitChromiumPath || resolveChromium(o.chromium, { chromium });
      browser = await chromium.launch({
        executablePath: chromiumPath, handleSIGINT: false, handleSIGTERM: false, handleSIGHUP: false,
      });
    } catch (e) {
      throw new RecordError(`起不来浏览器：${e.message.split('\n')[0]}（用 --chromium 或环境变量 VIEWER_CHROMIUM 指到 Chromium / Chrome）`);
    }
    live.add(closeBrowser);
    const ctx = await browser.newContext({ viewport: { width: cfg.view[0], height: cfg.view[1] }, deviceScaleFactor: cfg.scale });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    const query = new URLSearchParams({ ...o.params, rec: '1' });
    const url = `http://127.0.0.1:${server.port}/viewer/?${query}&files=${Object.keys(files).join(',')}`;
    await page.goto(url);
    try {
      await withTimeout(page.evaluate(() => window.viewer.ready), STEP_TIMEOUT, '页面加载');
    } catch (e) {
      const why = await page.evaluate(() => document.body?.dataset.error).catch(() => null);
      throw new RecordError(`页面没准备好：${why || e.message.split('\n')[0]}`);
    }

    // 一格一格走。cells 是 next() 的原始返回；list 是 [截图文件, 秒数]。
    const cells = [], list = [], cues = [];   // cues：[第几张截图开始响, 哪声]
    let n = 0;
    const shot = async () => {
      const f = path.join(shots, `f${String(n++).padStart(6, '0')}.png`);
      await page.screenshot({ path: f });
      return f;
    };
    for (let i = 0; ; i++) {
      if (i > 100_000) throw new RecordError('走了十万格还没到 end，页面序列不对');
      const r = await withTimeout(page.evaluate(() => window.viewer.next()), STEP_TIMEOUT, `第 ${i + 1} 格`);
      if (errors.length) throw new RecordError(`页面出错：${errors[0]}`);
      if (!r || !(r.hold >= 0) || !(r.anim >= 0 || r.anim === undefined)) {
        throw new RecordError(`next() 返回的不对：${JSON.stringify(r)}`);
      }
      cells.push(r);
      // 走子动画（anim 秒）：约定 next() 兑现时动画已开始并暂停在起点；这里按 1/30 秒逐格拨进度截图，
      // 然后把动画走完，再截静止画面停 hold。这一格总长 = anim + hold（页面给的 hold 已是 gap − anim）。
      // 各张的秒数加起来恰为 anim（末张补齐零头），帧数由 toFrames 按累计时刻取整。
      if (r.anim > 0) {
        const k = Math.max(1, Math.round(r.anim * FPS));
        for (let j = 0; j < k; j++) {
          await page.evaluate((ms) => { for (const a of document.getAnimations()) { a.pause(); a.currentTime = ms; } }, (j * 1000) / FPS);
          list.push([await shot(), j < k - 1 ? 1 / FPS : r.anim - (k - 1) / FPS]);
        }
        await page.evaluate(async () => {
          for (const a of document.getAnimations()) {
            if (a.effect?.getComputedTiming().endTime !== Infinity) a.finish();
          }
          await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
        });
      }
      // 声音响在棋子落地那一刻：动画帧之后、静止画面那一张的开头（没有动画时就是这格开头）。
      if (r.sound) cues.push([list.length, r.sound]);
      if (r.hold > 0) list.push([await shot(), r.hold]);
      if (r.kind === 'end') break;
      if ((i + 1) % 100 === 0) log(`已截 ${i + 1} 格…`);
    }
    live.delete(closeBrowser);
    await browser.close();
    browser = null;
    live.delete(closeServer);
    await server.close();
    server = null;
    if (!list.length) throw new RecordError('一格画面都没有（各格停留时长全是 0？）');

    // concat 列表：每张给足帧数的时长，末张再写一次（否则它的时长被忽略），总帧数在 -vf 用 trim=end_frame 截齐。
    const counts = toFrames(list.map(([, s]) => s));
    const kept = list.map(([f], i) => [f, counts[i]]).filter(([, c]) => c > 0);
    const frames = counts.reduce((a, b) => a + b, 0);
    if (!kept.length || frames <= 0) throw new RecordError('总时长不足 1 帧，无法生成视频（调大停留时长）');
    const lines = kept.flatMap(([f, c]) => [`file '${path.basename(f)}'`, `duration ${(c / FPS).toFixed(6)}`]);
    lines.push(`file '${path.basename(kept.at(-1)[0])}'`);
    const listFile = path.join(shots, 'list.txt');
    writeFileSync(listFile, lines.join('\n') + '\n');

    // 音轨：各声解码成 RATE 采样率的单声道浮点样本，在这里按时刻叠好写成一个文件，作为 ffmpeg 的第二路输入。
    // 不对整条音轨做响度归一化（稀疏的敲击声拉到 −14 LUFS 会刺耳），音量全由 lib/sound.js 的增益定。
    let sounds = [], audioIn = [], audioOut = ['-an'];
    if (o.sound !== false) {
      sounds = cueTimes(list.map(([, s]) => s), cues);
      const pcm = {};
      for (const [k, s] of Object.entries(SOUNDS)) {
        const f = path.join(tmp, `${k}.f32`);
        await runFfmpeg(cfg.ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-i', path.join(VIEWER, s.file),
          '-ac', '1', '-ar', String(RATE), '-f', 'f32le', f]);
        const b = readFileSync(f);
        pcm[k] = new Float32Array(b.buffer.slice(b.byteOffset, b.byteOffset + b.length));   // 拷一份，免得 byteOffset 不对齐
      }
      const mix = path.join(tmp, 'mix.f32');
      writeFileSync(mix, mixTrack(sounds, frames / FPS, pcm, o.vol ?? 1));
      audioIn = ['-f', 'f32le', '-ar', String(RATE), '-ac', '1', '-i', mix];
      // 单声道：素材本来就是单声道；转双声道时 ffmpeg 默认每路压 3 dB，照原样复制又会让 LUFS 读数多 3 dB，
      // 单声道出片则峰值、响度和 lib/sound.js 里定的数一一对得上，手机外放两个喇叭照样都响。
      audioOut = ['-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '128k', '-ar', String(RATE), '-ac', '1'];
    }
    await runFfmpeg(cfg.ffmpeg, [
      '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', listFile, ...audioIn,
      // 截图是全范围 RGB：转 bt709 矩阵的有限范围 yuv420p，并在码流里如实标注。
      '-vf', `fps=${FPS},trim=end_frame=${frames},scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p,setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709`,
      '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
      '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-color_range', 'tv',
      '-r', String(FPS), ...audioOut, '-movflags', '+faststart', '-f', 'mp4', tmpOut,
    ]);
    if (o.force) {
      renameSync(tmpOut, cfg.out);
    } else {
      try {
        linkSync(tmpOut, cfg.out);
        rmSync(tmpOut, { force: true });
      } catch (e) {
        if (e?.code === 'EEXIST') throw new RecordError(`输出文件已存在：${cfg.out}（换个路径，或加 --force 覆盖）`);
        throw e;
      }
    }
    return { out: cfg.out, seconds: frames / FPS, frames, shots: n, cells, sounds, ms: Date.now() - t0 };
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (server) await server.close().catch(() => {});
    rmSync(tmpOut, { force: true });
    dropTmp();
    for (const f of [dropTmp, dropOut, closeServer, closeBrowser]) live.delete(f);
  }
}

async function main() {
  let o;
  try { o = parseCli(process.argv.slice(2)); } catch (e) {
    console.error(`参数不对：${e.message}\n`);
    console.error(HELP);
    process.exit(2);
  }
  if (o.help) { process.stdout.write(HELP); return; }
  let stopping = false;
  const stop = async (sig) => {
    if (stopping) return;
    stopping = true;
    console.error(`收到 ${sig}，收掉浏览器、服务和临时文件后退出`);
    // 后起的先收：先杀 ffmpeg、关浏览器和服务，再删临时文件。
    for (const f of [...live].reverse()) { try { await f(); } catch { /* 尽力收 */ } }
    process.exit(130);
  };
  for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(sig, () => stop(sig));
  try {
    const r = await record(o);
    const kinds = {};
    for (const c of r.cells) kinds[c.kind] = (kinds[c.kind] || 0) + 1;
    const snd = {};
    for (const c of r.sounds) snd[c.sound] = (snd[c.sound] || 0) + 1;
    console.log(`已出片 ${r.out}：${r.seconds.toFixed(2)} 秒（${r.frames} 帧），截图 ${r.shots} 张，`
      + `格数 ${Object.entries(kinds).map(([k, v]) => `${k} ${v}`).join('、')}，`
      + `音效 ${r.sounds.length ? Object.entries(snd).map(([k, v]) => `${k} ${v}`).join('、') : '无'}，用时 ${(r.ms / 1000).toFixed(1)} 秒`);
  } catch (e) {
    if (stopping) return;
    console.error(e instanceof RecordError ? `录制失败：${e.message}` : `录制失败（意外错误）：${e.stack || e}`);
    process.exit(1);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
