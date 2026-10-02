// 走子音效（docs/viewer.md「走子音效」）：哪一格响哪一声、每声多大，页面播放和录制混音共用这一份。
// 纯数据 + 纯函数，不碰 DOM、不碰音频接口。

// 三种声音（素材与许可见 vendor/sounds/SOURCE.md）。gain 是加在原文件上的增益（dB），照 chess.com 的量级定：
// 落子峰值约 −10 dBFS、单声响度约 −31 LUFS；吃子比落子高 2.5 dB；终局比吃子再高 4 dB。
// 「单声响度」是补静音到 1.5 秒后量的 EBU R128 integrated（短于 400 ms 的音直接量测不出），量法见 SOURCE.md。
//   落子 move：原始 −12.2 dBFS / −32.7 LUFS，+1.7 → 约 −10.5 dBFS / −31.0 LUFS
//   吃子 capture：原始 −2.3 / −20.6，−7.9 → 约 −10.2 / −28.5
//   终局 end：原始 −6.6 / −25.2，+0.7 → 约 −5.9 / −24.5
export const SOUNDS = {
  move: { file: 'vendor/sounds/move.mp3', gain: 1.7 },
  capture: { file: 'vendor/sounds/capture.mp3', gain: -7.9 },
  end: { file: 'vendor/sounds/end.mp3', gain: 0.7 },
};

// 一步棋该响哪声：吃子用吃子声，否则落子声；将军不另配声（用户 2026-10-02 定）。step 是 replay() 的一步。
export const stepSound = (step) => (step?.capture ? 'capture' : 'move');

// 每声实际的线性倍数：表里的增益再乘整体音量 vol（1 = 默认）。
export const linear = (sound, vol = 1) => 10 ** (SOUNDS[sound].gain / 20) * vol;

// 网址参数 → 页面的声音设置。看棋谱默认静音，sound=1 打开；vol 是整体音量倍数（默认 1，0.5 约 −6 dB），
// 不合法（非数字、不大于 0）时用 1。录制脚本不看这两个参数，它自己混音（--no-sound / --vol）。
export function soundOptions(params) {
  const v = params.get('vol');
  const x = v === null || v.trim() === '' ? NaN : Number(v);
  return { on: params.get('sound') === '1', vol: Number.isFinite(x) && x > 0 ? x : 1 };
}
