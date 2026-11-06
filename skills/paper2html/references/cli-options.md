# 参数与命令行

## 工具 `paper2html_convert`

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `input` | string | ✅ | — | 本地 PDF 绝对路径，或 arXiv URL/ID |
| `outputDir` | string | — | `$DSH_HOME/paper2html/exports` | HTML 输出目录（绝对路径） |
| `style` | enum | — | `dark_lab` | `dark_lab` / `clean_paper` / `neon_tech` |
| `understand` | boolean | — | `false` | true 需要 DeepSeek key，否则报错并提示配置方式 |

返回：`htmlPath, title, style, engine(local|doc2x|pdf2x), pages, bytes, previewPath, previewUrl, understand, warnings`。

## 工具 `paper2html_status`

无参数。只读检查：Python 解释器 / 版本 / `pymupdf`、`markdown` 依赖、venv、三个 key 是否配置、导出目录与文件数量。

## 内置 Python CLI（排查或手动重转时用）

插件目录下的 `python/paper2html.py`，可独立运行：

```bash
cd <PLUGIN_ROOT>/python
python3 paper2html.py --input /abs/paper.pdf --output /tmp/paper.html --style clean_paper --no-understand
python3 paper2html.py --input https://arxiv.org/abs/1706.03762 --no-understand
python3 paper2html.py --input paper.pdf --engine local --no-understand
python3 paper2html.py --input paper.pdf --engine auto     # 有 key 先云端，否则本地
```

| CLI 参数 | 说明 |
|---|---|
| `--input, -i` | 必填：PDF 路径或 arXiv URL/ID |
| `--output, -o` | 输出 HTML 路径（缺省自动生成到 `$DSH_HOME/paper2html/exports/` 或 PDF 同目录） |
| `--style, -s` | `dark_lab`（默认）/ `clean_paper` / `neon_tech` |
| `--engine` | `auto`（默认）/ `local` / `doc2x` / `pdf2x` |
| `--no-understand` | 跳过 AI 理解层（无 key 时推荐） |
| `--no-images` | 本地解析不抽图片（HTML 更小） |
| `--api-key` / `--llm-api-key` / `--llm-base-url` / `--llm-model` | 覆盖环境变量 |
| `--debug` | 详细日志（stderr） |

成功时 stdout 最后一行是机器可读结果（插件靠它解析，手动排查时也可看）：

```
PAPER2HTML_RESULT_JSON:{"ok": true, "htmlPath": "...", "engine": "local", ...}
```

失败时输出 `PAPER2HTML_ERROR_JSON:{"ok": false, "error": "..."}` 并以非 0 退出。

## 环境变量

| 变量 | 用途 |
|---|---|
| `PAPER2HTML_PYTHON` | 指定 Python 解释器（跳过自动探测/venv） |
| `PAPER2HTML_CACHE_DIR` | arXiv PDF 缓存目录（默认 `$DSH_HOME/paper2html/cache`） |
| `DSH_HOME` | 数据根目录（默认 `~/.dsh`） |
| `DOC2X_APIKEY` / `PDF2X_APIKEY` / `DEEPSEEK_APIKEY` | 可选云端能力 key |

## 数据位置

```
$DSH_HOME/paper2html/
├── config.json           # 可选：{"deepseekKey": "...", "doc2xKey": "..."}（用户自己写）
├── venv/                 # 首次转换时懒建的 Python 环境
├── cache/                # arXiv PDF 缓存（可删）
├── exports/              # 默认导出目录（HTML + <name>_assets/images/）
└── preview-registry.json # /paper2html/ 预览服务的登记表
```
