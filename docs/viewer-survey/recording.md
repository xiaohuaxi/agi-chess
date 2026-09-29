# 棋谱播放录成社交平台视频：技术调研报告

日期 2026-09-29。本机：macOS 27.0（`sw_vers`；`sysctl kern.osversion` 显示 26A428）、Apple Silicon、两块 3840x2160 显示器（`system_profiler SPDisplaysDataType`）、Homebrew ffmpeg 9.0.2（有 libx264、libvpx、h264_videotoolbox）、node 24、Xcode 已装。

出处标记：【本机】= 本机命令或实验，实验目录 `exp/`；【源码】= 读 playwright-core 1.61.1 源码；其余为网址。标【未核实】的是没法在本机验证、只有二手来源或凭印象的内容。

---

## 一、结论先行

1. Playwright 自带 recordVideo 不适合发社交平台：输出固定是 VP8 webm、25fps、画质参数很低，而且**分辨率只等于 CSS 像素**，`deviceScaleFactor` 提高不会让视频变清晰（本机实测）。节奏还取决于当时机器负载。
2. 推荐方案：页面按「第 N 步 + 动画进度 t」确定性渲染，Playwright 逐帧截图（DSF 2 出 1080x1920 或 1920x1080），静止段只截一张、用 ffmpeg concat 给足时长，最后 libx264 编码。本机小实验跑通，两次渲染的每一帧逐字节一致。
3. 走子动画能保留：用 CSS transition/Web Animations，动画暂停后按时间逐帧 seek（`document.getAnimations()` 设 `currentTime`）。用 requestAnimationFrame 手写的动画不会被 seek，要改成 t 的纯函数。
4. timesnap/timecut 的 npm 最后发布是 2022-06，只改写 JS 时钟、不管 CSS 动画，不推荐；puppeteer-screen-recorder 底层仍是 CDP 实时截屏，和 Playwright 录屏同类限制。
5. 录桌面软件：屏幕录制权限要授给发起录制的进程（终端 / 宿主 app），每月一次「允许一个月」的确认在 macOS 15 起出现，本次查到的资料里没有 26/27 取消它的说法；自动点界面还要辅助功能权限；锁屏后录到黑帧、点击也送不到应用。全自动能做但脆弱，成本远高于网页方案。
6. 更值得考虑的是：不录桌面软件，直接拿棋谱走网页渲染。

---

## 二、A 网页录屏

### A1 Playwright recordVideo 实际质量

| 事实 | 出处 |
| --- | --- |
| 默认尺寸 = viewport 缩小到 800x800 以内；视频画面放在输出左上角，超出则缩小；视频在 context 关闭后才可用 | https://playwright.dev/docs/videos |
| 底层是 CDP `Page.startScreencast`，`format:"jpeg"`，quality 默认 90，`maxWidth/maxHeight` = 视频尺寸 | 【源码】coreBundle.js `startScreencast` / `_startScreencast` |
| 编码：喂 ffmpeg 的 mjpeg 管道，`-r 25 -c:v vp8 -qmin 0 -qmax 50 -crf 8 -deadline realtime -speed 8 -b:v 1M -threads 1`，输出只允许 `.webm`，帧率写死 25 | 【源码】`FfmpegVideoRecorder`（`fps = 25`） |
| 帧时间戳用 `frameSwapWallTime`（真实墙钟时间），即录的是实时播放，快慢受机器负载影响 | 【源码】`onFrame: writeFrame(frame.buffer, frame.frameSwapWallTime/1e3)` |
| 1.61 起还有 `page.screencast.start({path, size, quality, onFrame})`，`onFrame` 直接给 JPEG 帧，但仍是同一个 CDP 截屏通道 | 【源码】`types.d.ts` `interface Screencast` |

本机实验（`exp_video.js`，三种配置，页面切三步棋，每步等 1.5s）：

| 配置 | 输出 | 说明 |
| --- | --- | --- |
| viewport 1080x1920，DSF 1，size 1080x1920 | vp8，1080x1920，25fps，约 94KB / 4.4s | 尺寸对，但这是 CSS 1080 宽的布局，字和棋子相对偏小 |
| viewport 540x960，**DSF 2**，size 1080x1920 | vp8，1080x1920，25fps | **画面只占左上 540x960，其余是灰色填充**（见 `shots/rv_vid2.png`）。DSF 没起作用，帧仍是 CSS 像素大小 |
| viewport 540x960，DSF 2，不设 size | vp8，**450x800**，25fps | 按「缩到 800 以内」规则缩小 |

