// 全部 192 盘可筛选对局目录（catalog.html）：支持棋种、对局类别、高频模型快捷胶囊、批次筛选、关键词搜索与客观排序。
import { T, langOf } from './lib/i18n.js';
import { cleanReason } from './lib/match.js';
import { VIEWER_DIR, pageHref, saveReturnContext, viewerGameHref } from './lib/nav.js';

const DATA_URL = new URL('./lib/catalog-data.json', VIEWER_DIR).href;
const params = new URLSearchParams(location.search);
const LANG = langOf(params);
const L = T(LANG), P = L.pages;

const QUICK_MODELS = [
  ['neon', 'Neon'],
  ['carbon', 'Carbon'],
  ['astra', 'Astra'],
  ['opus', 'Opus'],
  ['argon', 'Argon'],
];
const VALID_SORTS = new Set(['newest', 'oldest', 'longest', 'shortest']);

const state = {
  variant: ['chess', 'xiangqi'].includes(params.get('variant')) ? params.get('variant') : 'all',
  cat: ['h2h', 'engine'].includes(params.get('cat')) ? params.get('cat') : 'all',
  model: (params.get('model') || '').trim().toLowerCase(),
  batch: (params.get('batch') || '').trim(),
  q: (params.get('q') || '').trim(),
  sort: VALID_SORTS.has(params.get('sort')) ? params.get('sort') : 'newest',
};

let catalog = null;
const dom = {};

function h(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== null && text !== undefined) e.textContent = text;
  return e;
}

function currentFilterParams() {
  const q = new URLSearchParams();
  if (state.variant !== 'all') q.set('variant', state.variant);
  if (state.cat !== 'all') q.set('cat', state.cat);
  if (state.model) q.set('model', state.model);
  if (state.batch) q.set('batch', state.batch);
  if (state.q) q.set('q', state.q);
  if (state.sort !== 'newest') q.set('sort', state.sort);
  return q;
}

function syncUrlAndLangSwitch() {
  const q = currentFilterParams();
  const extra = Object.fromEntries(q.entries());
  if (LANG === 'en') q.set('lang', 'en');
  const qs = q.toString();
  try { history.replaceState(history.state, '', location.pathname + (qs ? `?${qs}` : '') + location.hash); } catch { /* 忽略 */ }

  const nextLang = LANG === 'en' ? 'zh' : 'en';
  const langSwitch = document.querySelector('#top-header a.lang-switch');
  if (langSwitch) langSwitch.href = pageHref('catalog', extra, nextLang, location.hash);
}

function renderHeader(totalGames) {
  const wrap = h('div', 'p-header-inner');
  const left = h('div', 'p-brand-nav');
  const brand = h('a', 'p-brand', P.brand);
  brand.href = pageHref('index', {}, LANG);
  const nav = h('nav', 'p-tabs');

  const tabIndex = h('a', 'nav-pill', L.navFeatured);
  tabIndex.href = pageHref('index', {}, LANG);
  const tabSeries = h('a', 'nav-pill', L.navSeries);
  tabSeries.href = pageHref('series', {}, LANG);
  const tabCatalog = h('a', 'nav-pill active', L.navCatalog(totalGames));
  tabCatalog.href = pageHref('catalog', {}, LANG);
  tabCatalog.setAttribute('aria-current', 'page');
  nav.append(tabIndex, tabSeries, tabCatalog);
  left.append(brand, nav);

  const nextLang = LANG === 'en' ? 'zh' : 'en';
  const extra = Object.fromEntries(currentFilterParams().entries());
  const langBtn = h('a', 'nav-pill lang-switch', LANG === 'en' ? '中文' : 'EN');
  langBtn.href = pageHref('catalog', extra, nextLang, location.hash);
  wrap.append(left, langBtn);
  document.getElementById('top-header').replaceChildren(wrap);
}

