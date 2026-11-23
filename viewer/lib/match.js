// 录屏画面要显示的「比赛」信息：棋手显示名、思考 token 累计、比分、结果文字（docs/viewer.md「录屏画面（窄版）的版式」）。
// 纯函数，不碰 DOM；浏览器与 node 都能 import。一盘 = parsePgn 读出的 game 加 replay 走出的 steps。
// lang：界面语言（lib/i18n.js），默认中文；names：显示名覆盖表（i18n.js 的 parseNames，网址参数 names=），默认不覆盖。
import { T, reasonEn } from './i18n.js';

// 模型后端前缀：「claude:opus」→「opus」。其余（引擎、random、人）照原名显示。
const MODEL_PREFIXES = new Set(['agy', 'claude', 'codex', 'deepseek', 'gpt', 'openai', 'gemini', 'grok', 'openrouter']);
// 模型名尾部自带的思考深度后缀（仅用于对外展示名去重，不影响 playerOf().key 与比分归属）。
const EFFORT_SUFFIX_RE = /-(?:minimal|low|medium|high|xhigh|max)$/i;
// 无渠道前缀时仅对整串匹配已知模型 ID 的白名单做规范化，避免误改外部 PGN 棋手人名（如 Claude-Dupont、Stockfish 16）。
const KNOWN_BARE_MODEL_RE = /^(?:gemini-\d+(?:\.\d+)?-[a-z0-9-]+|claude-(?:opus|sonnet|haiku)-\d+[.-]\d+(?:-[a-z0-9-]+)?|claude-\d+[.-]\d+-(?:opus|sonnet|haiku)(?:-[a-z0-9-]+)?|gpt-\d+(?:\.\d+)?[a-z]?(?:-[a-z0-9-]+)?|deepseek-(?:v\d+(?:\.\d+)?(?:-[a-z0-9-]+)?|r\d+(?:-[a-z0-9-]+)?|reasoner|chat)|grok-\d+(?:\.\d+)?(?:-[a-z0-9-]+)?)$/i;

function capWord(w) {
  if (!w) return w;
  if (/^[a-z]\d+(?:\.\d+)*$/i.test(w)) return w[0].toUpperCase() + w.slice(1).toLowerCase();
  if (/^\d/.test(w)) return w;
  return w[0].toUpperCase() + w.slice(1).toLowerCase();
}

function formatModelToken(id, prefix) {
  const clean = id.replace(EFFORT_SUFFIX_RE, '') || id;
  const low = clean.toLowerCase();

  // Gemini 家族：gemini-4-neon → Gemini 4 Neon，gemini-3.8-flash-high → Gemini 3.8 Flash
  if (low === 'gemini' || low.startsWith('gemini-') || prefix === 'gemini') {
    const rest = low.startsWith('gemini-') ? clean.slice(7) : low === 'gemini' ? '' : clean;
    const parts = rest ? rest.split('-').filter(Boolean).map(capWord) : [];
    return ['Gemini', ...parts].join(' ');
  }

  // Claude 家族：claude-opus-5-5-high → Claude Opus 5.5，claude:opus → Claude Opus
  if (low === 'claude' || low.startsWith('claude-') || prefix === 'claude') {
    const rest = low.startsWith('claude-') ? clean.slice(7) : low === 'claude' ? '' : clean;
    if (!rest) return 'Claude';
    let m = rest.match(/^(opus|sonnet|haiku)-(\d+)[.-](\d+)(?:-(.+))?$/i);
    if (m) {
      const tail = m[4] ? ' ' + m[4].split('-').filter(Boolean).map(capWord).join(' ') : '';
      return `Claude ${capWord(m[1])} ${m[2]}.${m[3]}${tail}`;
    }
    m = rest.match(/^(\d+)[.-](\d+)-(opus|sonnet|haiku)(?:-(.+))?$/i);
    if (m) {
      const tail = m[4] ? ' ' + m[4].split('-').filter(Boolean).map(capWord).join(' ') : '';
      return `Claude ${m[1]}.${m[2]} ${capWord(m[3])}${tail}`;
    }
    return ['Claude', ...rest.split('-').filter(Boolean).map(capWord)].join(' ');
  }

  // GPT / Codex / OpenAI 家族：gpt-6.2-astra → GPT-6.2 Astra，codex:astra → GPT Astra
  if (low.startsWith('gpt-') || low === 'gpt' || prefix === 'codex' || prefix === 'gpt' || prefix === 'openai') {
    const m = clean.match(/^gpt-(\d+(?:\.\d+)?[a-z]?)(?:-(.+))?$/i);
    if (m) {
      const tail = m[2] ? ' ' + m[2].split('-').filter(Boolean).map(capWord).join(' ') : '';
      return `GPT-${m[1]}${tail}`;
    }
    const rest = low.startsWith('gpt-') ? clean.slice(4) : low === 'gpt' ? '' : clean;
    const parts = rest ? rest.split('-').filter(Boolean).map(capWord) : [];
    return ['GPT', ...parts].join(' ');
  }

  // DeepSeek 家族：deepseek-v4-pro → DeepSeek V4 Pro，deepseek:reasoner → DeepSeek Reasoner
  if (low === 'deepseek' || low.startsWith('deepseek-') || prefix === 'deepseek') {
    const rest = low.startsWith('deepseek-') ? clean.slice(9) : low === 'deepseek' ? '' : clean;
    const parts = rest ? rest.split('-').filter(Boolean).map(capWord) : [];
    return ['DeepSeek', ...parts].join(' ');
  }

  // Grok 家族：grok-4 → Grok 4
  if (low === 'grok' || low.startsWith('grok-') || prefix === 'grok') {
    const rest = low.startsWith('grok-') ? clean.slice(5) : low === 'grok' ? '' : clean;
    const parts = rest ? rest.split('-').filter(Boolean).map(capWord) : [];
    return ['Grok', ...parts].join(' ');
  }

  return null;
}

