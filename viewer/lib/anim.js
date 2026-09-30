// 走子滑动动画（docs/viewer.md「棋盘」）：两种棋盘共用的几个 Web Animations 小工具。
// 用 Web Animations 而不用 requestAnimationFrame，是为了能按进度定格：录制脚本对 document.getAnimations()
// 逐格设 currentTime 截图（docs/viewer.md「录屏：脚本出片」的动画约定）。
// 动画都是 fill: 'none'：走完（或被 finish()）后元素回到自己本来的样子——棋盘本身早已画成走完的局面，
// 所以结束时什么也不用补，被吃的子、临时叠上去的棋子也在结束时自动消失（它们本来的样子是透明）。

const EASING = 'ease-in-out';

export class Moves {
  constructor() {
    this.list = [];
  }

  // 结束上一段：新一步开始、换局面时调，直接跳到终点（不丢步、不错位）。
  stop() {
    for (const a of this.list) a.finish();
    this.list = [];
  }

  add(a, paused) {
    if (paused) a.pause();   // 录制模式：停在起点，由脚本拨进度
    this.list.push(a);
    return a;
  }

  // SVG 元素从 from 滑到 to（{x, y}，元素所在坐标系的用户单位）：动画期间 CSS transform 盖过元素的 transform 属性，
  // 结束后回到属性里写的位置。
  slide(el, from, to, ms, paused) {
    return this.add(el.animate([
      { transform: `translate(${from.x}px, ${from.y}px)` },
      { transform: `translate(${to.x}px, ${to.y}px)` },
    ], { duration: ms, easing: EASING, fill: 'none' }), paused);
  }

  // 只在动画期间看得见（被吃的子、临时叠上去的棋子）：本来透明，动画期间不透明，结束即消失。
  during(el, ms, paused) {
    el.style.opacity = '0';
    const a = this.add(el.animate([{ opacity: 1 }, { opacity: 1 }], { duration: ms, fill: 'none' }), paused);
    a.finished.then(() => el.remove(), () => {});
    return a;
  }

  // 只在动画期间看不见（国际象棋：棋盘上已画好的落点棋子，动画期间让位给滑动的那枚）。
  hide(el, ms, paused) {
    return this.add(el.animate([{ opacity: 0 }, { opacity: 0 }], { duration: ms, fill: 'none' }), paused);
  }
}
