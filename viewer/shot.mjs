// 第 3 步打样用：起一个绑本机的静态服务，无头打开 sample.html，两种棋各截一张 2 倍图。
// 用法：node viewer/shot.mjs <输出目录>
// 浏览器：playwright-core 锁在 1.58.2，默认用它配套的缓存 chromium-1208；
// 缓存里没有时用 VIEWER_CHROMIUM 指到任一 Chromium / Chrome 可执行文件。
import {chromium} from "playwright-core"
import {spawn} from "node:child_process"
import {mkdirSync} from "node:fs"
import {fileURLToPath} from "node:url"
import path from "node:path"

const out = process.argv[2]
if (!out) { console.error("usage: node viewer/shot.mjs <out-dir>"); process.exit(2) }
mkdirSync(out, {recursive: true})
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")

// 端口给 0 让系统挑空闲的，从服务的启动输出里读出实际端口
const server = spawn("python3", ["-u", "-m", "http.server", "--bind", "127.0.0.1", "0"],
  {cwd: root, stdio: ["ignore", "pipe", "pipe"]})
const port = await new Promise((ok, bad) => {
  const timer = setTimeout(() => bad(new Error("http.server did not start")), 5000)
  server.stdout.on("data", d => {
    const m = /port (\d+)/.exec(String(d))
    if (m) { clearTimeout(timer); ok(+m[1]) }
  })
  server.on("exit", code => bad(new Error(`http.server exited ${code}`)))
})

const browser = await chromium.launch({executablePath: process.env.VIEWER_CHROMIUM || undefined})
try {
  const ctx = await browser.newContext({viewport: {width: 540, height: 720}, deviceScaleFactor: 2})
  for (const game of ["chess", "xiangqi"]) {
    const page = await ctx.newPage()
    page.on("pageerror", e => console.error(game, "pageerror", e.message))
    await page.goto(`http://127.0.0.1:${port}/viewer/sample.html?game=${game}`)
    await page.evaluate(() => window.ready)
    const file = path.join(out, `sample-${game}.png`)
    await page.screenshot({path: file})
    console.log(file)
    await page.close()
  }
} finally {
  await browser.close()
  server.kill()
}
