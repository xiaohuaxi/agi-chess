// 中国象棋棋盘：自画 SVG 棋盘，棋子用 vendor/xiangqi-pieces 的 CC0 素材（docs/viewer.md「棋盘」）。
// 素材没有 viewBox、且各文件的渐变 / 滤镜 id 重名，所以补上 viewBox 后转成 blob 网址，按独立 <image> 放。
// load() 先把 14 个棋子读好并解码；render() 等本次放上去的每个 <image> 都加载完才兑现，截图不用轮询。
import { parseFen } from './xiangqi.js';

const NS = 'http://www.w3.org/2000/svg';
const NAMES = { k: 'king', a: 'advisor', b: 'elephant', n: 'horse', r: 'chariot', c: 'cannon', p: 'pawn' };
const PIECES = new URL('../vendor/xiangqi-pieces/', import.meta.url).href;

// 棋盘几何（SVG 用户单位；一格 = 1，9 路 10 线外各留半格，宽高比 9:10）。
const W = 9, H = 10;
const PIECE = 0.92;          // 棋子直径占一格的比例
const X = (x) => 0.5 + x;    // 纵线 x（0 = 红方左手 a 线）
const Y = (y) => 9.5 - y;    // 横线 y（0 = 红方底线）→ 屏幕从上往下

function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

async function loadPiece(code) {
  const color = code === code.toUpperCase() ? 'red' : 'black';
  const file = `${color}_${NAMES[code.toLowerCase()]}.svg`;
  const res = await fetch(PIECES + file);
  if (!res.ok) throw new Error(`加载 ${file} 失败：${res.status}`);
  const doc = new DOMParser().parseFromString(await res.text(), 'image/svg+xml');
  const root = doc.documentElement;
  root.setAttribute('viewBox', `0 0 ${parseFloat(root.getAttribute('width'))} ${parseFloat(root.getAttribute('height'))}`);
  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(doc)], { type: 'image/svg+xml' }));
  const img = new Image();
  img.src = url;
  await img.decode();
  return url;
}

export class XiangqiBoard {
  constructor(el) {
    this.el = el;
    this.urls = null;
  }

  async load() {
    const codes = [...'kabnrcpKABNRCP'];
    const urls = await Promise.all(codes.map(loadPiece));
    this.urls = Object.fromEntries(codes.map((c, i) => [c, urls[i]]));
    this.svg = el('svg', { class: 'xq-board', viewBox: `0 0 ${W} ${H}` }, this.el);
    this.drawGrid(el('g', { class: 'xq-grid' }, this.svg));
    this.marks = el('g', { class: 'xq-marks' }, this.svg);
    this.pieces = el('g', { class: 'xq-pieces' }, this.svg);
  }

  drawGrid(g) {
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
    const m = 0.08;                                   // 外框比网格外扩一点
    el('rect', { class: 'xq-frame', x: X(0) - m, y: Y(9) - m, width: 8 + 2 * m, height: 9 + 2 * m }, g);
    const river = el('text', { class: 'xq-river', x: W / 2, y: (Y(4) + Y(5)) / 2 }, g);
    river.textContent = '楚 河　　　　汉 界';
  }

  // fen：局面；last：{from, to}（ICCS 格名，如 'h2'）或 null；check：被将军一方的将 / 帅所在格名，或 null。
  async render({ fen, last, check }) {
    const { board } = parseFen(fen);
    this.marks.replaceChildren();
    this.pieces.replaceChildren();
    const at = (sq) => [X('abcdefghi'.indexOf(sq[0])), Y(Number(sq.slice(1)))];
    if (check) {
      const [cx, cy] = at(check);
      el('circle', { class: 'xq-check', cx, cy, r: PIECE / 2 + 0.06 }, this.marks);
    }
    if (last) {
      const [fx, fy] = at(last.from);
      el('circle', { class: 'xq-last-from', cx: fx, cy: fy, r: 0.12 }, this.marks);
    }
    const loads = [];
    board.forEach((p, i) => {
      if (!p) return;
      const x = i % 9, y = (i - x) / 9;
      const img = el('image', { href: this.urls[p], x: X(x) - PIECE / 2, y: Y(y) - PIECE / 2, width: PIECE, height: PIECE }, this.pieces);
      loads.push(new Promise((ok, bad) => { img.onload = ok; img.onerror = () => bad(new Error('棋子图加载失败：' + p)); }));
    });
    if (last) {                                       // 落点的框画在棋子上面
      const [tx, ty] = at(last.to);
      const s = PIECE + 0.08;
      el('rect', { class: 'xq-last-to', x: tx - s / 2, y: ty - s / 2, width: s, height: s }, this.pieces);
    }
    await Promise.all(loads);
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
