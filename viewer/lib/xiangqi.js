// 中国象棋：局面、中文纵线记谱解析（xqbase《着法表示》第四节）、将军判断。只为显示，不校验合法性——
// 着法合法与否由对局程序（pyffish）判过；这里只要认出记谱指的是哪个子、走到哪。这是 docs/viewer.md「棋盘」一节写明的
// 有意例外（项目规定规则判定照搬旧实现，那是对局程序的事；阅读器只画「将军」提示），正确性靠与 game.jsonl 逐步对照。
// 导出端的记谱生成在 llmchess/xiangqi.py 的 pgn_move，两边规则要一致。
//
// 坐标同 ICCS：纵线 a–i 从红方左手起（x = 0–8），横线 0–9 从红方底线起（y）。棋子用 FEN 字母，大写红、小写黑：
// k 帅将、a 仕士、b 相象、n 马、r 车、c 炮、p 兵卒。

export const START_FEN = 'rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1';
const FILES = 'abcdefghi';

export const sqName = (x, y) => FILES[x] + y;
export const sqXY = (s) => [FILES.indexOf(s[0]), Number(s.slice(1))];
const isRed = (p) => p === p.toUpperCase();

// FEN → { board: 90 格数组（下标 y*9+x，空格 null），turn: 'w' / 'b' }。容错 h→n（马）、e→b（象）的写法。
export function parseFen(fen) {
  const [rows, turn = 'w'] = fen.trim().split(/\s+/);
  const lines = rows.split('/');
  if (lines.length !== 10) throw new Error('FEN 横线数不对：' + fen);
  const board = new Array(90).fill(null);
  lines.forEach((row, i) => {
    const y = 9 - i;
    let x = 0;
    for (const ch of row.replace(/(\d+)/g, (d) => '.'.repeat(Number(d)))) {
      if (ch !== '.') {
        const p = ({ h: 'n', e: 'b', H: 'N', E: 'B' })[ch] || ch;
        if (!/^[kabnrcpKABNRCP]$/.test(p)) throw new Error('FEN 里有不认识的棋子：' + fen);
        if (x > 8) throw new Error('FEN 某一行格数不对：' + fen);
        board[y * 9 + x] = p;
      }
      x++;
    }
    if (x !== 9) throw new Error('FEN 某一行格数不对：' + fen);
  });
  return { board, turn: turn === 'b' ? 'b' : 'w' };
}

export function toFen(pos) {
  const rows = [];
  for (let y = 9; y >= 0; y--) {
    let row = '', blank = 0;
    for (let x = 0; x < 9; x++) {
      const p = pos.board[y * 9 + x];
      if (!p) { blank++; continue; }
      if (blank) { row += blank; blank = 0; }
      row += p;
    }
    rows.push(row + (blank || ''));
  }
  return rows.join('/') + ' ' + pos.turn;
}

const at = (board, x, y) => (x >= 0 && x < 9 && y >= 0 && y < 10 ? board[y * 9 + x] : undefined);

// 走一步（ICCS，如 'h2e2'），返回新局面；不检查合法性。
export function makeMove(pos, iccs) {
  const [x1, y1] = sqXY(iccs.slice(0, 2)), [x2, y2] = sqXY(iccs.slice(2, 4));
  const board = pos.board.slice();
  board[y2 * 9 + x2] = board[y1 * 9 + x1];
  board[y1 * 9 + x1] = null;
  return { board, turn: pos.turn === 'w' ? 'b' : 'w' };
}

// side（'w' / 'b'）的将帅是否被对方攻击（含帅将照面）。棋盘上找不到将帅返回 false。
export function inCheck(pos, side) {
  const { board } = pos;
  const kIdx = board.indexOf(side === 'w' ? 'K' : 'k');
  if (kIdx < 0) return false;
  const kx = kIdx % 9, ky = (kIdx - kx) / 9;
  // 直线：车、帅将照面（第一个子），炮（隔一个子的第二个子）
  for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
    let seen = 0;
    for (let x = kx + dx, y = ky + dy; x >= 0 && x < 9 && y >= 0 && y < 10; x += dx, y += dy) {
      const p = board[y * 9 + x];
      if (!p) continue;
      seen++;
      if (isRed(p) !== (side === 'w')) {
        const k = p.toLowerCase();
        if (seen === 1 && (k === 'r' || (k === 'k' && dx === 0))) return true;
        if (seen === 2 && k === 'c') return true;
      }
      if (seen === 2) break;
    }
  }
  // 马：马在 (kx+dx, ky+dy)，马腿在马朝将方向走长边的那一格
  for (const [dx, dy] of [[1, 2], [-1, 2], [1, -2], [-1, -2], [2, 1], [-2, 1], [2, -1], [-2, -1]]) {
    const p = at(board, kx + dx, ky + dy);
    if (!p || p.toLowerCase() !== 'n' || isRed(p) === (side === 'w')) continue;
    const legX = kx + dx - (Math.abs(dx) === 2 ? Math.sign(dx) : 0);
    const legY = ky + dy - (Math.abs(dy) === 2 ? Math.sign(dy) : 0);
    if (!at(board, legX, legY)) return true;
  }
  // 兵卒：对方兵从正面（它的前方）或过河后从侧面攻
  const enemyPawn = side === 'w' ? 'p' : 'P';
  const fwd = side === 'w' ? 1 : -1;               // 对方兵在将的「前方」一格（对红帅来说是 y+1）
  if (at(board, kx, ky + fwd) === enemyPawn) return true;
  for (const dx of [-1, 1]) {
    if (at(board, kx + dx, ky) === enemyPawn) return true;   // 能从侧面走到将位的兵一定已过河
  }
  return false;
}

