// 把 parsePgn 读出的一盘棋逐步走完，得到每步的起止格、将军标记和走后局面，给页面画棋盘用。
// 国际象棋用 vendor 的 chess.js 走子、判将军；中国象棋用 xiangqi.js。
import { Chess } from '../vendor/chess.js/chess.js';
import * as XQ from './xiangqi.js';

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
