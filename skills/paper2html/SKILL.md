---
name: paper2html
description: 把学术论文（PDF 或 arXiv）转成好看、可分享的网页阅读页，并支持页面内划线/高亮/批注、把带批注的版本发给同事、让 agent 读你的批注做总结。用户不用记任何工具名，直接说人话即可，例如：「这篇论文看着太累，帮我弄成网页」「把这个 PDF 变成能看的网页」「arXiv 这篇帮我转成阅读页」「这页我想划线做笔记」「我怎么在这篇上做批注」「把我标过的部分总结一下」「我在这篇上标注了哪些」「根据我的批注整理成笔记」「怎么把带批注的版本发给同事」。也可以说「论文转网页」「PDF 转 HTML」「论文排版」「可分享的阅读页」「做批注」「高亮」「记笔记」「总结我标的」「分享带批注的版本」时使用。（底层工具 paper2html_convert / paper2html_annotations 由我调用，用户不用记工具名。）
---

# Paper2HTML

把一篇论文变成**一份可以分享的交互式网页**：左侧目录 + 阅读模式切换 + 公式/图表渲染 + 三套主题。
文件是单个 self-contained HTML（图片 base64 内嵌），可以直接发给同事、放进笔记、离线打开；
在本机还能用 DSH Web 的 `/paper2html/` 预览服务直接看。

## 用户会怎么说（触发场景）

**用户不用记工具名，直接说人话，你负责翻译成工具调用。** 听到下面这些说法就按本 skill 工作：

- **转阅读页**：「这篇论文看着太累，帮我弄成网页」「把这个 PDF 变成能看的网页」「arXiv 这篇帮我转成阅读页」「帮我排成好读的页面」「能分享出去的论文网页」「这个 PDF 看起来太费劲」
- **批注 / 划线**：「这页我想划线做笔记」「我怎么在这篇上做批注」「想高亮重点」「帮我在这段加个笔记」
- **读批注**：「把我标过的部分总结一下」「我在这篇上标注了哪些」「根据我的批注整理成笔记」「我的批注里有哪些问题」
- **分享**：「怎么把带批注的版本发给同事」「把带批注的网页发我」「导出带批注的版本」

不确定用户是想转换还是只是问论文内容时，先用一句话确认（「要我把它转成可以批注的阅读页，还是直接讲内容？」）。
用户如果说出工具名，也照常按上面四种意图处理，不要要求用户记名字。

## 边界

- 只处理论文 PDF / arXiv；不负责 OCR（扫描件需要 OCR 或云端解析 key）。
- 工具只做「确定性重活」（下载、解析、排版、落盘）；**论文内容的讲解、摘要、翻译由你基于原文完成**。
- 默认无 key 可用（本地 PyMuPDF 解析 + 不生成 AI 摘要）；AI 摘要需要 DeepSeek key，属于可选项。
- 生成页面自带**页面内批注/高亮**（纯前端、离线可用）。用 DSH Web 预览页（`http://…/paper2html/…`）打开时，
  批注会同步到 Host 侧，你可以用 `paper2html_annotations` 读取（总结/答疑）；用 `file://` 直接打开时批注只存在
  浏览器 localStorage，你读不到，需要用户改用预览链接或导出带批注版。你始终**不能修改/删除**用户批注。

## 工作流

### 第 1 步：确认输入

- **本地 PDF**：必须拿到绝对路径（用户只给了文件名就先用 `working_directory` / 文件系统找到它）。
- **arXiv**：`https://arxiv.org/abs/1706.03762`、`https://arxiv.org/pdf/1706.03762`、纯 ID `1706.03762` 都可以。
- 用户没有指明论文时，先问清楚是哪一篇，不要猜。

### 第 2 步：调用 `paper2html_convert`

```
paper2html_convert({ input: "<绝对路径或 arXiv URL/ID>", style?: "dark_lab" })
```

- `style` 不给就用 `dark_lab`；用户说「打印/分享用浅色」→ `clean_paper`，说「科技感/深紫」→ `neon_tech`。
- `outputDir` 只有用户明确要求存到工作区某目录时才传（必须是绝对路径）。
- `understand` 默认 false。**不要**默认打开；只有用户明确说「要 AI 摘要」且本机配了 DeepSeek key 时才传 true。
- 转换通常 10–60 秒（首次可能需要装 Python 依赖，会慢一些）；超时是 300 秒。

### 第 3 步：把结果告诉用户（这是交付的核心）

从工具返回里拿：
- `htmlPath`：HTML 文件路径（单文件，可直接分享）
- `previewUrl`（或 `previewPath`）：DSH Web 里可直接打开的预览地址
- `title` / `style` / `engine` / `pages` / `bytes`

回复模板：

> 已生成《<title>》的阅读页（<style> 主题，<pages> 页，<X> MB）：
> - 预览：<previewUrl>
> - 文件：`<htmlPath>`（单文件，可直接发给别人）
>
> 页面右下角有「✍️ 批注」：选中正文可高亮/写批注；「导出带批注版」会把批注内嵌进文件发给别人。
>
> 如需换主题（dark_lab / clean_paper / neon_tech）或加 AI 摘要（需 DeepSeek key），告诉我即可。

### 第 4 步：用户问起批注时

页面批注是生成页面自带的能力，不需要调用任何工具。用户常见的三个问题：

- 「怎么批注？」→ 选中正文（≥2 字）会浮出工具条：4 个颜色圆点是纯高亮，「写批注…」可以写文字；
  右下角「✍️ 批注」打开侧栏，按文档顺序看/定位/删除。
