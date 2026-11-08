// 把 parsePgn 读出的一盘棋逐步走完，得到每步的起止格、将军标记和走后局面，给页面画棋盘用。
// 国际象棋用 vendor 的 chess.js 走子、判将军；中国象棋用 xiangqi.js。
import { Chess } from '../vendor/chess.js/chess.js';
import { parsePgn } from './pgn.js';
import * as XQ from './xiangqi.js';

export const CLS_NAG = { blunder: 4, mistake: 2, inaccuracy: 6 };

// 这盘是不是中国象棋：xqbase 的 Game 标签，或者有 Red 标签，或者第一步是中文。
export function isXiangqi(game) {
  if (/chinese/i.test(game.tags.Game || '')) return true;
  if ('Red' in game.tags) return true;
  return game.moves.length > 0 && /[一-鿿]/.test(game.moves[0].text);
}

// → { kind: 'xiangqi' / 'chess', start: 起始 FEN, steps: [...], error: null 或 { ply, text, message } }。
// steps[i] 是第 i+1 个半回合：{ ply, side: 'w'/'b', text: 记谱原文, from, to, move: 坐标着法（象棋 ICCS，
// 国际象棋 UCI 含升变字母）, capture: 被吃的子或 null, check: 走完对方是否被将军, fen: 走完的局面 }。
// 国际象棋另有 san（chess.js 规范化后的写法），中国象棋另有 wxf（xiangqi.js 的 wxfMove 从坐标算出的 WXF 记法，英文界面显示用）。走不下去时停在那一步，error 说明原因，steps 只到出错前。
export function replay(game) {
  return isXiangqi(game) ? replayXiangqi(game) : replayChess(game);
}

export function replayXiangqi(game) {
  const start = game.tags.FEN || XQ.START_FEN;
  const out = { kind: 'xiangqi', start, steps: [], error: null };
  let pos;
  try {
    pos = XQ.parseFen(start);
  } catch (e) {
    out.error = { ply: 0, text: '', message: e.message };
    return out;
  }
  game.moves.forEach((m, i) => {
    if (out.error) return;
    try {
      const mv = XQ.parseMove(pos, m.text);
      const side = pos.turn, wxf = XQ.wxfMove(pos, mv.iccs);
      pos = XQ.makeMove(pos, mv.iccs);
      out.steps.push({ ply: i + 1, side, text: m.text, wxf, from: mv.from, to: mv.to, move: mv.iccs,
                       capture: mv.capture, check: XQ.inCheck(pos, pos.turn), fen: XQ.toFen(pos) });
    } catch (e) {
      out.error = { ply: i + 1, text: m.text, message: e.message };
    }
  });
  return out;
}

export function replayChess(game) {
  const out = { kind: 'chess', start: null, steps: [], error: null };
  let chess;
  try {
    chess = game.tags.FEN ? new Chess(game.tags.FEN) : new Chess();
  } catch (e) {
    out.error = { ply: 0, text: '', message: e.message };
    return out;
  }
  out.start = chess.fen();
  game.moves.forEach((m, i) => {
    if (out.error) return;
    try {
      const side = chess.turn();
      const r = chess.move(m.text, { strict: false });
      out.steps.push({ ply: i + 1, side, text: m.text, san: r.san, from: r.from, to: r.to,
                       move: r.from + r.to + (r.promotion || ''), capture: r.captured || null,
                       check: chess.inCheck(), fen: chess.fen() });
    } catch (e) {
      out.error = { ply: i + 1, text: m.text, message: e.message };
    }
  });
  return out;
}

function fenStateKey(fen, kind) {
  if (typeof fen !== 'string') return null;
  const parts = fen.trim().split(/\s+/);
  if (parts.length < 2) return null;
  if (kind === 'xiangqi') {
    try {
      return XQ.toFen(XQ.parseFen(fen));
    } catch {
      return null;
    }
  }
  try {
    return new Chess(fen.trim()).fen();
  } catch {
    return null;
  }
}

export function parseAnalysisJsonl(text, name = '') {
  const label = name ? `（${name}）` : '';
  const lines = String(text || '').trim().split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) throw new Error(`分析文件为空${label}`);
  const rows = [];
  const seenPlies = new Set();
  for (const line of lines) {
    let obj;
    try {
      obj = JSON.parse(line);
    } catch {
      throw new Error(`分析文件 JSON 格式错误${label}`);
    }
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
      throw new Error(`分析文件记录不是对象${label}`);
    }
    if (!Number.isInteger(obj.ply) || obj.ply < 1 || typeof obj.move !== 'string' || !obj.move.trim() || typeof obj.fen !== 'string' || !obj.fen.trim()) {
      throw new Error(`分析文件缺少有效 ply / move / fen 字段${label}`);
    }
    if (seenPlies.has(obj.ply)) {
      throw new Error(`分析文件存在重复的半回合 ply=${obj.ply}${label}`);
    }
    seenPlies.add(obj.ply);
    rows.push(obj);
  }
  return rows;
}

