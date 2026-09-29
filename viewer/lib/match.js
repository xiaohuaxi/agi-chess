// 录屏画面要显示的「比赛」信息：棋手显示名、思考 token 累计、比分、结果文字（docs/viewer.md「录屏画面（窄版）的版式」）。
// 纯函数，不碰 DOM；浏览器与 node 都能 import。一盘 = parsePgn 读出的 game 加 replay 走出的 steps。

// 模型后端前缀：「claude:opus」→「opus」。其余（引擎、random、人）照原名显示。
const MODEL_PREFIXES = new Set(['claude', 'codex', 'deepseek', 'gpt', 'openai', 'gemini', 'grok', 'openrouter']);

// 两方在标签里的名字：国际象棋 White / Black，中国象棋 Red / Black。side 是 'w'（红 / 白）或 'b'。
export function playerOf(game, side) {
  const t = game.tags;
  const name = side === 'w' ? (t.Red ?? t.White ?? '?') : (t.Black ?? '?');
  const effort = side === 'w' ? (t.RedEffort ?? t.WhiteEffort ?? '') : (t.BlackEffort ?? '');
  const i = name.indexOf(':');
  const model = i > 0 && MODEL_PREFIXES.has(name.slice(0, i).toLowerCase());
  const short = model ? name.slice(i + 1).toLowerCase() : name;
  return { name: short, effort: model ? effort.toLowerCase() : effort, key: short + '+' + effort };
}

// 起始局面的回合数（FEN 第 6 段），没有就是 1。
export function startMoveNumber(game) {
  const f = (game.tags.FEN || '').trim().split(/\s+/);
  const n = Number(f[5]);
  return Number.isInteger(n) && n > 0 ? n : 1;
}

// token 数字的写法：不到一千照写，一万以内一位小数（3.4k），一百万以内取整（38k），再大写 M（1.2M）。
export function fmtTokens(n) {
  if (n < 1000) return String(Math.round(n));
  if (n < 9950) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
  if (n < 999500) return Math.round(n / 1000) + 'k';
  return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
}

// 每个半回合后的思考 token 累计：think[side][ply]（ply 0 = 开局前），has[side] = 这一方有没有给过 %think。
// notes[i] 是第 i+1 步的 moveNote 结果（pgn.js）。
export function thinkTotals(notes) {
  const think = { w: [0], b: [0] }, has = { w: false, b: false };
  notes.forEach((n, i) => {
    const side = i % 2 === 0 ? 'w' : 'b';
    const v = n.cmds.think;
    if (v !== undefined) has[side] = true;
    for (const s of ['w', 'b']) think[s].push(think[s][i] + (s === side && v ? v : 0));
  });
  return { think, has };
}

// PGN 结果 → 两方得分；未完（'*' 或没写）返回 null。
export function points(result) {
  if (result === '1-0') return { w: 1, b: 0 };
  if (result === '0-1') return { w: 0, b: 1 };
  if (result === '1/2-1/2') return { w: 0.5, b: 0.5 };
  return null;
}

// 第 index 盘开始前各人的比分（按 playerOf().key 归属）：{ key: 分 }。
export function scoresBefore(games, index) {
  const s = {};
  for (let i = 0; i < index; i++) {
    const g = games[i], p = points(g.result ?? g.tags.Result);
    for (const side of ['w', 'b']) {
      const k = playerOf(g, side).key;
      s[k] = (s[k] || 0) + (p ? p[side] : 0);
    }
  }
  return s;
}

export const fmtScore = (x) => (Number.isInteger(x) ? String(x) : x.toFixed(1));

// 结果横幅：「红方胜 · 将死」「和棋 · 三次重复」。xiangqi 决定叫红方还是白方。
export function resultText(game, xiangqi) {
  const r = game.result ?? game.tags.Result;
  const head = r === '1-0' ? (xiangqi ? '红方胜' : '白方胜') : r === '0-1' ? '黑方胜' : r === '1/2-1/2' ? '和棋' : null;
  if (!head) return null;
  const why = game.tags.Termination;
  return why ? head + ' · ' + why : head;
}
