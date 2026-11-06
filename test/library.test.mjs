// 本地测试 11：0.5.0 论文库单页 + /api/exports 扩展（annotations 计数，损坏跳过）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createHandler, registerPreview } from '../lib/preview.js'
import { annotationFilePath, writeAnnotations } from '../lib/annotations-store.js'
import { exportsDir } from '../lib/python-run.js'

const tempRoot = mkdtempSync(join(tmpdir(), 'p2h-library-'))
process.env.DSH_HOME = join(tempRoot, 'dsh')

const exportDir = exportsDir()
mkdirSync(exportDir, { recursive: true })

const annotatedHtml = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="p2h-doc-id" content="arxiv-1706.03762">
<title>Attention Is All You Need</title></head><body><h1>Attention</h1></body></html>`
const plainHtml = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Plain Paper</title></head><body>plain</body></html>`

const annotatedFile = join(exportDir, '1706.03762-dark_lab.html')
const plainFile = join(exportDir, 'plain-clean_paper.html')
writeFileSync(annotatedFile, annotatedHtml)
writeFileSync(plainFile, plainHtml)

const annotatedEntry = registerPreview({
  file: annotatedFile,
  title: 'Attention Is All You Need',
  style: 'dark_lab',
  engine: 'local',
  pages: 15,
  bytes: Buffer.byteLength(annotatedHtml),
})
const plainEntry = registerPreview({
  file: plainFile,
  title: 'Plain Paper <script>alert(1)</script>',
  style: 'clean_paper',
  engine: 'local',
  pages: 2,
  bytes: Buffer.byteLength(plainHtml),
})

writeAnnotations('arxiv-1706.03762', [
  {
    id: 'p2h-a1',
    color: 'yellow',
    note: '第一条',
    quote: { exact: 'Attention', prefix: '', suffix: '' },
    sectionId: 'Abstract',
    createdAt: '2026-11-06T02:00:00.000Z',
  },
  {
    id: 'p2h-a2',
    color: 'blue',
    note: '第二条',
    quote: { exact: 'All You Need', prefix: '', suffix: '' },
    sectionId: 'Title',
    createdAt: '2026-11-06T02:01:00.000Z',
  },
])
// 损坏的批注 store：应该被跳过，不影响 API
mkdirSync(join(tempRoot, 'dsh', 'paper2html', 'annotations'), { recursive: true })
writeFileSync(annotationFilePath('pdf-corrupt'), '{broken json', 'utf8')

function startServer() {
  const server = createServer(createHandler())
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }))
  })
}

