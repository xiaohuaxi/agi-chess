// 录屏画面要显示的「比赛」信息：棋手显示名、思考 token 累计、比分、结果文字（docs/viewer.md「录屏画面（窄版）的版式」）。
// 纯函数，不碰 DOM；浏览器与 node 都能 import。一盘 = parsePgn 读出的 game 加 replay 走出的 steps。
// lang：界面语言（lib/i18n.js），默认中文；names：显示名覆盖表（i18n.js 的 parseNames，网址参数 names=），默认不覆盖。
import { T, reasonEn } from './i18n.js';

// 模型后端前缀：「claude:opus」→「opus」。其余（引擎、random、人）照原名显示。
const MODEL_PREFIXES = new Set(['claude', 'codex', 'deepseek', 'gpt', 'openai', 'gemini', 'grok', 'openrouter']);

// 两方在标签里的名字：国际象棋 White / Black，中国象棋 Red / Black。side 是 'w'（红 / 白）或 'b'。
// names 里有这个人时 name 换成显示名；key（算比分用）始终按棋谱里的名字，覆盖不影响谁的分归谁。
export function playerOf(game, side, names = null) {
  const t = game.tags;
  const name = side === 'w' ? (t.Red ?? t.White ?? '?') : (t.Black ?? '?');
  const effort = side === 'w' ? (t.RedEffort ?? t.WhiteEffort ?? '') : (t.BlackEffort ?? '');
  const i = name.indexOf(':');
  const model = i > 0 && MODEL_PREFIXES.has(name.slice(0, i).toLowerCase());
  const short = model ? name.slice(i + 1).toLowerCase() : name;
  return { name: shownName(names, name, short) ?? short, effort: model ? effort.toLowerCase() : effort, key: short + '+' + effort };
}

// names 里给这个人的显示名：先按棋谱原名、再按简称找，都不分大小写；没有返回 undefined。
function shownName(names, raw, short) {
  return names?.get(raw.toLowerCase()) ?? names?.get(short.toLowerCase());
}

// 标题画面用的全称：观众不一定知道 astra 是哪家，前面补上厂商（「claude:opus」→「Claude opus」、「codex:astra」→「GPT astra」）。
// 认不出的后端照原名；深度同 playerOf。
const VENDORS = { claude: 'Claude', codex: 'GPT', gpt: 'GPT', openai: 'GPT', deepseek: 'DeepSeek', gemini: 'Gemini', grok: 'Grok' };

// vendor=false：不补厂商（网址参数 vendor=0）。names 覆盖了的名字照显示名写、不补厂商。
export function fullName(game, side, vendor = true, names = null) {
  const p = playerOf(game, side, names);
  const t = game.tags, raw = side === 'w' ? (t.Red ?? t.White ?? '?') : (t.Black ?? '?');
  if (shownName(names, raw, playerOf(game, side).name) !== undefined) return { name: p.name, effort: p.effort };   // 覆盖了
  const v = vendor && VENDORS[raw.slice(0, Math.max(0, raw.indexOf(':'))).toLowerCase()];
  return { name: v ? `${v} ${p.name}` : p.name, effort: p.effort };
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

// 结束原因只留事实：去掉括注（导出端写的「满 200 个半回合（研究设的上限），判和」→「满 200 个半回合，判和」），
// 导出不改，显示时处理。英文界面按 i18n.js 的对照表换成英文（那边的写法本来就只留事实）。
export function cleanReason(why, lang = 'zh') {
  if (lang === 'en') return reasonEn(why);
  return (why || '').replace(/\s*[（(][^（）()]*[）)]\s*/g, '').replace(/\s+([，,。])/g, '$1').trim();
}

// 结果横幅要的几样：head「红方胜」「和棋」，why 结束原因（已去括注，可能为空），winner 胜方 'w' / 'b' / null。
// 未完的盘返回 null。xiangqi 决定叫红方还是白方。
export function resultParts(game, xiangqi, lang = 'zh') {
  const r = game.result ?? game.tags.Result, L = T(lang);
  const head = r === '1-0' ? (xiangqi ? L.redWins : L.whiteWins) : r === '0-1' ? L.blackWins : r === '1/2-1/2' ? L.draw : null;
  if (!head) return null;
  return { head, why: cleanReason(game.tags.Termination, lang), winner: r === '1-0' ? 'w' : r === '0-1' ? 'b' : null };
}

export function resultText(game, xiangqi, lang = 'zh') {
  const p = resultParts(game, xiangqi, lang);
  return p && (p.why ? p.head + ' · ' + p.why : p.head);
}

// 连播播完后的总比分：每个出场的人（名字 + 思考深度）一行，按总分从高到低，同分按出场先后。
export function totals(games, names = null) {
  const s = scoresBefore(games, games.length);
  const seen = [];
  for (const g of games) {
    for (const side of ['w', 'b']) {
      const p = playerOf(g, side, names);
      if (!seen.some((x) => x.key === p.key)) seen.push(p);
    }
  }
  return seen.map((p, i) => ({ ...p, score: s[p.key] || 0, i }))
    .sort((a, b) => b.score - a.score || a.i - b.i)
    .map(({ i, ...p }) => p);
}
