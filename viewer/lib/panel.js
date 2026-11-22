// 宽版右侧面板要显示的东西（docs/viewer.md「版式」宽版）：着法列表的行、当前这步的各项数字（带中文标签）、标注。
// 纯函数，不碰 DOM；浏览器与 node 都能 import。lang 是界面语言（lib/i18n.js），默认中文。

import { NAG_SUFFIX } from './pgn.js';
import { T } from './i18n.js';

// 着法标注（NAG $1–$6 与 ! ? 等后缀一一对应）的说法在 i18n.js 的 nag；别的 $n 只显示编号。

export function nagText(n) {
  return NAG_SUFFIX[n] ?? `$${n}`;
}

export function nagLabel(n, lang = 'zh') {
  return NAG_SUFFIX[n] ? `${NAG_SUFFIX[n]} ${T(lang).nag[n]}` : `$${n}`;
}

// 用时：秒 → 「5 秒」「1 分 12 秒」「1 时 2 分 3 秒」（英文「5s」「1m 12s」「1h 2m 3s」），小数秒保留一位。
export function fmtSeconds(s, lang = 'zh') {
  const [hu, mu, su] = T(lang).hms, sep = lang === 'en' ? '' : ' ';
  const r = Math.round(s * 10) / 10;
  const h = Math.floor(r / 3600), m = Math.floor((r % 3600) / 60), sec = Math.round((r % 60) * 10) / 10;
  const parts = [];
  if (h) parts.push(`${h}${sep}${hu}`);
  if (h || m) parts.push(`${m}${sep}${mu}`);
  parts.push(`${sec}${sep}${su}`);
  return parts.join(' ');
}

// 评注命令的显示顺序（design.md 第四节的口径）；各命令的标签在 i18n.js 的 cmd。
// dropped 只有开了 drop_thinking 的一方有，0 也写（design.md 第四节）。
export const CMD_KEYS = ['emt', 'think', 'out', 'in', 'cacheread', 'cachewrite', 'illegal', 'flagged', 'empty', 'dropped'];

// 一步的评注（moveNote 的结果）→ [{ key, label, value }]，只列这步写了的命令。
export function noteItems(note, lang = 'zh') {
  const out = [];
  for (const k of CMD_KEYS) {
    const v = note.cmds[k];
    if (v === undefined) continue;
    out.push({ key: k, label: T(lang).cmd[k], value: k === 'emt' ? fmtSeconds(v, lang) : v.toLocaleString('en-US') });
  }
  return out;
}

// 着法列表的行：每回合一行 { no, w, b }，w / b 是 { ply, text } 或 null（黑方先走时第一行白 / 红格空着）。
// text 是记谱（国际象棋用 SAN，带 + #；象棋用棋谱里的中文记谱，wxf 为 true 时换成 WXF 记法）加标注后缀。
export function moveRows(steps, moves, startTurn, moveNo0, xiangqi, wxf = false) {
  const rows = [];
  steps.forEach((st, i) => {
    const k = i + (startTurn === 'b' ? 1 : 0);
    const no = moveNo0 + Math.floor(k / 2);
    if (!rows.length || rows[rows.length - 1].no !== no) rows.push({ no, w: null, b: null });
    const nags = (moves[i]?.nags || []).map(nagText).join('');
    rows[rows.length - 1][st.side] = { ply: i + 1, text: (xiangqi ? (wxf ? st.wxf : st.text) : st.san) + nags };
  });
  return rows;
}

// ---------------------------------------------------------------- 逐着引擎评估换算（统一白方 / 红方固定先手视角）
const EVAL_RE = /^(cp|mate|end)\s+([+-]?\d+)$/;

function parseEvalRaw(raw) {
  if (typeof raw !== 'string') return null;
  const m = raw.trim().match(EVAL_RE);
  return m ? { kind: m[1], n: Number(m[2]) } : null;
}

