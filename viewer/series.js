// 无引擎对阵总览页（series.html）：国际象棋 / 中国象棋分栏、同赛程循环赛速览、标准对称番棋主榜、独立引擎等级分锚点、折叠探索局。
import { T, langOf } from './lib/i18n.js';
import { fmtScore } from './lib/match.js';
import { VIEWER_DIR, pageHref, saveReturnContext, viewerGameHref } from './lib/nav.js';

const DATA_URL = new URL('./lib/catalog-data.json', VIEWER_DIR).href;
const params = new URLSearchParams(location.search);
const LANG = langOf(params);
const L = T(LANG), P = L.pages;

let activeVariant = params.get('variant') === 'xiangqi' ? 'xiangqi' : 'chess';
let catalog = null;

function h(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== null && text !== undefined) e.textContent = text;
  return e;
}

function makePlayIcon() {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 16 16');
  svg.setAttribute('aria-hidden', 'true');
  const p = document.createElementNS(ns, 'path');
  p.setAttribute('d', 'M4 2.8v10.4L13 8z');
  svg.append(p);
  return svg;
}

function currentFilterParams() {
  const q = new URLSearchParams();
  if (activeVariant === 'xiangqi') q.set('variant', 'xiangqi');
  return q;
}

function syncAddressAndHeader() {
  const q = currentFilterParams();
  if (LANG === 'en') q.set('lang', 'en');
  const qs = q.toString();
  const nextUrl = location.pathname + (qs ? `?${qs}` : '') + location.hash;
  try { history.replaceState(history.state, '', nextUrl); } catch { /* 忽略 */ }

  const nextLang = LANG === 'en' ? 'zh' : 'en';
  const langExtra = activeVariant === 'xiangqi' ? { variant: 'xiangqi' } : {};
  const langSwitch = document.querySelector('#top-header a.lang-switch');
  if (langSwitch) langSwitch.href = pageHref('series', langExtra, nextLang, location.hash);
}

function bindViewerLink(a, targetFiles, href) {
  a.href = href;
  a.addEventListener('click', () => {
    saveReturnContext('series', currentFilterParams(), targetFiles);
  });
  return a;
}

function renderHeader(totalGames) {
  const wrap = h('div', 'p-header-inner');
  const left = h('div', 'p-brand-nav');
  const brand = h('a', 'p-brand', P.brand);
  brand.href = pageHref('index', {}, LANG);
  const nav = h('nav', 'p-tabs');

  const tabIndex = h('a', 'nav-pill', L.navFeatured);
  tabIndex.href = pageHref('index', {}, LANG);
  const tabSeries = h('a', 'nav-pill active', L.navSeries);
  tabSeries.href = pageHref('series', activeVariant === 'xiangqi' ? { variant: 'xiangqi' } : {}, LANG);
  tabSeries.setAttribute('aria-current', 'page');
  const tabCatalog = h('a', 'nav-pill', L.navCatalog(totalGames));
  tabCatalog.href = pageHref('catalog', {}, LANG);
  nav.append(tabIndex, tabSeries, tabCatalog);
  left.append(brand, nav);

  const nextLang = LANG === 'en' ? 'zh' : 'en';
  const langBtn = h('a', 'nav-pill lang-switch', LANG === 'en' ? '中文' : 'EN');
  langBtn.href = pageHref('series', activeVariant === 'xiangqi' ? { variant: 'xiangqi' } : {}, nextLang, location.hash);
  wrap.append(left, langBtn);
  document.getElementById('top-header').replaceChildren(wrap);
}

