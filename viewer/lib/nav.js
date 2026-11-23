// 三页静态站共享路由与安全返回状态管理（viewer/{index,series,catalog}.html）。
// 严格分离页面目录 VIEWER_DIR（本机 /viewer/，线上 /agi-chess/）与数据根 SITE_ROOT（本机 /，线上 /agi-chess/）。

export const VIEWER_DIR = new URL('..', import.meta.url);
export const SITE_ROOT = VIEWER_DIR.pathname.endsWith('/viewer/') ? new URL('..', VIEWER_DIR) : VIEWER_DIR;

const RETURN_KEY = `agi-chess:return:${VIEWER_DIR.pathname}`;
const ALLOWED_PAGES = new Set(['series', 'catalog']);
const ALLOWED_PARAMS = new Set(['variant', 'cat', 'model', 'batch', 'q', 'sort']);

export function normalizeFilesParam(raw) {
  return String(raw || '')
    .split(',')
    .map((s) => s.trim().replace(/^\/+/, '').replace(/\/+$/, ''))
    .filter(Boolean)
    .join(',');
}

export function pageHref(page, extra = {}, lang = 'zh', hash = '') {
  const rel = page === 'index' ? './' : `${page}.html`;
  const u = new URL(rel, VIEWER_DIR);
  for (const [k, v] of Object.entries(extra || {})) {
    if (v !== undefined && v !== null && v !== '') u.searchParams.set(k, String(v));
  }
  if (lang === 'en') u.searchParams.set('lang', 'en');
  const h = hash ? (hash.startsWith('#') ? hash : `#${hash}`) : '';
  return u.pathname + u.search + h;
}

export function viewerGameHref(files, { ply = null, autoplay = false, lang = 'zh' } = {}) {
  const u = new URL('./', VIEWER_DIR);
  const list = Array.isArray(files) ? files.join(',') : String(files || '');
  u.searchParams.set('files', list);
  if (autoplay) u.searchParams.set('autoplay', '1');
  else if (ply !== null && ply !== undefined && ply > 0) u.searchParams.set('ply', String(ply));
  if (lang === 'en') u.searchParams.set('lang', 'en');
  const qs = u.searchParams.toString().replace(/%2F/gi, '/').replace(/%2C/gi, ',');
  return u.pathname + (qs ? `?${qs}` : '');
}

function sanitizePairs(pairs) {
  if (!Array.isArray(pairs)) return [];
  const out = [];
  for (const item of pairs) {
    if (!Array.isArray(item) || item.length !== 2) continue;
    const [k, v] = item;
    if (typeof k !== 'string' || typeof v !== 'string') continue;
    if (!ALLOWED_PARAMS.has(k) || !v || v.length > 120) continue;
    out.push([k, v]);
  }
  return out;
}

export function saveReturnContext(page, searchParams, targetFiles) {
  if (!ALLOWED_PAGES.has(page)) return;
  const files = normalizeFilesParam(targetFiles);
  if (!files) return;
  const pairs = [];
  if (searchParams) {
    for (const [k, v] of searchParams.entries()) {
      if (ALLOWED_PARAMS.has(k) && v && v.length <= 120) pairs.push([k, v]);
    }
  }
  try {
    sessionStorage.setItem(RETURN_KEY, JSON.stringify({ page, params: pairs, files }));
  } catch { /* 隐私模式或受限沙箱静默忽略 */ }
}

export function persistReturnForReload(back) {
  if (!back || !ALLOWED_PAGES.has(back.page) || !back.files) return;
  try {
    sessionStorage.setItem(RETURN_KEY, JSON.stringify({
      page: back.page,
      params: sanitizePairs(back.params),
      files: normalizeFilesParam(back.files),
    }));
  } catch { /* 受限沙箱静默忽略 */ }
}

export function clearReturnContext() {
  try { sessionStorage.removeItem(RETURN_KEY); } catch { /* 忽略 */ }
}

export function consumeReturnContext(currentFilesRaw) {
  const curFiles = normalizeFilesParam(currentFilesRaw);
  if (!curFiles) {
    clearReturnContext();
    return null;
  }
  let stored = null;
  try {
    const raw = sessionStorage.getItem(RETURN_KEY);
    if (raw !== null) sessionStorage.removeItem(RETURN_KEY);
    if (raw) stored = JSON.parse(raw);
  } catch { /* 忽略损坏 JSON */ }

  if (stored && ALLOWED_PAGES.has(stored.page) && normalizeFilesParam(stored.files) === curFiles) {
    const back = { page: stored.page, params: sanitizePairs(stored.params), files: curFiles };
    try {
      const nextState = { ...(history.state && typeof history.state === 'object' ? history.state : {}), back };
      history.replaceState(nextState, '', location.href);
    } catch { /* 受限沙箱静默忽略 */ }
    return back;
  }

  const stBack = history.state?.back;
  if (stBack && ALLOWED_PAGES.has(stBack.page) && normalizeFilesParam(stBack.files) === curFiles) {
    return { page: stBack.page, params: sanitizePairs(stBack.params), files: curFiles };
  }
  return null;
}

export function buildBackHref(back, lang = 'zh') {
  if (!back || !ALLOWED_PAGES.has(back.page)) return pageHref('index', {}, lang);
  const u = new URL(`${back.page}.html`, VIEWER_DIR);
  for (const [k, v] of sanitizePairs(back.params)) u.searchParams.set(k, v);
  if (lang === 'en') u.searchParams.set('lang', 'en');
  return u.pathname + u.search;
}
