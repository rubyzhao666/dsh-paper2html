// 本地测试 6：F3 页面批注/高亮 —— 注入标记 / DOM 契约 / 无外部引用 / 注入脚本语法 /
// docId 稳定性 / 三主题渲染。真实浏览器交互测试由 Lead 执行（本文件只做可静态验证部分）。
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { convertTool } from '../lib/tools.js'

const PLUGIN_ROOT = fileURLToPath(new URL('..', import.meta.url))
const tempRoot = mkdtempSync(join(tmpdir(), 'p2h-annotation-'))
process.env.DSH_HOME = join(tempRoot, 'dsh')

function findPython() {
  const candidates = [process.env.PAPER2HTML_PYTHON, '/opt/homebrew/bin/python3.11', '/usr/bin/python3', 'python3'].filter(Boolean)
  for (const python of candidates) {
    try {
      execFileSync(python, ['-c', 'import pymupdf'], { stdio: 'ignore', timeout: 20_000 })
      return python
    } catch {
      // 换下一个
    }
  }
  return ''
}

const python = findPython()
const skip = !python || process.env.PAPER2HTML_SKIP_E2E === '1'

function makeFixturePdf(name = 'annotation-fixture.pdf', extra = '') {
  const script = join(tempRoot, `make-${name}.py`)
  const pdf = join(tempRoot, name)
  writeFileSync(
    script,
    `import pymupdf
doc = pymupdf.open()
p = doc.new_page()
lines = [
    ("Annotation Fixture Paper", 20, 40),
    ("Alice Zhang, Bob Li, Carol Wang", 11, 28),
    ("Abstract", 13, 22),
    ("This paper exists only to test page annotations. The local parser should turn it into HTML. " * 3, 10, 14),
    ("1 Introduction", 13, 22),
    ("Readers can select sentences in the body and highlight them, then write a note. " * 4, 10, 14),
]
y = 80
for text, size, gap in lines:
    p.insert_text((72, y), text[:95], fontsize=size, fontname="helv")
    y += gap
${extra}
p2 = doc.new_page()
p2.insert_text((72, 80), "2 Method", fontsize=13, fontname="helv")
p2.insert_text((72, 110), "More body text for the second page, including the word annotation. " * 4, fontsize=10, fontname="helv")
doc.save("${pdf}")
`,
  )
  execFileSync(python, [script], { stdio: 'ignore', timeout: 60_000 })
  return pdf
}

function readMeta(html, name) {
  const match = html.match(new RegExp(`<meta name="${name}" content="([^"]*)"`))
  return match ? match[1] : ''
}

const ANNOTATION_SCRIPT_OPEN = '<script id="p2h-annotation-script">'
const EMBEDDED_JSON_OPEN = '<script type="application/json" id="p2h-annotations">'

function extractAnnotationScript(html) {
  const start = html.indexOf(ANNOTATION_SCRIPT_OPEN)
  assert.notEqual(start, -1, '缺少 <script id="p2h-annotation-script">')
  const bodyStart = start + ANNOTATION_SCRIPT_OPEN.length
  const end = html.indexOf('</script>', bodyStart)
  assert.notEqual(end, -1, '批注脚本没有结束标签')
  return { script: html.slice(bodyStart, end), start, end }
}

let sharedData = null
async function getData() {
  if (sharedData) return sharedData
  const pdf = makeFixturePdf()
  const outDir = join(tempRoot, 'out')
  const result = await convertTool.execute({ input: pdf, outputDir: outDir, style: 'dark_lab' })
  const html = readFileSync(result.htmlPath, 'utf8')
  sharedData = { pdf, outDir, result, html }
  return sharedData
}

test('F3 注入标记与 DOM 契约齐全', { skip, timeout: 180_000 }, async () => {
  const { html } = await getData()
  const markers = [
    '<style id="p2h-annotation-style">',
    ANNOTATION_SCRIPT_OPEN,
    'id="p2h-annotate-toggle"',
    'id="p2h-annotation-panel"',
    'id="p2h-annotation-list"',
    'id="p2h-export-annotated"',
    'id="p2h-clear-annotations"',
    'id="p2h-selection-toolbar"',
    'id="p2h-add-note"',
    'id="p2h-note-editor"',
    'id="p2h-note-input"',
    'id="p2h-note-save"',
    'id="p2h-note-cancel"',
    'id="p2h-share-banner"',
    'data-p2h-color="yellow"',
    'data-p2h-color="green"',
    'data-p2h-color="blue"',
    'data-p2h-color="pink"',
  ]
  for (const marker of markers) assert.ok(html.includes(marker), `缺少注入标记 ${marker}`)
  assert.ok(html.includes('mark.p2h-hl'), '缺少高亮样式 mark.p2h-hl')
  assert.ok(html.includes('p2h-annotations:'), '缺少 localStorage key 前缀 p2h-annotations:')
  assert.ok(html.includes('__P2H_ANNOTATIONS_READY__'), '缺少页面就绪标志')
  assert.ok(html.includes('-annotated.html'), '缺少导出文件名后缀 -annotated.html')
  assert.ok(html.includes('application/json'), '导出代码里应使用 application/json 内嵌批注')
})