结论：recordVideo 的清晰度上限 = CSS 像素，想要 1080 宽就得把页面按 1080 CSS 宽排版（放弃 DSF 高清文字），而且是低码率 VP8 实时编码。平台一般还会再转码一遍，源头画质低会叠加变糟。这是「不适合发社交平台」的依据；平台具体的上传规格（码率、帧率）我没有查【未核实】。

**本机意外**：Playwright 缓存里自带的 ffmpeg（`~/Library/Caches/ms-playwright/ffmpeg-1011/ffmpeg-mac`）在本机跑不起来，直接执行被 SIGKILL（退出码 137）；`codesign -s -` 报 "main executable failed strict validation"；Playwright 报 `spawn Unknown system error -88`（errno 88 在 macOS 上一般指 Mach-O 格式不合法，来源 https://github.com/ship-studio/ship-studio/issues/967 等二手讨论）。多半是缓存文件损坏，重装可能能好，我没动缓存。实验时用 `PLAYWRIGHT_BROWSERS_PATH=$PWD/pwb`（里面把 ffmpeg-mac 符号链接到 Homebrew ffmpeg）绕过，编码参数与源码相同，所以上表尺寸和帧率结论有效，码率是 Homebrew 版 libvpx 的结果。【本机】

另外 playwright-core 1.61.1 要的 chromium 是 1228，缓存里只有 1208，实验用 `executablePath` 指向缓存的 1208（Chrome for Testing）。npm 上 playwright 最新是 1.63.0，Apache-2.0（`npm view`）。

### A2 方案对比

| 方案 | 机制 | 帧率/节奏 | 分辨率 | 动画 | 维护与许可 | 评价 |
| --- | --- | --- | --- | --- | --- | --- |
| Playwright recordVideo | CDP screencast + VP8 | 25fps、实时墙钟 | 只到 CSS 像素，DSF 无效（本机实测） | 保留，但实时、有掉帧 | Apache-2.0，活跃 | 调试够用，发布不够 |
| 直接用 CDP `Page.startScreencast` / `page.screencast.onFrame` | 同上，自己编码 | 仍是实时，只在画面变化时出帧 | 同上，JPEG | 同上 | 同上 | 能换 x264 编码，但没解决实时与 CSS 像素两个问题 |
| puppeteer-screen-recorder | CDP 原生 screencast，内部调 ffmpeg，可选 mp4/webm 等，默认 25fps | 实时 | 受 screencast 限制 | 保留（实时） | MIT；npm 最新 3.0.6，发布于 2024-10-27（`npm view`）；README 见 https://github.com/prasanaworld/puppeteer-screen-recorder | 没试；机制与上一行同类 |
| timesnap / timecut | 改写页面的 `Date`、`performance.now`、rAF、setTimeout 等做虚拟时间，逐帧截图，交给 ffmpeg | 可控（默认 60fps） | 支持 viewport 和 deviceScaleFactor | **只覆盖 JS 时钟和 video，CSS 动画/transition 不受控** | BSD-3-Clause；npm 最新 0.3.3，发布于 2022-06-27（`npm view`）；README 见 https://github.com/tungs/timesnap 、https://github.com/tungs/timecut | 没试；停更近四年、依赖 puppeteer，不推荐 |
| **逐帧截图 + ffmpeg（推荐）** | 页面自己提供 `renderStep(k)` 和动画时间 t，脚本逐帧截图 | 由脚本决定，绝对稳定 | DSF 任意，可直接出 1080x1920 / 1920x1080 | 通过 seek 动画保留 | Playwright Apache-2.0、ffmpeg 已在本机 | 本机实验通过 |

### A3 推荐做法与本机实验

做法要点：

