// 棋谱阅读器页面外壳（docs/viewer.md）。现在只实现窄版（录屏画面）的静态渲染：给定第几盘、第几个半回合，画出
// 顶部细条、两条棋手条、棋盘、终局横幅。播放、宽版、标题画面、录制接口在后续步骤接到这里。
//
// 网址参数：files=逗号分隔的棋谱路径（按站点根解析）；game=第几盘（从 1 起，默认 1）；ply=半回合数或 end（默认 0）。
// window.viewer.ready：棋谱、棋子图、字体都加载好并画完第一帧才兑现；失败时 reject，并在 body 上写 data-error。
// window.viewer.show(game, ply)：改画另一格，画完（含两帧）才兑现。window.viewer.summary()：多盘连播播完后的总比分画面。
import { decodeText, parsePgn, moveNote } from './lib/pgn.js';
import { replay } from './lib/replay.js';
import { playerOf, startMoveNumber, fmtTokens, thinkTotals, points, scoresBefore, fmtScore, resultParts, totals } from './lib/match.js';
import { ChessBoard, kingSquare } from './lib/chessboard.js';
import { XiangqiBoard, xqKingSquare } from './lib/xqboard.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const frames = (n = 2) => new Promise((ok) => {
  const step = () => (n-- <= 0 ? ok() : requestAnimationFrame(step));
  step();
});

// ---------------------------------------------------------------- 读棋谱
async function loadGames(paths) {
  const texts = await Promise.all(paths.map(async (p) => {
    const res = await fetch(p);
    if (!res.ok) throw new Error(`读不到棋谱 ${p}：${res.status}`);
    return decodeText(new Uint8Array(await res.arrayBuffer()));
  }));
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
function frameData(games, gi, ply) {
  const g = games[gi], { game, rep, notes, startTurn, tokens, xiangqi } = g;
  const steps = rep.steps;
  ply = Math.max(0, Math.min(ply, steps.length));
  const over = ply === steps.length && points(game.result ?? game.tags.Result) !== null;
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
             active: !over && toMove === s, won: !!pts && pts[s] === 1 };
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
  if (rep.error && ply === steps.length) banner = { head: `第 ${rep.error.ply} 步读不懂：${rep.error.text}`, why: '', winner: null };
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

// 总比分画面（多盘连播播完后的一格，docs/viewer.md「播放」的 kind=end）：标题 + 每人一行名字与总分，领先的一行点亮。
function showSummary() {
  const rows = totals(games.map((g) => g.game));
  const box = $('summary');
  const kids = [h('div', 's-title', `总比分 · 共 ${games.length} 局`)];
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

let games = [];
const boards = {};

async function show(gi, ply) {
  $('stage').classList.remove('summary');
  $('summary').hidden = true;
  const d = frameData(games, gi, ply);
  $('strip').hidden = !d.strip;
  $('strip').textContent = d.strip || '';
  renderBar($('bar-top'), d.top);
  renderBar($('bar-bottom'), d.bottom);
  $('board-chess').hidden = d.xiangqi;
  $('board-xq').hidden = !d.xiangqi;
  await (d.xiangqi ? boards.xq : boards.chess).render(d);
  showBanner(d.banner);
  await document.fonts.ready;
  await frames(2);
}

async function summary() {
  $('stage').classList.add('summary');
  $('strip').hidden = true;
  $('summary').hidden = false;
  showSummary();
  await document.fonts.ready;
  await frames(2);
}

async function init() {
  const files = (params.get('files') || '').split(',').map((s) => s.trim()).filter(Boolean);
  if (!files.length) throw new Error('没给棋谱：网址加 ?files=/runs/xxx/game.pgn');
  games = await loadGames(files);
  if (!games.length) throw new Error('棋谱里没有读到对局');
  // 用到哪种棋就先加载哪种棋盘（棋子图读好、解码完）
  // （cm-chessboard 在构造时按容器尺寸定棋盘大小，所以加载时先让容器显示出来，show() 再按当前这盘切换）
  if (games.some((g) => !g.xiangqi)) {
    $('board-chess').hidden = false;
    boards.chess = new ChessBoard($('board-chess'));
    await boards.chess.load();
  }
  if (games.some((g) => g.xiangqi)) { boards.xq = new XiangqiBoard($('board-xq')); await boards.xq.load(); }
  const gi = Math.max(0, Math.min(games.length - 1, (Number(params.get('game')) || 1) - 1));
  const p = params.get('ply');
  if (params.get('summary') === '1' && games.length > 1) await summary();
  else await show(gi, p === 'end' ? Infinity : Number(p) || 0);
  return true;
}

window.viewer = { show, summary, ready: init() };
window.viewer.ready.catch((e) => { document.body.dataset.error = String(e && e.message || e); console.error(e); });