test('F3 docId / 文件名 meta 正确且稳定', { skip, timeout: 180_000 }, async () => {
  const { pdf, outDir, result, html } = await getData()
  const docId = readMeta(html, 'p2h-doc-id')
  assert.ok(docId, '缺少 meta p2h-doc-id')
  assert.match(docId, /^pdf-[a-f0-9]{16}$/, `本地 PDF 的 docId 应该是内容 hash: ${docId}`)
  const fileName = readMeta(html, 'p2h-file-name')
  assert.equal(fileName, result.htmlPath.split('/').pop().replace(/\.html$/, ''))

  // 重转：docId 不变（批注不丢）
  const again = await convertTool.execute({ input: pdf, outputDir: join(tempRoot, 'out-again'), style: 'dark_lab' })
  assert.equal(readMeta(readFileSync(again.htmlPath, 'utf8'), 'p2h-doc-id'), docId, '同一文档重转 docId 应该保持一致')

  // 复制成不同文件名（内容相同）：docId 不变（按内容 hash，而不是路径）
  const copy = join(tempRoot, 'renamed-copy of fixture.pdf')
  copyFileSync(pdf, copy)
  const copied = await convertTool.execute({ input: copy, outputDir: join(tempRoot, 'out-copy'), style: 'dark_lab' })
  assert.equal(readMeta(readFileSync(copied.htmlPath, 'utf8'), 'p2h-doc-id'), docId, '改名/移动后 docId 应该保持一致')

  // 内容不同：docId 不同
  const otherPdf = makeFixturePdf(
    'other-fixture.pdf',
    'p.insert_text((72, 320), "Unique tail text for a different document. " * 3, fontsize=10, fontname="helv")',
  )
  const other = await convertTool.execute({ input: otherPdf, outputDir: outDir, style: 'dark_lab' })
  assert.notEqual(readMeta(readFileSync(other.htmlPath, 'utf8'), 'p2h-doc-id'), docId, '不同文档 docId 应该不同')
})