function subcatLabel(subcat) {
  if (subcat === 'selfplay') return P.catBadgeSelf;
  if (subcat === 'engine_anchor') return P.catBadgeAnchor;
  if (subcat === 'random') return P.catBadgeRandom;
  if (subcat === 'legacy_engine') return P.catBadgeEngine;
  return P.catBadgeH2h;
}

function resultShortText(g) {
  const xq = g.variant === 'xiangqi';
  const head = g.result === '1-0'
    ? `1-0 · ${xq ? L.redWins : L.whiteWins}`
    : g.result === '0-1'
      ? `0-1 · ${L.blackWins}`
      : `1/2-1/2 · ${L.draw}`;
  const why = cleanReason(g.termination, LANG);
  return { head, why };
}

function filterAndSortGames() {
  const needle = state.q.replace(/\s+/g, ' ').toLowerCase();
  const out = catalog.games.filter((g) => {
    if (state.variant !== 'all' && g.variant !== state.variant) return false;
    if (state.cat !== 'all' && g.cat !== state.cat) return false;
    if (state.batch && g.batch.toLowerCase() !== state.batch.toLowerCase()) return false;
    if (state.model) {
      const hitTag = g.modelTags.includes(state.model);
      const hitRaw = g.w.raw.toLowerCase().includes(state.model) || g.b.raw.toLowerCase().includes(state.model);
      if (!hitTag && !hitRaw) return false;
    }
    if (needle) {
      const sideTerms = (p) => {
        const terms = [
          p.raw,
          p.short,
          p.name,
          p.labelZh,
          p.labelEn,
          p.effort,
          p.effort ? `${p.short}+${p.effort}` : '',
          p.effort ? `${p.labelEn || p.name} +${p.effort}` : '',
          p.effort ? `${p.labelEn || p.name}+${p.effort}` : '',
          p.effort ? `${p.labelZh || p.name} +${p.effort}` : '',
          p.effort ? `${p.labelZh || p.name}+${p.effort}` : '',
        ];
        if (Array.isArray(p.aliases)) {
          for (const a of p.aliases) {
            terms.push(a);
            if (p.effort) terms.push(`${a} +${p.effort}`, `${a}+${p.effort}`);
          }
        }
        return terms;
      };
      const hay = [
        g.dir, g.batch, g.date, g.protocol, g.sessionMode,
        ...sideTerms(g.w),
        ...sideTerms(g.b),
      ].filter(Boolean).join(' ').toLowerCase();
      if (!hay.includes(needle) && !needle.split(' ').every((tok) => hay.includes(tok))) return false;
    }
    return true;
  });

  out.sort((a, b) => {
    if (state.sort === 'oldest') return a.date.localeCompare(b.date) || a.dir.localeCompare(b.dir);
    if (state.sort === 'longest') return b.plies - a.plies || b.date.localeCompare(a.date) || a.dir.localeCompare(b.dir);
    if (state.sort === 'shortest') return a.plies - b.plies || b.date.localeCompare(a.date) || a.dir.localeCompare(b.dir);
    return b.date.localeCompare(a.date) || a.dir.localeCompare(b.dir);
  });
  return out;
}

