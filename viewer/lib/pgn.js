// 两种棋共用的 PGN 读取：解码、分词成一盘盘棋、评注命令解析（docs/viewer.md「做成什么样·输入」「棋盘」）。
// 不认记谱：着法原样交给 xiangqi.js / replay.js 去走。变着（圆括号）整段跳过。浏览器与 node 都能 import，无依赖。

// ---------------------------------------------------------------- 解码
// 先按 UTF-8 严格解码，失败回退 gb18030（GBK 的超集，老象棋软件导出的棋谱常是 GBK）。BOM 由 TextDecoder 去掉。
export function decodeText(bytes) {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    return new TextDecoder('gb18030').decode(bytes);
  }
}

// ---------------------------------------------------------------- 全角判断与评注断行还原
// 导出端（llmchess/records.py 的 wide / chunks）只在两个全角字符之间断中文长句，全角 = Unicode 东亚宽度 W / F。
// JS 没有东亚宽度表，这里列出 W / F 的主要区段（中日韩表意文字、假名、谚文、全角标点与数字、常见 emoji），
// 是近似：漏判只会让断行处多一个或少一个空格，不影响内容。
const WIDE = [
  [0x1100, 0x115f], [0x231a, 0x231b], [0x2329, 0x232a], [0x23e9, 0x23ec], [0x23f0, 0x23f0], [0x23f3, 0x23f3],
  [0x25fd, 0x25fe], [0x2614, 0x2615], [0x2648, 0x2653], [0x267f, 0x267f], [0x2693, 0x2693], [0x26a1, 0x26a1],
  [0x26aa, 0x26ab], [0x26bd, 0x26be], [0x26c4, 0x26c5], [0x26ce, 0x26ce], [0x26d4, 0x26d4], [0x26ea, 0x26ea],
  [0x26f2, 0x26f3], [0x26f5, 0x26f5], [0x26fa, 0x26fa], [0x26fd, 0x26fd], [0x2705, 0x2705], [0x270a, 0x270b],
  [0x2728, 0x2728], [0x274c, 0x274c], [0x274e, 0x274e], [0x2753, 0x2755], [0x2757, 0x2757], [0x2795, 0x2797],
  [0x27b0, 0x27b0], [0x27bf, 0x27bf], [0x2b1b, 0x2b1c], [0x2b50, 0x2b50], [0x2b55, 0x2b55],
  [0x2e80, 0x303e], [0x3041, 0x33ff], [0x3400, 0x4dbf], [0x4e00, 0x9fff], [0xa000, 0xa4cf], [0xa960, 0xa97f],
  [0xac00, 0xd7a3], [0xf900, 0xfaff], [0xfe10, 0xfe19], [0xfe30, 0xfe6f], [0xff01, 0xff60], [0xffe0, 0xffe6],
  [0x16fe0, 0x18cff], [0x1b000, 0x1b2ff], [0x1f004, 0x1f004], [0x1f0cf, 0x1f0cf], [0x1f18e, 0x1f18e],
  [0x1f191, 0x1f19a], [0x1f200, 0x1f2ff], [0x1f300, 0x1f64f], [0x1f680, 0x1f6ff], [0x1f7e0, 0x1f7eb],
  [0x1f90c, 0x1f9ff], [0x1fa70, 0x1faff], [0x20000, 0x3fffd],
];

export function wide(ch) {
  const c = ch.codePointAt(0);
  for (const [a, b] of WIDE) {
    if (c < a) return false;
    if (c <= b) return true;
  }
  return false;
}

// 评注里的换行：两边都是全角字符就直接相接，否则当一个空格；连续空白压成一个空格，去掉首尾空白。
export function unwrap(text) {
  const s = text.replace(/[ \t]*\r?\n[ \t]*/g, '\n');
  const cs = Array.from(s);
  let out = '';
  for (let i = 0; i < cs.length; i++) {
    if (cs[i] !== '\n') { out += cs[i]; continue; }
    const prev = cs[i - 1], next = cs[i + 1];
    out += prev && next && prev !== '\n' && next !== '\n' && wide(prev) && wide(next) ? '' : ' ';
  }
  return out.replace(/\s+/g, ' ').trim();
}

// ---------------------------------------------------------------- 评注命令
// 本项目的命令（真身 docs/design.md 第四节）：数字值。%emt 是 PGN 规范补充的标准命令，写成 h:mm:ss。
export const NUMERIC_CMDS = ['think', 'out', 'in', 'cacheread', 'cachewrite', 'illegal', 'flagged', 'empty', 'dropped'];

// 解析 h:mm:ss / m:ss / 秒数（可带小数）；认不出返回 null。
export function parseClock(v) {
  const m = /^(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)$/.exec(v.trim());
  if (!m) return null;
  const parts = [m[1], m[2], m[3]].filter((x) => x !== undefined).map(Number);
  return parts.reduce((acc, x) => acc * 60 + x, 0);
}

// 一段评注（已 unwrap）→ { cmds: {emt: 秒, think: n, …}, unknown: ['[%clk 0:01:00]', …], text: '理由' }。
// 认得但值写坏的命令也放进 unknown 原样显示。
export function parseComment(comment) {
  const cmds = {}, unknown = [];
  const text = comment.replace(/\[%\s*([A-Za-z0-9_]+)\s*([^\]]*)\]/g, (raw, name, val) => {
    const v = val.trim();
    if (name === 'emt') {
      const s = parseClock(v);
      if (s !== null) { cmds.emt = s; return ' '; }
    } else if (NUMERIC_CMDS.includes(name) && /^-?\d+(\.\d+)?$/.test(v)) {
      cmds[name] = Number(v);
      return ' ';
    }
    unknown.push(raw);
    return ' ';
  });
  return { cmds, unknown, text: text.replace(/\s+/g, ' ').trim() };
}

