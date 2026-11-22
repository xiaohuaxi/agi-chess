// 全量对局目录与无引擎番棋聚合构建脚本（零外部依赖）。
// 用法：
//   node viewer/build-catalog.mjs          # 重新生成 viewer/lib/catalog-data.json
//   node viewer/build-catalog.mjs --check  # 校验内存重算结果与入库文件逐字节一致（CI / 单测零漂移门禁）
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { hasCjk } from './lib/i18n.js';
import { fullName, playerOf, points } from './lib/match.js';
import { decodeText, parsePgn } from './lib/pgn.js';
import { isXiangqi } from './lib/replay.js';

const VIEWER = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(VIEWER, '..');
const META_PATH = path.join(VIEWER, 'catalog-meta.json');
const OUT_PATH = path.join(VIEWER, 'lib', 'catalog-data.json');

const MODEL_FAMILIES = [
  ['neon', /neon/i],
  ['carbon', /carbon/i],
  ['astra', /astra/i],
  ['opus', /opus/i],
  ['argon', /argon/i],
  ['sol', /(^|:)sol$/i],
  ['flash', /flash/i],
];

function isNonModelPlayer(raw) {
  const s = String(raw || '').trim().toLowerCase();
  return s.startsWith('engine:') || s === 'random';
}

function detectModelTags(wRaw, bRaw) {
  const tags = [];
  for (const [tag, re] of MODEL_FAMILIES) {
    if ((!isNonModelPlayer(wRaw) && re.test(wRaw)) || (!isNonModelPlayer(bRaw) && re.test(bRaw))) {
      tags.push(tag);
    }
  }
  return tags;
}

function assertNoCjkInEn(obj, where = 'meta') {
  if (typeof obj === 'string') return;
  if (Array.isArray(obj)) {
    obj.forEach((v, i) => assertNoCjkInEn(v, `${where}[${i}]`));
    return;
  }
  if (obj && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj)) {
      if (/En$/.test(k) && typeof v === 'string' && hasCjk(v)) {
        throw new Error(`英文元数据字段含 CJK 或全角字符 (${where}.${k}): ${v}`);
      }
      assertNoCjkInEn(v, `${where}.${k}`);
    }
  }
}

