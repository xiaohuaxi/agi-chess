// 界面语言（docs/viewer.md「英文界面」）：网址参数 lang=en 出英文界面，不给或别的值是中文（默认，与加这张表之前逐字节一致）。
// 界面上所有写死的文字都收在这张对照表里，两种语言平行各一份，加一处就两边都加（test/i18n.test.js 核对键一一对应、英文里没有中文）。
// 棋谱内容不翻：模型写的理由、别人棋谱里的文字照原样显示；象棋棋盘上的汉字棋子保留。
// 纯函数，不碰 DOM；浏览器与 node 都能 import。

export const LANGS = ['zh', 'en'];

// 网址参数 → 语言；认不出的值退回中文（和其余参数一样，不合法时用默认）。
export function langOf(params) {
  const v = (params.get('lang') || '').trim().toLowerCase();
  return LANGS.includes(v) ? v : 'zh';
}

export const TEXT = {
  zh: {
    htmlLang: 'zh-CN',
    pageTitle: '棋谱阅读器',
    // 窄版（录屏画面）
    gameOf: (i, n) => `第 ${i} 局 · 共 ${n} 局`,          // 顶部细条、标题画面第一行
    won: '胜',                                          // 胜方名字旁的小标签
    check: '将军',
    thinking: '思考',                                    // 「思考 52k +3.4k」
    vs: '对',                                           // 标题画面两名棋手之间；宽版换盘下拉框
    chess: '国际象棋', xiangqi: '中国象棋',
    finalScore: (n) => `总比分 · 共 ${n} 局`,
    redWins: '红方胜', whiteWins: '白方胜', blackWins: '黑方胜', draw: '和棋',
    unreadable: (ply, text) => `第 ${ply} 步读不懂：${text}`,
    // 宽版右栏
    switchGame: '换盘（PgUp / PgDn）',
    gameItem: (i, w, b, r) => `第 ${i} 局 · ${w} 对 ${b} · ${r}`,
    effort: '思考深度',
    result: '结果：',
    unfinished: '未完',
    start: '开局',
    startPos: '开局局面',
    comment: '评注',
    reason: '理由 / 评注',
    otherCmds: '其他命令',
    noNote: '这步没有评注',
    finalLbl: '终局',
    play: '播放', pause: '暂停',
    btn: { first: '本盘开头（Home）', prev: '上一步（←）', play: '播放 / 暂停（空格）', next: '下一步（→）', last: '本盘结尾（End）' },
    keys: [[['←', '→'], '单步'], [['空格'], '播放 / 暂停'], [['Home', 'End'], '本盘首尾'], [['PgUp', 'PgDn'], '换盘'], [[], '点着法跳到那步']],
    hint: '把棋谱文件（.pgn）拖进来\n或在网址后加 ?files=/runs/xxx/game.pgn',
    samplesTitle: '直接打开仓内代表局（自动加载恶手复盘）',
    samples: [
      ['国际象棋巅峰局 · Opus Max vs Astra Max', '/runs/g7-c-opus-astra-1'],
      ['中国象棋巅峰局 · Opus Max vs Astra Max', '/runs/g7-x-opus-astra-1'],
      ['国际象棋 · Argon High vs Opus High', '/runs/argon-vs-agy-opus-high-20261019'],
      ['国际象棋等级分锚定局 · Opus Max vs Maia-1900', '/runs/zc/maia-1900-s1-w'],
    ],
    // 着法标注与评注数字（lib/panel.js）
    nag: { 1: '好棋', 2: '错着', 3: '妙着', 4: '大错', 5: '有意思', 6: '可疑' },
    hms: ['时', '分', '秒'],
    cmd: {
      emt: '用时', think: '思考 token', out: '输出 token', in: '输入 token', cacheread: '缓存读', cachewrite: '缓存写',
      illegal: '非法重选', flagged: '被拦截', empty: '空回复', dropped: '去掉的思考段',
    },
  },
  en: {
    htmlLang: 'en',
    pageTitle: 'Game Viewer',
    gameOf: (i, n) => `Game ${i} of ${n}`,
    won: 'Won',
    check: 'Check',
    thinking: 'Thinking',
    vs: 'vs',
    chess: 'Chess', xiangqi: 'Xiangqi',
    finalScore: (n) => `Final score · ${n} games`,
    redWins: 'Red wins', whiteWins: 'White wins', blackWins: 'Black wins', draw: 'Draw',
    unreadable: (ply, text) => `Can't read move ${ply}: ${text}`,
    switchGame: 'Switch game (PgUp / PgDn)',
    gameItem: (i, w, b, r) => `Game ${i} · ${w} vs ${b} · ${r}`,
    effort: 'Effort',
    result: 'Result: ',
    unfinished: 'Unfinished',
    start: 'Start',
    startPos: 'Starting position',
    comment: 'Comment',
    reason: 'Reasoning / comment',
    otherCmds: 'Other commands',
    noNote: 'No comment on this move',
    finalLbl: 'Result',
    play: 'Play', pause: 'Pause',
    btn: { first: 'Start of game (Home)', prev: 'Previous move (←)', play: 'Play / pause (Space)', next: 'Next move (→)', last: 'End of game (End)' },
    keys: [[['←', '→'], 'Step'], [['Space'], 'Play / pause'], [['Home', 'End'], 'First / last move'], [['PgUp', 'PgDn'], 'Switch game'], [[], 'Click a move to jump to it']],
    hint: 'Drop PGN files here\nor add ?files=/runs/xxx/game.pgn to the URL',
    samplesTitle: 'Or open a featured game from runs/ (with blunder annotations)',
    samples: [
      ['Chess Peak Match · Opus Max vs Astra Max', '/runs/g7-c-opus-astra-1'],
      ['Xiangqi Peak Match · Opus Max vs Astra Max', '/runs/g7-x-opus-astra-1'],
      ['Chess Match · Argon High vs Opus High', '/runs/argon-vs-agy-opus-high-20261019'],
      ['Chess Rating Match · Opus Max vs Maia-1900', '/runs/zc/maia-1900-s1-w'],
    ],
    nag: { 1: 'Good move', 2: 'Mistake', 3: 'Brilliant move', 4: 'Blunder', 5: 'Interesting move', 6: 'Dubious move' },
    hms: ['h', 'm', 's'],
    cmd: {
      emt: 'Time', think: 'Thinking tokens', out: 'Output tokens', in: 'Input tokens', cacheread: 'Cache read', cachewrite: 'Cache write',
      illegal: 'Illegal retries', flagged: 'Blocked', empty: 'Empty replies', dropped: 'Thinking dropped',
    },
  },
};