test('F3 注入脚本可被 node --check 解析，且无网络/外部依赖', { skip, timeout: 180_000 }, async () => {
  const { html } = await getData()
  const { script } = extractAnnotationScript(html)
  assert.ok(script.length > 5000, `批注脚本过短: ${script.length}`)
  const scriptFile = join(tempRoot, 'extracted-annotation-script.js')
  writeFileSync(scriptFile, script)
  execFileSync(process.execPath, ['--check', scriptFile], { stdio: 'pipe', timeout: 30_000 })

  for (const forbidden of ['http://', 'https://', 'fetch(', 'XMLHttpRequest', 'WebSocket', 'importScripts']) {
    assert.ok(!script.includes(forbidden), `批注脚本不应包含 ${forbidden}`)
  }
  assert.match(script, /IGNORE_SELECTOR/, '缺少忽略区域选择器')
  assert.ok(script.includes('.katex'), '忽略区域缺少 .katex')
  assert.ok(/[\s,'"]pre[\s,'"]/.test(script), '忽略区域缺少 pre')
  assert.ok(/[\s,'"]code[\s,'"]/.test(script), '忽略区域缺少 code')
  assert.ok(script.includes('localStorage'), '缺少 localStorage 持久化')
  assert.ok(script.includes('quote'), '缺少文本锚定 quote')
  assert.ok(script.includes('prefix') && script.includes('suffix'), '缺少 prefix/suffix 消歧')
  assert.ok(script.includes('application/json'), '导出缺少内嵌 JSON')
  assert.ok(script.includes('未找到原文位置'), '缺少定位失败提示（侧栏标记）')
  assert.ok(script.includes('分享版'), '缺少分享版提示')
})

test('F3 CSS 无外部资源引用（无 @import / http URL）', { skip, timeout: 180_000 }, async () => {
  const { html } = await getData()
  const open = '<style id="p2h-annotation-style">'
  const start = html.indexOf(open)
  const end = html.indexOf('</style>', start)
  assert.notEqual(start, -1)
  const css = html.slice(start + open.length, end)
  assert.ok(!css.includes('@import'), '批注 CSS 不应 @import 外部样式')
  assert.ok(!/url\(\s*['"]?https?:/i.test(css), '批注 CSS 不应引用外部 URL')
  assert.ok(css.includes('mark.p2h-hl'), '缺少高亮样式')
  assert.ok(css.includes('[data-p2h-color="green"]'), '缺少颜色样式 green')
})

test('F3 原始文件里没有真正的内嵌批注 JSON 元素（只有脚本源码里的字符串）', { skip, timeout: 180_000 }, async () => {
  const { html } = await getData()
  const { start, end } = extractAnnotationScript(html)
  const occurrence = html.indexOf(EMBEDDED_JSON_OPEN)
  if (occurrence !== -1) {
    // 唯一允许出现的位置：导出构造逻辑的 JS 字符串字面量（在批注脚本内部）
    assert.ok(occurrence > start && occurrence < end, '原始 HTML 不应包含内嵌批注 JSON 元素')
  }
  const dataAttr = '<script type="application/json"'
  let from = 0
  let count = 0
  while ((from = html.indexOf(dataAttr, from)) !== -1) {
    count += 1
    assert.ok(from > start && from < end, '原始 HTML 不应包含额外的 application/json script')
    from += 1
  }
  assert.ok(count <= 1, `application/json 字符串出现次数异常: ${count}`)
})

test('F3 三套主题都能生成且注入完整', { skip, timeout: 240_000 }, async () => {
  const { pdf, outDir } = await getData()
  for (const style of ['dark_lab', 'clean_paper', 'neon_tech']) {
    const result = await convertTool.execute({ input: pdf, outputDir: join(outDir, 'themes'), style })
    const html = readFileSync(result.htmlPath, 'utf8')
    assert.ok(html.includes(`reading-mode ${style}`), `${style}: body class 不正确`)
    assert.ok(html.includes('<style id="p2h-annotation-style">'), `${style}: 缺少批注样式注入`)
    assert.ok(html.includes(ANNOTATION_SCRIPT_OPEN), `${style}: 缺少批注脚本注入`)
    assert.ok(html.includes('id="p2h-annotate-toggle"'), `${style}: 缺少批注入口`)
    assert.ok(html.includes('id="p2h-share-banner"'), `${style}: 缺少分享提示条`)
    assert.ok(html.includes('__P2H_ANNOTATIONS_READY__'), `${style}: 缺少就绪标志`)
  }
})

test('F3 生成页面没有新增外部资源域名', { skip, timeout: 180_000 }, async () => {
  const { html } = await getData()
  const urls = [...html.matchAll(/(?:src|href)="(https?:\/\/[^"]+)"/g)].map((match) => match[1])
  const hosts = new Set(urls.map((url) => new URL(url).host).filter(Boolean))
  assert.ok(hosts.size > 0, '预期页面仍有上游的 CDN 资源（KaTeX/Mermaid）')
  for (const host of hosts) {
    assert.equal(host, 'cdn.jsdelivr.net', `页面引入了新的外部资源域名: ${host}`)
  }
})

test('F3 Python 源码语法全部通过（含 annotations.py）', { skip, timeout: 120_000 }, async () => {
  const checker = `
import ast, pathlib, sys
root = pathlib.Path(${JSON.stringify(join(PLUGIN_ROOT, 'python'))})
bad = []
for path in sorted(root.rglob('*.py')):
    try:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except SyntaxError as exc:
        bad.append('%s:%s %s' % (path, exc.lineno, exc.msg))
if bad:
    print('\\n'.join(bad))
    sys.exit(1)
print('ok', len(list(root.rglob('*.py'))), 'files')
`
  const out = execFileSync(python, ['-c', checker], { encoding: 'utf8', timeout: 60_000 })
  assert.match(out, /^ok \d+ files/)
  const annotationsFile = join(PLUGIN_ROOT, 'python', 'rendering', 'annotations.py')
  assert.ok(existsSync(annotationsFile), '缺少 python/rendering/annotations.py')
})
