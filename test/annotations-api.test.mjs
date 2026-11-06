// 本地测试 8：批注同步 HTTP API（0.3.0 G3）—— 在本地 http server 上测真实 handler
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer, request as httpRequest } from 'node:http'
import { existsSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createHandler } from '../lib/preview.js'
import { annotationFilePath } from '../lib/annotations-store.js'

const tempRoot = mkdtempSync(join(tmpdir(), 'p2h-api-'))
process.env.DSH_HOME = join(tempRoot, 'dsh')

function startServer() {
  const server = createServer(createHandler())
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }))
  })
}

function rawRequest(port, { method = 'GET', path, headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const payload = body === undefined ? undefined : Buffer.from(body)
    const request = httpRequest(
      {
        host: '127.0.0.1',
        port,
        method,
        path,
        headers: {
          ...(payload ? { 'content-length': payload.length } : {}),
          ...headers,
        },
      },
      (response) => {
        const chunks = []
        response.on('data', (chunk) => chunks.push(chunk))
        response.on('end', () => {
          const text = Buffer.concat(chunks).toString('utf8')
          let json = null
          try {
            json = JSON.parse(text)
          } catch {
            json = null
          }
          resolve({ status: response.statusCode, headers: response.headers, text, json })
        })
      },
    )
    request.on('error', reject)
    if (payload) request.write(payload)
    request.end()
  })
}

function sampleAnnotation(overrides = {}) {
  return {
    id: 'p2h-api-1',
    color: 'green',
    note: 'API 测试批注',
    quote: { exact: 'Attention Is All You Need', prefix: '', suffix: '' },
    sectionId: 'Abstract',
    createdAt: '2026-11-06T02:00:00.000Z',
    ...overrides,
  }
}

test('GET 无记录 → 200 空数组', () => {
  return (async () => {
    const { server, port } = await startServer()
    try {
      const res = await rawRequest(port, { path: '/paper2html/api/annotations/arxiv-none' })
      assert.equal(res.status, 200)
      assert.deepEqual(res.json, { docId: 'arxiv-none', annotations: [], updatedAt: '' })
      assert.match(res.headers['content-type'], /application\/json/)
    } finally {
      await new Promise((resolve) => server.close(resolve))
    }
  })()
})

test('PUT 合法 → 200 且磁盘文件正确；GET 读回', () => {
  return (async () => {
    const { server, port } = await startServer()
    try {
      const docId = 'arxiv-1706.03762'
      const put = await rawRequest(port, {
        method: 'PUT',
        path: `/paper2html/api/annotations/${docId}`,
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ annotations: [sampleAnnotation()] }),
      })
      assert.equal(put.status, 200)
      assert.equal(put.json.ok, true)
      assert.equal(put.json.count, 1)
      assert.ok(put.json.updatedAt)
      const file = annotationFilePath(docId)
      assert.ok(existsSync(file))
      const disk = JSON.parse(readFileSync(file, 'utf8'))
      assert.equal(disk.version, 1)
      assert.equal(disk.annotations[0].id, 'p2h-api-1')

      const get = await rawRequest(port, { path: `/paper2html/api/annotations/${docId}` })
      assert.equal(get.status, 200)
      assert.equal(get.json.docId, docId)
      assert.equal(get.json.annotations.length, 1)
      assert.equal(get.json.annotations[0].note, 'API 测试批注')
      assert.equal(get.json.updatedAt, put.json.updatedAt)
    } finally {
      await new Promise((resolve) => server.close(resolve))
    }
  })()
})

test('PUT 非法 JSON / 结构错 / 字段错 → 400', () => {
  return (async () => {
    const { server, port } = await startServer()
    const url = '/paper2html/api/annotations/arxiv-bad'
    try {
      const badJson = await rawRequest(port, {
        method: 'PUT',
        path: url,
        headers: { 'content-type': 'application/json' },
        body: '{not-json',
      })
      assert.equal(badJson.status, 400)
      assert.match(badJson.json.error, /不是合法 JSON/)

      const badShape = await rawRequest(port, {
        method: 'PUT',
        path: url,
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ items: [] }),
      })
      assert.equal(badShape.status, 400)
      assert.match(badShape.json.error, /annotations/)

      const badItem = await rawRequest(port, {
        method: 'PUT',
        path: url,
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ annotations: [sampleAnnotation({ color: 'red' })] }),
      })
      assert.equal(badItem.status, 400)
      assert.match(badItem.json.error, /第 1 条批注字段不合法/)

      const badType = await rawRequest(port, {
        method: 'PUT',
        path: url,
        headers: { 'content-type': 'text/plain' },
        body: JSON.stringify({ annotations: [] }),
      })
      assert.equal(badType.status, 400)
      assert.match(badType.json.error, /Content-Type/)
    } finally {
      await new Promise((resolve) => server.close(resolve))
    }
  })()
})