1. 页面暴露确定性接口：`applyMove(k)` 切到第 k 步并触发动画（本实验用 CSS transition，Web Animations 同理）。
2. 每次走子：调 `applyMove(k)` 后 `document.getAnimations().forEach(a=>a.pause())`，再对 i=0..N 设 `a.currentTime = i*1000/FPS`，每设一次截一张。动画走完 `finish()`，截一张「静止帧」。
3. 静止段（每步之后的停顿）只截这一张，在 ffmpeg concat 列表里给 `duration`，不重复截图。
4. 截图前 `await document.fonts.ready`，避免字体没加载。
5. 尺寸：9:16 用 viewport 540x960 + DSF 2 → 1080x1920；16:9 用 viewport 960x540 + DSF 2 → 1920x1080。页面按宽高比切布局（本实验用 `@media (min-aspect-ratio:1/1)` 切竖版与横版）。想要更清晰的字，就保持 CSS 尺寸小、DSF 高。
6. 编码：`libx264 -crf 18 -preset slow -profile:v high yuv420p`，加 `-movflags +faststart`，颜色标签 bt709。平台有音频要求的话另行合成，我没查各平台要求【未核实】。
7. 注意：用 rAF 手写的动画、canvas 逐帧绘制、`setTimeout` 驱动的过渡不会被 `getAnimations` seek，要把动画写成 `render(t)` 的纯函数，由脚本传 t。

实验命令与结果（【本机】，目录 `exp/`，脚本 `exp_frames.js`，页面 `page.html`）：

```
cd exp
npm init -y && npm i playwright-core@1.61.1          # 本地装，没动系统
node exp_frames.js 1080 1920 fr_916                   # 9:16
node exp_frames.js 1920 1080 fr_169                   # 16:9
ffmpeg -y -f concat -safe 0 -i fr_916/list.txt \
  -vf "fps=30,scale=in_range=full:out_range=tv,format=yuv420p" \
  -c:v libx264 -preset slow -crf 18 -profile:v high -level 4.2 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 -movflags +faststart -an out_916.mp4
```

结果：

- 9:16：h264 High，yuv420p，1080x1920，30fps，268 帧，约 8.9s，94KB（本页面太简单，码率没参考意义）。16:9：1920x1080，同参数，89KB。
- 截图速度：61 张 1080x1920 PNG 约 3.9s（含启动浏览器），约 65ms/张。外推：200 步、每步 0.5s 动画（15 帧）+ 1 张静止帧，约 3400 张，约 4 分钟（外推，没实测）。
- 动画：抽 1.0s、1.3s、1.6s 三帧对比，兵在 e2、中途、e4 三个位置（`shots/anim_strip.png`），说明 seek 有效。
- 确定性：同一命令跑两遍，62 张帧的 md5 完全一致（`IDENTICAL_FRAMES`）。
- 小问题：计划时长 8.60s，实际 8.93s，concat 末尾多约 0.3s，正式做时用 `-t` 截断或把末帧时长显式算好。
- 没测的：timesnap/timecut/puppeteer-screen-recorder 都没装没跑，只看了 README 和 npm 元数据；没验证 Chromium 的虚拟时间/beginFrame 方案【未核实】。

---

## 三、B Mac 上录非 web 桌面软件

### B1 权限

