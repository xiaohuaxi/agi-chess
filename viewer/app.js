// 棋谱阅读器页面外壳（docs/viewer.md）。现在只有窄版（录屏画面）：顶部细条、两条棋手条、棋盘、终局横幅、标题画面、
// 总比分，加上自动播放、连播和录制接口。宽版另做。
//
// 网址参数（docs/viewer.md「播放」有完整清单）：
//   files=逗号分隔的棋谱路径（按站点根解析，一个文件可以有多盘）；也可以把文件拖进页面。
//   autoplay=1 打开就自动播放；gap / titlehold / resulthold / summaryhold 各格停几秒；title=0 不要标题画面。
//   rec=1 录制模式：隐含 layout=compact，不起任何计时器，由脚本调 viewer.next() 一格一格走。
//   静态看某一格（截图用）：game=第几盘（从 1 起）&ply=半回合数或 end；多盘时 summary=1 看总比分。
// window.viewer.ready：棋谱、棋子图、字体都加载好并画完第一格才兑现；失败时 reject，并在 body 上写 data-error。
// window.viewer.next()：前进一格，画完（再等两帧）才兑现 {kind, hold, anim}；播完后再调返回 {kind: 'end', hold: 0, anim: 0}。
// 播完（到了 end 那格）在 body 上置 data-done="1"，window.viewer.done 为 true。
// window.viewer.play() / pause()：自动播放的开关（rec=1 时不起作用）；空格键同样切换。
// window.viewer.show(game, ply) / summary()：直接画某一格（截图、调试用）。
import { decodeText, parsePgn, moveNote } from './lib/pgn.js';
import { replay } from './lib/replay.js';
import { playerOf, fullName, startMoveNumber, fmtTokens, thinkTotals, points, scoresBefore, fmtScore, resultParts, totals } from './lib/match.js';
import { playOptions, sequence } from './lib/play.js';
import { ChessBoard, kingSquare } from './lib/chessboard.js';
import { XiangqiBoard, xqKingSquare } from './lib/xqboard.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const REC = params.get('rec') === '1';   // 录制模式；现在只有窄版，所以「隐含 layout=compact」不用另做
const OPT = playOptions(params);
const frames = (n = 2) => new Promise((ok) => {
  const step = () => (n-- <= 0 ? ok() : requestAnimationFrame(step));
  step();
});

// ---------------------------------------------------------------- 读棋谱
async function fetchTexts(paths) {
  return Promise.all(paths.map(async (p) => {
    const res = await fetch(p);
    if (!res.ok) throw new Error(`读不到棋谱 ${p}：${res.status}`);
    return decodeText(new Uint8Array(await res.arrayBuffer()));
  }));
}

function parseGames(texts) {
  return texts.flatMap((t) => parsePgn(t)).map((game) => {
    const rep = replay(game);
    const notes = game.moves.slice(0, rep.steps.length).map(moveNote);
    const startTurn = rep.kind === 'xiangqi'
      ? (/\sb(\s|$)/.test(rep.start) ? 'b' : 'w')
      : rep.start.split(' ')[1];
    return { game, rep, notes, startTurn, tokens: thinkTotals(notes), xiangqi: rep.kind === 'xiangqi' };
  });
}

