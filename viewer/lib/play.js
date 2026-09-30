// 播放顺序（docs/viewer.md「播放」）：把一场比赛（连播清单里的所有盘）排成一格一格的画面，每格停多久。
// 纯函数，不碰 DOM；页面的自动播放和录制接口 viewer.next() 都照这张单子走。

// 网址参数 → 播放设置。时长单位是秒，不合法（非数字、负数）时用默认值。
export const DEFAULTS = { gap: 2.5, titlehold: 3, resulthold: 4, summaryhold: 5 };

export function playOptions(params) {
  const sec = (k) => {
    const v = params.get(k);
    const x = v === null || v.trim() === '' ? NaN : Number(v);
    return Number.isFinite(x) && x >= 0 ? x : DEFAULTS[k];
  };
  return {
    gap: sec('gap'), titlehold: sec('titlehold'), resulthold: sec('resulthold'), summaryhold: sec('summaryhold'),
    title: params.get('title') !== '0',
  };
}

// games[i] = { plies: 走得通的半回合数, over: 这盘有结果（或读到一半读不懂、要在结果格报错） }。
// → [{ kind, game, ply, hold }]，kind 依次是：
//   每盘：title（标题画面，盖在开局局面上；title=0 时换成停 gap 的开局局面，kind 记 move、ply 0）
//        → move（第 1 … N 个半回合，各停 gap）→ result（终局横幅，这盘有结果才有）；
//   最后：end——多盘时画总比分、停 summaryhold；单盘不改画面、hold 0。
export function sequence(games, opt) {
  const out = [];
  games.forEach((g, gi) => {
    out.push(opt.title ? { kind: 'title', game: gi, ply: 0, hold: opt.titlehold } : { kind: 'move', game: gi, ply: 0, hold: opt.gap });
    for (let p = 1; p <= g.plies; p++) out.push({ kind: 'move', game: gi, ply: p, hold: opt.gap });
    if (g.over) out.push({ kind: 'result', game: gi, ply: g.plies, hold: opt.resulthold });
  });
  out.push(games.length > 1 ? { kind: 'end', game: null, ply: null, hold: opt.summaryhold }
                            : { kind: 'end', game: null, ply: null, hold: 0 });
  return out;
}
