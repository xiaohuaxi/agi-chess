// 国际象棋棋盘：包一层 vendor 的 cm-chessboard，只管「画某个局面 + 上一步高亮 + 被将军的王」。
// 棋子、标记两张精灵图由这里先 fetch 好、塞进 cm-chessboard 认的缓存 div（它自己用 XHR 异步加载、不给完成信号），
// 这样 load() 兑现时图已经在页面里，截图不用轮询。
import { Chessboard } from '../vendor/cm-chessboard/src/Chessboard.js';
import { Markers } from '../vendor/cm-chessboard/src/extensions/markers/Markers.js';

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
    this.board?.view.handleResize();
  }

  // fen：局面；last：{from, to} 或 null；check：走完后被将军一方的王所在格，或 null。
  async render({ fen, last, check }) {
    const b = this.board;
    await b.setPosition(fen, false);
    b.removeMarkers();
    if (last) { b.addMarker(LAST, last.from); b.addMarker(LAST, last.to); }
    if (check) b.addMarker(CHECK, check);
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