// 统一对外棋手显示名（单一事实源，供阅读器普通浏览态、目录页与总览榜共用）。
// 纯展示转换，绝不影响 playerOf().key、比分归属或录屏短名；未知外部 PGN 棋手保守保留原名。
export function displayName(raw, lang = 'zh') {
  const s = String(raw ?? '').trim();
  if (!s) return '?';
  const low = s.toLowerCase();

  if (low === 'random') return lang === 'en' ? 'Random' : '随机棋手';

  // 引擎：Fairy-Stockfish / Stockfish / Maia，其余未知引擎保守保留原名
  if (low.startsWith('engine:')) {
    const body = s.slice(7);
    const fsf = body.match(/^fsf(?::(.+))?$/i);
    if (fsf) return fsf[1] ? `Fairy-Stockfish · ${fsf[1]}` : 'Fairy-Stockfish';
    const sf = body.match(/^(?:sf|stockfish)(?::(.+))?$/i);
    if (sf) return sf[1] ? `Stockfish · ${sf[1]}` : 'Stockfish';
    const maia = body.match(/^maia[-:](.+)$/i);
    if (maia) return `Maia ${maia[1]}`;
    if (/^maia$/i.test(body)) return 'Maia';
    return s;
  }

  const i = s.indexOf(':');
  const hasPrefix = i > 0 && MODEL_PREFIXES.has(s.slice(0, i).toLowerCase());
  const prefix = hasPrefix ? s.slice(0, i).toLowerCase() : '';
  const body = hasPrefix ? s.slice(i + 1) : s;

  if (prefix === 'openrouter') {
    const slash = body.indexOf('/');
    const sub = slash > 0 ? body.slice(slash + 1) : body;
    return formatModelToken(sub, '') ?? (sub.replace(EFFORT_SUFFIX_RE, '') || sub);
  }

  // agy: 渠道同时运行多家族模型，严禁按 agy: 臆断厂商；非 Gemini 家族模型经 agy 代理时保留 (agy) 渠道标记。
  if (prefix === 'agy') {
    const formatted = formatModelToken(body, '');
    const base = formatted ?? (body.replace(EFFORT_SUFFIX_RE, '') || body);
    const isGemini = /^gemini(?:-|$)/i.test(body);
    return isGemini ? base : `${base} (agy)`;
  }

  if (hasPrefix) {
    const formatted = formatModelToken(body, prefix);
    return formatted ?? (body.replace(EFFORT_SUFFIX_RE, '') || body);
  }

  if (KNOWN_BARE_MODEL_RE.test(s)) {
    return formatModelToken(s, '') ?? s;
  }
  return s;
}

// 普通浏览模式的棋手展示信息：复用 playerOf() 的 key 与 effort，但 name 统一走 displayName（显式 names= 覆盖优先）。
export function displayPlayer(game, side, { lang = 'zh', names = null } = {}) {
  const p = playerOf(game, side, names);
  const t = game.tags, raw = side === 'w' ? (t.Red ?? t.White ?? '?') : (t.Black ?? '?');
  if (shownName(names, raw, playerOf(game, side).name) !== undefined) return p;
  return { ...p, name: displayName(raw, lang) };
}

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
  const low = p.name.toLowerCase(), vLow = v ? v.toLowerCase() : '';
  const hasVendor = v && (low === vLow || low.startsWith(vLow + '-') || low.startsWith(vLow + ' ') || low.startsWith(vLow + '_'));
  return { name: v && !hasVendor ? `${v} ${p.name}` : p.name, effort: p.effort };
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
export function totals(games, names = null, opts = null) {
  const s = scoresBefore(games, games.length);
  const useDisplay = Boolean(opts?.display);
  const lang = opts?.lang || 'zh';
  const seen = [];
  for (const g of games) {
    for (const side of ['w', 'b']) {
      const p = useDisplay ? displayPlayer(g, side, { lang, names }) : playerOf(g, side, names);
      if (!seen.some((x) => x.key === p.key)) seen.push(p);
    }
  }
  return seen.map((p, i) => ({ ...p, score: s[p.key] || 0, i }))
    .sort((a, b) => b.score - a.score || a.i - b.i)
    .map(({ i, ...p }) => p);
}