// ---------------------------------------------------------------- 中文记谱解析
const KIND = {
  车: 'r', 車: 'r', 俥: 'r', 伡: 'r', 马: 'n', 馬: 'n', 傌: 'n', 㐷: 'n', 炮: 'c', 砲: 'c', 包: 'c',
  相: 'b', 象: 'b', 仕: 'a', 士: 'a', 帅: 'k', 帥: 'k', 将: 'k', 將: 'k', 兵: 'p', 卒: 'p',
};
const OP = { 进: 1, 進: 1, 退: -1, 平: 0 };
const POS = { 前: 'front', 中: 'mid', 后: 'back', 後: 'back' };

// 数字：汉字「一」到「九」、全角「１」到「９」、半角「1」到「9」都认，不管是哪方走（哪方走由局面定）。
export function digit(ch) {
  let i = '一二三四五六七八九'.indexOf(ch);
  if (i >= 0) return i + 1;
  i = '１２３４５６７８９'.indexOf(ch);
  if (i >= 0) return i + 1;
  return /^[1-9]$/.test(ch) ? Number(ch) : null;
}

// 纵线号 ↔ x：红方从红方右手起一到九，黑方从黑方右手起１到９
const fileToX = (red, n) => (red ? 9 - n : n - 1);
const xToFile = (red, x) => (red ? 9 - x : x + 1);

function inPalace(x, y, red) {
  return x >= 3 && x <= 5 && (red ? y <= 2 : y >= 7);
}

// 起点 (x, y) 的 kind 子按 op / num 走到哪；走不出去（出界、形状不对、落在己方子上）返回 null。
function destOf(pos, x, y, kind, red, op, num) {
  const dir = red ? 1 : -1;
  let tx, ty;
  if (op === 0) {
    if ('nab'.includes(kind)) return null;
    tx = fileToX(red, num); ty = y;
    if (tx === x) return null;
  } else if ('rcpk'.includes(kind)) {
    tx = x; ty = y + op * dir * num;
  } else {
    tx = fileToX(red, num);
    const adx = Math.abs(tx - x);
    const ady = kind === 'n' ? { 1: 2, 2: 1 }[adx] : kind === 'a' ? (adx === 1 ? 1 : null) : (adx === 2 ? 2 : null);
    if (!ady) return null;
    ty = y + op * dir * ady;
  }
  if (tx < 0 || tx > 8 || ty < 0 || ty > 9) return null;
  const tgt = pos.board[ty * 9 + tx];
  if (tgt && isRed(tgt) === red) return null;
  if ((kind === 'a' || kind === 'k') && !inPalace(tx, ty, red)) return null;
  if (kind === 'b' && (red ? ty > 4 : ty < 5)) return null;
  if (kind === 'p' && op !== 0 && (op < 0 || num !== 1)) return null;
  return [tx, ty];
}

