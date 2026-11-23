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
    homeBrand: 'agi-chess · 棋谱阅读器',
    home: '首页',
    backHome: '返回首页',
    errTitle: '无法加载棋谱',
    errHint: '请检查网址中的 ?files= 棋谱路径，或直接打开下方精选对局。',
    fetchErr: (p, st) => `读不到棋谱 ${p}：${st}`,
    samplesTitle: '直接打开仓内代表局（自动加载恶手复盘）',
    samples: [
      ['国际象棋 · GPT-6.2 Astra vs Gemini 4 Neon', '/runs/neon-xhigh-vs-astra-max-20261119-4'],
      ['国际象棋 · Gemini 4 Neon vs Gemini 4 Carbon', '/runs/neon-xhigh-vs-carbon-high-20261119'],
      ['中国象棋 · Claude Opus 5.5 (agy) vs Gemini 4 Carbon', '/runs/carbon-vs-agy-opus-high-xq-20261114-3'],
      ['国际象棋 · Claude Opus vs GPT Astra (max)', '/runs/g7-c-opus-astra-1'],
      ['中国象棋 · Claude Opus vs GPT Astra (max)', '/runs/g7-x-opus-astra-1'],
      ['国际象棋标定 · Claude Opus vs Maia 1900', '/runs/zc/maia-1900-s1-w'],
    ],
    // 着法标注与评注数字（lib/panel.js）
    nag: { 1: '好棋', 2: '错着', 3: '妙着', 4: '大错', 5: '有意思', 6: '可疑' },
    hms: ['时', '分', '秒'],
    cmd: {
      emt: '用时', think: '思考 token', out: '输出 token', in: '输入 token', cacheread: '缓存读', cachewrite: '缓存写',
      illegal: '非法重选', flagged: '被拦截', empty: '空回复', dropped: '去掉的思考段',
    },
    evalWhite: '白方评分',
    evalRed: '红方评分',
    evalWp: '白方胜率',
    evalBest: '最佳着',
    navFeatured: '精选首页',
    navSeries: '对阵总览',
    navCatalog: (n) => `全部对局 (${n})`,
    navSeriesShort: '对阵榜',
    navCatalogShort: '目录',
    backSeries: '← 对阵榜',
    backCatalog: '← 目录',
    pages: {
      brand: 'agi-chess',
      seriesTitle: '无引擎对阵总览 · agi-chess',
      seriesHeading: '无引擎模型对阵总览',
      seriesSub: '通用大模型零引擎、零合法着法提示整盘对弈记录。不同时期、提示语言与思考预算分开呈列，不合并拟合跨代等级分。',
      catalogTitle: '全部对局目录 (192) · agi-chess',
      catalogHeading: '全部正式对局目录',
      catalogSub: '收录仓内全部 192 盘正式对局（64 盘模型互弈 + 128 盘对阵固定强度引擎或随机走子），点击任意对局直接进入逐步复盘。',
      rrBadge: '2026-11-19 · 英文协议对称循环赛（12 局）',
      rrTitle: '国际象棋三强同赛程四盘循环赛速览',
      rrNote: '每组 4 局先后手对称、标准开局、独立连续会话（全部规则将死完赛，0 工具尝试，0 安全拒答）。小样本只看方向。',
      rrColModel: '模型与档位',
      rrColScore: '总分（8 局）',
      rrColSplit: '执白 / 执黑得分',
      rrColPairings: '分项交手比分',
      mainSectionChess: '标准对称番棋交手（国际象棋）',
      mainSectionXq: '标准对称番棋交手（中国象棋）',
      promptLang: (l) => (l === 'en' ? '英文提示' : '中文提示'),
      gamesCount: (n) => `${n} 局`,
      playSeries: '连播整组',
      reportLink: '研究报告 ↗',
      asFirst: (w) => `${w}得分`,
      asSecond: '执黑得分',
      firstWordChess: '执白',
      firstWordXq: '执红',
      acplLbl: '加权 ACPL',
      blundersLbl: '恶手数',
      keyBlundersLbl: '关键恶手直达',
      gameBtn: (i) => `G${i}`,
      resWin: '胜',
      resLoss: '负',
      resDraw: '和',
      anchorHeading: '独立引擎棋力标定锚点（CLI Opus 5.5 Max）',
      anchorBadge: '固定强度引擎阶梯标定',
      anchorNote: '仅针对 2026-10 CLI claude-opus-5-5 (max) 实测标定；不同渠道、思考档位与后续模型的比分不可直接传递换算人类等级分。',
      browseBatch: (n) => `浏览全部 ${n} 局标定谱 ›`,
      expSummary: (n) => `研究对照、首跑探路与自弈局（共 ${n} 盘，默认折叠，不计入对称主榜）`,
      expSub: '包含单方去掉历史思考（drop_thinking）对照、首轮无理由协议验证、单局探路及同模型自弈记录，完整覆盖其余无引擎对局。',
      filterVariantAll: (n) => `全部棋种 (${n})`,
      filterChess: (n) => `国际象棋 (${n})`,
      filterXq: (n) => `中国象棋 (${n})`,
      filterCatAll: (n) => `全部类别 (${n})`,
      filterCatH2h: (n) => `模型互弈 (${n})`,
      filterCatEngine: (n) => `对引擎/随机 (${n})`,
      modelFilterLbl: '模型快筛',
      searchPlaceholder: '搜索棋手、引擎或目录',
      searchAria: '搜索棋手、模型、引擎档位（如 maia-1900 / nodes=100）或目录名',
      sortAria: '排序方式',
      sortNewest: '日期：新 → 旧',
      sortOldest: '日期：旧 → 新',
      sortLongest: '步数：多 → 少',
      sortShortest: '步数：少 → 多',
      batchFilterTag: (b) => `批次筛选：${b}`,
      clearFilters: '清除筛选',
      showingCount: (shown, total) => `显示 ${shown} / ${total} 盘`,
      emptyCatalog: '没有匹配当前筛选条件的对局。',
      resetCatalogBtn: '重置全部筛选条件',
      catBadgeH2h: '模型互弈',
      catBadgeSelf: '模型自弈',
      catBadgeAnchor: '等级分标定',
      catBadgeEngine: '对阵引擎',
      catBadgeRandom: '对随机走子',
      pliesCount: (n) => `${n} 半回合`,
      unanalyzed: '无引擎分析',
      blundersShort: (n) => `恶手 ${n}`,
      acplShort: (v) => `ACPL ${v}`,
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
    homeBrand: 'agi-chess · Game Viewer',
    home: 'Home',
    backHome: 'Back to Home',
    errTitle: 'Failed to load game record',
    errHint: 'Check the ?files= path in the URL, or open a featured game below.',
    fetchErr: (p, st) => `Failed to load ${p}: ${st}`,
    samplesTitle: 'Open a featured game from runs/ (with blunder annotations)',
    samples: [
      ['Chess · GPT-6.2 Astra vs Gemini 4 Neon', '/runs/neon-xhigh-vs-astra-max-20261119-4'],
      ['Chess · Gemini 4 Neon vs Gemini 4 Carbon', '/runs/neon-xhigh-vs-carbon-high-20261119'],
      ['Xiangqi · Claude Opus 5.5 (agy) vs Gemini 4 Carbon', '/runs/carbon-vs-agy-opus-high-xq-20261114-3'],
      ['Chess · Claude Opus vs GPT Astra (max)', '/runs/g7-c-opus-astra-1'],
      ['Xiangqi · Claude Opus vs GPT Astra (max)', '/runs/g7-x-opus-astra-1'],
      ['Chess Anchor · Claude Opus vs Maia 1900', '/runs/zc/maia-1900-s1-w'],
    ],
    nag: { 1: 'Good move', 2: 'Mistake', 3: 'Brilliant move', 4: 'Blunder', 5: 'Interesting move', 6: 'Dubious move' },
    hms: ['h', 'm', 's'],
    cmd: {
      emt: 'Time', think: 'Thinking tokens', out: 'Output tokens', in: 'Input tokens', cacheread: 'Cache read', cachewrite: 'Cache write',
      illegal: 'Illegal retries', flagged: 'Blocked', empty: 'Empty replies', dropped: 'Thinking dropped',
    },
    evalWhite: 'White eval',
    evalRed: 'Red eval',
    evalWp: 'White win%',
    evalBest: 'Best',
    navFeatured: 'Featured',
    navSeries: 'Series Board',
    navCatalog: (n) => `All Games (${n})`,
    navSeriesShort: 'Series',
    navCatalogShort: 'Catalog',
    backSeries: '← Series Board',
    backCatalog: '← Catalog',
    pages: {
      brand: 'agi-chess',
      seriesTitle: 'No-Engine Series Board · agi-chess',
      seriesHeading: 'No-Engine Model Series Board',
      seriesSub: 'Full Chess and Xiangqi matches played by untuned frontier LLMs with zero engines or legal-move hints. Listed by date, prompt language, and effort without cross-era Elo pooling.',
      catalogTitle: 'Game Catalog (192) · agi-chess',
      catalogHeading: 'Official Game Catalog',
      catalogSub: 'Browse all 192 official checked-in games (64 model-vs-model + 128 vs fixed-strength engines or random movers) and jump straight into move-by-move replay.',
      rrBadge: '2026-11-19 · English-Prompt Symmetric Round-Robin (12 Games)',
      rrTitle: 'Chess Three-Model Symmetric Round-Robin Snapshot',
      rrNote: 'Three color-balanced 4-game matches from the standard start in continuous sessions (all decisive checkmates, 0 tool attempts, 0 safety refusals). Small-sample directional evidence only.',
      rrColModel: 'Model & Effort',
      rrColScore: 'Total (8 Games)',
      rrColSplit: 'As White / As Black',
      rrColPairings: 'Head-to-Head Splits',
      mainSectionChess: 'Symmetric Head-to-Head Series (Chess)',
      mainSectionXq: 'Symmetric Head-to-Head Series (Xiangqi)',
      promptLang: (l) => (l === 'en' ? 'EN prompt' : 'ZH prompt'),
      gamesCount: (n) => (n === 1 ? '1 game' : `${n} games`),
      playSeries: 'Play Series',
      reportLink: 'Report ↗',
      asFirst: (w) => `As ${w}`,
      asSecond: 'As Black',
      firstWordChess: 'White',
      firstWordXq: 'Red',
      acplLbl: 'Weighted ACPL',
      blundersLbl: 'Blunders',
      keyBlundersLbl: 'Key Blunders',
      gameBtn: (i) => `G${i}`,
      resWin: 'W',
      resLoss: 'L',
      resDraw: 'D',
      anchorHeading: 'Independent Engine Rating Anchor (CLI Opus 5.5 Max)',
      anchorBadge: 'Fixed-Strength Engine Ladder',
      anchorNote: 'Calibrated specifically for 2026-10 CLI claude-opus-5-5 (max); head-to-head scores across other channels, effort levels, or later models do not transfer linearly to human ratings.',
      browseBatch: (n) => `Browse all ${n} calibration games ›`,
      expSummary: (n) => `Control Conditions, Pilot Runs & Self-Play (${n} games, collapsed outside symmetric main board)`,
      expSub: 'Includes one-sided drop_thinking controls, initial no-rationale protocol runs, single-game pilots, and self-play diagnostics covering all remaining no-engine games.',
      filterVariantAll: (n) => `All Variants (${n})`,
      filterChess: (n) => `Chess (${n})`,
      filterXq: (n) => `Xiangqi (${n})`,
      filterCatAll: (n) => `All Categories (${n})`,
      filterCatH2h: (n) => `Model vs Model (${n})`,
      filterCatEngine: (n) => `vs Engine/Random (${n})`,
      modelFilterLbl: 'Quick Model',
      searchPlaceholder: 'Search players, engines or paths',
      searchAria: 'Search players, models, engine levels (maia-1900 / nodes=100), or run paths',
      sortAria: 'Sort games',
      sortNewest: 'Date: Newest first',
      sortOldest: 'Date: Oldest first',
      sortLongest: 'Length: Most plies',
      sortShortest: 'Length: Fewest plies',
      batchFilterTag: (b) => `Batch: ${b}`,
      clearFilters: 'Clear filters',
      showingCount: (shown, total) => `Showing ${shown} of ${total} games`,
      emptyCatalog: 'No games match the current filters.',
      resetCatalogBtn: 'Reset all filters',
      catBadgeH2h: 'Model vs Model',
      catBadgeSelf: 'Self-Play',
      catBadgeAnchor: 'Rating Anchor',
      catBadgeEngine: 'vs Engine',
      catBadgeRandom: 'vs Random',
      pliesCount: (n) => (n === 1 ? '1 ply' : `${n} plies`),
      unanalyzed: 'Unanalyzed',
      blundersShort: (n) => (n === 1 ? '1 blunder' : `${n} blunders`),
      acplShort: (v) => `ACPL ${v}`,
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
  [/^同一局面出现三次，判和$/, 'Threefold repetition'],
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