function fmtEvalToken(parsed, k, xiangqi) {
  if (!parsed || parsed.kind === 'end') return null;
  if (parsed.kind === 'mate') {
    if (parsed.n === 0) return null;
    const m = k * parsed.n;
    return m > 0 ? `+M${Math.abs(parsed.n)}` : `-M${Math.abs(parsed.n)}`;
  }
  const v = k * parsed.n;
  if (xiangqi) return v === 0 ? '0' : v > 0 ? `+${v}` : String(v);
  return v === 0 ? '0.00' : v > 0 ? `+${(v / 100).toFixed(2)}` : (v / 100).toFixed(2);
}

export function formatStepEval(step, xiangqi, lang = 'zh') {
  const ev = step?.eval;
  if (!ev) return null;
  const L = T(lang);
  const k = step.side === 'w' ? 1 : -1;
  const bParsed = parseEvalRaw(ev.before);
  const aParsed = parseEvalRaw(ev.after);
  let score = null;
  if (bParsed && aParsed && aParsed.kind !== 'end') {
    const bTxt = fmtEvalToken(bParsed, k, xiangqi);
    const aTxt = fmtEvalToken(aParsed, k, xiangqi);
    if (bTxt !== null && aTxt !== null) {
      if (!xiangqi) score = `${bTxt} → ${aTxt}`;
      else if (bParsed.kind === 'cp' && aParsed.kind === 'cp') score = `${bTxt} → ${aTxt} cp`;
      else if (bParsed.kind === 'cp') score = `${bTxt} cp → ${aTxt}`;
      else if (aParsed.kind === 'cp') score = `${bTxt} → ${aTxt} cp`;
      else score = `${bTxt} → ${aTxt}`;
    }
  }
  let wp = null;
  if (!xiangqi && aParsed?.kind !== 'end' && typeof ev.wp_before === 'number' && typeof ev.wp_after === 'number') {
    const w1 = step.side === 'w' ? ev.wp_before : 100 - ev.wp_before;
    const w2 = step.side === 'w' ? ev.wp_after : 100 - ev.wp_after;
    wp = `${w1.toFixed(1)}% → ${w2.toFixed(1)}%`;
  }
  let best = null;
  if (ev.played_best === false && typeof ev.best === 'string' && ev.best.length >= 4) {
    best = xiangqi ? (lang === 'en' ? ev.bestWxf : ev.bestZh) : ev.bestSan;
  }
  if (!score && !wp && !best) return null;
  return {
    scoreLabel: xiangqi ? L.evalRed : L.evalWhite,
    score,
    wpLabel: L.evalWp,
    wp,
    bestLabel: L.evalBest,
    best,
  };
}

// ---------------------------------------------------------------- 通道内部重试告警分段（精确匹配 3 种已知英文注入模板，零误切）
export const CHANNEL_WARN_RE = /⚠ (?:Model produced invalid output\.|Your previous response (?:was blocked by content safety filters Please provide a response that complies with content policies, or briefly explain to the user why you cannot help with this request|contained an improperly formatted function call: Malformed function call: Failed to parse function call: Function call is empty - no input to parse\. Please retry with a properly formatted function call) Retries remaining: \d+)/g;

export function splitWarnings(text) {
  const s = String(text || '');
  if (!s) return [];
  const out = [];
  let pos = 0;
  for (const m of s.matchAll(CHANNEL_WARN_RE)) {
    const start = m.index, end = start + m[0].length;
    if ((start > 0 && s[start - 1] !== ' ') || (end < s.length && s[end] !== ' ')) continue;
    if (start > pos) {
      const prev = s.slice(pos, start - 1);
      if (prev) out.push({ warn: false, text: prev });
    }
    out.push({ warn: true, text: m[0] });
    pos = end < s.length && s[end] === ' ' ? end + 1 : end;
  }
  if (!out.length) return [{ warn: false, text: s }];
  if (pos < s.length) out.push({ warn: false, text: s.slice(pos) });
  return out;
}
