// 跨平台可执行文件查找（ffmpeg / ffprobe / Chromium）：供 serve.mjs、record.mjs、shot.mjs 与 viewer/test/*.test.js 共用。
import { accessSync, constants, statSync } from 'node:fs';
import path from 'node:path';

export function isExecutableFile(p) {
  if (!p) return false;
  try {
    accessSync(p, constants.X_OK);
    return statSync(p).isFile();
  } catch {
    return false;
  }
}

export function findExecutable(names, extraPaths = [], platform = process.platform) {
  const list = Array.isArray(names) ? names : [names];
  const exts = platform === 'win32' ? ['', '.exe', '.cmd', '.bat'] : [''];
  const dirs = (process.env.PATH || '').split(path.delimiter).filter(Boolean);
  for (const dir of dirs) {
    for (const name of list) {
      const hasExt = /\.(exe|cmd|bat|com)$/i.test(name);
      for (const ext of (hasExt ? [''] : exts)) {
        const candidate = path.join(dir, name + ext);
        if (isExecutableFile(candidate)) return candidate;
      }
    }
  }
  for (const candidate of extraPaths) {
    if (isExecutableFile(candidate)) return candidate;
  }
  return null;
}

function isBareCommand(s) {
  return Boolean(s) && !s.includes(path.sep) && !s.includes('/') && !s.includes('\\');
}

const FFMPEG_EXTRAS = ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', '/usr/bin/ffmpeg'];
const FFPROBE_EXTRAS = ['/opt/homebrew/bin/ffprobe', '/usr/local/bin/ffprobe', '/usr/bin/ffprobe'];
const CHROMIUM_EXTRAS = [
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/google-chrome',
  '/snap/bin/chromium',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
];

export function resolveFfmpeg(explicit) {
  const pick = (explicit || process.env.VIEWER_FFMPEG || '').trim();
  if (pick) {
    const found = isBareCommand(pick) ? findExecutable([pick], []) : (isExecutableFile(pick) ? pick : null);
    if (!found) throw new Error(`找不到可执行的 ffmpeg：${pick}`);
    return found;
  }
  return findExecutable(['ffmpeg'], FFMPEG_EXTRAS) || 'ffmpeg';
}

export function resolveFfprobe(ffmpegPath, explicit) {
  const pick = (explicit || process.env.VIEWER_FFPROBE || '').trim();
  if (pick) {
    const found = isBareCommand(pick) ? findExecutable([pick], []) : (isExecutableFile(pick) ? pick : null);
    if (!found) throw new Error(`找不到可执行的 ffprobe：${pick}`);
    return found;
  }
  if (ffmpegPath && (ffmpegPath.includes(path.sep) || ffmpegPath.includes('/') || ffmpegPath.includes('\\'))) {
    const ext = /\.exe$/i.test(ffmpegPath) ? '.exe' : '';
    const sibling = path.join(path.dirname(ffmpegPath), 'ffprobe' + ext);
    if (isExecutableFile(sibling)) return sibling;
  }
  return findExecutable(['ffprobe'], FFPROBE_EXTRAS) || 'ffprobe';
}

export function resolveChromium(explicit, pw) {
  const pick = (explicit || process.env.VIEWER_CHROMIUM || '').trim();
  if (pick) {
    const found = isBareCommand(pick) ? findExecutable([pick], []) : (isExecutableFile(pick) ? pick : null);
    if (!found) throw new Error(`找不到可执行的浏览器：${pick}`);
    return found;
  }
  try {
    const p = pw?.chromium?.executablePath?.();
    if (isExecutableFile(p)) return p;
  } catch { /* ignore and fall back to system browsers */ }
  return findExecutable(
    ['chromium', 'chromium-browser', 'google-chrome-stable', 'google-chrome'],
    CHROMIUM_EXTRAS,
  ) || undefined;
}

export { resolveChromium as resolveBrowser };