- 「我标的东西会丢吗？」→ 存在**当前浏览器**的 localStorage（key `p2h-annotations:<docId>`），刷新、
  重开同一文件、同一论文重转都不会丢；换浏览器/清站点数据会丢。
- 「怎么把我标的发给同事？」→ 打开侧栏点「导出带批注版」，得到 `<原文件名>-annotated.html`；对方打开
  即见高亮和顶部「分享版：含 N 条批注」提示，还能继续加批注，再次导出会合并去重。
- 查批注内容：**调用 `paper2html_annotations`**。无参数先列本机有批注的文档，再传 `docId` 或 `htmlPath`
  读具体批注（颜色/摘录/批注文字/章节）。详细工作流见 `references/annotations.md`。
- 注意：只有 **DSH Web 预览页**打开的论文会同步到 Host；`file://` 打开的页面批注只在用户浏览器里。
  工具读不到时说明原因并给替代方案（改用预览链接 / 导出带批注版）。

### 第 5 步：按需讲解论文

- 用户接着问论文内容时，**直接基于你已经读到的正文回答**；需要细节再用 `pdf` skill / `read` 工具读 PDF 或 HTML，不要把整篇 HTML 塞回对话。
- 工具返回的 `engine` 说明解析方式：`local` = 本机 PyMuPDF；`doc2x` / `pdf2x` = 云端解析（用户配了 key）。
- 本地解析的公式/表格还原有限（见 `references/local-parser.md`）；用户抱怨公式或表格错乱时，建议配置 Doc2X/PDF2X key 后重转。

## 三种主题

| 主题 | 风格 | 适用 |
|---|---|---|
| `dark_lab`（默认） | 深色背景 + 绿色强调 | 夜间阅读、自己看 |
| `clean_paper` | 白底 + 学术蓝 | 打印、正式分享、嵌入笔记 |
| `neon_tech` | 深紫 + 霓虹 | 演示、科技感展示 |

详见 `references/style-presets.md`。

## 有没有 key 的差别

| 能力 | 无 key（默认） | 有 DeepSeek key | 有 Doc2X/PDF2X key |
|---|---|---|---|
| 解析 | 本地 PyMuPDF | 同左 | 云端高保真解析（公式/表格/版式更好） |
| 排版/主题/目录/图片 | ✅ | ✅ | ✅ |
| TL;DR / 关键发现 / 章节摘要 | ❌（页面仍完整可读） | ✅ | 取决于是否配 |
| 扫描件 OCR | ❌ | ❌ | ✅ |

- 配置方式（**不要让用户把 key 贴在对话里**）：环境变量 `DEEPSEEK_APIKEY` / `DOC2X_APIKEY` / `PDF2X_APIKEY`，
  或写入 `$DSH_HOME/paper2html/config.json`：
  ```json
  { "deepseekKey": "sk-...", "doc2xKey": "sk-..." }
  ```
- 用户问「为什么没有 AI 摘要」→ 解释默认无 key 模式；按上面方式配置后重跑并带上 `understand: true`。
- 配置细节见 `references/api-keys.md`。

## 失败兜底

| 工具报错关键词 | 你该做什么 |
|---|---|
| `需要 Python` / `pip install` / `venv` | 把报错里的手动命令原样给用户；或让用户装好 `pymupdf markdown` 后设 `PAPER2HTML_PYTHON` |
| `扫描件` / `没有可提取的文本层` | 说明本地模式不支持 OCR；建议换 arXiv 版本、先用 OCR 工具处理，或配置 Doc2X key |
| `arXiv 下载失败` | 检查 ID/网络，换 `https://export.arxiv.org/abs/<id>` 重试 |
| `超时` | 建议先换 `clean_paper` 不是解法；应拆分/压缩 PDF，或改用 arXiv 版 |
| `PDF 已加密` | 让用户解密后再转，或配 Doc2X key |
| `understand=true 需要 DeepSeek key` | 改回 `understand: false`，或引导用户配置 key |

不要把原始报错直接甩给用户：先翻译成「发生了什么 + 下一步怎么做」。
详见 `references/troubleshooting.md`。

## 交付前自查

- [ ] 工具返回的 `htmlPath` 文件存在，且 `title` 不是 `Untitled Paper`（是的话说明 PDF 元数据怪，可提醒用户）
- [ ] 回复里同时给了 **预览地址** 和 **文件路径**
- [ ] 没有把大段正文塞进工具参数/返回；讲解内容在对话里写
- [ ] 用户没要求时没有打开 `understand`，也没有让用户贴 key
- [ ] 提到批注时说明了「http 预览会同步、file:// 只在本地；导出带批注版才能分享」，没有声称能修改用户批注
- [ ] 用户问批注内容时调用 `paper2html_annotations`；无参数先列文档，读不到时给出可操作说明
- [ ] 提到数据位置时用 `$DSH_HOME/paper2html/`（默认 `~/.dsh/paper2html/`）

## references

- `references/local-parser.md` —— 本地解析的能力边界（公式/表格/双栏/扫描件），以及什么时候该建议用云端解析
- `references/style-presets.md` —— 三套主题的视觉细节与选择建议
- `references/cli-options.md` —— 工具参数 + 内置 Python CLI 参数（高级排查/手动重转用）
- `references/api-keys.md` —— DeepSeek / Doc2X / PDF2X key 从哪来、怎么配、云端解析与理解层的行为
- `references/troubleshooting.md` —— 常见错误与处理
- `references/annotations.md` —— **读取用户批注**（0.3.0）：`paper2html_annotations` 工作流、http 预览同步 vs file:// 本地、上限与隐私边界