export function analysisMatchesRep(rows, rep) {
  if (!Array.isArray(rows) || !rows.length || !rep || !Array.isArray(rep.steps) || !rep.steps.length) return false;
  for (const r of rows) {
    if (!Number.isInteger(r.ply) || r.ply < 1 || r.ply > rep.steps.length) return false;
    const step = rep.steps[r.ply - 1];
    if (typeof r.move !== 'string' || r.move.trim().toLowerCase() !== step.move.toLowerCase()) return false;
    const expectedFen = r.ply === 1 ? rep.start : rep.steps[r.ply - 2].fen;
    const gotKey = fenStateKey(r.fen, rep.kind);
    const wantKey = fenStateKey(expectedFen, rep.kind);
    if (!gotKey || !wantKey || gotKey !== wantKey) return false;
  }
  return true;
}

function isAnalysisInput(name, text) {
  if (/\.pgn$/i.test(name)) return false;
  if (/\.jsonl$/i.test(name)) return true;
  const lines = String(text || '').trim().split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return false;
  return lines.every((l) => /^\{\s*"/.test(l) && l.endsWith('}'));
}

function dirOf(name) {
  const s = String(name || '').trim();
  const i = s.lastIndexOf('/');
  return i >= 0 ? s.slice(0, i) : '';
}

// 解析输入文本列表（支持纯字符串或 { name, text }），将 analysis.jsonl 严格校验后叠加到对应棋谱。
// 校验规则：逐条核对 ply、走子坐标 move、走前局面 fen；多盘 PGN 歧义、孤立分析或着法/局面不匹配均显式抛错。
// 恶手标注口径（与 agi_chess/analyze.py 一致）：国际象棋仅用 lichess（胜率口径），中国象棋仅用 cls（厘兵口径），不跨口径补齐。
export function loadGamesWithAnalysis(inputs) {
  const entries = [];
  const analyses = [];
  for (const item of inputs || []) {
    const name = typeof item === 'string' ? '' : String(item?.name || '');
    const text = typeof item === 'string' ? item : String(item?.text || '');
    if (isAnalysisInput(name, text)) {
      analyses.push({ name, dir: dirOf(name), rows: parseAnalysisJsonl(text, name) });
      continue;
    }
    const gList = parsePgn(text);
    for (const game of gList) {
      entries.push({
        game,
        rep: replay(game),
        name,
        dir: dirOf(name),
        multiInFile: gList.length > 1,
        hasAnalysis: false,
      });
    }
  }
  if (analyses.length > 0 && entries.length === 0) {
    throw new Error('只有分析文件，没有对应的棋谱（game.pgn）');
  }
  for (const a of analyses) {
    const label = a.name ? `（${a.name}）` : '';
    let matched = entries.filter((e) => analysisMatchesRep(a.rows, e.rep));
    if (!matched.length) {
      throw new Error(`分析文件与棋谱不匹配（着法或局面不一致）${label}`);
    }
    if (a.dir && entries.some((e) => e.dir)) {
      const dirMatched = matched.filter((e) => e.dir === a.dir);
      if (!dirMatched.length) {
        throw new Error(`分析文件与棋谱目录不一致${label}`);
      }
      matched = dirMatched;
    }
    if (matched.length > 1 || matched[0].multiInFile) {
      throw new Error(`多盘棋谱存在歧义，无法唯一关联分析文件${label}`);
    }
    const target = matched[0];
    if (target.hasAnalysis) {
      throw new Error(`同一盘棋谱重复关联了多份分析文件${label}`);
    }
    target.hasAnalysis = true;
    for (const r of a.rows) {
      const mv = target.game.moves[r.ply - 1];
      if (!mv) continue;
      const rawTag = target.rep.kind === 'chess' ? r.lichess : r.cls;
      const tag = typeof rawTag === 'string' ? rawTag.trim().toLowerCase() : '';
      const nag = CLS_NAG[tag];
      if (nag && !mv.nags.includes(nag)) mv.nags.push(nag);
    }
  }
  return entries.map(({ game, rep }) => ({ game, rep }));
}
