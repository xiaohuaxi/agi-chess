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
