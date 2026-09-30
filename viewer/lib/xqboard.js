// 中国象棋棋盘：整块自画 SVG（棋盘、路数、棋子、上一步、将军），照主流象棋软件的样子（docs/viewer.md「棋盘」）：
// 参照象棋巫师 / 象棋小巫师（xqbase）——浅木色棋盘、双线外框、炮位兵位的「花」、上下标路数（黑方 1–9 在上、红方 九–一 在下）；
// 棋子是木色圆子，红方红字红圈、黑方黑字黑圈；上一步在起点和落点各画四个蓝色角框。
// 棋子上的字用页面字体现画（楷体，见 app.css 的 --xq-font），不拷任何字体或字形轮廓：本机没有楷体时会退回别的中文字体。
import { parseFen } from './xiangqi.js';

const NS = 'http://www.w3.org/2000/svg';
// 棋子字：红方俥傌相仕帥炮兵，黑方車馬象士將砲卒（象棋软件的常见写法，与此前素材一致）。
const GLYPH = { K: '帥', A: '仕', B: '相', N: '傌', R: '俥', C: '炮', P: '兵', k: '將', a: '士', b: '象', n: '馬', r: '車', c: '砲', p: '卒' };
const RED_FILES = '九八七六五四三二一';
const BLACK_FILES = '１２３４５６７８９';

// 几何（SVG 用户单位，一格 = 1）：9 路 10 线外各留半格放棋子；上下各加一条标路数的带子。
// 带子只比路数字（0.3 格高）略宽：字靠外、离棋子近些，和棋盘外沿（贴着棋手条）之间仍留几像素空白、不贴死。
// 第三轮定稿是 0.5 / 0.3（字靠里、离棋子远）；第四轮用户要棋盘更宽，收窄成下面的值，待用户看图定（2026-09-30）。
const BAND = 0.34;
// 路数字中心离棋盘外沿（格）。上下不对称是有意的：下方的汉字数字（一、二、三）墨迹偏低，
// 同一个值会让下方的字比上方的阿拉伯数字更贴棋手条；各取一个值，让两边墨迹离外沿都约 5 像素（页面 540 宽时）。
const FILE_TOP = 0.2, FILE_BOTTOM = 0.22;
const W = 9, H = 10 + 2 * BAND;
const R = 0.45;              // 棋子半径（格）
const X = (x) => 0.5 + x;    // 纵线 x（0 = 红方左手 a 线）
const Y = (y) => BAND + 9.5 - y;  // 横线 y（0 = 红方底线）→ 屏幕从上往下

function el(tag, attrs, parent, text) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text != null) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}

export class XiangqiBoard {
  constructor(el) {
    this.el = el;
    el.style.aspectRatio = `${W} / ${H}`;   // 容器宽高比跟着几何走（高度由 app.css 定）
  }

  async load() {
    this.svg = el('svg', { class: 'xq-board', viewBox: `0 0 ${W} ${H}` }, this.el);
    const defs = el('defs', {}, this.svg);
    for (const side of ['red', 'black', 'mated']) {
      const g = el('radialGradient', { id: `xq-face-${side}`, cx: 0.4, cy: 0.35, r: 0.7 }, defs);
      el('stop', { offset: 0, class: `xq-face-hi ${side}` }, g);
      el('stop', { offset: 1, class: `xq-face-lo ${side}` }, g);
    }
    this.drawBoard(el('g', { class: 'xq-grid' }, this.svg));
    this.under = el('g', { class: 'xq-under' }, this.svg);
    this.pieces = el('g', { class: 'xq-pieces' }, this.svg);
    this.over = el('g', { class: 'xq-over' }, this.svg);
    // 棋子字用的字体要先载入，第一帧才不会先用替代字体画
    const font = getComputedStyle(this.el).getPropertyValue('--xq-font').trim();
    if (font) await document.fonts.load(`700 24px ${font}`, Object.values(GLYPH).join('') + RED_FILES + BLACK_FILES + '楚河漢界');
  }