function renderGameRow(g) {
  const xq = g.variant === 'xiangqi';
  const row = h('a', 'cat-row');
  row.href = viewerGameHref(g.dir, { lang: LANG });
  row.dataset.dir = g.dir;
  row.addEventListener('click', () => {
    saveReturnContext('catalog', currentFilterParams(), g.dir);
  });

  const body = h('div', 'cat-body');
  const meta = h('div', 'cat-meta');
  meta.append(
    h('span', 'badge', xq ? L.xiangqi : L.chess),
    h('span', null, g.date),
    h('span', 'badge', subcatLabel(g.subcat)),
  );
  if (g.lang === 'en') meta.append(h('span', 'badge en', 'EN'));
  meta.append(h('span', 'cat-dir', g.dir.replace(/^runs\//, '')));

  const players = h('div', 'cat-players');
  const makePlayer = (p, discCls) => {
    const sp = h('span', 'cat-side');
    const disp = LANG === 'en' ? (p.labelEn || p.name) : (p.labelZh || p.name);
    sp.append(h('span', `disc ${discCls}`), h('span', 'cat-pname', disp));
    if (p.effort) sp.append(h('span', 'cat-peff', `+${p.effort}`));
    return sp;
  };
  players.append(
    makePlayer(g.w, xq ? 'red' : 'white'),
    h('span', 'cat-vs', L.vs),
    makePlayer(g.b, 'black'),
  );

  const foot = h('div', 'cat-foot');
  const outcome = h('div', 'cat-outcome');
  const { head, why } = resultShortText(g);
  outcome.append(h('span', 'cat-res', head));
  if (why) outcome.append(h('span', 'cat-why', why));

  const stats = h('div', 'cat-stats');
  stats.append(h('span', null, P.pliesCount(g.plies)));
  if (g.analyzed && g.w.acpl !== null && g.b.acpl !== null) {
    stats.append(h('span', null, `${P.acplShort(`${g.w.acpl.toFixed(1)} / ${g.b.acpl.toFixed(1)}`)}`));
    const blSpan = h('span', g.w.blunders + g.b.blunders > 0 ? 'bl-bad' : null,
      `${P.blundersLbl} ${g.w.blunders} / ${g.b.blunders}`);
    stats.append(blSpan);
  } else {
    stats.append(h('span', 'badge', P.unanalyzed));
  }
  foot.append(outcome, stats);

  body.append(meta, players, foot);
  row.append(body, h('span', 'cat-arr', '›'));
  return row;
}

function resetAllFilters() {
  state.variant = 'all';
  state.cat = 'all';
  state.model = '';
  state.batch = '';
  state.q = '';
  state.sort = 'newest';
  if (dom.search) dom.search.value = '';
  if (dom.sort) dom.sort.value = 'newest';
  refreshView();
}

function hasActiveFilter() {
  return state.variant !== 'all' || state.cat !== 'all' || Boolean(state.model) || Boolean(state.batch) || Boolean(state.q);
}

function refreshView() {
  syncUrlAndLangSwitch();
  for (const b of dom.variantBtns) b.classList.toggle('active', b.dataset.val === state.variant);
  for (const b of dom.catBtns) b.classList.toggle('active', b.dataset.val === state.cat);
  for (const b of dom.modelBtns) b.classList.toggle('active', b.dataset.val === state.model);

  const filtered = filterAndSortGames();
  dom.countText.textContent = P.showingCount(filtered.length, catalog.counts.total);

  const tags = [];
  if (state.batch) {
    const chip = h('button', 'tag-chip', `${P.batchFilterTag(state.batch)} ×`);
    chip.type = 'button';
    chip.addEventListener('click', () => {
      state.batch = '';
      refreshView();
    });
    tags.push(chip);
  }
  if (hasActiveFilter()) {
    const clr = h('button', 'clear-btn', P.clearFilters);
    clr.type = 'button';
    clr.addEventListener('click', resetAllFilters);
    tags.push(clr);
  }
  dom.activeTags.replaceChildren(...tags);

  if (!filtered.length) {
    const empty = h('div', 'empty-box');
    const rst = h('button', 'btn-outline', P.resetCatalogBtn);
    rst.type = 'button';
    rst.addEventListener('click', resetAllFilters);
    empty.append(h('p', null, P.emptyCatalog), rst);
    dom.listWrap.replaceChildren(empty);
    return;
  }

  const list = h('div', 'cat-list');
  for (const g of filtered) list.append(renderGameRow(g));
  dom.listWrap.replaceChildren(list);
}

function buildShell() {
  const c = catalog.counts;
  const app = document.getElementById('app');

  const intro = h('section', 'p-intro');
  intro.append(h('h1', null, P.catalogHeading), h('p', null, P.catalogSub));

  const panel = h('section', 'filter-panel');

  // 第 1 行：棋种分段 + 类别分段
  const row1 = h('div', 'filter-row');
  const varGroup = h('div', 'pill-group');
  dom.variantBtns = [
    ['all', P.filterVariantAll(c.total)],
    ['chess', P.filterChess(c.chess)],
    ['xiangqi', P.filterXq(c.xiangqi)],
  ].map(([val, label]) => {
    const b = h('button', 'f-pill', label);
    b.type = 'button';
    b.dataset.val = val;
    b.addEventListener('click', () => { state.variant = val; refreshView(); });
    return b;
  });
  varGroup.append(...dom.variantBtns);

  const catGroup = h('div', 'pill-group');
  dom.catBtns = [
    ['all', P.filterCatAll(c.total)],
    ['h2h', P.filterCatH2h(c.h2h)],
    ['engine', P.filterCatEngine(c.engine)],
  ].map(([val, label]) => {
    const b = h('button', 'f-pill', label);
    b.type = 'button';
    b.dataset.val = val;
    b.addEventListener('click', () => { state.cat = val; refreshView(); });
    return b;
  });
  catGroup.append(...dom.catBtns);
  row1.append(varGroup, catGroup);

  // 第 2 行：高频模型胶囊
  const row2 = h('div', 'pill-group');
  row2.append(h('span', 'f-lbl', `${P.modelFilterLbl}:`));
  dom.modelBtns = QUICK_MODELS.map(([val, label]) => {
    const b = h('button', 'f-pill model-pill', label);
    b.type = 'button';
    b.dataset.val = val;
    b.addEventListener('click', () => {
      state.model = state.model === val ? '' : val;
      refreshView();
    });
    return b;
  });
  row2.append(...dom.modelBtns);

  // 第 3 行：关键词搜索框 + 排序下拉
  const row3 = h('div', 'search-sort-row');
  const search = h('input', 'search-input');
  search.id = 'cat-q';
  search.type = 'search';
  search.placeholder = P.searchPlaceholder;
  search.setAttribute('aria-label', P.searchAria);
  search.setAttribute('autocapitalize', 'none');
  search.setAttribute('autocorrect', 'off');
  search.setAttribute('spellcheck', 'false');
  search.setAttribute('autocomplete', 'off');
  search.value = state.q;
  search.addEventListener('input', () => {
    state.q = search.value.trim();
    refreshView();
  });
  dom.search = search;

  const sort = h('select', 'sort-select');
  sort.setAttribute('aria-label', P.sortAria);
  for (const [val, label] of [
    ['newest', P.sortNewest],
    ['oldest', P.sortOldest],
    ['longest', P.sortLongest],
    ['shortest', P.sortShortest],
  ]) {
    const opt = h('option', null, label);
    opt.value = val;
    sort.append(opt);
  }
  sort.value = state.sort;
  sort.addEventListener('change', () => {
    state.sort = sort.value;
    refreshView();
  });
  dom.sort = sort;
  row3.append(search, sort);

  panel.append(row1, row2, row3);

  const statusBar = h('div', 'status-bar');
  dom.countText = h('span', null, '');
  dom.activeTags = h('div', 'active-tags');
  statusBar.append(dom.countText, dom.activeTags);

  dom.listWrap = h('section', 'cat-results');
  app.replaceChildren(intro, panel, statusBar, dom.listWrap);
}

async function init() {
  document.documentElement.lang = L.htmlLang;
  document.title = P.catalogTitle;
  const res = await fetch(DATA_URL);
  if (!res.ok) throw new Error(`Failed to load catalog-data.json: ${res.status}`);
  catalog = await res.json();
  renderHeader(catalog.counts.total);
  buildShell();
  refreshView();
  addEventListener('hashchange', syncUrlAndLangSwitch);
  await document.fonts?.ready;
  return true;
}

window.pageReady = init();