test('PUT 过大 → 413（请求体 >512KB）', () => {
  return (async () => {
    const { server, port } = await startServer()
    try {
      const big = JSON.stringify({
        annotations: [{ ...sampleAnnotation(), note: 'x'.repeat(600 * 1024) }],
      })
      const res = await rawRequest(port, {
        method: 'PUT',
        path: '/paper2html/api/annotations/arxiv-huge',
        headers: { 'content-type': 'application/json' },
        body: big,
      })
      assert.equal(res.status, 413)
      assert.match(res.json.error, /512KB|过大/)
    } finally {
      await new Promise((resolve) => server.close(resolve))
    }
  })()
})

test('非 GET/PUT → 405；非法 docId / 路径穿越 → 400/404', () => {
  return (async () => {
    const { server, port } = await startServer()
    try {
      for (const method of ['POST', 'DELETE', 'PATCH']) {
        const res = await rawRequest(port, { method, path: '/paper2html/api/annotations/arxiv-x' })
        assert.equal(res.status, 405, `${method} 应该 405`)
        assert.match(String(res.headers.allow || ''), /GET/)
      }
      // WHATWG URL 会先把 %2e%2e 规范化成上级目录（→ 404）；无论 400/404 都必须是拒绝
      const badDoc = await rawRequest(port, { path: '/paper2html/api/annotations/%2e%2e' })
      assert.ok([400, 404].includes(badDoc.status), `%2e%2e 应被拒绝，实际 ${badDoc.status}`)

      const traversal = await rawRequest(port, { path: '/paper2html/api/annotations/..%2F..%2Fetc%2Fpasswd' })
      assert.equal(traversal.status, 404)

      const extraSegment = await rawRequest(port, { path: '/paper2html/api/annotations/a/b' })
      assert.equal(extraSegment.status, 404)
    } finally {
      await new Promise((resolve) => server.close(resolve))
    }
  })()
})

test('同源校验：跨域 Origin → 403；同源 Origin → 正常', () => {
  return (async () => {
    const { server, port } = await startServer()
    try {
      const evil = await rawRequest(port, {
        method: 'PUT',
        path: '/paper2html/api/annotations/arxiv-origin',
        headers: { 'content-type': 'application/json', origin: 'http://evil.example.com' },
        body: JSON.stringify({ annotations: [] }),
      })
      assert.equal(evil.status, 403)

      const nullOrigin = await rawRequest(port, {
        path: '/paper2html/api/annotations/arxiv-origin',
        headers: { origin: 'null' },
      })
      assert.equal(nullOrigin.status, 403)

      const same = await rawRequest(port, {
        method: 'PUT',
        path: '/paper2html/api/annotations/arxiv-origin',
        headers: { 'content-type': 'application/json', origin: `http://127.0.0.1:${port}` },
        body: JSON.stringify({ annotations: [sampleAnnotation({ id: 'origin-ok' })] }),
      })
      assert.equal(same.status, 200)
      assert.equal(same.json.count, 1)
    } finally {
      await new Promise((resolve) => server.close(resolve))
    }
  })()
})

test('静态文件行为不回归（API 分支不影响 /p/ 与直链）', () => {
  return (async () => {
    const { mkdirSync, writeFileSync } = await import('node:fs')
    const { server, port } = await startServer()
    try {
      const { exportsDir } = await import('../lib/python-run.js')
      mkdirSync(exportsDir(), { recursive: true })
      writeFileSync(join(exportsDir(), 'plain.html'), '<html><body>plain</body></html>')
      const res = await rawRequest(port, { path: '/paper2html/plain.html' })
      assert.equal(res.status, 200)
      assert.match(res.text, /plain/)
      const post = await rawRequest(port, { method: 'POST', path: '/paper2html/plain.html' })
      assert.equal(post.status, 405)
    } finally {
      await new Promise((resolve) => server.close(resolve))
    }
  })()
})
