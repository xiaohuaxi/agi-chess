// 棋谱阅读器页面外壳（docs/viewer.md）。两种版式共用：顶部细条、两条棋手条、棋盘、终局横幅、标题画面、总比分，
// 加上自动播放、连播和录制接口。宽版（给人读棋谱）右边多一栏：对局信息、播放按钮、着法列表、这步的评注和数字。
// 版式：layout=compact / wide 强制，不给按窗口宽度自动选（宽 ≥ WIDE_MIN 用宽版，窗口改大小时跟着切）；rec=1 恒为窄版。
// 键盘（rec=1 时都不理）：← → 单步，空格 播放 / 暂停，Home / End 本盘首尾，PgUp / PgDn 上一盘 / 下一盘；
// 手动跳步会先停下自动播放，再播从跳到的那一格接着往下。
//
// 网址参数（docs/viewer.md「播放」有完整清单）：
//   files=逗号分隔的棋谱路径（按站点根解析，一个文件可以有多盘）；也可以把文件拖进页面。
//   autoplay=1 打开就自动播放；gap / titlehold / resulthold / summaryhold 各格停几秒，openhold 每盘开局局面停几秒（默认同 gap）；
//   title=1 加标题画面（默认不加）；
//   anim=走子滑动的秒数（默认 0.3，算在 gap 之内，0 关掉）。静态看某一格不带动画。
//   rec=1 录制模式：隐含 layout=compact，不起任何计时器，由脚本调 viewer.next() 一格一格走。
//   sound=1 打开走子音效（默认静音；浏览器要等页面上有过一次点击或按键才放得出声），vol=整体音量倍数（默认 1）。
//   录制时页面不出声，声音由录制脚本按 next() 给的 sound 混进视频。
//   静态看某一格（截图用）：game=第几盘（从 1 起）&ply=半回合数或 end；多盘时 summary=1 看总比分。
//   lang=en 英文界面（默认中文；对照表在 lib/i18n.js，象棋着法改显示 WXF 记法）；
//   names=棋谱里的名字=显示名,…  覆盖棋手显示名（两种语言都认，写法见 lib/i18n.js 的 parseNames）。
// window.viewer.ready：棋谱、棋子图、字体都加载好并画完第一格才兑现；失败时 reject，并在 body 上写 data-error。
// window.viewer.next()：前进一格，画完（再等两帧）才兑现 {kind, hold, anim, sound}；播完后再调返回 {kind: 'end', hold: 0, anim: 0, sound: null}。
//   sound 是这格响哪声（'move' / 'capture' / 'end' / null），响在这格开头再过 anim 秒（棋子落地那一刻）。
//   anim > 0 时这格开头有走子滑动：rec=1 下兑现时动画已开始、停在起点，由录制脚本拨进度；这格总长 anim + hold = gap。
// 播完（到了 end 那格）在 body 上置 data-done="1"，window.viewer.done 为 true。
// window.viewer.play() / pause()：自动播放的开关（rec=1 时不起作用）；空格键同样切换。
// window.viewer.show(game, ply) / summary()：直接画某一格（截图、调试用）。
import { decodeText, moveNote } from './lib/pgn.js';
import { loadGamesWithAnalysis } from './lib/replay.js';
import { playerOf, fullName, startMoveNumber, fmtTokens, thinkTotals, points, scoresBefore, fmtScore, resultParts, resultText, totals } from './lib/match.js';
import { moveRows, nagLabel, noteItems } from './lib/panel.js';
import { playOptions, sequence } from './lib/play.js';
import { T, langOf, parseNames } from './lib/i18n.js';
import { SOUNDS, linear, soundOptions, stepSound } from './lib/sound.js';
import { ChessBoard, kingSquare } from './lib/chessboard.js';
import { XiangqiBoard, xqKingSquare } from './lib/xqboard.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const REC = params.get('rec') === '1';   // 录制模式，隐含 layout=compact
const OPT = playOptions(params);
const SND = REC ? { on: false, vol: 1 } : soundOptions(params);   // 录制时页面不出声，脚本自己混音
const VENDOR = params.get('vendor') !== '0';   // 标题画面名字前补厂商（「GPT astra」），vendor=0 不补
const LANG = langOf(params), L = T(LANG);      // 界面语言：lang=en 英文，默认中文
const NAMES = parseNames(params.get('names')); // 显示名覆盖，没给就是空表
const pl = (game, side) => playerOf(game, side, NAMES);
const TITLE_INSET = 24;                        // 标题卡片左右各离棋盘边多远
const FORCED = REC ? 'compact' : ['compact', 'wide'].includes(params.get('layout')) ? params.get('layout') : null;
// 自动选版式的分界。录 16:9 时页面宽 960 会判成宽版，所以录制靠 rec=1（恒为窄版），不靠自动判断
const WIDE_MIN = 900;
const frames = (n = 2) => new Promise((ok) => {
  const step = () => (n-- <= 0 ? ok() : requestAnimationFrame(step));
  step();
});

