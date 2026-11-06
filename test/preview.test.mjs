// 本地测试 3：/paper2html/ 只读预览服务的路径安全 + 真实 HTTP 行为
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer, request as httpRequest } from 'node:http'
import { mkdtempSync, mkdirSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createHandler, lookupPreview, registerPreview, safeFile } from '../lib/preview.js'
import { exportsDir } from '../lib/python-run.js'

const tempRoot = mkdtempSync(join(tmpdir(), 'p2h-preview-'))
process.env.DSH_HOME = join(tempRoot, 'dsh')

const exportDir = exportsDir()
mkdirSync(join(exportDir, 'nested'), { recursive: true })
writeFileSync(join(exportDir, 'paper.html'), '<!DOCTYPE html><html><body><h1>Hello Paper</h1></body></html>')
writeFileSync(join(exportDir, 'nested', 'other.html'), '<html><body>nested</body></html>')
writeFileSync(join(exportDir, 'notes.txt'), 'not html')
writeFileSync(join(exportDir, '.hidden.html'), '<html></html>')
const outside = join(tempRoot, 'outside.html')
writeFileSync(outside, '<html><body>outside</body></html>')
symlinkSync(outside, join(exportDir, 'evil-link.html'))

function startServer() {
  const server = createServer(createHandler())
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }))
  })
}

test('safeFile：只允许目录内普通文件', () => {
  assert.ok(safeFile(exportDir, 'paper.html'), '正常文件应该放行')
  assert.ok(safeFile(exportDir, 'nested/other.html'), '子目录文件应该放行')
  assert.equal(safeFile(exportDir, '../outside.html'), null, '../ 必须拒绝')
  assert.equal(safeFile(exportDir, 'nested/../../outside.html'), null, '多级 ../ 必须拒绝')
  assert.equal(safeFile(exportDir, '.hidden.html'), null, '点文件必须拒绝')
  assert.ok(safeFile(exportDir, 'notes.txt'), 'safeFile 本身不判断扩展名（直链路由只放行 .html）')
  assert.equal(safeFile(exportDir, 'evil-link.html'), null, '指向目录外的软链必须拒绝')
  assert.equal(safeFile(exportDir, 'missing.html'), null, '不存在的文件返回 null')
  assert.equal(safeFile(join(tempRoot, 'not-a-dir'), 'x.html'), null, '目录不存在返回 null')
})

test('registerPreview / lookupPreview：登记后可查，id 稳定', () => {
  const file = join(exportDir, 'paper.html')
  const first = registerPreview({ file, title: 'Hello Paper', style: 'dark_lab', engine: 'local', pages: 3, bytes: 12345 })
  assert.match(first.previewPath, /^\/paper2html\/p\/[a-f0-9]{12}$/)
  assert.equal(lookupPreview(first.id)?.title, 'Hello Paper')
  const second = registerPreview({ file, title: 'Hello Paper v2' })
  assert.equal(second.id, first.id, '同一个文件重复登记应该复用 id')
  assert.equal(lookupPreview(first.id)?.title, 'Hello Paper v2')
  assert.equal(lookupPreview('../../etc/passwd'), null)
  assert.equal(lookupPreview('deadbeef0000'), null)
})

test('HTTP：首页 / 登记条目 / 导出目录直链 / 404 / 405', async () => {
  const { server, port } = await startServer()
  try {
    const file = join(exportDir, 'paper.html')
    const { id } = registerPreview({ file, title: 'Hello Paper', style: 'clean_paper', engine: 'local', pages: 3 })

    const index = await fetch(`http://127.0.0.1:${port}/paper2html/`)
    assert.equal(index.status, 200)
    assert.match(index.headers.get('content-type'), /text\/html/)
    const indexHtml = await index.text()
    assert.match(indexHtml, /Paper2HTML 预览/)
    assert.match(indexHtml, /Hello Paper/)

    const byId = await fetch(`http://127.0.0.1:${port}/paper2html/p/${id}`)
    assert.equal(byId.status, 200)
    assert.match(await byId.text(), /Hello Paper/)

    const direct = await fetch(`http://127.0.0.1:${port}/paper2html/paper.html`)
    assert.equal(direct.status, 200)
    assert.match(await direct.text(), /Hello Paper/)

    // 只允许 .html 直链
    const txt = await fetch(`http://127.0.0.1:${port}/paper2html/notes.txt`)
    assert.equal(txt.status, 404)

    const missing = await fetch(`http://127.0.0.1:${port}/paper2html/missing.html`)
    assert.equal(missing.status, 404)

    const post = await fetch(`http://127.0.0.1:${port}/paper2html/paper.html`, { method: 'POST' })
    assert.equal(post.status, 405)

    const badId = await fetch(`http://127.0.0.1:${port}/paper2html/p/../../etc/passwd`)
    assert.equal(badId.status, 404)

    const head = await fetch(`http://127.0.0.1:${port}/paper2html/paper.html`, { method: 'HEAD' })
    assert.equal(head.status, 200)
    assert.ok(Number(head.headers.get('content-length')) > 0)

    const exportsJson = await fetch(`http://127.0.0.1:${port}/paper2html/api/exports`)
    assert.equal(exportsJson.status, 200)
    const payload = await exportsJson.json()
    assert.ok(Array.isArray(payload.entries))
    assert.ok(payload.files.some((item) => item.name === 'paper.html'))
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
})

test('HTTP：原始 ../ 路径不会穿越到目录外', async () => {
  const { server, port } = await startServer()
  try {
    const response = await new Promise((resolve, reject) => {
      // http.request 直接发原始 path（fetch 会先规范化 ../，测不到 handler 的路径校验）
      const req = httpRequest({ host: '127.0.0.1', port, path: '/paper2html/../outside.html' })
      req.on('response', (res) => {
        const chunks = []
        res.on('data', (chunk) => chunks.push(chunk))
        res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString('utf8') }))
      })
      req.on('error', reject)
      req.end()
    })
    assert.equal(response.status, 404)
    assert.ok(!response.body.includes('outside'), '不应返回目录外文件内容')
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
})
