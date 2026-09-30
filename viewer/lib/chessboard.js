// 国际象棋棋盘：包一层 vendor 的 cm-chessboard，只管「画某个局面 + 上一步高亮 + 被将军的王」。
// 棋子、标记两张精灵图由这里先 fetch 好、塞进 cm-chessboard 认的缓存 div（它自己用 XHR 异步加载、不给完成信号），
// 这样 load() 兑现时图已经在页面里，截图不用轮询。
import { Chessboard } from '../vendor/cm-chessboard/src/Chessboard.js';
import { Markers } from '../vendor/cm-chessboard/src/extensions/markers/Markers.js';
import { Position } from '../vendor/cm-chessboard/src/model/Position.js';
import { Moves } from './anim.js';

const ASSETS = new URL('../vendor/cm-chessboard/assets/', import.meta.url).href;
const SPRITES = { 'cm-chessboard-sprite': 'pieces/cburnett.svg', 'cm-chessboard-markers': 'extensions/markers/markers.svg' };

// 照 lichess：上一步起止两格盖一层黄绿色（app.css 的 .marker-last），被将军的王所在格垫一团红色径向渐变
// （.marker-check，渐变 #cb-check 定义在 index.html）。两者都画在棋子下面。
const LAST = { class: 'marker-last', slice: 'markerSquare' };
const CHECK = { class: 'marker-check', slice: 'markerSquare' };

async function preloadSprites() {
  await Promise.all(Object.entries(SPRITES).map(async ([id, file]) => {
    if (document.getElementById(id)) return;
    const res = await fetch(ASSETS + file);
    if (!res.ok) throw new Error(`加载 ${file} 失败：${res.status}`);
    const div = document.createElement('div');
    div.id = id;
    div.setAttribute('aria-hidden', 'true');
    div.style.cssText = 'transform: scale(0); position: absolute';
    div.innerHTML = await res.text();
    document.body.appendChild(div);
  }));
}

export class ChessBoard {
  constructor(el) {
    this.el = el;
    this.board = null;
    this.moves = new Moves();
  }

  async load() {
    await preloadSprites();
    this.board = new Chessboard(this.el, {
      assetsUrl: ASSETS,
      responsive: false,
      style: { animationDuration: 0, showCoordinates: true },
      extensions: [{ class: Markers, props: { autoMarkers: null } }],
    });
  }

  // 容器尺寸变了（宽版随窗口高度定棋盘边长、切换版式）时按新尺寸重画；构造时 responsive 关着，所以要手动调。
  resize() {
    this.moves.stop();
    this.board?.view.handleResize();
  }

  // fen：局面；last：{from, to} 或 null；check：走完后被将军一方的王所在格，或 null；prev：走这步之前的局面。
  // anim > 0（秒）且有 last、prev 时画走子滑动；paused：录制模式，动画停在起点等脚本拨进度。
  // cm-chessboard 自带的动画（requestAnimationFrame 手写、不能定格）一直关着（animationDuration: 0），
  // 滑动由 slide() 在它画好的终局上叠一层补上。
  async render({ fen, last, check, prev }, { anim = 0, paused = false } = {}) {
    this.moves.stop();
    const b = this.board;
    await b.setPosition(fen, false);
    b.removeMarkers();
    if (last) { b.addMarker(LAST, last.from); b.addMarker(LAST, last.to); }
    if (check) b.addMarker(CHECK, check);
    if (anim > 0 && last && prev) this.slide(prev, last, anim * 1000, paused);
  }

  // 棋盘已画成走完的样子。动画期间：落点上的真棋子藏起来，另叠一枚走之前的棋子从起点滑到落点
  // （升变时滑的是兵、结束才变成后）；被吃的子在原位（吃过路兵是旁边那格）待到结束；王车易位时车同时滑。
  slide(prevFen, { from, to }, ms, paused) {
    const view = this.board.view, pos = new Position(prevFen);
    const piece = pos.getPiece(from);
    if (!piece) return;
    const real = (sq) => view.piecesGroup.querySelector(`g[data-square='${sq}']`);
    const pairs = [[from, to, piece]];
    let taken = pos.getPiece(to), takenAt = to;
    if (piece[1] === 'p' && from[0] !== to[0] && !taken) {           // 吃过路兵：被吃的兵在起点那一横排
      takenAt = to[0] + from[1];
      taken = pos.getPiece(takenAt);
    }
    if (piece[1] === 'k' && Math.abs(from.charCodeAt(0) - to.charCodeAt(0)) === 2) {   // 王车易位
      const r = from[1], short = to[0] === 'g';
      pairs.push([(short ? 'h' : 'a') + r, (short ? 'f' : 'd') + r, piece[0] + 'r']);
    }
    if (taken) this.moves.during(view.drawPieceOnSquare(takenAt, taken), ms, paused);
    for (const [a, z, name] of pairs) {
      const dest = real(z);
      if (dest) this.moves.hide(dest, ms, paused);
      const g = view.drawPieceOnSquare(a, name);
      this.moves.during(g, ms, paused);
      this.moves.slide(g, view.squareToPoint(a), view.squareToPoint(z), ms, paused);
    }
  }
}

// 被将军时王在哪格：side 是被将的一方（'w' / 'b'）。fen 取棋子段逐格找 K / k。
export function kingSquare(fen, side) {
  const want = side === 'w' ? 'K' : 'k';
  const rows = fen.split(' ')[0].split('/');
  for (let r = 0; r < 8; r++) {
    let f = 0;
    for (const ch of rows[r]) {
      if (/\d/.test(ch)) { f += Number(ch); continue; }
      if (ch === want) return 'abcdefgh'[f] + (8 - r);
      f++;
    }
  }
  return null;
}