- **屏幕录制（System Settings > Privacy & Security > Screen & System Audio Recording）**：TCC 按「负责进程」判断，不是父进程。从终端里跑 screencapture，授权对象是终端 app；若经 LaunchAgent、`exec` 包装等改变了责任进程，会变成 node 之类的二进制没授权而失败。出处：https://github.com/openclaw/openclaw/issues/14138（用户报告，二手）。
- macOS 26.1 起，无 bundle 的裸可执行文件申请录屏时仍会弹窗、授权后可用，但**不出现在设置列表里**；被终端或 VS Code 拉起时，列表里出现的是父 app。Apple DTS 称这像个 bug，建议做成 .app bundle。出处：https://developer.apple.com/forums/thread/807898 。另一篇讲 Tahoe 下裸二进制「不弹窗也不显示」（https://dev.to/sanjayajoseph/how-i-fixed-sunshine-screen-sharing-on-macos-tahoe-the-native-wrapper-method-558g ，个人博客），与前者有出入，以 Apple 论坛为准，本机没验证。
- **辅助功能（Accessibility）**：用程序去点别的 app 界面（AXUIElement、System Events、cliclick 等）需要给发起点击的 app 授权。出处：https://support.apple.com/guide/mac-help/allow-accessibility-apps-to-access-your-mac-mh43185/mac 。AppleScript 控制某个 app 另有「自动化」授权【未核实，凭印象】。
- **每月确认**：macOS 15（Sequoia）起，已授权屏幕录制的 app 会定期弹「XX 正请求绕过系统窗口选择器，直接访问你的屏幕和音频…」，按钮有「允许一个月」。测试版是每周，正式版改为每月，重启后不再重弹，没有「永久允许」。出处：https://www.macrumors.com/2024/08/15/macos-sequoia-screen-recording-app-permissions/ 、https://tidbits.com/2024/08/19/apple-reduces-excessive-sequoia-permission-requests-shifts-to-monthly/ 。用 ScreenCaptureKit 的 app 同样会弹（TidBITS 说开发者反馈新 API 也没免掉）。
- 绕过办法：一是把系统时间调远再批准（TidBITS https://tidbits.com/2024/09/23/how-to-avoid-sequoias-repetitive-screen-recording-permissions-prompts/ ），二是改 `ScreenCaptureApprovals.plist`（Jamf 社区帖 https://community.jamf.com/t5/jamf-pro/monthly-tccc-prompts-macos-v15/m-p/339150 ），三是受管设备用 Jamf 的 Restrictions 配置。这些都是改系统设置或数据库的动作，本次没做、也不建议由 agent 做。
- **macOS 26/27**：面板改名为「Screen & System Audio Recording」，有二手博客称 26 保留了定期确认（https://www.screenify.studio/blog/2026-04-23-macos-screen-recording-permissions ，博客，可信度一般，且它写的是 weekly）。macOS 27 的新声明式隐私模型不含屏幕录制，Accessibility 的 PPPC 授权在 27.0 移除（https://mdm.tools/blog/pppc-macos-27-still-needs-a-profile/ ，2026-07）。**「每月确认」在 26/27 是否改了频率，我没查到可靠说法。**
- 怎么查本机当前授权：TCC 数据库 `~/Library/Application Support/com.apple.TCC/TCC.db` 需要给终端完全磁盘访问才能读，`tccutil` 只能重置不能读。本次没读，没有本机授权现状。也没跑会弹窗的命令。

### B2 工具

| 工具 | 能力 | 限制 | 出处 |
| --- | --- | --- | --- |
| `screencapture` | `-v` 录屏、`-V 秒数` 定时、`-D 显示器号`（1 为主屏，2 为副屏…）、`-k` 显示点击、`-l 窗口号` 截单个窗口、`-g` 录音频 | man 页写明 `-l` 是「Captures the window with windowid」，`-v/-V` 是录屏；**`-v` 与 `-l` 能否组合成只录一个窗口，man 页没写，搜索结果里的用法是推断，没验证**；没跑，因为会触发录屏权限 | 【本机】`man screencapture` |
| `ffmpeg -f avfoundation` | `-list_devices true` 列设备，屏幕当视频设备用，可设 `capture_cursor`、`capture_mouse_clicks`、`framerate` | 文档没有单窗口捕获；只能整块显示器再自己 crop；没跑（枚举设备也可能触发提示） | https://ffmpeg.org/ffmpeg-devices.html#avfoundation |
| ScreenCaptureKit（自写或现成命令行） | 单窗口过滤 `desktopIndependentWindow`；窗口被遮挡或整个移到屏幕外，输出仍是完整内容；**窗口最小化则流暂停，恢复后继续**；输出尺寸基本固定，不随窗口缩放；帧率最高到源显示器刷新率；`minimumFrameInterval`、`width/height` 可配 | 需要屏幕录制权限，每月确认；要写 Swift（本机有 Xcode） | https://developer.apple.com/videos/play/wwdc2022/10155/ |
| capture-helper | 命令行，按窗口 ID/PID/应用名/标题录 mp4，默认最长边 720、最高 15fps，权限给终端或父 app | MIT，macOS 13+；本机没装没跑 | https://github.com/deeeed/capture-helper |
| macosrec | 命令行按 app 名或窗口 ID 录 gif/mov | GPL-3.0，按项目许可政策属于不能进出货产物的一类；只做本机工具是否可用请维护者定 | https://github.com/xenodium/macosrec |
| OBS | 「macOS Screen Capture」源，基于 ScreenCaptureKit，可选整屏、单窗口或某个 app 的全部窗口，macOS 13+ 可采音频 | 是图形界面软件；OBS 的 obs-websocket 可远程控制是我的印象【未核实】 | https://obsproject.com/kb/macos-screen-capture-source |

窗口和显示器状态：

