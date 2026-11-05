# 公开与发行的许可复核

2026-11-05；事实清单见 [dependencies.md](dependencies.md)。本文区分许可原文、FSF 解释与本仓推断；不代替权利人授权或适用法下的法律判断，未选择项目 LICENSE，也未改变仓库依赖政策。

**GPL 不禁止公开源码；但“只公开源码，所以只放 MIT/Apache 就够了”不成立。二进制发行也不是免交源码的办法。** 作者可对自己有权授权的独立代码采用 MIT/Apache-2.0；第三方授权仍保留，组合程序若落入 GPL 范围，还须满足 GPL。

## 为什么需要区分接入方式

许可原文：[GPLv3 §4–6](https://www.gnu.org/licenses/gpl-3.0.html#section4) 对原样源码、修改后的源码、非源码发行分别规定义务；§5 的独立作品集合（aggregate）不把其中所有作品都变成 GPL。因此源码分发本身可能受约束，是否带 `.so` 或可执行文件不是唯一判断点。

FSF 解释：[库链接与语言绑定](https://www.gnu.org/licenses/gpl-faq.html#IfLibraryIsGPL) 通常形成组合程序；[独立进程](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation) 要看通信机制和语义，不能仅凭进程不同就保证独立。它是许可作者的解释，不是“任何 import 在所有法域必然构成派生作品”的司法结论。

本仓推断：`chess`、`pyffish` 被规则层直接 import，尤其后者是同进程本机扩展，应认真按组合使用处理；Stockfish/Fairy-Stockfish/lc0 经可替换的 UCI 文本接口作为独立进程，更支持独立作品解释。把引擎装在同一压缩包/容器里可构成单纯集合，但不能因此免除引擎自己的发行义务。`cchess` 另有 LGPL 元数据与 GPL 源文件冲突，不能拿它作为已确认的弱 copyleft 示例。

## 场景与义务

| 行为 | 对当前项目的影响 |
|---|---|
| 私下运行、内部研究 | 普通 GPL 允许私用修改；“研究/非商业”不是对外分发的通用豁免。项目禁 GPL 是内部政策问题，不等于使用行为违法 |
| 只公开当前自有源码，第三方库由用户安装 | GPL 不一概阻止。独立自有部分可保留兼容许可；若构成 GPL 组合/派生作品，源码发布也要满足相应条件。未复制库不自动排除组合判断，不能宣传完整程序只有 MIT/Apache 条件 |
| 随包提供库、引擎二进制、wheel 或容器镜像 | 对包含的 GPL 部件履行许可证、版权及对应源码义务；属于组合程序时范围可能包括自有代码。集合中的独立程序仍各守自身许可 |
| 只在服务器运行，用户只收结果 | 普通 GPLv3 §0 不把无副本传递的网络交互当 convey；仅此通常不触发公开服务端源码义务。镜像交给客户、前端代码发送到浏览器则分别是分发问题 |
| 使用 AGPL 修改版提供网络服务 | [AGPLv3 §13](https://www.gnu.org/licenses/agpl-3.0.html#section13) 另要求向远程交互用户提供对应源码机会；不能把普通 GPL 的结论直接套过来。本轮核心依赖未发现 AGPL |

[GPLv3 §1、§6](https://www.gnu.org/licenses/gpl-3.0.html#section1) 的 Corresponding Source 是生成、安装、运行和修改所需源码及控制脚本（有系统库等例外），不是只给仓库主页或上游最新版本。网络下载可用 §6(d) 的配套源码下载方式；若源码在别处，发行者仍须确保符合条件、持续可用。二进制可单独下载，不代表可以完全不提供源码途径。[GPLv2 §3](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html#section3) 也有源码/书面要约等具体方式，不能随意跨版本套用。

普通 GPL 的动态链接并无普遍免责；[LGPLv3 §4](https://www.gnu.org/licenses/lgpl-3.0.html#section4) 才为应用保留不同许可提供条件，包括库的声明、许可文本、允许修改库和为调试修改而逆向，以及可替换/重新链接机制等。随包提供库仍须处理库源码义务；静态链接也不是绝对禁用，但不能只给不可重新链接的最终二进制。

## MIT、Apache 与下一步选择

[FSF 对兼容许可模块的解释](https://www.gnu.org/licenses/gpl-faq.html#GPLModuleLicense) 允许自有模块保留更宽松的兼容许可，同时组合整体按 GPL 发行。这不是 GPL 库被重新许可为 MIT。MIT 通常兼容 GPLv2/v3；[Apache 官方兼容说明](https://www.apache.org/licenses/GPL-compatibility.html) 明确 Apache-2.0 与 GPLv3 兼容，与 GPLv2 不兼容：GPL-2.0-only 不能直接升级解决，GPL-2.0-or-later 才可在授权范围内选 v3。当前明确的强 copyleft 核心库是 v3 系列，不应虚构 v2-only 冲突。

当前可行路径待维护者选择：

- 接受完整组合的 GPL 合规发布，同时让有权授权的自有模块保留 MIT/Apache；需明确范围、附齐文本与声明，并处理内部禁 GPL 政策。
- 若目标是完整发行物仅承担宽松许可条件，需替换直接依赖、取得额外授权，或在实际架构上建立经核实的独立边界；不能只改 LICENSE 或把 import 换成包装进程就宣告解决。
- 暂只发布明确独立的研究文字/阅读器材料，也要保留资源各自许可；并不自动解决后端未来发行问题。

前提已核实：实际 import/UCI 边界、版本元数据、vendored 声明；待验证：cchess 权利人对该版授权的澄清、Maia 权重的独立授权与来源、最终发行清单和构建、组合边界在适用法下的判断。最小下一步是决定“仅公开源码还是也分发可运行包，以及是否接受 GPL 组合条件”，再落实许可证与政策；不是立即删库或仅放一份 MIT 文本。
