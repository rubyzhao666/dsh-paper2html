# 常见错误与处理

## 1. `本地模式需要 Python` / `pip install` / `venv`

**原因**：本机没有 Python 3.9+，或没有 `pymupdf` / `markdown`，自动建 venv/装依赖失败（多为网络问题）。

**处理**（把命令原样给用户，不要让他贴 key）：
```bash
python3 -m venv ~/.dsh/paper2html/venv
~/.dsh/paper2html/venv/bin/pip install -r <PLUGIN_ROOT>/python/requirements-minimal.txt
```
或让用户用已有的 Python 装好依赖后：
```bash
export PAPER2HTML_PYTHON=/path/to/python3
```
本机若 `/usr/bin/python3` 已装 `pymupdf markdown`，插件会直接用它，不需要建 venv。

## 2. `这个 PDF 没有可提取的文本层，可能是扫描件`

本地模式不做 OCR。按优先级给用户建议：
1. 换 arXiv 版本（arXiv PDF 一定有文本层）；
2. 用 OCR 工具（OCRmyPDF、Adobe Acrobat）处理后再转；
3. 配置 `DOC2X_APIKEY`（支持扫描件 OCR）。

## 3. `arXiv 下载失败`

- 确认 ID 正确（形如 `1706.03762`）、论文公开；
- 检查网络是否可达 `arxiv.org` / `export.arxiv.org`；
- 用户可以直接下载 PDF 到本地，再用本地路径转换（更稳）。

## 4. `转换超时（超过 300 秒）`

- 大 PDF（>100 页 / 图多）在本地解析上偏慢；
- 建议：换 arXiv 版本、拆分 PDF、或先用系统 PDF 工具压缩；
- 换主题不会变快（解析才是瓶颈）。

## 5. `PDF 已加密`

本地解析无法读加密 PDF。先解密，或配置 Doc2X key（云端支持部分加密/扫描件）。

## 6. `understand=true 需要 DeepSeek key`

两种处理：保持 `understand: false`（默认、无 key 模式，页面照样完整）；或按
`references/api-keys.md` 配置 key 后重试。

## 7. 转换成功但页面「没有 AI 摘要 / TL;DR 是摘要原文」

正常：无 key 模式不做 AI 理解，TL;DR 卡片回退为论文 Abstract 原文，页面其余部分完整。
配置 DeepSeek key 并 `understand: true` 后会生成 TL;DR / 关键发现 / 章节摘要。

## 8. 公式/表格错乱

本地解析的能力边界（见 `references/local-parser.md`）。解决方案：配置 Doc2X/PDF2X key 重新转换。

## 9. 预览地址打不开

- `/paper2html/` 预览服务由插件在 DSH Web 进程内注册；确认插件已启用、DSH Web 正常；
- 预览路径形如 `/paper2html/p/<12位id>` 或 `/paper2html/<文件名>.html`；
- 文件被删除/移动后预览会 404，重新转换一次即可；
- 不想用预览时，直接双击/浏览器打开返回的 `htmlPath` 文件也能看。

## 10. 文件名/输出目录

默认输出到 `$DSH_HOME/paper2html/exports/<slug>-<style>.html`；同一篇、同一主题重复转换会覆盖同名文件（幂等）。
用户指定 `outputDir` 时必须给绝对路径。
