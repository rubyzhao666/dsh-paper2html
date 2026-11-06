# dsh-paper2html

> Turn academic papers (local PDF or arXiv) into **polished, shareable, interactive HTML reading pages**.
> A DeepSeek Harness plugin adapted from [rubyzhao666/paper2html](https://github.com/rubyzhao666/paper2html) (MIT).

**No API key required**: a bundled local parser (PyMuPDF) extracts title/body/figures and the upstream
rendering layer lays the page out. A DeepSeek key enables optional AI summaries; Doc2X / PDF2X keys enable
optional high-fidelity cloud parsing (formulas, tables, scanned PDFs).

## What you get

| Capability | Details |
|---|---|
| One-call conversion | Ask in chat, the model calls `paper2html_convert` |
| Three themes | `dark_lab` (night reading) / `clean_paper` (print & share) / `neon_tech` (demos) |
| Interactive reader | sidebar TOC, ⌘K search, quick/standard/deep reading modes, progress bar, anchor copy |
| Math & figures | KaTeX math (best with cloud parsing), Mermaid diagrams, base64-embedded figures |
| Single shareable file | the output is one self-contained HTML — send it, archive it, open it offline |
| In-page annotations / highlights | "✍️ 批注" button in the corner: select text to highlight in 4 colors or write a note; sidebar lists notes in document order; survives reload |
| Export with annotations | "导出带批注版" downloads `<name>-annotated.html` with annotations embedded; recipients see them on open, can add their own, and re-export merged |
| DSH Web preview | plugin registers a read-only `/paper2html/` route and returns a preview link |
| Works without keys | local parsing + no AI summary by default; layout/TOC/figures are complete |
| Stronger with keys | DeepSeek → TL;DR / key findings / section summaries (built-in stdlib HTTP client, no extra openai install); Doc2X/PDF2X → high-fidelity parsing incl. OCR |

## Install

Install the plugin through DeepSeek Harness (`plugin_manager` or a local-directory install). Afterwards:

- tools `paper2html_convert` and `paper2html_status` are available;
- skill `paper2html` shows up in the skill list;
- the `/paper2html/` preview route is registered.

**First conversion** prepares Python automatically: it prefers a system Python that already has
`pymupdf` and `markdown`; otherwise it lazily creates `~/.dsh/paper2html/venv` and installs the minimal
requirements (about 50 MB, one-time). If installation fails, the error includes manual commands.

## Usage

Just say:

- “Convert `/Users/me/Papers/attention.pdf` into a web page”
- “Make arXiv 1706.03762 a shareable reading page, light theme”
- “Convert this paper and add an AI summary” (requires a configured DeepSeek key)

The model calls:

```
paper2html_convert({
  input: "/abs/path/paper.pdf" | "https://arxiv.org/abs/1706.03762" | "1706.03762",
  outputDir?: "/abs/out/dir",         // defaults to $DSH_HOME/paper2html/exports
  style?: "dark_lab" | "clean_paper" | "neon_tech",
  understand?: false                   // true requires a DeepSeek key
})
```

Returns `htmlPath`, `previewPath` / `previewUrl`, `title`, `engine` (`local|doc2x|pdf2x`), `pages`, `bytes`,
`understand`, `warnings`.

### Preview & sharing

- Preview: open the returned `previewUrl` (e.g. `http://127.0.0.1:<port>/paper2html/p/<id>`); the
  `/paper2html/` index lists every converted paper.
- Share: send the `htmlPath` HTML file itself (figures are embedded, it is a single file).
- KaTeX/Mermaid load from a CDN: online gives the fullest rendering, offline content is still readable.

### Annotations / highlights / annotated export

Generated pages have an "✍️ 批注" button in the bottom-right corner (pure frontend, works offline over `file://`):

1. Select body text (≥2 chars) → a toolbar appears: four color dots for plain highlights, "写批注…" opens a note editor.
2. Open the sidebar to see all annotations in document order (color bar + excerpt + note + section). Click an item to
   scroll to it and flash the highlight; delete single items or clear your own annotations.
3. Annotations live in the browser's `localStorage` (key `p2h-annotations:<docId>`), so they survive reloads and
   re-conversions of the same paper (same docId). They are per-browser: clearing site data or switching browsers loses them.
4. "导出带批注版" downloads `<original-name>-annotated.html` with the annotation JSON embedded and highlights
   re-rendered on open. Recipients see a "分享版：含 N 条批注" banner, can add their own notes, and re-exporting
   merges embedded + local annotations and dedupes them.
5. Pages without annotations behave exactly like the previous version (no share banner). KaTeX formulas,
   `<pre>/<code>` blocks and the annotation UI itself are not annotatable.

## With vs. without keys

| | No key (default) | DeepSeek key | Doc2X/PDF2X key |
|---|---|---|---|
| Parsing | local PyMuPDF | local PyMuPDF | high-fidelity cloud parsing (formulas/tables/OCR) |
| Layout / themes / TOC / figures | ✅ | ✅ | ✅ |
| TL;DR / key findings / section summaries | ❌ (abstract text instead) | ✅ (`understand: true`) | depends |
| Scanned PDFs | ❌ | ❌ | ✅ |

**Configuration** (never paste keys into chat):

```bash
export DEEPSEEK_APIKEY="sk-..."
export DOC2X_APIKEY="sk-..."     # or PDF2X_APIKEY
```

Or `~/.dsh/paper2html/config.json` (recommended; also works for GUI-launched DSH):

```json
{
  "deepseekKey": "sk-...",
  "doc2xKey": "sk-..."
}
```

Optional fields: `deepseekBaseUrl` (default `https://api.deepseek.com/v1`), `llmModel` (default `deepseek-chat`).
The plugin only reads this file and never writes keys.

## Requirements

- DeepSeek Harness `>=0.2.1-rc.2 <0.3.0` (Node 22.19+ / 24+)
- Python 3.9+ (macOS `/usr/bin/python3` is fine; dependencies auto-install)
- Optional: `PAPER2HTML_PYTHON=/path/to/python3` to pin the interpreter

## Data locations

```
$DSH_HOME/paper2html/            # default ~/.dsh/paper2html/
├── config.json                  # optional, user-managed keys
├── venv/                        # lazily created Python environment
├── cache/                       # arXiv PDF cache (safe to delete)
├── exports/                     # default output dir (HTML + <name>_assets/)
└── preview-registry.json        # preview route registry
```

> Annotations are not on disk: they live in the browser's localStorage; use the in-page "export annotated version"
> when you need to carry or share them.

## Manual checks / development

```bash
# environment self-check (CLI equivalent of the paper2html_status tool)
node -e "import('./lib/tools.js').then(m => m.statusTool.execute({})).then(console.log)"

# real conversion without the model
node scripts/smoke.mjs https://arxiv.org/abs/1706.03762 --style clean_paper

# run the bundled Python CLI directly (advanced debugging)
python3 python/paper2html.py --input /abs/paper.pdf --style clean_paper --no-understand

# local tests
node --check lib/index.js
node --test test/*.test.mjs
npm pack --dry-run
```

## Known limitations

- Local parsing restores math/tables/complex layouts only approximately (see the skill's
  `references/local-parser.md`); configure Doc2X/PDF2X for perfect formulas and tables.
- Scanned PDFs (no text layer) cannot be parsed locally — use OCR or cloud parsing.
- Two-column papers are ordered by a left/right-column heuristic; rare complex layouts may interleave.
- Figure limits: 80 figures per paper, 4 MB per figure, 20 MB total images (extras are skipped and reported in `warnings`).
- The preview route only exists inside DSH Web; the HTML file itself does not depend on DSH.
- Annotations are client-side only: they live in the current browser's localStorage; the only way to share them is
  the in-page "export annotated version". Embedded annotations in an exported file are read-only; notes added by a
  recipient stay on their machine.

## License & attribution

MIT. The upstream [paper2html](https://github.com/rubyzhao666/paper2html) (Copyright © 2026 paper2html Team, MIT)
`paper2html.py`, `parsers/`, `understanding/` and `rendering/` are copied into `python/` and adapted for
keyless operation. The local parser (`python/parsers/local_parser.py`), the plugin host half (`lib/`) and the
skill are new work for this plugin. See [LICENSE](./LICENSE).