test('GET /paper2html/ 返回论文库单页（内联 CSS/JS、主题/动作桥、无外链）', async () => {
  const { server, port } = await startServer()
  try {
    const response = await fetch(`http://127.0.0.1:${port}/paper2html/`)
    assert.equal(response.status, 200)
    assert.match(response.headers.get('content-type'), /text\/html/)
    const html = await response.text()

    const markers = [
      'Paper2HTML',
      'id="paper-app"',
      'id="p2h-stat"',
      'id="p2h-convert"',
      'id="p2h-refresh"',
      'id="p2h-search"',
      'id="p2h-chips"',
      'id="p2h-sort"',
      'id="p2h-grid"',
      'id="p2h-empty"',
      'id="p2h-toast"',
      'data-theme="light"',
      'paper2html:ready',
      'paper2html:theme',
      'paper2html:start-session',
      'prefers-color-scheme',
      '打开阅读页',
      '复制链接',
      '复制文件路径',
      '转换新论文',
      '--bg: #f6f4ef',
      '--accent: #7c3aed',
      'grid-template-columns: repeat(auto-fill',
      '@media (max-width: 720px)',
      'skeleton',
      'toast',
    ]
    for (const marker of markers) {
      assert.ok(html.includes(marker), `论文库单页缺少标记：${marker}`)
    }
    // 前端渲染必须用 textContent，不允许把动态数据拼进 innerHTML
    assert.ok(html.includes('textContent'), '页面应使用 textContent 渲染动态文本')
    assert.ok(!/\.innerHTML\s*=/.test(html), '页面不应把动态内容写入 innerHTML')
    // 无外部资源 / 无 CDN（空状态里的 arxiv 示例文案不算资源引用）
    assert.ok(!/<script[^>]+src=/i.test(html), '不应有外部 script')
    assert.ok(!/<link[^>]+stylesheet/i.test(html), '不应有外部样式表')
    assert.ok(!/url\(\s*['"]?https?:/i.test(html), 'CSS 不应引用外部 URL')
    assert.ok(!/src=["']https?:/i.test(html), '不应有外部资源 src')
    assert.ok(!/fetch\(\s*['"]https?:/i.test(html), '页面不应 fetch 外部 URL')
    // 数据来源必须是同源 API
    assert.ok(html.includes("fetch(REPO_BASE + '/api/exports'") || html.includes('/api/exports'), '页面应从 /api/exports 取数')
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
})

test('GET /paper2html/index.html 与 HEAD 也返回论文库单页', async () => {
  const { server, port } = await startServer()
  try {
    const indexHtml = await fetch(`http://127.0.0.1:${port}/paper2html/index.html`).then((res) => res.text())
    assert.ok(indexHtml.includes('id="paper-app"'))
    const head = await fetch(`http://127.0.0.1:${port}/paper2html/`, { method: 'HEAD' })
    assert.equal(head.status, 200)
    assert.ok(Number(head.headers.get('content-length')) > 1000)
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
})

test('GET /api/exports：形状 + 每篇 annotations 计数 + 损坏 store 跳过', async () => {
  const { server, port } = await startServer()
  try {
    const response = await fetch(`http://127.0.0.1:${port}/paper2html/api/exports`)
    assert.equal(response.status, 200)
    const payload = await response.json()
    assert.ok(Array.isArray(payload.entries), 'entries 应该是数组')
    assert.equal(typeof payload.exportsDir, 'string')
    assert.ok(Array.isArray(payload.files), '保留 files 字段（向后兼容）')
    assert.equal(payload.entries.length, 2)

    const byId = Object.fromEntries(payload.entries.map((entry) => [entry.id, entry]))
    const annotated = byId[annotatedEntry.id]
    const plain = byId[plainEntry.id]
    assert.ok(annotated, '缺少带批注的条目')
    assert.ok(plain, '缺少普通条目')

    for (const entry of payload.entries) {
      for (const field of ['id', 'title', 'name', 'style', 'pages', 'bytes', 'updatedAt', 'file', 'annotations']) {
        assert.ok(entry[field] !== undefined, `条目缺少字段 ${field}`)
      }
      assert.equal(typeof entry.annotations, 'number')
      assert.ok(entry.annotations >= 0)
    }
    assert.equal(annotated.annotations, 2, '带批注论文应统计到 2 条')
    assert.equal(plain.annotations, 0, '没有 p2h-doc-id 的旧页面应计 0 条')
    assert.match(payload.exportsDir, /paper2html[/\\]exports$/)
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
})

test('旧路由行为不变：/p/<id> 200、批注 API 200、非 GET 405', async () => {
  const { server, port } = await startServer()
  try {
    const preview = await fetch(`http://127.0.0.1:${port}/paper2html/p/${annotatedEntry.id}`)
    assert.equal(preview.status, 200)
    assert.match(await preview.text(), /Attention Is All You Need/)

    const annotations = await fetch(`http://127.0.0.1:${port}/paper2html/api/annotations/arxiv-1706.03762`)
    assert.equal(annotations.status, 200)
    const payload = await annotations.json()
    assert.equal(payload.docId, 'arxiv-1706.03762')
    assert.equal(payload.annotations.length, 2)

    const post = await fetch(`http://127.0.0.1:${port}/paper2html/plain-clean_paper.html`, { method: 'POST' })
    assert.equal(post.status, 405)
    const missing = await fetch(`http://127.0.0.1:${port}/paper2html/p/deadbeef0000`)
    assert.equal(missing.status, 404)
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
})

test('单页静态资源不存在时仍可服务（library.html 已随包）', () => {
  const source = readFileSync(join(process.cwd(), 'lib', 'library.html'), 'utf8')
  assert.ok(source.length > 10000, 'library.html 应是非空单页')
  assert.ok(source.includes('<style>') && source.includes('<script>'), 'CSS/JS 应内联在页面里')
})
