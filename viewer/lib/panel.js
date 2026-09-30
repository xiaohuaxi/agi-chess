// 宽版右侧面板要显示的东西（docs/viewer.md「版式」宽版）：着法列表的行、当前这步的各项数字（带中文标签）、标注。
// 纯函数，不碰 DOM；浏览器与 node 都能 import。

import { NAG_SUFFIX } from './pgn.js';

// 着法标注（NAG $1–$6 与 ! ? 等后缀一一对应）的中文说法；别的 $n 只显示编号。
const NAG_NAMES = { 1: '好棋', 2: '错着', 3: '妙着', 4: '大错', 5: '有意思', 6: '可疑' };

export function nagText(n) {
  return NAG_SUFFIX[n] ?? `$${n}`;
}

export function nagLabel(n) {
  return NAG_SUFFIX[n] ? `${NAG_SUFFIX[n]} ${NAG_NAMES[n]}` : `$${n}`;
}

// 用时：秒 → 「5 秒」「1 分 12 秒」「1 时 2 分 3 秒」，小数秒保留一位。
export function fmtSeconds(s) {
  const r = Math.round(s * 10) / 10;
  const h = Math.floor(r / 3600), m = Math.floor((r % 3600) / 60), sec = Math.round((r % 60) * 10) / 10;
  const parts = [];
  if (h) parts.push(`${h} 时`);
  if (h || m) parts.push(`${m} 分`);
  parts.push(`${sec} 秒`);
  return parts.join(' ');
}

// 评注命令 → 中文标签（design.md 第四节的口径），按显示顺序。
export const CMD_LABELS = [
  ['emt', '用时'], ['think', '思考 token'], ['out', '输出 token'], ['in', '输入 token'],
  ['cacheread', '缓存读'], ['cachewrite', '缓存写'], ['illegal', '非法重选'], ['flagged', '被拦截'], ['empty', '空回复'],
  ['dropped', '去掉的思考段'],   // 只有开了 drop_thinking 的一方有，0 也写（design.md 第四节）
];

// 一步的评注（moveNote 的结果）→ [{ key, label, value }]，只列这步写了的命令。
export function noteItems(note) {
  const out = [];
  for (const [k, label] of CMD_LABELS) {
    const v = note.cmds[k];
    if (v === undefined) continue;
    out.push({ key: k, label, value: k === 'emt' ? fmtSeconds(v) : v.toLocaleString('en-US') });
  }
  return out;
}

// 着法列表的行：每回合一行 { no, w, b }，w / b 是 { ply, text } 或 null（黑方先走时第一行白 / 红格空着）。
// text 是记谱（国际象棋用 SAN，带 + #）加标注后缀。
export function moveRows(steps, moves, startTurn, moveNo0, xiangqi) {
  const rows = [];
  steps.forEach((st, i) => {
    const k = i + (startTurn === 'b' ? 1 : 0);
    const no = moveNo0 + Math.floor(k / 2);
    if (!rows.length || rows[rows.length - 1].no !== no) rows.push({ no, w: null, b: null });
    const nags = (moves[i]?.nags || []).map(nagText).join('');
    rows[rows.length - 1][st.side] = { ply: i + 1, text: (xiangqi ? st.text : st.san) + nags };
  });
  return rows;
}