  drawBoard(g) {
    el('rect', { class: 'xq-bg', x: 0, y: 0, width: W, height: H }, g);
    const lines = el('g', { class: 'xq-lines' }, g);
    for (let y = 0; y < 10; y++) el('line', { x1: X(0), y1: Y(y), x2: X(8), y2: Y(y) }, lines);
    for (let x = 0; x < 9; x++) {
      if (x === 0 || x === 8) { el('line', { x1: X(x), y1: Y(0), x2: X(x), y2: Y(9) }, lines); continue; }
      el('line', { x1: X(x), y1: Y(0), x2: X(x), y2: Y(4) }, lines);
      el('line', { x1: X(x), y1: Y(5), x2: X(x), y2: Y(9) }, lines);
    }
    for (const [y0, y1] of [[0, 2], [7, 9]]) {       // 九宫斜线
      el('line', { x1: X(3), y1: Y(y0), x2: X(5), y2: Y(y1) }, lines);
      el('line', { x1: X(5), y1: Y(y0), x2: X(3), y2: Y(y1) }, lines);
    }
    // 炮位、兵位的「花」：交叉点四角各一个小直角，靠边的只画朝里的一半
    const d = 0.07, l = 0.2;
    const marks = [[1, 2], [7, 2], [1, 7], [7, 7], ...[0, 2, 4, 6, 8].flatMap((x) => [[x, 3], [x, 6]])];
    for (const [x, y] of marks) {
      for (const sx of [-1, 1]) {
        if ((x === 0 && sx < 0) || (x === 8 && sx > 0)) continue;
        for (const sy of [-1, 1]) {
          const cx = X(x) + sx * d, cy = Y(y) + sy * d;
          el('polyline', { points: `${cx + sx * l},${cy} ${cx},${cy} ${cx},${cy + sy * l}` }, lines);
        }
      }
    }
    const m = 0.1;                                    // 外框：粗线，比网格外扩一点
    el('rect', { class: 'xq-frame', x: X(0) - m, y: Y(9) - m, width: 8 + 2 * m, height: 9 + 2 * m }, g);
    // 河界字放在两条纵线之间的格子正中、字号小，棋子站在河岸时也碰不到（棋子画在上层）
    const ry = (Y(4) + Y(5)) / 2;
    [['楚', 1.5], ['河', 2.5], ['漢', 5.5], ['界', 6.5]].forEach(([c, x]) => el('text', { class: 'xq-river', x: X(x), y: ry }, g, c));
    // 路数：黑方在上（从黑方右手数，即画面左起 1–9），红方在下（画面左起 九–一）
    for (let x = 0; x < 9; x++) {
      el('text', { class: 'xq-file', x: X(x), y: FILE_TOP }, g, BLACK_FILES[x]);
      el('text', { class: 'xq-file', x: X(x), y: H - FILE_BOTTOM }, g, RED_FILES[x]);
    }
  }

  // fen：局面；last：{from, to}（ICCS 格名，如 'h2'）或 null；check：被将军一方的将 / 帅所在格名或 null；mated：被将死。
  async render({ fen, last, check, mated }) {
    const { board } = parseFen(fen);
    this.under.replaceChildren();
    this.pieces.replaceChildren();
    this.over.replaceChildren();
    const at = (sq) => [X('abcdefghi'.indexOf(sq[0])), Y(Number(sq.slice(1)))];
    if (check && !mated) {
      const [cx, cy] = at(check);
      el('circle', { class: 'xq-check', cx, cy, r: R + 0.07 }, this.under);
    }
    board.forEach((p, i) => {
      if (!p) return;
      const x = i % 9, y = (i - x) / 9;
      const red = p === p.toUpperCase();
      const dead = mated && check && 'abcdefghi'[x] + y === check;
      const side = dead ? 'mated' : red ? 'red' : 'black';
      const g = el('g', { class: `xq-piece ${red ? 'red' : 'black'}${dead ? ' mated' : ''}`, transform: `translate(${X(x)} ${Y(y)})` }, this.pieces);
      el('circle', { class: 'xq-shadow', cx: 0.03, cy: 0.05, r: R }, g);
      el('circle', { class: 'xq-face', r: R, fill: `url(#xq-face-${side})` }, g);
      el('circle', { class: 'xq-ring', r: R * 0.8 }, g);
      el('text', { class: 'xq-glyph', x: 0, y: 0.02 }, g, GLYPH[p]);
    });
    if (last) {                                       // 上一步：起点、落点各画四个角框
      const s = 0.47, k = 0.15;
      for (const sq of [last.from, last.to]) {
        const [cx, cy] = at(sq);
        for (const sx of [-1, 1]) for (const sy of [-1, 1]) {
          const x0 = cx + sx * s, y0 = cy + sy * s;
          el('polyline', { class: 'xq-last', points: `${x0 - sx * k},${y0} ${x0},${y0} ${x0},${y0 - sy * k}` }, this.over);
        }
      }
    }
  }
}

// 被将军的一方的将 / 帅在哪格：side 是被将的一方（'w' 红 / 'b' 黑）。
export function xqKingSquare(fen, side) {
  const { board } = parseFen(fen);
  const i = board.indexOf(side === 'w' ? 'K' : 'k');
  if (i < 0) return null;
  const x = i % 9;
  return 'abcdefghi'[x] + (i - x) / 9;
}
