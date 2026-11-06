# dsh-paper2html

> 把学术论文（本地 PDF 或 arXiv）一键变成**精美、可分享、可交互的 HTML 阅读页**。
> 基于 [rubyzhao666/paper2html](https://github.com/rubyzhao666/paper2html)（MIT）改造成 DeepSeek Harness 插件。

**不需要任何 API key**：内置本地解析引擎（PyMuPDF）负责抽标题/正文/图片，上游渲染层负责排版。
配置 DeepSeek key 后可选开启 AI 摘要；配置 Doc2X / PDF2X key 后可选高质量云端解析（公式、表格、扫描件）。

## 它给你什么

| 能力 | 说明 |
|---|---|
| 一条命令出页面 | 对话里说「把这篇论文转成网页」，模型调 `paper2html_convert` |
| 三套主题 | `dark_lab`（夜间）/ `clean_paper`（打印、分享）/ `neon_tech`（演示） |
| 交互阅读器 | 左侧目录、⌘K 搜索、速读/标准/精读三种阅读模式、阅读进度、锚点复制 |
| 公式与图表 | KaTeX 渲染公式（云端解析时最完整）、Mermaid 架构图、论文插图 base64 内嵌 |
| 单文件可分享 | 产物是一个 self-contained HTML，可直接发给别人、放进笔记、离线打开 |
| 页面内批注/高亮 | 生成页右下角「✍️ 批注」：划词高亮（4 色）或写批注，侧栏按文档顺序列出，刷新不丢 |
| 带批注导出分享 | 「导出带批注版」下载 `<原名>-annotated.html`，批注内嵌在文件里；对方打开即见，可继续批注并再次合并导出 |
| 批注同步 & agent 读取 | DSH Web 预览页（http）里做的批注自动同步到 Host（`$DSH_HOME/paper2html/annotations/`），agent 可用 `paper2html_annotations` 读取你的高亮/批注来总结或答疑 |
| 侧栏「Paper2HTML」论文库 | DSH Web 左侧栏出现「Paper2HTML」入口，点开是会自动适配明暗主题的论文库单页：顶栏统计（N 篇 · 共 M 批注）、搜索/主题筛选/排序、卡片网格（主题渐变条、页数/体积/时间/批注数）、打开阅读页 / 复制链接 / 复制文件路径，还能一键「转换新论文」 |
| DSH Web 预览 | 插件注册 `/paper2html/` 只读服务，转换完直接给预览链接 |
| 无 key 可跑 | 默认本地解析 + 不生成 AI 摘要；页面排版/目录/图片完整 |
| 有 key 更强 | DeepSeek → TL;DR/关键发现/章节摘要（内置标准库 HTTP 客户端，无需额外装 openai）；Doc2X/PDF2X → 高保真解析（含扫描件 OCR） |

## 安装

插件由 DeepSeek Harness 安装（`plugin_manager` 或本地目录安装）。安装后：

- 工具 `paper2html_convert`、`paper2html_status`、`paper2html_annotations` 自动可用；
- skill `paper2html` 出现在 skill 列表；
- `/paper2html/` 预览路由自动注册；
- DSH Web **左侧栏出现「Paper2HTML」入口**，点开即论文库单页（`/paper2html/`）。

> 左侧栏入口属于浏览器的 client 半边：安装或更新插件后需要**重启 DSH**（或重载 Web 界面）才会出现，重启前别的功能（工具/skill/预览路由）不受影响。

**首次转换**会自动准备 Python 环境：优先使用本机已装好 `pymupdf` / `markdown` 的 Python；
没有时在 `~/.dsh/paper2html/venv` 懒建 venv 并联网安装最小依赖（约 50 MB，只装一次）。
自动安装失败会在报错里给出手动命令。

## 使用

### 论文库（左侧栏入口）

DSH Web 左侧栏点 **Paper2HTML** 打开论文库单页（不用记任何命令）：

- **顶栏**：`N 篇 · 共 M 批注`；「＋ 转换新论文」会在新会话里填好提示词（补上 PDF 路径或 arXiv 链接即可）；「刷新」重新拉取。
- **工具栏**：搜索标题（按 `/` 聚焦）、按主题筛选（全部 / Dark Lab / Clean Paper / Neon Tech）、按时间或页数排序。
- **卡片**：顶部主题渐变条 + 标题 + 主题/页数/体积/生成时间/批注数；按钮：`打开阅读页`、`复制链接`、`复制文件路径`。
- 自动跟随 DSH 明暗主题（light 默认，dark 由 client 推送）；窗口变窄时卡片自动单列。
- 数据仍来自 `$DSH_HOME/paper2html/exports` 与本机批注 store，页面本身不发任何外网请求。

### 直接这样说（不用记工具名）

用户直接说人话就行，不用知道背后有什么工具；模型会自己判断该做什么。例如：

- 「这篇论文看着太累，帮我弄成网页」
- 「把这个 PDF 变成能看的网页」
- 「这页我想划线做笔记 / 我怎么在这篇上做批注」
- 「把我标过的部分总结一下 / 根据我的批注整理成笔记」
- 「怎么把带批注的版本发给同事」

> 只有 DSH Web 预览页打开的论文，批注才会同步给 agent；`file://` 打开的批注只在浏览器里（可以让用户把带批注版发回来）。

### 工具与参数（给开发者 / 排查用，用户不用记）

模型会调用：

```
paper2html_convert({
  input: "/abs/path/paper.pdf" | "https://arxiv.org/abs/1706.03762" | "1706.03762",
  outputDir?: "/abs/out/dir",         // 默认 $DSH_HOME/paper2html/exports
  style?: "dark_lab" | "clean_paper" | "neon_tech",
  understand?: false                   // true 需要 DeepSeek key
})
```

返回 `htmlPath`（文件）、`previewPath` / `previewUrl`（DSH Web 预览）、`title`、`engine`（`local|doc2x|pdf2x`）、
`pages`、`bytes`、`understand`、`warnings`。

### 预览与分享

- 预览：打开返回的 `previewUrl`（形如 `http://127.0.0.1:<端口>/paper2html/p/<id>`）；`/paper2html/` 首页列出所有转换过的论文。
- 分享：直接发送 `htmlPath` 那个 HTML 文件即可（图片已内嵌，单文件）。
- 公式/图表由 CDN 加载 KaTeX/Mermaid：联网打开渲染最完整，离线打开正文仍可读。

### 批注 / 高亮 / 带批注分享

生成页面右下角有「✍️ 批注」入口（纯前端，离线 `file://` 也能用）：

1. 选中正文文字（≥2 字）→ 浮出工具条：4 个颜色圆点 = 纯高亮；「写批注…」= 弹输入框写文字批注。
2. 点「✍️ 批注」打开侧栏：按文档顺序列出「颜色条 + 摘录 + 批注文字 + 所在章节」，点击条目会滚动定位并闪烁高亮；可删除单条或清空自己的批注。
3. 批注保存在浏览器 `localStorage`（key 为 `p2h-annotations:<docId>`）：刷新页面、重新打开同一文件都还在；同一篇论文重转（docId 相同）批注也不会丢。换浏览器 / 清站点数据会丢。
4. 点「导出带批注版」→ 下载 `<原文件名>-annotated.html`：批注 JSON 内嵌在文件里，并在打开时重渲染高亮。接收方打开会看到顶部「分享版：含 N 条批注」提示，可继续添加自己的批注；再次导出会把「内嵌 + 本地」合并去重。
5. 无批注时页面行为与旧版完全一致（不显示分享提示）；KaTeX 公式、`<pre>/<code>`、批注侧栏自身不可标注。
6. **同步（0.3.0）**：用 DSH Web 预览页（`http://127.0.0.1:<端口>/paper2html/…`）打开时，批注会在 400ms 防抖后
   同步到本机 Host 存储（`$DSH_HOME/paper2html/annotations/<docId>.json`），面板顶部显示「已同步到本机」；
   同步失败时显示「同步失败」并继续保存在本浏览器。`file://` 打开时不发任何同步请求，行为与旧版一致。
7. **让 agent 读批注（0.3.0）**：在对话里说「把我标的部分总结一下」/「我批注里有哪些问题」，模型会调用
   `paper2html_annotations` 读取 Host 侧同步的批注（无参数先列出有批注的文档；也可传 `docId` 或 HTML 绝对路径）。
   注意：只有 DSH Web 预览页的批注会同步；`file://` 页面批注只在浏览器本地，agent 读不到。

## 有没有 key 的差别

| | 无 key（默认） | 有 DeepSeek key | 有 Doc2X/PDF2X key |
|---|---|---|---|
| 解析 | 本地 PyMuPDF | 本地 PyMuPDF | 云端高保真（公式/表格/OCR） |
| 排版 / 主题 / 目录 / 图片 | ✅ | ✅ | ✅ |
| TL;DR / 关键发现 / 章节摘要 | ❌（Abstract 原文顶替） | ✅（`understand: true`） | 视配置 |
| 扫描件 | ❌ | ❌ | ✅ |

**配置方式**（不要把 key 贴在对话里）：

```bash
export DEEPSEEK_APIKEY="sk-..."
export DOC2X_APIKEY="sk-..."     # 或 PDF2X_APIKEY
```

或写入 `~/.dsh/paper2html/config.json`（更稳，GUI 启动也生效）：

```json
{
  "deepseekKey": "sk-...",
  "doc2xKey": "sk-..."
}
```

可选字段：`deepseekBaseUrl`（默认 `https://api.deepseek.com/v1`）、`llmModel`（默认 `deepseek-chat`）。
插件只读这个文件，不会自动写 key。

## 环境要求

- DeepSeek Harness `>=0.2.1-rc.2 <0.3.0`（Node 22.19+ / 24+）
- Python 3.9+（macOS 自带 `/usr/bin/python3` 即可；依赖自动安装）
- 可选：`PAPER2HTML_PYTHON=/path/to/python3` 指定解释器

## 数据位置

```
$DSH_HOME/paper2html/            # 默认 ~/.dsh/paper2html/
├── config.json                  # 可选，用户手工放 key
├── venv/                        # 首次转换时懒建的 Python 环境
├── cache/                       # arXiv PDF 缓存（可删）
├── exports/                     # 默认输出目录（HTML + 同名 _assets/ 图片目录）
├── annotations/                 # 0.3.0：从 DSH Web 预览页同步的批注（<docId>.json，≤500 条/≤512KB）
└── preview-registry.json        # 预览服务登记表
```

> 页面批注有两份：浏览器 localStorage（所有打开方式都有）+ Host 侧 JSON（仅 DSH Web 预览页会同步，agent 可读）。
> 需要带走/分享时用页面内的「导出带批注版」。

## 手动排查 / 开发

```bash
# 环境自检（工具 paper2html_status 的等价命令行版本）
node -e "import('./lib/tools.js').then(m => m.statusTool.execute({})).then(console.log)"

# 手动转换（跳过模型）
node scripts/smoke.mjs https://arxiv.org/abs/1706.03762 --style clean_paper

# 直接跑内置 Python CLI（高级排查）
python3 python/paper2html.py --input /abs/paper.pdf --style clean_paper --no-understand

# 本地测试
node --check lib/index.js
node --test test/*.test.mjs
npm pack --dry-run
```

## 已知限制

- 本地解析对公式、表格、复杂版式还原有限（详见 skill 的 `references/local-parser.md`）；要完美公式/表格请配 Doc2X/PDF2X key。
- 扫描件（无文本层）本地模式无法解析，需要 OCR 或云端解析。
- 双栏论文按左右栏启发式排序，极少数复杂版式可能串行。
- 论文插图上限：单篇 80 张、单张 ≤4 MB、总原始图 ≤20 MB（超出跳过并在 `warnings` 提示）。
- 预览路由只在 DSH Web 内生效；HTML 文件本身不依赖 DSH，可单独打开。
- 批注有两处存储：**当前浏览器**的 localStorage（所有打开方式）+ Host 侧 JSON（仅 DSH Web 预览页同步，供 agent 读取）。
  两者不互通：`file://` 里做的批注不会同步到 Host（agent 读不到，但同一浏览器刷新仍在）；分享批注仍用「导出带批注版」。
  同步上限单文档 500 条 / 512KB，超出时页面提示同步失败（本地仍保存）。
- 导出文件里的批注是只读内嵌内容（接收方新增的批注只存在其本机）。

## 许可与署名

MIT。上游 [paper2html](https://github.com/rubyzhao666/paper2html)（Copyright © 2026 paper2html Team，MIT）的
`paper2html.py`、`parsers/`、`understanding/`、`rendering/` 被复制进 `python/` 并按「无 key 可跑」改造；
本地解析器 `python/parsers/local_parser.py`、插件 Host 半边（`lib/`）、skill 为本次新增。
完整许可文本见 [LICENSE](./LICENSE)。