// ---------------------------------------------------------------- 一格画面要显示什么（纯数据）
// final：画成终局那格（横幅、比分加上这盘、「胜」）。播放时走完最后一步那格还不是终局，下一格 result 才是；
// 这时两边都不点亮（棋已经下完，不该让输的一方亮着等走棋）。
function frameData(games, gi, ply, final = true) {
  const g = games[gi], { game, rep, notes, startTurn, tokens, xiangqi } = g;
  const steps = rep.steps;
  ply = Math.max(0, Math.min(ply, steps.length));
  const ended = ply === steps.length && points(game.result ?? game.tags.Result) !== null;
  const over = ended && final;
  const pts = over ? points(game.result ?? game.tags.Result) : null;
  const match = games.length > 1;
  const before = scoresBefore(games.map((x) => x.game), gi);
  const toMove = ply === 0 ? startTurn : steps[ply - 1].side === 'w' ? 'b' : 'w';
  const moveNo0 = startMoveNumber(game);
  const side = (s) => {
    const p = playerOf(game, s);
    let j = ply - 1;
    while (j >= 0 && steps[j].side !== s) j--;
    let move = null;
    if (j >= 0) {
      const st = steps[j];
      const n = moveNo0 + Math.floor((j + (startTurn === 'b' ? 1 : 0)) / 2);
      const text = xiangqi ? st.text : st.san.replace(/[+#]$/, '');
      move = { text: s === 'w' ? `${n}. ${text}` : `${n}... ${text}`, check: st.check && j === ply - 1 };
    }
    const think = tokens.has[s] ? {
      total: fmtTokens(tokens.think[s][ply]),
      delta: ply > 0 && steps[ply - 1].side === s && notes[ply - 1].cmds.think !== undefined
        ? '+' + fmtTokens(notes[ply - 1].cmds.think) : null,
    } : null;
    const score = match ? fmtScore((before[p.key] || 0) + (pts ? pts[s] : 0)) : null;
    return { ...p, disc: s === 'w' ? (xiangqi ? 'red' : 'white') : 'black', move, think, score,
             active: !ended && toMove === s, won: !!pts && pts[s] === 1 };
  };
  const last = ply > 0 ? steps[ply - 1] : null;
  const fen = last ? last.fen : rep.start;
  const inCheck = last && last.check;
  const kingSq = inCheck ? (xiangqi ? xqKingSquare(fen, toMove) : kingSquare(fen, toMove)) : null;
  let banner = null;
  if (over) {
    const r = resultParts(game, xiangqi);
    banner = { head: r.head, why: r.why, winner: r.winner ? playerOf(game, r.winner) : null };
  }
  if (rep.error && ply === steps.length && final) banner = { head: `第 ${rep.error.ply} 步读不懂：${rep.error.text}`, why: '', winner: null };
  const mated = !!(over && inCheck && pts && pts.w !== pts.b);
  return {
    xiangqi, fen, last: last ? { from: last.from, to: last.to } : null, check: kingSq, mated, banner,
    strip: match ? `第 ${gi + 1} 局 · 共 ${games.length} 局` : null,
    top: side('b'), bottom: side('w'),
  };
}

// ---------------------------------------------------------------- 画出来
function h(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

// 名字太长时从中间省略（思考深度、比分不截）：逐字从中间去掉，直到放得下。
function fitMiddle(span, full) {
  span.textContent = full;
  if (span.scrollWidth <= span.clientWidth) return;
  const cs = Array.from(full);
  for (let keep = cs.length - 1; keep > 1; keep--) {
    const head = Math.ceil(keep / 2), tail = keep - head;
    span.textContent = cs.slice(0, head).join('') + '…' + cs.slice(cs.length - tail).join('');
    if (span.scrollWidth <= span.clientWidth) return;
  }
}

function renderBar(el, d) {
  el.className = 'bar' + (d.active ? ' active' : '') + (d.won ? ' done' : '');
  const row1 = h('div', 'row1');
  row1.append(h('span', 'disc ' + d.disc));
  const name = h('span', 'name');
  row1.append(name);
  if (d.effort) row1.append(h('span', 'effort', '+' + d.effort));
  if (d.won) row1.append(h('span', 'win', '胜'));
  if (d.score !== null) row1.append(h('span', 'score', d.score));
  const row2 = h('div', 'row2');
  const mv = h('span', 'move');
  if (d.move) {
    mv.append(h('span', 'mv', d.move.text));
    if (d.move.check) mv.append(h('span', 'tag', '将军'));
  }
  row2.append(mv);
  if (d.think) {
    const t = h('span', 'think', '思考 ' + d.think.total);
    if (d.think.delta) t.append(h('span', 'delta', d.think.delta));
    row2.append(t);
  }
  el.replaceChildren(row1, row2);
  fitMiddle(name, d.name);
}

// 终局横幅：第一行「黑方胜 · 将死」（放不下就把原因挪到下一行、小一号）；第二行胜方名字，太长从中间省略，和棋没有这行。
function showBanner(d) {
  const b = $('banner');
  b.hidden = !d;
  b.classList.remove('split');
  if (!d) return;
  const head = h('div', 'b-head');
  head.append(h('span', 'res', d.head));
  if (d.why) head.append(h('span', 'sep', ' · '), h('span', 'why', d.why));
  const kids = [head];
  let name = null;
  if (d.winner) {
    const row = h('div', 'b-name');
    name = h('span', 'name');
    row.append(name);
    if (d.winner.effort) row.append(h('span', 'effort', '+' + d.winner.effort));
    kids.push(row);
  }
  b.replaceChildren(...kids);
  if (head.scrollWidth > head.clientWidth) b.classList.add('split');
  if (name) fitMiddle(name, d.winner.name);
}

// 总比分画面（多盘连播播完后的一格，docs/viewer.md「播放」的 kind=end）：棋种、标题 + 每人一行名字与总分，领先的一行点亮。
function showSummary() {
  const rows = totals(games.map((g) => g.game));
  const box = $('summary');
  // 这格没有棋盘，所以写明棋种；清单里混了两种棋就都写上
  const kinds = [...new Set(games.map((g) => (g.xiangqi ? '中国象棋' : '国际象棋')))].join(' / ');
  const kids = [h('div', 's-kind', kinds), h('div', 's-title', `总比分 · 共 ${games.length} 局`)];
  const names = [];
  rows.forEach((p, i) => {
    const row = h('div', 's-row' + (i === 0 && p.score > rows[rows.length - 1].score ? ' top' : ''));
    const name = h('span', 'name');
    row.append(name);
    if (p.effort) row.append(h('span', 'effort', '+' + p.effort));
    row.append(h('span', 'score', fmtScore(p.score)));
    kids.push(row);
    names.push([name, p.name]);
  });
  box.replaceChildren(...kids);
  for (const [el, full] of names) fitMiddle(el, full);
}

// 标题画面（每盘开头一格，盖在开局局面上）：棋种与第几局，双方全称（带厂商）与思考深度，红 / 白方在前。
function showTitle(gi) {
  const g = games[gi], box = $('title');
  const head = [g.xiangqi ? '中国象棋' : '国际象棋'];
  if (games.length > 1) head.push(`第 ${gi + 1} 局 · 共 ${games.length} 局`);
  const kids = [h('div', 't-head', head.join(' · '))];
  const names = [];
  for (const s of ['w', 'b']) {
    if (s === 'b') kids.push(h('div', 't-vs', '对'));
    const p = fullName(g.game, s);
    const row = h('div', 't-row');
    row.append(h('span', 'disc ' + (s === 'w' ? (g.xiangqi ? 'red' : 'white') : 'black')));
    const name = h('span', 'name');
    row.append(name);
    if (p.effort) row.append(h('span', 'effort', '+' + p.effort));
    kids.push(row);
    names.push([name, p.name]);
  }
  box.replaceChildren(...kids);
  box.hidden = false;
  for (const [el, full] of names) fitMiddle(el, full);
}

let games = [];
const boards = {};

// opts.final：见 frameData（默认 true，静态看 ply=end 时带横幅）；opts.title：盖上标题画面。
async function show(gi, ply, opts = {}) {
  $('stage').classList.remove('summary', 'empty');
  $('summary').hidden = true;
  $('title').hidden = true;
  const d = frameData(games, gi, ply, opts.final ?? true);
  $('strip').hidden = !d.strip;
  $('strip').textContent = d.strip || '';
  renderBar($('bar-top'), d.top);
  renderBar($('bar-bottom'), d.bottom);
  $('board-chess').hidden = d.xiangqi;
  $('board-xq').hidden = !d.xiangqi;
  await (d.xiangqi ? boards.xq : boards.chess).render(d);
  showBanner(d.banner);
  if (opts.title) showTitle(gi);
  await document.fonts.ready;
  await frames(2);
}

async function summary() {
  $('stage').classList.remove('empty');
  $('stage').classList.add('summary');
  $('strip').hidden = true;
  $('summary').hidden = false;
  showSummary();
  await document.fonts.ready;
  await frames(2);
}

// ---------------------------------------------------------------- 播放
let seq = [], cur = -1, done = false;
let chain = Promise.resolve();          // next() 串行：上一格画完才画下一格
let run = 0, playing = false, wake = null;   // run 是自动播放的轮次编号，pause() 让正在跑的那轮作废

function setDone(v) {
  done = v;
  if (v) document.body.dataset.done = '1';
  else delete document.body.dataset.done;
}

function resetSequence() {
  seq = sequence(games.map((g) => ({
    plies: g.rep.steps.length,
    over: !!g.rep.error || points(g.game.result ?? g.game.tags.Result) !== null,
  })), OPT);
  cur = -1;
  setDone(false);
}

async function draw(f) {
  if (f.kind === 'end') {
    if (games.length > 1) await summary();
    else await frames(2);                // 单盘：不改画面
    return;
  }
  await show(f.game, f.ply, { final: f.kind === 'result', title: f.kind === 'title' });
}

function next() {
  const step = async () => {
    if (!seq.length || cur >= seq.length - 1) return { kind: 'end', hold: 0, anim: 0 };
    const f = seq[++cur];
    await draw(f);
    if (f.kind === 'end') setDone(true);
    return { kind: f.kind, hold: f.hold, anim: 0 };   // 走子动画还没做，anim 恒为 0
  };
  const p = chain.then(step);
  chain = p.catch(() => {});
  return p;
}

function fail(e) {
  document.body.dataset.error = String(e && e.message || e);
  console.error(e);
}

// 自动播放：画一格、停 hold 秒、再下一格，到 end 那格为止。播完再调从头来。
async function play() {
  if (REC || playing || !seq.length) return;
  if (done) resetSequence();
  playing = true;
  const me = ++run;
  try {
    while (me === run) {
      const r = await next();
      if (me !== run || cur >= seq.length - 1) break;
      await new Promise((ok) => { wake = ok; setTimeout(ok, r.hold * 1000); });
    }
  } catch (e) {
    fail(e);
  } finally {
    if (me === run) playing = false;
  }
}

function pause() {
  run++;
  playing = false;
  if (wake) wake();
}

// ---------------------------------------------------------------- 载入
async function ensureBoards() {
  // 用到哪种棋就先加载哪种棋盘（棋子图读好、解码完）
  // （cm-chessboard 在构造时按容器尺寸定棋盘大小，所以加载时先让容器显示出来，show() 再按当前这盘切换）
  if (!boards.chess && games.some((g) => !g.xiangqi)) {
    $('board-chess').hidden = false;
    boards.chess = new ChessBoard($('board-chess'));
    await boards.chess.load();
  }
  if (!boards.xq && games.some((g) => g.xiangqi)) { boards.xq = new XiangqiBoard($('board-xq')); await boards.xq.load(); }
}

async function useTexts(texts) {
  const gs = parseGames(texts);
  if (!gs.length) throw new Error('棋谱里没有读到对局');
  pause();
  await chain;
  games = gs;
  $('stage').classList.remove('empty');
  await ensureBoards();
  resetSequence();
  delete document.body.dataset.error;
}

function showHint(text) {
  $('stage').classList.add('empty');
  $('hint').textContent = text;
}

async function init() {
  const files = (params.get('files') || '').split(',').map((s) => s.trim()).filter(Boolean);
  if (!files.length) {
    if (REC) throw new Error('没给棋谱：网址加 ?files=/runs/xxx/game.pgn');
    showHint('把棋谱文件（.pgn）拖进来\n或在网址后加 ?files=/runs/xxx/game.pgn');
    return true;
  }
  await useTexts(await fetchTexts(files));
  const still = !REC && params.get('autoplay') !== '1' && ['game', 'ply', 'summary'].some((k) => params.has(k));
  if (still) {                                            // 静态看某一格
    const gi = Math.max(0, Math.min(games.length - 1, (Number(params.get('game')) || 1) - 1));
    const p = params.get('ply');
    if (params.get('summary') === '1' && games.length > 1) await summary();
    else await show(gi, p === 'end' ? Infinity : Number(p) || 0);
  } else {
    await draw(seq[0]);                                   // 先画出第一格；next() 第一次调用仍从这一格算起
  }
  if (!REC && params.get('autoplay') === '1') play();
  return true;
}

// 拖文件进页面：按文件名排序后当作一场比赛，从头播（autoplay=0 时只画第一格）。
async function onDrop(e) {
  e.preventDefault();
  const list = [...(e.dataTransfer?.files || [])].sort((a, b) => a.name.localeCompare(b.name));
  if (!list.length) return;
  try {
    await useTexts(await Promise.all(list.map(async (f) => decodeText(new Uint8Array(await f.arrayBuffer())))));
    if (!REC && params.get('autoplay') !== '0') play();
    else await draw(seq[0]);
  } catch (err) {
    fail(err);
    showHint(document.body.dataset.error);
  }
}
document.addEventListener('dragover', (e) => e.preventDefault());
document.addEventListener('drop', onDrop);
document.addEventListener('keydown', (e) => {
  if (REC || e.code !== 'Space') return;
  e.preventDefault();
  if (playing) pause(); else play();
});

window.viewer = {
  show, summary, next, play, pause,
  get done() { return done; },
  ready: init(),
};
window.viewer.ready.catch(fail);
