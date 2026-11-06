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
| DSH Web 预览 | 插件注册 `/paper2html/` 只读服务，转换完直接给预览链接 |
| 无 key 可跑 | 默认本地解析 + 不生成 AI 摘要；页面排版/目录/图片完整 |
| 有 key 更强 | DeepSeek → TL;DR/关键发现/章节摘要（内置标准库 HTTP 客户端，无需额外装 openai）；Doc2X/PDF2X → 高保真解析（含扫描件 OCR） |

## 安装

插件由 DeepSeek Harness 安装（`plugin_manager` 或本地目录安装）。安装后：

- 工具 `paper2html_convert`、`paper2html_status` 自动可用；
- skill `paper2html` 出现在 skill 列表；
- `/paper2html/` 预览路由自动注册。

**首次转换**会自动准备 Python 环境：优先使用本机已装好 `pymupdf` / `markdown` 的 Python；
没有时在 `~/.dsh/paper2html/venv` 懒建 venv 并联网安装最小依赖（约 50 MB，只装一次）。
自动安装失败会在报错里给出手动命令。

## 使用

对话里直接说：

- 「把 `/Users/me/Papers/attention.pdf` 转成网页」
- 「把 arXiv 1706.03762 做成可分享的阅读页，用浅色主题」
- 「这篇论文转成网页，要 AI 摘要」（需已配置 DeepSeek key）

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
└── preview-registry.json        # 预览服务登记表
```

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

## 许可与署名

MIT。上游 [paper2html](https://github.com/rubyzhao666/paper2html)（Copyright © 2026 paper2html Team，MIT）的
`paper2html.py`、`parsers/`、`understanding/`、`rendering/` 被复制进 `python/` 并按「无 key 可跑」改造；
本地解析器 `python/parsers/local_parser.py`、插件 Host 半边（`lib/`）、skill 为本次新增。
完整许可文本见 [LICENSE](./LICENSE)。