- 被别的窗口挡住：ScreenCaptureKit 单窗口模式不受影响（上表 WWDC 出处）。`screencapture -l` 是否同样，未验证。
- 最小化：ScreenCaptureKit 流暂停。
- 锁屏：有第三方报告「锁屏时 ScreenCaptureKit 返回黑帧，辅助功能事件被送到 loginwindow 而不是用户应用」（https://github.com/trycua/cua/issues/1745 ，issue 描述，非 Apple 文档）。另一条二手搜索结果说 display 锁定或睡眠时 screencapture 报 "could not create image from display"，来源较弱。你全局规范里 Codex 的「Locked Use」条目也说明锁屏下操作 GUI 是要特殊处理的问题，与上面一致。
- 息屏/睡眠：录制可能中断（https://www.screenify.studio/blog/2026-04-23-screen-recording-stops-unexpectedly ，博客）。缓解可用系统自带的 `caffeinate -d` 阻止息屏，我没验证过本机上的效果。
- 多显示器：`screencapture -D` 选显示器，本机是两块 4K。窗口若在另一块屏上，ScreenCaptureKit 单窗口模式不受影响（WWDC 出处）。
- 分辨率：录出来的是窗口在屏幕上的像素（Retina 下是 2x 物理像素，ScreenCaptureKit 可配输出尺寸），要 1080x1920 竖屏需要后期裁剪、缩放，或调好窗口比例。

### B3 agent 能否全自动，与网页方案比较

流程：`open -a <App> <棋谱文件>`（软件能关联棋谱格式时）或界面点菜单加载 → 点击播放 → 开始录制 → 判断播完 → 停止 → 转码。

难点：

1. **权限没法全自动一次性解决**：屏幕录制与辅助功能都要用户在系统设置里手动授权一次；屏幕录制每月还会弹一次确认，没人点就会卡住或录到黑屏。这是必须事先跟用户约好的人工步骤。
2. **软件本身没有脚本接口时靠点界面**：菜单位置、文件对话框、弹窗（版本更新、广告、登录）都会让流程走偏，要靠辅助功能或图像识别，脆弱。
3. **判断播完**：没有事件可订阅，只能靠帧差、OCR 结局文字、或按手数×间隔估算时长，容易早停或多录。
4. **实时录制**：播放多快就录多久，遇到卡顿、弹窗就直接进了视频；没法像网页逐帧方案那样重来一遍得到同一结果。
5. **锁屏/息屏/被别的应用抢焦点**：要保证机器解锁、常亮、专用会话，跑的时候人不能用这台机器；若走 Computer Use 类工具，还有输入被物理键鼠打断的问题。
6. 画质：窗口大小和 UI 由软件决定，版式做不到自定义 9:16；且软件界面上的品牌、广告、水印可能带来版权和平台审核问题（这点是我的判断，没查规则）。

对比：

| 维度 | 网页逐帧方案 | 桌面软件录屏 |
| --- | --- | --- |
| 一次性人工步骤 | 无 | 授权两个权限，每月确认 |
| 可重复性 | 逐字节一致（实测） | 实时录，每次不同 |
| 画质/版式 | 任意尺寸和 DPI，9:16 直接排 | 受窗口和屏幕限制，需裁剪 |
| 时间 | 200 步约 4 分钟（外推） | 等于播放时长，且需要独占机器 |
| 判断结束 | 自己知道总步数 | 要靠识别 |
| 故障面 | 少 | 弹窗、焦点、锁屏、权限提示 |
| 开发代价 | 写页面渲染 + 一个脚本 | 写 Swift/命令行录制 + UI 自动化 + 结束判断，且每个软件单独适配 |

建议：只有确实需要那个桌面软件的界面本身时才录桌面软件；如果目的只是「把一盘棋讲成视频」，把棋谱喂给自家网页播放器，走 A3 的逐帧方案。

---

## 四、没做的事

- 没装系统级软件，没改系统设置，没动 Playwright 缓存；实验的 npm 包和符号链接都在 `exp/` 里。
- 没跑任何会触发屏幕录制/摄像头权限弹窗的命令（`screencapture -v/-l`、`ffmpeg avfoundation`、SCK 小工具）。
- 没测 timesnap、timecut、puppeteer-screen-recorder、OBS、capture-helper。
- 没验证各平台对上传视频的具体规格要求。

## 五、实验文件

- 页面：`exp/page.html`
- recordVideo 实验：`exp_video.js`，输出 `vid1/ vid2/ vid3/`
- 逐帧实验：`exp_frames.js`，帧在 `fr_916/ fr_169/`，成片 `out_916.mp4`、`out_169.mp4`
- 截图：`shots/`