export const T = (lang) => TEXT[lang] || TEXT.zh;

// 结束原因（PGN 的 Termination）。导出端写的是中文（agi_chess/chess_.py 的 TERMINATION 与 outcome、xiangqi.py 的终局判定、
// runner.py 的半回合上限与连续非法判负、analyze.py 的上限评分裁决），英文界面按这张表换；新增结束原因时这里同步加一条。
// 表里没有的：不含中文的（别人的英文棋谱）照原样，含中文的不显示（横幅只留「Red wins」这类结果），免得英文画面上冒出中文。
const SIDE_EN = { 红方: 'Red', 白方: 'White', 黑方: 'Black' };
const REASONS_EN = [
  [/^将死$/, 'Checkmate'],
  [/^困毙$/, 'Stalemate'],                                  // 象棋无着可走判负
  [/^逼和，判和$/, 'Stalemate'],
  [/^双方子力都不足以将死，判和$/, 'Insufficient material'],
  [/^七十五回合没有吃子和兵的走动，判和$/, '75-move rule'],
  [/^同一局面出现五次，判和$/, 'Fivefold repetition'],
  [/^同一局面出现三次，程序替棋手申诉，判和$/, 'Threefold repetition'],
  [/^五十回合没有吃子和兵的走动，程序替棋手申诉，判和$/, '50-move rule'],
  [/^一百个半回合没有吃子，判和$/, 'No capture in 100 plies'],
  [/^长将，判负$/, 'Perpetual check'],
  [/^长捉，判负$/, 'Perpetual chase'],
  [/^满 (\d+) 个半回合（研究设的上限），判和$/, (n) => `Move limit (${n} plies)`],
  [/^满 (\d+) 个半回合（研究设的上限），到上限按引擎评分判：(红方|白方|黑方)已有杀棋（(\d+) 步杀），判\2胜$/,
    (n, side, mate) => `Engine adjudication at ${n} plies: ${SIDE_EN[side]} wins (mate in ${mate})`],
  [/^满 (\d+) 个半回合（研究设的上限），到上限按引擎评分判：(红方|白方|黑方)领先 (\d+) 厘兵（≥(\d+)），判\2胜$/,
    (n, side, cp, margin) => `Engine adjudication at ${n} plies: ${SIDE_EN[side]} wins (+${cp} cp ≥ ${margin})`],
  [/^满 (\d+) 个半回合（研究设的上限），到上限按引擎评分判：(红方|白方) ([+-]\d+) 厘兵，差距不到 (\d+)，判和$/,
    (n, side, cp, margin) => `Engine adjudication at ${n} plies: draw (${SIDE_EN[side]} ${cp} cp; gap < ${margin})`],
  [/^(?:红方|白方|黑方)连续 (\d+) 次给出非法着法，判负$/, (n) => `${n} illegal moves in a row`],
];

const CJK = /[　-〿㐀-鿿＀-￯]/;

export function reasonEn(raw) {
  const s = (raw || '').trim();
  for (const [re, out] of REASONS_EN) {
    const m = s.match(re);
    if (m) return typeof out === 'function' ? out(...m.slice(1)) : out;
  }
  return CJK.test(s) ? '' : s;
}

export const hasCjk = (s) => CJK.test(s);

// 显示名覆盖（网址参数 names=）：逗号分隔的「棋谱里的名字=显示名」，如
//   names=claude:opus=Claude Opus,codex:astra=GPT astra
// 左边先按 PGN 标签原样（White / Black / Red 的值）比，比不上再按去掉后端前缀的简称（opus）比，都不分大小写。
// 显示名照写（不改大小写、不补厂商）；思考深度仍取 PGN 标签、照常接在后面。写错的段（没有「=」、某边为空）跳过。
export function parseNames(s) {
  const m = new Map();
  for (const part of (s || '').split(',')) {
    const i = part.indexOf('=');
    if (i <= 0) continue;
    const k = part.slice(0, i).trim().toLowerCase(), v = part.slice(i + 1).trim();
    if (k && v) m.set(k, v);
  }
  return m;
}
