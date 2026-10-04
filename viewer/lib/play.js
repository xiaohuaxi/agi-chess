// 播放顺序（docs/viewer.md「播放」）：把一场比赛（连播清单里的所有盘）排成一格一格的画面，每格停多久。
// 纯函数，不碰 DOM；页面的自动播放和录制接口 viewer.next() 都照这张单子走。

// 网址参数 → 播放设置。时长单位是秒，不合法（非数字、负数）时用默认值。
// anim：走子滑动动画的时长，算在这步的 gap 之内（这格停 gap − anim），0 关掉动画。
// openhold：每盘开局局面（第一步之前那格）停多久，默认跟 gap 一样（所以不在 DEFAULTS 里）；
// 视频开头停太久读者会以为卡住，出片时可以单独调短。标题画面那格不受它管（停 titlehold）。
export const DEFAULTS = { gap: 1.8, titlehold: 3, resulthold: 4, summaryhold: 5, anim: 0.3 };

export function playOptions(params) {
  const sec = (k, dflt = DEFAULTS[k]) => {
    const v = params.get(k);
    const x = v === null || v.trim() === '' ? NaN : Number(v);
    return Number.isFinite(x) && x >= 0 ? x : dflt;
  };
  const gap = sec('gap');
  return {
    gap, openhold: sec('openhold', gap), titlehold: sec('titlehold'), resulthold: sec('resulthold'), summaryhold: sec('summaryhold'),
    anim: sec('anim'), title: params.get('title') === '1',   // 标题画面默认不加，title=1 才加
  };
}

// games[i] = { plies: 走得通的半回合数, over: 这盘有结果（或读到一半读不懂、要在结果格报错），
//              captures: 第 1 … N 步各是不是吃子（可不给，按都不是吃子算） }。
// → [{ kind, game, ply, hold, anim, sound }]，kind 依次是：
//   每盘：title（标题画面，盖在开局局面上，只在 title=1 时有；默认换成停 openhold 的开局局面，kind 记 move、ply 0；
//        openhold 没给时按 gap）
//        → move（第 1 … N 个半回合，各停 gap）→ result（终局横幅，这盘有结果才有）；
//   最后：end——多盘时画总比分、停 summaryhold；单盘不改画面、hold 0。
// anim 是这格开头走子滑动的秒数，只有第 1 … N 个半回合那几格有（其余为 0）；它算在 gap 之内：
// anim = min(opt.anim, gap)，hold = gap − anim，一格总长仍是 gap（docs/viewer.md「录屏：脚本出片」）。
// sound 是这格响哪声（docs/viewer.md「走子音效」）：第 1 … N 步 'capture' 或 'move'，result 格 'end'，其余 null；
// 响在这格开头再过 anim 秒，也就是棋子落地那一刻（anim 为 0 时就是格的开头）。
export function sequence(games, opt) {
  const out = [];
  const a = Math.min(opt.anim ?? 0, opt.gap);
  const cell = (kind, game, ply, hold, anim = 0, sound = null) => ({ kind, game, ply, hold, anim, sound });
  games.forEach((g, gi) => {
    out.push(opt.title ? cell('title', gi, 0, opt.titlehold) : cell('move', gi, 0, opt.openhold ?? opt.gap));
    for (let p = 1; p <= g.plies; p++) out.push(cell('move', gi, p, opt.gap - a, a, g.captures?.[p - 1] ? 'capture' : 'move'));
    if (g.over) out.push(cell('result', gi, g.plies, opt.resulthold, 0, 'end'));
  });
  out.push(cell('end', null, null, games.length > 1 ? opt.summaryhold : 0));
  return out;
}