// 中文记谱 → { iccs, from, to, piece, capture }。认不出抛 Error（消息是中文，可直接显示）。
// 写法：「炮二平五」（子 + 纵线）、「前车进一」「中兵平四」（前中后）、「一兵平五」（同线四五兵或两条多兵纵线的编号，
// 见 llmchess/xiangqi.py pgn_move 的注释）。仕相同线不写前后，靠进退和落点分辨。容错繁体、半角数字、汉字 / 全角数字混用。
export function parseMove(pos, text) {
  const cs = Array.from(text.trim().replace(/[+#＋]$/, ''));
  if (cs.length !== 4) throw new Error('认不出的着法：' + text);
  const red = pos.turn === 'w';
  let kind, file = null, sel = null;
  if (KIND[cs[0]] && digit(cs[1])) {
    kind = KIND[cs[0]]; file = digit(cs[1]);
  } else if (KIND[cs[1]] && (POS[cs[0]] || (digit(cs[0]) && digit(cs[0]) <= 5))) {
    kind = KIND[cs[1]]; sel = POS[cs[0]] || digit(cs[0]);
  } else {
    throw new Error('认不出的着法：' + text);
  }
  const op = OP[cs[2]], num = digit(cs[3]);
  if (op === undefined || num === null) throw new Error('认不出的着法：' + text);
  const piece = red ? kind.toUpperCase() : kind;
  const files = new Map();                          // x → [y]，同种子按纵线分组
  pos.board.forEach((p, i) => {
    if (p !== piece) return;
    const x = i % 9;
    if (!files.has(x)) files.set(x, []);
    files.get(x).push((i - x) / 9);
  });
  const frontFirst = (ys) => ys.slice().sort((a, b) => (red ? b - a : a - b));
  let cands;
  if (file !== null) {
    const x = fileToX(red, file);
    cands = (files.get(x) || []).map((y) => [x, y]);
  } else {
    const multi = [...files.keys()].filter((x) => files.get(x).length >= 2)
      .sort((a, b) => xToFile(red, a) - xToFile(red, b));
    let line;
    if (kind === 'p' && multi.length >= 2) {
      if (typeof sel !== 'number') throw new Error('两条纵线都有多个兵，要用一二三四五编号：' + text);
      line = multi.flatMap((x) => frontFirst(files.get(x)).map((y) => [x, y]));
    } else if (multi.length === 1) {
      line = frontFirst(files.get(multi[0])).map((y) => [multi[0], y]);
    } else {
      throw new Error('没有同一纵线上的两个' + cs[1] + '：' + text);
    }
    const idx = sel === 'front' ? 0 : sel === 'back' ? line.length - 1 : sel === 'mid' ? (line.length === 3 ? 1 : -1) : sel - 1;
    if (idx < 0 || idx >= line.length) throw new Error('这条纵线上没有这个子：' + text);
    cands = [line[idx]];
  }
  const hits = [];
  for (const [x, y] of cands) {
    const d = destOf(pos, x, y, kind, red, op, num);
    if (d) hits.push([x, y, d[0], d[1]]);
  }
  if (hits.length === 0) throw new Error('局面里找不到能这样走的子：' + text);
  if (hits.length > 1) throw new Error('有两个子都能这样走，记谱有歧义：' + text);
  const [x1, y1, x2, y2] = hits[0];
  const from = sqName(x1, y1), to = sqName(x2, y2);
  return { iccs: from + to, from, to, piece, capture: pos.board[y2 * 9 + x2] || null };
}

// ---------------------------------------------------------------- WXF 记法（只为英文界面显示，docs/viewer.md「英文界面」）
// 从局面和坐标算，不看棋谱里的中文原文，所以别人棋谱里不规范的写法也能写成规范的 WXF。规则照 xqbase《着法表示》第五节
// 与导出端 pgn_move（llmchess/xiangqi.py）的消歧规则逐条对应，只把汉字换成字母和符号：
//   棋子 K A E H R C P（世界象棋联合会推荐的字母：相 E、马 H）；进 +、退 -、平 .；纵线与格数都用阿拉伯数字，两方各从自己右手数。
//   车马炮兵同一纵线两个：「前」「后」写成 + / -，放在棋子字母后面、代替纵线号（前炮退二 → C+-2）。
//   兵卒同一纵线三个以上，或两条纵线各有多个（这时两条线的兵一起编号）：从前往后编 a b c d e（xqbase：「一二三四五」用 abcde），
//   三兵的「前中后」也写成 a b c——原文「前中后分别用 + - .」与「前炮 → C+」放在一起读不通中兵，这里取不会有歧义的编号写法。
//   仕相同线不写前后（能退的在前、能进的在后），照常写纵线号。
const WXF_LETTER = { k: 'K', a: 'A', b: 'E', n: 'H', r: 'R', c: 'C', p: 'P' };

export function wxfMove(pos, iccs) {
  const [x1, y1] = sqXY(iccs.slice(0, 2)), [x2, y2] = sqXY(iccs.slice(2, 4));
  const p = pos.board[y1 * 9 + x1];
  if (!p) return iccs;                               // 起点没子（不会发生：parseMove 已认出这个子）
  const red = isRed(p), kind = p.toLowerCase(), L = WXF_LETTER[kind];
  const ahead = (a, b) => (red ? b - a : a - b);     // 越靠前（越接近对方底线）越先
  let head = L + xToFile(red, x1);
  if ('rncp'.includes(kind)) {
    const files = new Map();                         // x → [y]
    pos.board.forEach((q, i) => {
      if (q !== p) return;
      const x = i % 9;
      if (!files.has(x)) files.set(x, []);
      files.get(x).push((i - x) / 9);
    });
    const mine = files.get(x1).slice().sort(ahead);
    const multi = [...files.keys()].filter((x) => files.get(x).length >= 2).sort((a, b) => xToFile(red, a) - xToFile(red, b));
    if (kind === 'p' && multi.length >= 2 && multi.includes(x1)) {
      const order = multi.flatMap((x) => files.get(x).slice().sort(ahead).map((y) => [x, y]));
      head = L + 'abcde'[order.findIndex(([x, y]) => x === x1 && y === y1)];
    } else if (mine.length === 2) head = L + '+-'[mine.indexOf(y1)];
    else if (mine.length >= 3) head = L + 'abcde'[mine.indexOf(y1)];
  }
  const dy = (y2 - y1) * (red ? 1 : -1);
  const op = dy === 0 ? '.' : dy > 0 ? '+' : '-';
  return head + op + ('rcpk'.includes(kind) && dy !== 0 ? Math.abs(dy) : xToFile(red, x2));
}