function renderRoundRobin(rr) {
  const card = h('section', 'rr-card');
  const top = h('div', 'rr-top');
  const tw = h('div', 'rr-title-wrap');
  tw.append(h('div', 'rr-kicker', P.rrBadge), h('h2', 'rr-title', P.rrTitle));
  const rep = h('a', 'ext-link', P.reportLink);
  rep.href = rr.reportUrl;
  rep.target = '_blank';
  rep.rel = 'noopener';
  top.append(tw, rep);

  const grid = h('div', 'rr-grid');
  for (const st of rr.standings) {
    const item = h('div', 'rr-item');
    const row1 = h('div', 'rr-model-row');
    const nameSpan = h('span', 'rr-model-name', LANG === 'en' ? st.labelEn : st.labelZh);
    nameSpan.append(h('span', 'rr-eff', `+${st.effort}`));
    row1.append(nameSpan, h('span', 'rr-pts', `${fmtScore(st.pts)}–${fmtScore(st.losses)}`));

    const meta1 = h('div', 'rr-meta');
    meta1.append(
      h('span', null, `${P.asFirst(P.firstWordChess)} ${fmtScore(st.whitePts)}/${st.whiteGames}`),
      h('span', null, `${P.asSecond} ${fmtScore(st.blackPts)}/${st.blackGames}`),
    );
    const meta2 = h('div', 'rr-meta');
    for (const pr of st.pairings) {
      meta2.append(h('span', null, `${L.vs} ${pr.vsShort} ${pr.score}`));
    }
    item.append(row1, meta1, meta2);
    grid.append(item);
  }

  card.append(top, grid, h('p', 'rr-note', P.rrNote));
  return card;
}

function renderSeriesCard(s) {
  const card = h('article', 's-card');
  const top = h('div', 's-top');
  const badges = h('div', 's-badges');
  badges.append(
    h('span', null, s.date),
    h('span', 'badge' + (s.lang === 'en' ? ' en' : ''), P.promptLang(s.lang)),
    h('span', 'badge', P.gamesCount(s.gamesCount)),
  );

  const actions = h('div', 's-actions');
  const playAll = bindViewerLink(
    h('a', 'btn-play'),
    s.files.join(','),
    viewerGameHref(s.files, { autoplay: true, lang: LANG }),
  );
  playAll.append(makePlayIcon(), h('span', null, P.playSeries));
  const rep = h('a', 'ext-link', P.reportLink);
  rep.href = s.reportUrl;
  rep.target = '_blank';
  rep.rel = 'noopener';
  actions.append(playAll, rep);
  top.append(badges, actions);

  // 双方模型 + 中央比分条
  const matchup = h('div', 's-matchup');
  const makeSide = (side, right = false) => {
    const box = h('div', 's-side' + (right ? ' right' : ''));
    const line = h('div', 's-name-line');
    line.append(
      h('span', 's-model', LANG === 'en' ? side.labelEn : side.labelZh),
      h('span', 's-effort', `+${side.effort}`),
    );
    box.append(line, h('div', 's-raw', side.raw));
    return box;
  };

  const scoreBox = h('div', 's-score-box');
  const nums = h('div', 's-score-nums');
  nums.append(
    h('span', s.scoreA > s.scoreB ? 'lead' : '', fmtScore(s.scoreA)),
    h('span', 'sep', ':'),
    h('span', s.scoreB > s.scoreA ? 'lead' : '', fmtScore(s.scoreB)),
  );
  const bar = h('div', 's-bar');
  const tot = s.scoreA + s.scoreB || 1;
  const barA = h('div', 's-bar-a');
  barA.style.width = `${(s.scoreA / tot) * 100}%`;
  const barB = h('div', 's-bar-b');
  barB.style.width = `${(s.scoreB / tot) * 100}%`;
  bar.append(barA, barB);

  const firstWord = s.variant === 'xiangqi' ? P.firstWordXq : P.firstWordChess;
  const splitText = `${P.asFirst(firstWord)} ${fmtScore(s.aFirst.pts)}/${s.aFirst.total} · ${P.asSecond} ${fmtScore(s.aSecond.pts)}/${s.aSecond.total}`;
  scoreBox.append(nums, bar, h('div', 's-split', splitText));

  matchup.append(makeSide(s.sideA, false), scoreBox, makeSide(s.sideB, true));

  // 加权 ACPL + 恶手数
  const statsRow = h('div', 's-stats-row');
  const metrics = h('div', 's-metrics');
  if (s.acplA !== null && s.acplB !== null) {
    const acplPair = h('span', 'm-pair', `${P.acplLbl}: `);
    acplPair.append(h('b', null, `${s.acplA.toFixed(1)}`), ' / ', h('b', null, `${s.acplB.toFixed(1)}`));
    const blPair = h('span', 'm-pair', `${P.blundersLbl}: `);
    blPair.append(h('b', null, String(s.blundersA)), ' / ', h('b', null, String(s.blundersB)));
    metrics.append(acplPair, blPair);
  }
  statsRow.append(metrics);

  // G1..Gn 单局胶囊 + 关键恶手步直达（严禁带 autoplay=1）
  const linksRow = h('div', 's-links-row');
  const gPills = h('div', 'g-pills');
  for (const gm of s.games) {
    const gp = bindViewerLink(
      h('a', 'g-pill'),
      gm.dir,
      viewerGameHref(gm.dir, { lang: LANG }),
    );
    const resWord = gm.aScore === 1 ? P.resWin : gm.aScore === 0 ? P.resLoss : P.resDraw;
    gp.append(
      h('span', 'disc ' + (gm.aSide === 'w' ? (s.variant === 'xiangqi' ? 'red' : 'white') : 'black')),
      h('span', null, P.gameBtn(gm.no)),
      h('span', 'g-res', resWord),
    );
    gPills.append(gp);
  }
  linksRow.append(gPills);

  if (s.keyBlunders?.length) {
    const bPills = h('div', 'b-pills');
    bPills.append(h('span', 'b-lbl', `${P.keyBlundersLbl}:`));
    for (const kb of s.keyBlunders) {
      const bp = bindViewerLink(
        h('a', 'b-pill', LANG === 'en' ? kb.labelEn : kb.labelZh),
        kb.file,
        viewerGameHref(kb.file, { ply: kb.ply, lang: LANG }),
      );
      bPills.append(bp);
    }
    linksRow.append(bPills);
  }

  card.append(top, matchup, statsRow, linksRow);
  const note = LANG === 'en' ? s.noteEn : s.noteZh;
  if (note) card.append(h('p', 's-footnote', note));
  return card;
}