// ---------------------------------------------------------------- 读棋谱
async function fetchTexts(paths) {
  return Promise.all(paths.map(async (p) => {
    const res = await fetch(p);
    if (!res.ok) throw new Error(`读不到棋谱 ${p}：${res.status}`);
    return { name: p, text: decodeText(new Uint8Array(await res.arrayBuffer())) };
  }));
}

function parseGames(inputs) {
  return loadGamesWithAnalysis(inputs).map(({ game, rep }) => {
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
    const p = pl(game, s);
    let j = ply - 1;
    while (j >= 0 && steps[j].side !== s) j--;
    let move = null;
    if (j >= 0) {
      const st = steps[j];
      const n = moveNo0 + Math.floor((j + (startTurn === 'b' ? 1 : 0)) / 2);
      const text = xiangqi ? (LANG === 'en' ? st.wxf : st.text) : st.san.replace(/[+#]$/, '');
      // 回合号：国际象棋黑方照标准写「11...」；中国象棋黑方不带省略号，写「11. 马３退２」（用户 2026-09-30 定，只改显示）
      move = { text: s === 'w' || xiangqi ? `${n}. ${text}` : `${n}... ${text}`, check: st.check && j === ply - 1 };
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
    const r = resultParts(game, xiangqi, LANG);
    banner = { head: r.head, why: r.why, winner: r.winner ? pl(game, r.winner) : null };
  }
  if (rep.error && ply === steps.length && final) banner = { head: L.unreadable(rep.error.ply, rep.error.text), why: '', winner: null };
  const mated = !!(over && inCheck && pts && pts.w !== pts.b);
  return {
    xiangqi, fen, last: last ? { from: last.from, to: last.to } : null, check: kingSq, mated, banner,
    prev: ply > 1 ? steps[ply - 2].fen : ply === 1 ? rep.start : null,   // 走这步之前的局面（画走子滑动用）
    strip: match ? L.gameOf(gi + 1, games.length) : null,
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
  if (d.won) row1.append(h('span', 'win', L.won));
  if (d.score !== null) row1.append(h('span', 'score', d.score));
  const row2 = h('div', 'row2');
  const mv = h('span', 'move');
  if (d.move) {
    mv.append(h('span', 'mv', d.move.text));
    if (d.move.check) mv.append(h('span', 'tag', L.check));
  }
  row2.append(mv);
  if (d.think) {
    const t = h('span', 'think', L.thinking + ' ' + d.think.total);
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
  const rows = totals(games.map((g) => g.game), NAMES);
  const box = $('summary');
  // 这格没有棋盘，所以写明棋种；清单里混了两种棋就都写上
  const kinds = [...new Set(games.map((g) => (g.xiangqi ? L.xiangqi : L.chess)))].join(' / ');
  const kids = [h('div', 's-kind', kinds), h('div', 's-title', L.finalScore(games.length))];
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

// 标题画面（每盘开头一格，盖在开局局面上）：第几局（多盘时），双方全称与思考深度，红 / 白方在前。
// 不写棋种（棋盘一看便知，用户 2026-09-30）；名字前补厂商，网址参数 vendor=0 不补。
// 卡片左右各离棋盘边 24：象棋棋盘比页面窄，按棋盘实际位置算，两种棋看着一样。
function showTitle(gi) {
  const g = games[gi], box = $('title');
  const kids = games.length > 1 ? [h('div', 't-head', L.gameOf(gi + 1, games.length))] : [];
  const names = [];
  for (const s of ['w', 'b']) {
    if (s === 'b') kids.push(h('div', 't-vs', L.vs));
    const p = fullName(g.game, s, VENDOR, NAMES);
    const row = h('div', 't-row');
    row.append(h('span', 'disc ' + (s === 'w' ? (g.xiangqi ? 'red' : 'white') : 'black')));
    const name = h('span', 'name');
    row.append(name);
    if (p.effort) row.append(h('span', 'effort', '+' + p.effort));
    kids.push(row);
    names.push([name, p.name]);
  }
  box.replaceChildren(...kids);
  const area = $('board-area').getBoundingClientRect(), bd = $(g.xiangqi ? 'board-xq' : 'board-chess').getBoundingClientRect();
  box.style.left = `${bd.left - area.left + TITLE_INSET}px`;
  box.style.right = `${area.right - bd.right + TITLE_INSET}px`;
  box.hidden = false;
  for (const [el, full] of names) fitMiddle(el, full);
}

// ---------------------------------------------------------------- 宽版右栏
// 换了一盘（或换了棋谱）才重建对局信息和着法列表；同一盘里走动只改高亮和下面的评注。
let side = { games: null, gi: -1, cells: new Map() };

function renderSide(gi, ply, final) {
  const g = games[gi], { game, rep, notes, startTurn, xiangqi } = g;
  const steps = rep.steps;
  if (side.games !== games || side.gi !== gi) {
    side = { games, gi, cells: new Map() };
    // 对局信息：棋种、第几局（多盘时是下拉框，可以换盘）
    const head = [h('span', null, xiangqi ? L.xiangqi : L.chess)];
    if (games.length > 1) {
      const sel = h('select');
      sel.id = 's-game';
      sel.title = L.switchGame;
      games.forEach((x, i) => {
        const o = h('option', null, L.gameItem(i + 1, pl(x.game, 'w').name, pl(x.game, 'b').name, x.game.result ?? x.game.tags.Result ?? '*'));
        o.value = i;
        sel.append(o);
      });
      sel.value = gi;
      head.push(sel);
    }
    $('s-head').replaceChildren(...head);
    // 双方：圆片、全称、思考深度；最后一行结果
    const ps = ['w', 'b'].map((s) => {
      const p = fullName(game, s, true, NAMES), row = h('div', 'p');
      row.append(h('span', 'disc ' + (s === 'w' ? (xiangqi ? 'red' : 'white') : 'black')), h('span', 'pname', p.name));
      if (p.effort) { const e = h('span', 'eff', L.effort + ' '); e.append(h('b', null, p.effort)); row.append(e); }
      return row;
    });
    const res = rep.error ? L.unreadable(rep.error.ply, rep.error.text) : resultText(game, xiangqi, LANG) || L.unfinished;
    $('s-players').replaceChildren(...ps, h('div', 'res', L.result + res));
    // 着法列表：开局一格，之后每回合一行（回合号、红 / 白、黑），末尾写结果
    const list = [];
    const start = h('div', 'r');
    const s0 = h('div', 'm start', L.start);
    s0.dataset.ply = 0;
    side.cells.set(0, s0);
    start.append(h('div', 'no'), s0);
    list.push(start);
    for (const r of moveRows(steps, game.moves, startTurn, startMoveNumber(game), xiangqi, LANG === 'en')) {
      const row = h('div', 'r');
      row.append(h('div', 'no', r.no + '.'));
      for (const s of ['w', 'b']) {
        const c = h('div', 'm', r[s] ? r[s].text : '');
        if (r[s]) {
          c.dataset.ply = r[s].ply;
          const nag = game.moves[r[s].ply - 1].nags[0];
          if ([2, 4, 6].includes(nag)) c.classList.add('bad');
          if ([1, 3, 5].includes(nag)) c.classList.add('good');
          side.cells.set(r[s].ply, c);
        } else c.style.visibility = 'hidden';
        row.append(c);
      }
      list.push(row);
    }
    list.push(h('div', 'end', res));
    $('s-moves').replaceChildren(...list);
  }
  const sel = $('s-game');
  if (sel) sel.value = gi;
  for (const c of $('s-moves').querySelectorAll('.cur')) c.classList.remove('cur');
  const cell = side.cells.get(ply);
  if (cell) {
    cell.classList.add('cur');
    const box = $('s-moves'), top = cell.offsetTop, bottom = top + cell.offsetHeight;
    if (top < box.scrollTop + 8) box.scrollTop = Math.max(0, top - 8);            // 只滚列表本身，不动页面
    else if (bottom > box.scrollTop + box.clientHeight - 8) box.scrollTop = bottom - box.clientHeight + 8;
  }
  $('s-note').replaceChildren(...noteView(g, ply, final));
}

// 当前这步的评注：记谱、标注、谁走的；各项数字（带中文标签）；理由文字；不认识的命令原样列出。
function noteView(g, ply, final) {
  const { game, rep, notes, startTurn, xiangqi } = g;
  if (ply === 0) {
    const kids = [h('div', 'n-head', L.startPos)];
    if (game.pre.length) kids.push(h('div', 'lbl', L.comment), h('div', 'why', game.pre.join('\n')));
    return kids;
  }
  const st = rep.steps[ply - 1], note = notes[ply - 1], move = game.moves[ply - 1];
  const no = startMoveNumber(game) + Math.floor((ply - 1 + (startTurn === 'b' ? 1 : 0)) / 2);
  const text = xiangqi ? (LANG === 'en' ? st.wxf : st.text) : st.san;
  const head = h('div', 'n-head', `${no}${st.side === 'w' || xiangqi ? '.' : '...'} ${text}`);   // 象棋黑方不带省略号
  for (const n of move.nags) head.append(h('span', 'nag' + ([2, 4, 6].includes(n) ? ' bad' : [1, 3, 5].includes(n) ? ' good' : ''), nagLabel(n, LANG)));
  if (st.check) head.append(h('span', 'nag bad', L.check));
  const p = pl(game, st.side);
  head.append(h('span', 'who', p.name + (p.effort ? '+' + p.effort : '')));
  const kids = [head];
  const items = noteItems(note, LANG);
  if (items.length) {
    const dl = h('dl');
    for (const it of items) {
      dl.append(h('dt', null, it.label));
      dl.append(h('dd', ['illegal', 'flagged', 'empty'].includes(it.key) && it.value !== '0' ? 'warn' : null, it.value));
    }
    kids.push(dl);
  }
  if (note.text) kids.push(h('div', 'lbl', L.reason), h('div', 'why', note.text));
  if (note.unknown.length) kids.push(h('div', 'lbl', L.otherCmds), h('div', 'raw', note.unknown.join(' ')));
  if (!items.length && !note.text && !note.unknown.length) kids.push(h('div', 'none', L.noNote));
  if (final && ply === rep.steps.length) {
    const r = rep.error ? L.unreadable(rep.error.ply, rep.error.text) : resultText(game, xiangqi, LANG);
    if (r) kids.push(h('div', 'lbl', L.finalLbl), h('div', null, r));
  }
  return kids;
}

let games = [];
const boards = {};
let pos = { gi: 0, ply: 0, opts: {} };   // 现在画着哪一格（总比分那格不改它）
let wide = false;

// opts.final：见 frameData（默认 true，静态看 ply=end 时带横幅）；opts.title：盖上标题画面；
// opts.anim：走子滑动的秒数（0 或不给就不动），rec=1 时动画停在起点等录制脚本拨进度。
async function show(gi, ply, opts = {}) {
  $('stage').classList.remove('summary', 'empty');
  $('summary').hidden = true;
  $('title').hidden = true;
  ply = Math.max(0, Math.min(ply, games[gi].rep.steps.length));
  pos = { gi, ply, opts };
  const d = frameData(games, gi, ply, opts.final ?? true);
  $('strip').hidden = !d.strip;
  $('strip').textContent = d.strip || '';
  renderBar($('bar-top'), d.top);
  renderBar($('bar-bottom'), d.bottom);
  $('board-chess').hidden = d.xiangqi;
  $('board-xq').hidden = !d.xiangqi;
  $('stage').classList.toggle('xq', d.xiangqi);
  const other = d.xiangqi ? boards.chess : boards.xq;
  other?.moves.stop();                   // 换了棋种：另一块棋盘上没走完的那段直接结束
  await (d.xiangqi ? boards.xq : boards.chess).render(d, { anim: opts.anim || 0, paused: REC });
  showBanner(d.banner);
  if (opts.title) showTitle(gi);
  if (wide) renderSide(gi, ply, opts.final ?? true);
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

const hasEnd = (g) => !!g.rep.error || points(g.game.result ?? g.game.tags.Result) !== null;

function resetSequence() {
  seq = sequence(games.map((g) => ({
    plies: g.rep.steps.length,
    over: hasEnd(g),
    captures: g.rep.steps.map((st) => stepSound(st) === 'capture'),
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
  await show(f.game, f.ply, { final: f.kind === 'result', title: f.kind === 'title', anim: f.anim });
}

function next() {
  const step = async () => {
    if (!seq.length || cur >= seq.length - 1) return { kind: 'end', hold: 0, anim: 0, sound: null };
    const f = seq[++cur];
    await draw(f);
    if (f.kind === 'end') setDone(true);
    return { kind: f.kind, hold: f.hold, anim: f.anim, sound: f.sound };
  };
  const p = chain.then(step);
  chain = p.catch(() => {});
  return p;
}

function fail(e) {
  document.body.dataset.error = String(e && e.message || e);
  console.error(e);
}

// 自动播放：画一格、停 anim + hold 秒（走子滑动算在这格之内）、再下一格，到 end 那格为止。播完再调从头来。
async function play() {
  if (REC || playing || !seq.length) return;
  if (done) resetSequence();
  playing = true;
  syncPlay();
  const me = ++run;
  try {
    while (me === run) {
      const r = await next();
      if (me === run) ring(r.sound, r.anim);
      if (me !== run || cur >= seq.length - 1) break;
      await new Promise((ok) => { wake = ok; setTimeout(ok, (r.anim + r.hold) * 1000); });
    }
  } catch (e) {
    fail(e);
  } finally {
    if (me === run) { playing = false; syncPlay(); }
  }
}

function pause() {
  run++;
  playing = false;
  syncPlay();
  if (wake) wake();
}

function syncPlay() {
  const b = $('s-play');
  b.textContent = playing ? L.pause : L.play;
  b.classList.toggle('on', playing);
}

// ---------------------------------------------------------------- 手动跳步（宽版按钮、点着法、键盘）
// 先停下自动播放，画「第 gi 盘走完 ply 个半回合」（走完最后一步时带终局横幅），再把播放位置对到这一格，
// 之后按播放就从这里往下。want 是最近一次要去的位置：连按方向键时按它累加，不等上一格画完。
let want = null;

function seqIndex(gi, ply) {
  let at = -1;                     // 同一位置有几格时取最后一格：开局有标题格（title=1 时）和开局格，最后一步有走子格和结果格
  seq.forEach((f, i) => { if (f.game === gi && f.ply === ply) at = i; });
  return at;
}

function goto(gi, ply) {
  if (!games.length) return Promise.resolve();
  pause();
  gi = Math.max(0, Math.min(games.length - 1, gi));
  ply = Math.max(0, Math.min(games[gi].rep.steps.length, ply));
  const me = want = { gi, ply, final: true };
  const p = chain.then(async () => {
    // 同一盘往前走一步才滑（上一段没走完的由棋盘直接结束）、才响落子 / 吃子声；往回、跳步、换盘直接画、不出声。
    // 停在最后一步还没出横幅时（自动播放停下的那格）再往前，是补上终局那格，响终局声。
    const one = pos.gi === gi && pos.ply === ply - 1 && !summaryShown();
    const fin = pos.gi === gi && pos.ply === ply && pos.opts.final === false && !summaryShown() && hasEnd(games[gi]);
    await show(gi, ply, { anim: one ? OPT.anim : 0 });
    if (one) ring(stepSound(games[gi].rep.steps[ply - 1]), OPT.anim);
    else if (fin) ring('end');
    cur = seqIndex(gi, ply);
    setDone(false);
  }).finally(() => { if (want === me) want = null; });
  chain = p.catch(() => {});
  return p;
}

const summaryShown = () => $('stage').classList.contains('summary');
const here = () => want || { ...pos, final: pos.opts.final ?? true };

function step(d) {
  const { gi, ply, final } = here(), n = games[gi]?.rep.steps.length ?? 0;
  if (d > 0) {
    if (ply < n || !final) return goto(gi, ply + (ply < n ? 1 : 0));   // 播到最后一步还没出横幅时，先补上终局那格
    if (gi < games.length - 1) return goto(gi + 1, 0);
    return Promise.resolve();
  }
  if (ply > 0) return goto(gi, ply - 1);
  if (gi > 0) return goto(gi - 1, Infinity);
  return Promise.resolve();
}

const toStart = () => goto(here().gi, 0);
const toEnd = () => goto(here().gi, Infinity);
const toGame = (d) => goto(here().gi + d, 0);

function toggle() {
  if (playing) pause(); else play();
}

// ---------------------------------------------------------------- 走子音效
// 看棋谱时默认静音（sound=1 打开）。声音文件在载入时读好（不挡 ready），没读好或浏览器还不让出声时就不响。
// 浏览器的自动播放限制：页面上没点过、没按过键时音频是挂起的，第一次点击或按键时恢复。
let audio = null;   // { ctx, bufs: { move, capture, end } }

function loadAudio() {
  if (!SND.on || audio || typeof AudioContext === 'undefined') return;
  const ctx = new AudioContext();
  audio = { ctx, bufs: {} };
  for (const [k, s] of Object.entries(SOUNDS)) {
    fetch(s.file).then((r) => r.arrayBuffer()).then((b) => ctx.decodeAudioData(b))
      .then((buf) => { audio.bufs[k] = buf; })
      .catch((e) => console.warn(`音效 ${k} 读不了：${e.message || e}`));   // 只是少一声，不影响看棋
  }
  const resume = () => { if (ctx.state === 'suspended') ctx.resume().catch(() => {}); };
  for (const ev of ['pointerdown', 'keydown']) document.addEventListener(ev, resume, true);
}

// 过 delay 秒响一声 sound（null 不响）。
function ring(sound, delay = 0) {
  const buf = audio?.bufs[sound];
  if (!SND.on || !buf) return;
  try {
    const src = audio.ctx.createBufferSource();
    const g = audio.ctx.createGain();
    src.buffer = buf;
    g.gain.value = linear(sound, SND.vol);
    src.connect(g).connect(audio.ctx.destination);
    src.start(audio.ctx.currentTime + delay);
  } catch (e) { console.warn(`音效没放出来：${e.message || e}`); }
}

// ---------------------------------------------------------------- 界面语言
// index.html 里写的是中文；英文界面在这里换掉页面上那几处固定文字（html 的 lang、标题、按钮提示、快捷键提示）。
// 中文界面什么都不动，页面与加语言之前逐字节一致。
function applyLang() {
  if (LANG === 'zh') return;
  document.documentElement.lang = L.htmlLang;
  document.title = L.pageTitle;
  for (const b of $('s-ctrl').querySelectorAll('button')) b.title = L.btn[b.dataset.act];
  syncPlay();
  $('s-keys').replaceChildren(...L.keys.map(([keys, what]) => {
    const sp = h('span');
    keys.forEach((k) => sp.append(h('b', null, k), ' '));
    sp.append(what);
    return sp;
  }));
}

// ---------------------------------------------------------------- 版式
function applyLayout() {
  const w = FORCED ? FORCED === 'wide' : innerWidth >= WIDE_MIN;
  const st = $('stage');
  st.classList.toggle('wide', w);
  st.classList.toggle('compact', !w);
  const changed = w !== wide;
  wide = w;
  boards.chess?.resize();
  // 换了版式：棋手条宽度变了（名字从中间省略要重算），宽版右栏要补画，所以把当前这格重画一遍
  if (changed && games.length && !st.classList.contains('summary') && !st.classList.contains('empty')) {
    const { gi, ply, opts } = pos;
    chain = chain.then(() => show(gi, ply, opts)).catch(() => {});
  }
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
  if (!boards.xq && games.some((g) => g.xiangqi)) { boards.xq = new XiangqiBoard($('board-xq'), { lang: LANG }); await boards.xq.load(); }
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
  loadAudio();
  const files = (params.get('files') || '').split(',').map((s) => s.trim()).filter(Boolean);
  if (!files.length) {
    if (REC) throw new Error('没给棋谱：网址加 ?files=/runs/xxx/game.pgn');
    showHint(L.hint);
    return true;
  }
  await useTexts(await fetchTexts(files));
  const still = !REC && params.get('autoplay') !== '1' && ['game', 'ply', 'summary'].some((k) => params.has(k));
  if (still) {                                            // 静态看某一格
    const gi = Math.max(0, Math.min(games.length - 1, (Number(params.get('game')) || 1) - 1));
    const p = params.get('ply');
    if (params.get('summary') === '1' && games.length > 1) await summary();
    else {
      await show(gi, p === 'end' ? Infinity : Number(p) || 0);
      cur = seqIndex(pos.gi, pos.ply);                     // 之后按播放从这一格接着往下
    }
  } else {
    await draw(seq[0]);                                   // 先画出第一格；next() 第一次调用仍从这一格算起
  }
  if (!REC && params.get('autoplay') === '1') play();
  return true;
}

// 拖文件进页面：按文件名排序后当作一场比赛，从头播（autoplay=0 时只画第一格）。
// analysis.jsonl 会按每步坐标与走前局面自动校验并叠加到对应棋谱，不受文件名排序先后影响。
async function onDrop(e) {
  e.preventDefault();
  const list = [...(e.dataTransfer?.files || [])].sort((a, b) => a.name.localeCompare(b.name));
  if (!list.length) return;
  try {
    await useTexts(await Promise.all(list.map(async (f) => ({
      name: f.name,
      text: decodeText(new Uint8Array(await f.arrayBuffer())),
    }))));
    if (!REC && params.get('autoplay') !== '0') play();
    else await draw(seq[0]);
  } catch (err) {
    fail(err);
    showHint(document.body.dataset.error);
  }
}
document.addEventListener('dragover', (e) => e.preventDefault());
document.addEventListener('drop', onDrop);
const KEYS = {
  Space: toggle, ArrowRight: () => step(1), ArrowLeft: () => step(-1), Home: toStart, End: toEnd,
  PageDown: () => toGame(1), PageUp: () => toGame(-1),
};
document.addEventListener('keydown', (e) => {
  const act = KEYS[e.code];
  if (REC || !act || e.altKey || e.ctrlKey || e.metaKey || e.target.closest?.('select, input, textarea')) return;
  e.preventDefault();
  if (!games.length) return;
  Promise.resolve(act()).catch(fail);
});
// 宽版右栏：按钮、点着法、下拉换盘。按钮不拿焦点，免得空格键既触发按钮又切换播放。
$('s-ctrl').addEventListener('mousedown', (e) => e.preventDefault());
$('s-ctrl').addEventListener('click', (e) => {
  const act = e.target.closest('button')?.dataset.act;
  const fn = { first: toStart, prev: () => step(-1), play: toggle, next: () => step(1), last: toEnd }[act];
  if (fn && games.length) Promise.resolve(fn()).catch(fail);
});
$('s-moves').addEventListener('click', (e) => {
  const c = e.target.closest('[data-ply]');
  if (c) goto(side.gi, Number(c.dataset.ply)).catch(fail);
});
$('s-head').addEventListener('change', (e) => {
  if (e.target.id !== 's-game') return;
  e.target.blur();
  goto(Number(e.target.value), 0).catch(fail);
});
applyLang();
applyLayout();
addEventListener('resize', applyLayout);

window.viewer = {
  show, summary, next, play, pause,
  get done() { return done; },
  ready: init(),
};
window.viewer.ready.catch(fail);
