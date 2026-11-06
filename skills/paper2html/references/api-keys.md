# API key 与云端能力（可选）

**默认不需要任何 key。** 下面这些是「想把解析质量/摘要拉满」时的可选项。

## 三条路径

| 路径 | 作用 | 需要 |
|---|---|---|
| 本地解析（默认） | PyMuPDF 抽标题/正文/图片 → 排版 | 无 |
| 云端解析（Doc2X / PDF2X） | 高保真 Markdown：公式、表格、扫描件 OCR | 对应平台的 API key |
| AI 理解层（DeepSeek） | TL;DR / 关键发现 / 章节摘要 / 结构化面板 | DeepSeek API key |

引擎为 `auto` 时的优先级：Doc2X → PDF2X → 本地（前两者无 key 或失败自动回退，不会阻塞转换）。

## 获取 key

| Key | 平台 | 用途 | 费用 |
|---|---|---|---|
| `DOC2X_APIKEY` | https://doc2x.noedgeai.com | PDF 解析（推荐） | 有免费额度，超出约 0.02 元/页 |
| `PDF2X_APIKEY` | https://pdf2x.cn | PDF 解析（备选） | 有免费额度 |
| `DEEPSEEK_APIKEY` | https://platform.deepseek.com | AI 摘要 | 极低成本 |

> key 由用户自己注册。**不要要求用户把 key 贴在对话里**，也不要写进插件代码或仓库。

## 配置方式（任选其一）

### 1. 环境变量（对 DSH 进程生效）

```bash
export DEEPSEEK_APIKEY="sk-..."
export DOC2X_APIKEY="sk-..."
export PDF2X_APIKEY="sk-..."
```

注意：GUI 里启动的 DSH 不一定继承终端环境变量；改完需要重启 DSH 才生效。更稳的是方式 2。

### 2. `$DSH_HOME/paper2html/config.json`（推荐）

```json
{
  "deepseekKey": "sk-...",
  "doc2xKey": "sk-...",
  "pdf2xKey": "sk-..."
}
```

也接受别名：`deepseekApiKey` / `llmKey`、`doc2xApiKey`、`pdf2xApiKey`；
可选 `deepseekBaseUrl`（默认 `https://api.deepseek.com/v1`）、`llmModel`（默认 `deepseek-chat`）。
这个文件由**用户自己**创建，插件只读不写。

## 行为说明

- 配了 DeepSeek key：`paper2html_convert({ understand: true })` 才会生成 AI 摘要；不传 `understand` 依旧不调用 LLM（省 token）。理解层用插件内置的标准库 HTTP 客户端调用 OpenAI 兼容接口，不需要额外安装 `openai` 包。
- 配了 Doc2X/PDF2X key：即使 `understand: false`，解析也会自动走云端（返回的 `engine` 会显示 `doc2x`/`pdf2x`），公式/表格质量更好。
- 想让某次强制走本地：在插件外手动跑 CLI `--engine local`（工具参数不暴露 engine，避免模型乱选）。
- key 无效/余额不足：`auto` 会回退本地并继续生成页面，`warnings` 里会有说明；显式 `--engine doc2x` 才直接报错。