function renderAnchorCard(anc) {
  const card = h('section', 'anchor-card');
  const top = h('div', 'anchor-top');
  top.append(h('span', 'anchor-kicker', `${P.anchorBadge} · ${anc.date}`), h('span', 'badge', P.gamesCount(anc.count)));
  card.append(
    top,
    h('h2', 'anchor-title', P.anchorHeading),
    h('div', 'anchor-headline', LANG === 'en' ? anc.headlineEn : anc.headlineZh),
    h('p', 'anchor-detail', LANG === 'en' ? anc.detailEn : anc.detailZh),
    h('p', 'anchor-scope', P.anchorNote),
  );
  const actions = h('div', 'anchor-actions');
  const jump = h('a', 'btn-outline', P.browseBatch(anc.count));
  jump.href = pageHref('catalog', { batch: anc.batch }, LANG);
  const rep = h('a', 'ext-link', P.reportLink);
  rep.href = anc.reportUrl;
  rep.target = '_blank';
  rep.rel = 'noopener';
  actions.append(jump, rep);
  card.append(actions);
  return card;
}

function renderExploratory(groups) {
  const totalExpGames = groups.reduce((n, g) => n + g.gamesCount, 0);
  const det = h('details', 'exp-details');
  det.append(h('summary', null, P.expSummary(totalExpGames)));
  const body = h('div', 'exp-body');
  body.append(h('p', 'exp-sub', P.expSub));

  for (const ex of groups) {
    const row = h('div', 'exp-row');
    const head = h('div', 'exp-head');
    const badges = h('div', 's-badges');
    badges.append(
      h('span', null, ex.date),
      h('span', 'badge', LANG === 'en' ? ex.tagEn : ex.tagZh),
      h('span', 'badge' + (ex.lang === 'en' ? ' en' : ''), P.promptLang(ex.lang)),
      h('span', 'badge', P.gamesCount(ex.gamesCount)),
    );
    const rep = h('a', 'ext-link', P.reportLink);
    rep.href = ex.reportUrl;
    rep.target = '_blank';
    rep.rel = 'noopener';
    head.append(badges, rep);

    const match = h('div', 'exp-match');
    const pl = h('div', 'exp-players');
    const nameA = `${LANG === 'en' ? ex.sideA.labelEn : ex.sideA.labelZh} +${ex.sideA.effort}`;
    const nameB = `${LANG === 'en' ? ex.sideB.labelEn : ex.sideB.labelZh} +${ex.sideB.effort}`;
    pl.append(h('span', null, nameA), h('span', 'vs', L.vs), h('span', null, nameB));
    match.append(pl, h('div', 'exp-score', `${fmtScore(ex.scoreA)} : ${fmtScore(ex.scoreB)}`));

    const foot = h('div', 's-links-row');
    const stats = h('div', 's-metrics');
    if (ex.acplA !== null && ex.acplB !== null) {
      const acpl = h('span', 'm-pair', `${P.acplLbl}: `);
      acpl.append(h('b', null, `${ex.acplA.toFixed(1)}`), ' / ', h('b', null, `${ex.acplB.toFixed(1)}`));
      const bl = h('span', 'm-pair', `${P.blundersLbl}: `);
      bl.append(h('b', null, String(ex.blundersA)), ' / ', h('b', null, String(ex.blundersB)));
      stats.append(acpl, bl);
    } else {
      stats.append(h('span', 'm-pair', P.unanalyzed));
    }
    const gPills = h('div', 'g-pills');
    if (ex.games.length > 1) {
      const playBtn = bindViewerLink(
        h('a', 'btn-play'),
        ex.files.join(','),
        viewerGameHref(ex.files, { autoplay: true, lang: LANG }),
      );
      playBtn.append(makePlayIcon(), h('span', null, P.playSeries));
      gPills.append(playBtn);
    }
    for (const gm of ex.games) {
      const gp = bindViewerLink(
        h('a', 'g-pill', ex.games.length === 1 ? `${P.gameBtn(1)} · ${P.pliesCount(gm.plies)}` : P.gameBtn(gm.no)),
        gm.dir,
        viewerGameHref(gm.dir, { lang: LANG }),
      );
      gPills.append(gp);
    }
    foot.append(stats, gPills);

    row.append(head, match, h('p', 'exp-desc', LANG === 'en' ? ex.descEn : ex.descZh), foot);
    body.append(row);
  }

  det.append(body);
  return det;
}