// ---------------------------------------------------------------- 分词
export const SUFFIX_NAG = { '!': 1, '?': 2, '!!': 3, '??': 4, '!?': 5, '?!': 6 };
export const NAG_SUFFIX = Object.fromEntries(Object.entries(SUFFIX_NAG).map(([k, v]) => [v, k]));
const RESULTS = new Set(['1-0', '0-1', '1/2-1/2', '*', '½-½']);
const TAG_RE = /\[\s*([A-Za-z0-9_]+)\s+"((?:[^"\\]|\\.)*)"\s*\]/y;

function newGame() {
  return { tags: {}, pre: [], moves: [], result: null, errors: [] };
}

// 文本 → 一盘盘棋：[{ tags: {名: 值}, pre: [着法前的评注], moves: [{ text, nags: [n], comments: [已 unwrap 的评注] }],
//   result: '1-0' / '0-1' / '1/2-1/2' / '*' / null, errors: [读不懂的地方] }]。
// 着法号（「12.」「12...」「12.e4」）一律丢掉、按先后顺序交替算两方，所以象棋评注后直接接黑方着法也认。
// 着法后缀的 ! ? !! ?? !? ?! 转成 NAG（$1–$6），和单独写的 $n 一起放进 nags。「;」到行尾是评注，行首「%」整行跳过。
export function parsePgn(text) {
  const games = [];
  let g = newGame();
  let inMoves = false;           // 已经读到着法区：再遇到标签就是下一盘
  const finish = () => {
    if (Object.keys(g.tags).length || g.moves.length || g.pre.length) games.push(g);
    g = newGame();
    inMoves = false;
  };
  const addComment = (raw) => {
    const c = unwrap(raw);
    if (!c) return;
    inMoves = true;
    if (g.moves.length) g.moves[g.moves.length - 1].comments.push(c);
    else g.pre.push(c);
  };
  const addNag = (n) => {
    if (g.moves.length) g.moves[g.moves.length - 1].nags.push(n);
  };
  const n = text.length;
  let i = 0;
  let lineStart = true;
  while (i < n) {
    const ch = text[i];
    if (ch === '\n') { lineStart = true; i++; continue; }
    if (/\s/.test(ch)) { i++; continue; }
    const atLineStart = lineStart;
    lineStart = false;
    if (ch === '%' && atLineStart) {               // 转义行
      while (i < n && text[i] !== '\n') i++;
      continue;
    }
    if (ch === '[') {
      if (inMoves) finish();
      TAG_RE.lastIndex = i;
      const m = TAG_RE.exec(text);
      if (m) {
        g.tags[m[1]] = m[2].replace(/\\(["\\])/g, '$1');
        i = TAG_RE.lastIndex;
      } else {
        const end = text.indexOf('\n', i);
        const stop = end < 0 ? n : end;
        g.errors.push('读不懂的标签：' + text.slice(i, stop).trim());
        i = stop;
      }
      continue;
    }
    if (ch === '{') {
      const end = text.indexOf('}', i + 1);
      const stop = end < 0 ? n : end;
      addComment(text.slice(i + 1, stop));
      i = stop + 1;
      continue;
    }
    if (ch === ';') {
      const end = text.indexOf('\n', i);
      const stop = end < 0 ? n : end;
      addComment(text.slice(i + 1, stop));
      i = stop;
      continue;
    }
    if (ch === '(') {                              // 变着：跳到配对的右括号，中间的评注里的括号不算
      let depth = 0;
      while (i < n) {
        const c = text[i];
        if (c === '{') { const e = text.indexOf('}', i + 1); i = e < 0 ? n : e + 1; continue; }
        if (c === ';') { const e = text.indexOf('\n', i); i = e < 0 ? n : e; continue; }
        if (c === '(') depth++;
        else if (c === ')' && --depth === 0) { i++; break; }
        i++;
      }
      inMoves = true;
      continue;
    }
    if (ch === ')') { i++; continue; }
    // 其余：读到空白或分隔符为止
    let j = i;
    while (j < n && !/[\s{}()\[\];]/.test(text[j])) j++;
    if (j === i) { i++; continue; }            // 单独的 ] 等
    let tok = text.slice(i, j);
    i = j;
    inMoves = true;
    if (RESULTS.has(tok)) {
      g.result = tok === '½-½' ? '1/2-1/2' : tok;
      finish();
      continue;
    }
    let m = /^\$(\d+)$/.exec(tok);
    if (m) { addNag(Number(m[1])); continue; }
    m = /^\d+\s*(?:\.+|…)/.exec(tok);
    if (m) tok = tok.slice(m[0].length);
    if (!tok) continue;
    const sm = /[!?]+$/.exec(tok);
    let nag = null;
    if (sm) {
      nag = SUFFIX_NAG[sm[0]] ?? null;
      tok = tok.slice(0, -sm[0].length);
    }
    if (!tok) { if (nag) addNag(nag); continue; }  // 单独写的「!?」之类
    if (RESULTS.has(tok)) { g.result = tok; finish(); continue; }
    g.moves.push({ text: tok, nags: nag ? [nag] : [], comments: [] });
  }
  finish();
  return games;
}

// 一步的全部评注合成一段再解析（多数棋谱每步至多一段）。
export function moveNote(move) {
  return parseComment(move.comments.join(' '));
}
