// 棋谱阅读器页面外壳（docs/viewer.md）。现在只实现窄版（录屏画面）的静态渲染：给定第几盘、第几个半回合，画出
// 顶部细条、两条棋手条、棋盘、终局横幅。播放、宽版、标题画面、录制接口在后续步骤接到这里。
//
// 网址参数：files=逗号分隔的棋谱路径（按站点根解析）；game=第几盘（从 1 起，默认 1）；ply=半回合数或 end（默认 0）。
// window.viewer.ready：棋谱、棋子图、字体都加载好并画完第一帧才兑现；失败时 reject，并在 body 上写 data-error。
// window.viewer.show(game, ply)：改画另一格，画完（含两帧）才兑现。
import { decodeText, parsePgn, moveNote } from './lib/pgn.js';
import { replay } from './lib/replay.js';
import { playerOf, startMoveNumber, fmtTokens, thinkTotals, points, scoresBefore, fmtScore, resultText } from './lib/match.js';
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
  let banner = over ? resultText(game, xiangqi) : null;
  if (rep.error && ply === steps.length) banner = `第 ${rep.error.ply} 步读不懂：${rep.error.text}`;
  return {
    xiangqi, fen, last: last ? { from: last.from, to: last.to } : null, check: kingSq, banner,
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

// 终局横幅：「黑方胜 · 将死」一行放得下就一行；放不下（结束原因很长）就把原因挪到第二行、小一号，不在词中间折断。
function showBanner(text) {
  const b = $('banner');
  b.hidden = !text;
  b.classList.remove('split');
  if (!text) return;
  const i = text.indexOf(' · ');
  if (i < 0) { b.textContent = text; return; }
  b.replaceChildren(h('span', 'head', text.slice(0, i)), h('span', 'sep', ' · '), h('span', 'why', text.slice(i + 3)));
  if (b.scrollWidth > b.clientWidth) b.classList.add('split');
}

let games = [];
const boards = {};

async function show(gi, ply) {
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
  await show(gi, p === 'end' ? Infinity : Number(p) || 0);
  return true;
}

window.viewer = { show, ready: init() };
window.viewer.ready.catch((e) => { document.body.dataset.error = String(e && e.message || e); console.error(e); });