function render() {
  const app = document.getElementById('app');
  const intro = h('section', 'p-intro');
  intro.append(h('h1', null, P.seriesHeading), h('p', null, P.seriesSub));

  const chSeries = catalog.series.filter((s) => s.variant === 'chess');
  const xqSeries = catalog.series.filter((s) => s.variant === 'xiangqi');
  const seg = h('div', 'seg-bar');
  const makeVarBtn = (v, label) => {
    const b = h('button', 'seg-btn' + (activeVariant === v ? ' active' : ''), label);
    b.type = 'button';
    b.dataset.variant = v;
    b.addEventListener('click', () => {
      if (activeVariant === v) return;
      activeVariant = v;
      renderHeader(catalog.counts.total);
      syncAddressAndHeader();
      render();
    });
    return b;
  };
  seg.append(
    makeVarBtn('chess', `${L.chess} (${chSeries.length})`),
    makeVarBtn('xiangqi', `${L.xiangqi} (${xqSeries.length})`),
  );

  const kids = [intro, seg];
  if (activeVariant === 'chess') {
    kids.push(renderRoundRobin(catalog.roundRobin.chess20261119));
  }

  kids.push(h('h2', 'sec-head', activeVariant === 'xiangqi' ? P.mainSectionXq : P.mainSectionChess));
  const curSeries = activeVariant === 'xiangqi' ? xqSeries : chSeries;
  const list = h('div', 'series-list');
  for (const s of curSeries) list.append(renderSeriesCard(s));
  kids.push(list);

  const anc = catalog.engineAnchors[activeVariant];
  if (anc) kids.push(renderAnchorCard(anc));

  const curExp = catalog.exploratory.filter((e) => e.variant === activeVariant);
  if (curExp.length) kids.push(renderExploratory(curExp));

  app.replaceChildren(...kids);
}

async function init() {
  document.documentElement.lang = L.htmlLang;
  document.title = P.seriesTitle;
  const res = await fetch(DATA_URL);
  if (!res.ok) throw new Error(`Failed to load catalog-data.json: ${res.status}`);
  catalog = await res.json();
  renderHeader(catalog.counts.total);
  syncAddressAndHeader();
  render();
  addEventListener('hashchange', syncAddressAndHeader);
  await document.fonts?.ready;
  return true;
}

window.pageReady = init();
