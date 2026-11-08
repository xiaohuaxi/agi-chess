// 跨平台可执行文件查找（ffmpeg / ffprobe / Chromium）：供 serve.mjs、record.mjs、shot.mjs 与 viewer/test/*.test.js 共用。
import { accessSync, constants, statSync } from 'node:fs';
import path from 'node:path';

function isExecutableFile(p) {
  if (!p) return false;
  try {
    accessSync(p, constants.X_OK);
    return statSync(p).isFile();
  } catch {
    return false;
  }
}

export function findExecutable(names, extraPaths = []) {
  const list = Array.isArray(names) ? names : [names];
  const dirs = (process.env.PATH || '').split(path.delimiter).filter(Boolean);
  for (const dir of dirs) {
    for (const name of list) {
      const candidate = path.join(dir, name);
      if (isExecutableFile(candidate)) return candidate;
    }
  }
  for (const candidate of extraPaths) {
    if (isExecutableFile(candidate)) return candidate;
  }
  return null;
}

export function resolveFfmpeg(explicit) {
  const pick = explicit || process.env.VIEWER_FFMPEG;
  if (pick) return pick;
  return findExecutable(['ffmpeg'], ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', '/usr/bin/ffmpeg']) || 'ffmpeg';
}

export function resolveFfprobe(ffmpegPath) {
  if (process.env.VIEWER_FFPROBE) return process.env.VIEWER_FFPROBE;
  if (ffmpegPath && ffmpegPath.includes(path.sep)) {
    const sibling = path.join(path.dirname(ffmpegPath), 'ffprobe');
    if (isExecutableFile(sibling)) return sibling;
  }
  return findExecutable(['ffprobe'], ['/opt/homebrew/bin/ffprobe', '/usr/local/bin/ffprobe', '/usr/bin/ffprobe']) || 'ffprobe';
}

export function resolveChromium(explicit, pw) {
  const pick = explicit || process.env.VIEWER_CHROMIUM;
  if (pick) return pick;
  try {
    const p = pw?.chromium?.executablePath?.();
    if (isExecutableFile(p)) return p;
  } catch { /* ignore and fall back to system browsers */ }
  return findExecutable(
    ['chromium', 'chromium-browser', 'google-chrome-stable', 'google-chrome'],
    [
      '/usr/bin/chromium',
      '/usr/bin/chromium-browser',
      '/usr/bin/google-chrome-stable',
      '/usr/bin/google-chrome',
      '/snap/bin/chromium',
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ],
  ) || undefined;
}