export function buildCatalogObject() {
  const meta = JSON.parse(readFileSync(META_PATH, 'utf8'));
  assertNoCjkInEn(meta);

  // 严格仅扫描 Git 已跟踪的 runs/ 文件，杜绝混入本机未跟踪的 zcal-* 等本地标定目录
  const tracked = execFileSync('git', ['ls-files', '-z', 'runs/'], { cwd: ROOT, maxBuffer: 16 * 1024 * 1024 })
    .toString('utf8')
    .split('\0')
    .filter(Boolean)
    .sort();
  const trackedSet = new Set(tracked);

  const pgnFiles = tracked.filter((f) => /^runs\/(?!quiz-).+\/game\.pgn$/.test(f));
  const rules = [...meta.batchRules].sort((a, b) => b.prefix.length - a.prefix.length);

  const games = [];
  const gameByDir = new Map();

  for (const relPgn of pgnFiles) {
    const dir = relPgn.replace(/\/game\.pgn$/, '');
    const rule = rules.find((r) => dir === r.prefix || dir.startsWith(r.prefix));
    if (!rule) throw new Error(`未在 catalog-meta.json batchRules 中配置目录规则：${dir}`);

    const parsed = parsePgn(decodeText(readFileSync(path.join(ROOT, relPgn))));
    if (parsed.length !== 1) throw new Error(`${relPgn} 预期单盘 PGN，实得 ${parsed.length} 盘`);
    const g = parsed[0];
    const xq = isXiangqi(g);
    const variant = xq ? 'xiangqi' : 'chess';

    const wRaw = g.tags.Red ?? g.tags.White ?? '?';
    const bRaw = g.tags.Black ?? '?';
    const wFull = fullName(g, 'w', true);
    const bFull = fullName(g, 'b', true);
    const wShort = playerOf(g, 'w');
    const bShort = playerOf(g, 'b');

    const hasRandom = wRaw.toLowerCase() === 'random' || bRaw.toLowerCase() === 'random';
    const hasEngine = wRaw.toLowerCase().startsWith('engine:') || bRaw.toLowerCase().startsWith('engine:');
    const cat = hasEngine || hasRandom ? 'engine' : 'h2h';
    const subcat = hasRandom ? 'random' : rule.subcat;

    const sumRel = `${dir}/analysis-summary.json`;
    const sum = trackedSet.has(sumRel) ? JSON.parse(readFileSync(path.join(ROOT, sumRel), 'utf8')) : null;
    const anaRel = `${dir}/analysis.jsonl`;
    const hasAnalysis = Boolean(sum && trackedSet.has(anaRel));

    const sideStats = (s) => {
      if (!sum) return { plies: null, acpl: null, blunders: null };
      const sd = sum.sides?.[s];
      if (!sd) throw new Error(`${sumRel} 缺少 sides.${s}`);
      const bl = xq ? sd.blunders : sd.lichess?.Blunder;
      if (typeof bl !== 'number') throw new Error(`${sumRel} 缺少合法恶手数字段 (${s})`);
      return { plies: sd.plies, acpl: sd.acpl, blunders: bl };
    };

    const wSt = sideStats('w');
    const bSt = sideStats('b');
    const result = g.result ?? g.tags.Result ?? '*';
    if (!points(result)) throw new Error(`${relPgn} 结果未完或非法：${result}`);

    const entry = {
      dir,
      variant,
      date: rule.date,
      batch: rule.batch,
      cat,
      subcat,
      protocol: rule.protocol,
      lang: rule.lang,
      sessionMode: rule.sessionMode,
      result,
      termination: g.tags.Termination || '',
      plies: g.moves.length,
      openingPlies: sum ? (sum.opening_plies ?? 0) : 0,
      analyzed: hasAnalysis,
      modelTags: detectModelTags(wRaw, bRaw),
      report: rule.report,
      w: {
        raw: wRaw,
        name: wFull.name,
        short: wShort.name,
        effort: wShort.effort,
        plies: wSt.plies,
        acpl: wSt.acpl,
        blunders: wSt.blunders,
      },
      b: {
        raw: bRaw,
        name: bFull.name,
        short: bShort.name,
        effort: bShort.effort,
        plies: bSt.plies,
        acpl: bSt.acpl,
        blunders: bSt.blunders,
      },
    };
    games.push(entry);
    gameByDir.set(dir, entry);
  }

  // 校验并聚合番棋（标准对称主榜 series 与探索/对照局 exploratory 共用同一聚合器）
  const coveredH2h = new Set();

  function aggregateMatchGroup(def, isExploratory = false) {
    const selfPlay = Boolean(def.selfPlay);
    let scoreA = 0, scoreB = 0;
    const aFirst = { w: 0, d: 0, l: 0, pts: 0, total: 0 };
    const aSecond = { w: 0, d: 0, l: 0, pts: 0, total: 0 };
    let pliesA = 0, acplWeightedA = 0, blundersA = 0, hasAllStats = true;
    let pliesB = 0, acplWeightedB = 0, blundersB = 0;
    const memberGames = [];

    def.files.forEach((dir, idx) => {
      const gm = gameByDir.get(dir);
      if (!gm) throw new Error(`番棋 ${def.id} 引用了不存在的对局目录：${dir}`);
      if (gm.cat !== 'h2h') throw new Error(`番棋 ${def.id} 引用了非模型互弈目录：${dir}`);
      if (gm.variant !== def.variant) throw new Error(`番棋 ${def.id} 棋种不匹配：${dir}`);
      if (coveredH2h.has(dir)) throw new Error(`无引擎对局被重复归入多个分组：${dir}`);
      coveredH2h.add(dir);

      let aSide;
      if (selfPlay) {
        if (gm.w.raw !== def.sideA.raw || gm.b.raw !== def.sideB.raw) {
          throw new Error(`自弈组 ${def.id} 棋手标签不匹配：${dir}`);
        }
        aSide = 'w';
      } else {
        const matchW = gm.w.raw === def.sideA.raw && gm.w.effort === def.sideA.effort
          && gm.b.raw === def.sideB.raw && gm.b.effort === def.sideB.effort;
        const matchB = gm.b.raw === def.sideA.raw && gm.b.effort === def.sideA.effort
          && gm.w.raw === def.sideB.raw && gm.w.effort === def.sideB.effort;
        if (matchW === matchB) {
          throw new Error(`番棋 ${def.id} 无法唯一匹配双方身份 (${gm.w.raw}+${gm.w.effort} vs ${gm.b.raw}+${gm.b.effort})：${dir}`);
        }
        aSide = matchW ? 'w' : 'b';
      }
      const bSide = aSide === 'w' ? 'b' : 'w';
      const pts = points(gm.result);
      const aPts = pts[aSide], bPts = pts[bSide];
      scoreA += aPts;
      scoreB += bPts;
      const bucket = aSide === 'w' ? aFirst : aSecond;
      bucket.total += 1;
      bucket.pts += aPts;
      if (aPts === 1) bucket.w += 1;
      else if (aPts === 0.5) bucket.d += 1;
      else bucket.l += 1;

      const sA = gm[aSide], sB = gm[bSide];
      if (!gm.analyzed || sA.acpl === null || sB.acpl === null) {
        hasAllStats = false;
      } else {
        pliesA += sA.plies;
        acplWeightedA += sA.acpl * sA.plies;
        blundersA += sA.blunders;
        pliesB += sB.plies;
        acplWeightedB += sB.acpl * sB.plies;
        blundersB += sB.blunders;
      }

      memberGames.push({
        no: idx + 1,
        dir,
        aSide,
        result: gm.result,
        aScore: aPts,
        plies: gm.plies,
        aAcpl: sA.acpl,
        bAcpl: sB.acpl,
        aBlunders: sA.blunders,
        bBlunders: sB.blunders,
      });
    });

    // 校验精选恶手步真实性（确保文件在组内、半回合存在且确系该棋种口径下的恶手）
    const keyBlunders = (def.keyBlunders || []).map((kb) => {
      const gIdx = def.files.indexOf(kb.file);
      if (gIdx < 0) throw new Error(`番棋 ${def.id} 的 keyBlunder 文件不在组内：${kb.file}`);
      const gm = gameByDir.get(kb.file);
      if (!Number.isInteger(kb.ply) || kb.ply < 1 || kb.ply > gm.plies) {
        throw new Error(`番棋 ${def.id} 的 keyBlunder ply 超界：${kb.file} ply=${kb.ply}`);
      }
      const anaLines = readFileSync(path.join(ROOT, kb.file, 'analysis.jsonl'), 'utf8').trim().split(/\r?\n/);
      const row = JSON.parse(anaLines[kb.ply - 1]);
      const isBl = gm.variant === 'chess' ? row.lichess === 'Blunder' : row.cls === 'blunder';
      if (!isBl) {
        throw new Error(`番棋 ${def.id} 的 keyBlunder 在引擎分析中不是恶手：${kb.file} ply=${kb.ply}`);
      }
      return {
        file: kb.file,
        gameNo: gIdx + 1,
        ply: kb.ply,
        labelZh: kb.labelZh,
        labelEn: kb.labelEn,
      };
    });

    const sampleSide = (spec, fallbackSide) => {
      const g0 = memberGames[0];
      const sideObj = gameByDir.get(g0.dir)[g0.aSide === 'w' ? fallbackSide : (fallbackSide === 'w' ? 'b' : 'w')];
      return {
        raw: spec.raw,
        techName: sideObj.name,
        effort: spec.effort,
        labelZh: spec.labelZh,
        labelEn: spec.labelEn,
        ...(spec.shortLabel ? { shortLabel: spec.shortLabel } : {}),
      };
    };

    const base = {
      id: def.id,
      variant: def.variant,
      date: def.date,
      lang: def.lang,
      selfPlay,
      sideA: sampleSide(def.sideA, 'w'),
      sideB: sampleSide(def.sideB, 'b'),
      files: def.files,
      gamesCount: def.files.length,
      scoreA,
      scoreB,
      aFirst,
      aSecond,
      acplA: hasAllStats && pliesA > 0 ? Number((acplWeightedA / pliesA).toFixed(1)) : null,
      acplB: hasAllStats && pliesB > 0 ? Number((acplWeightedB / pliesB).toFixed(1)) : null,
      blundersA: hasAllStats ? blundersA : null,
      blundersB: hasAllStats ? blundersB : null,
      games: memberGames,
      reportUrl: meta.repoBlobBase + def.report,
    };

    if (!isExploratory) {
      return {
        ...base,
        protocol: def.protocol,
        sessionMode: def.sessionMode,
        roundRobinGroup: def.roundRobinGroup || null,
        keyBlunders,
        noteZh: def.noteZh || null,
        noteEn: def.noteEn || null,
      };
    }
    return {
      ...base,
      tagZh: def.tagZh,
      tagEn: def.tagEn,
      descZh: def.descZh,
      descEn: def.descEn,
    };
  }

  const series = meta.series.map((s) => aggregateMatchGroup(s, false));
  const exploratory = meta.exploratory.map((e) => aggregateMatchGroup(e, true));

  // 严格校验全部 64 盘无引擎对局 100% 归入 series ∪ exploratory，零遗漏
  const allH2hDirs = games.filter((g) => g.cat === 'h2h').map((g) => g.dir);
  const missingH2h = allH2hDirs.filter((d) => !coveredH2h.has(d));
  if (missingH2h.length) {
    throw new Error(`存在未归入 series 或 exploratory 的无引擎对局：${missingH2h.join(', ')}`);
  }

  // 自动聚合 2026-11-19 国象三强对称循环赛（12 局）速览表
  const rrSeries = series.filter((s) => s.roundRobinGroup === 'chess-20261119');
  const rrMap = new Map();
  const ensureRr = (side) => {
    const key = `${side.raw}+${side.effort}`;
    if (!rrMap.has(key)) {
      rrMap.set(key, {
        key,
        raw: side.raw,
        techName: side.techName,
        effort: side.effort,
        labelZh: side.labelZh,
        labelEn: side.labelEn,
        shortLabel: side.shortLabel || `${side.labelEn} ${side.effort}`,
        pts: 0,
        losses: 0,
        games: 0,
        whitePts: 0,
        whiteGames: 0,
        blackPts: 0,
        blackGames: 0,
        pairings: [],
      });
    }
    return rrMap.get(key);
  };
  for (const s of rrSeries) {
    const pA = ensureRr(s.sideA);
    const pB = ensureRr(s.sideB);
    pA.pts += s.scoreA;
    pA.losses += s.scoreB;
    pA.games += s.gamesCount;
    pA.whitePts += s.aFirst.pts;
    pA.whiteGames += s.aFirst.total;
    pA.blackPts += s.aSecond.pts;
    pA.blackGames += s.aSecond.total;
    pA.pairings.push({ vsShort: pB.shortLabel, score: `${s.scoreA}:${s.scoreB}`, seriesId: s.id });

    pB.pts += s.scoreB;
    pB.losses += s.scoreA;
    pB.games += s.gamesCount;
    const bWhitePts = s.aSecond.total - s.aSecond.pts;
    const bBlackPts = s.aFirst.total - s.aFirst.pts;
    pB.whitePts += bWhitePts;
    pB.whiteGames += s.aSecond.total;
    pB.blackPts += bBlackPts;
    pB.blackGames += s.aFirst.total;
    pB.pairings.push({ vsShort: pA.shortLabel, score: `${s.scoreB}:${s.scoreA}`, seriesId: s.id });
  }
  const roundRobinChess20261119 = [...rrMap.values()].sort((a, b) => b.pts - a.pts);

  // 引擎棋力标定锚点（自动校验对应 batch 实际盘数）
  const engineAnchors = {};
  for (const [variant, anc] of Object.entries(meta.engineAnchors)) {
    const batchGames = games.filter((g) => g.batch === anc.batch && g.variant === variant);
    if (!batchGames.length) throw new Error(`engineAnchors.${variant} 未匹配到批次对局：${anc.batch}`);
    engineAnchors[variant] = {
      ...anc,
      count: batchGames.length,
      reportUrl: meta.repoBlobBase + anc.report,
    };
  }

  // 统计计数与权威金标硬断言（防静默口径漂移）
  const counts = {
    total: games.length,
    chess: games.filter((g) => g.variant === 'chess').length,
    xiangqi: games.filter((g) => g.variant === 'xiangqi').length,
    h2h: games.filter((g) => g.cat === 'h2h').length,
    engine: games.filter((g) => g.cat === 'engine').length,
    vsEngineOnly: games.filter((g) => g.cat === 'engine' && g.subcat !== 'random').length,
    vsRandom: games.filter((g) => g.subcat === 'random').length,
    analyzed: games.filter((g) => g.analyzed).length,
  };

  if (counts.total !== 192 || counts.chess !== 108 || counts.xiangqi !== 84) {
    throw new Error(`总盘数分布偏离预期 192 (108+84)：${JSON.stringify(counts)}`);
  }
  if (counts.h2h !== 64 || counts.engine !== 128 || counts.vsEngineOnly !== 126 || counts.vsRandom !== 2) {
    throw new Error(`类别分布偏离预期 64 + (126+2)：${JSON.stringify(counts)}`);
  }
  if (counts.analyzed !== 191) {
    throw new Error(`已分析盘数偏离预期 191：${counts.analyzed}`);
  }

  const golden = {
    'neon-vs-carbon-20261119': [4, 0, 35.1, 46.4, 8, 13],
    'neon-vs-astra62-20261119': [2, 2, 40.8, 41.0, 9, 9],
    'carbon-vs-astra62-20261119': [1, 3, 45.1, 35.8, 14, 8],
    'carbon-vs-agy-opus-20261114': [4, 0, 18.1, 35.4, 2, 7],
    'opus-max-vs-astra-max-ch-20260930': [3, 1, 47.0, 58.0, 12, 16],
    'carbon-vs-agy-opus-xq-20261114': [3, 1, 50.1, 56.0, 11, 14],
    'opus-max-vs-astra-max-xq-20260930': [4, 0, 54.8, 86.3, 3, 12],
  };
  for (const [id, want] of Object.entries(golden)) {
    const got = series.find((s) => s.id === id);
    const actual = got && [got.scoreA, got.scoreB, got.acplA, got.acplB, got.blundersA, got.blundersB];
    if (JSON.stringify(actual) !== JSON.stringify(want)) {
      throw new Error(`金标番棋 ${id} 指标漂移：实得 ${JSON.stringify(actual)}，预期 ${JSON.stringify(want)}`);
    }
  }

  // 默认按日期倒序、目录字典序排好，前端开箱即用
  const sortedGames = [...games].sort((a, b) => b.date.localeCompare(a.date) || a.dir.localeCompare(b.dir));

  return {
    counts,
    roundRobin: {
      chess20261119: {
        date: '2026-11-19',
        reportUrl: meta.repoBlobBase + 'docs/results/neon-carbon-astra-chess-20261119.md',
        standings: roundRobinChess20261119,
      },
    },
    series,
    exploratory,
    engineAnchors,
    games: sortedGames,
  };
}

export function serializeCatalog() {
  return JSON.stringify(buildCatalogObject(), null, 2) + '\n';
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const checkOnly = process.argv.includes('--check');
  const expected = serializeCatalog();
  if (checkOnly) {
    if (!existsSync(OUT_PATH)) {
      console.error(`缺少构建产物：${OUT_PATH}（请运行 node viewer/build-catalog.mjs）`);
      process.exit(1);
    }
    const current = readFileSync(OUT_PATH, 'utf8');
    if (current !== expected) {
      console.error(`索引产物已漂移：${OUT_PATH} 与现场重算不一致（请运行 node viewer/build-catalog.mjs 更新）`);
      process.exit(1);
    }
    console.log(`Catalog check passed: 192 games, 12 symmetric series, 8 exploratory groups (${OUT_PATH})`);
  } else {
    const tmp = `${OUT_PATH}.tmp`;
    writeFileSync(tmp, expected, 'utf8');
    renameSync(tmp, OUT_PATH);
    console.log(`Wrote ${OUT_PATH} (${(Buffer.byteLength(expected) / 1024).toFixed(1)} KiB)`);
  }
}
