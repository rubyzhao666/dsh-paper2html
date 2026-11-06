// /paper2html/ 预览服务 + 导出登记表 + 批注同步 API（0.3.0 G3）。
// - 静态文件：只读 GET/HEAD；只服务 .html；只允许导出目录内文件（拒绝 ..、点文件、目录外软链）
// - 批注 API：GET/PUT /paper2html/api/annotations/<docId>（同源校验、400/405/413、路径穿越拒绝）
// - 用户指定了导出目录时，用登记表按 id 服务那一个具体文件
import { closeSync, createReadStream, existsSync, mkdirSync, openSync, readFileSync, readSync, realpathSync, renameSync, statSync, writeFileSync } from 'node:fs'
import { extname, join, normalize, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  AnnotationStoreError,
  MAX_STORE_BYTES,
  extractDocIdFromHtml,
  isValidDocId,
  listDocuments,
  readAnnotations,
  writeAnnotations,
} from './annotations-store.js'
import { exportsDir, hashOf, listExports, registryFile } from './python-run.js'

const ROOT = fileURLToPath(new URL('..', import.meta.url))

export const BASE = '/paper2html'
const MAX_ENTRIES = 500

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.htm': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.woff2': 'font/woff2',
}

function ensureDataDir() {
  try {
    mkdirSync(join(exportsDir(), '..'), { recursive: true })
  } catch {
    // 目录创建失败留给后续写文件报错
  }
}

function readRegistry() {
  try {
    const parsed = JSON.parse(readFileSync(registryFile(), 'utf8'))
    if (parsed && typeof parsed === 'object' && parsed.entries && typeof parsed.entries === 'object') {
      return parsed.entries
    }
  } catch {
    // 没有登记表或已损坏
  }
  return {}
}

function writeRegistry(entries) {
  const keys = Object.keys(entries)
  const trimmed = {}
  // 只保留最近的 N 条，避免登记表无限增长
  for (const key of keys.slice(-MAX_ENTRIES)) trimmed[key] = entries[key]
  ensureDataDir()
  const file = registryFile()
  const tmp = `${file}.${process.pid}.tmp`
  writeFileSync(tmp, `${JSON.stringify({ entries: trimmed }, null, 2)}\n`)
  renameSync(tmp, file)
}

/** 登记一次导出，返回 { id, previewPath }。同一文件重复转换会复用同一个 id（更新元信息）。 */
export function registerPreview({ file, title = '', style = '', engine = '', pages = 0, bytes = 0 }) {
  const id = hashOf(file)
  const entries = readRegistry()
  entries[id] = {
    id,
    file,
    name: file.split(/[\\/]/).pop() || file,
    title: String(title || ''),
    style: String(style || ''),
    engine: String(engine || ''),
    pages: Number(pages) || 0,
    bytes: Number(bytes) || 0,
    updatedAt: new Date().toISOString(),
  }
  writeRegistry(entries)
  return { id, previewPath: `${BASE}/p/${id}` }
}

export function lookupPreview(id) {
  if (!/^[a-f0-9]{12}$/.test(String(id || ''))) return null
  const entry = readRegistry()[id]
  return entry || null
}

/** 只在 dir 里面找文件：拒绝 ..、点文件和目录外的符号链接。 */
export function safeFile(dir, rel) {
  if (!dir || !rel) return null
  const parts = String(rel).split('/')
  if (parts.some((part) => !part || part === '.' || part === '..' || part.startsWith('.'))) return null
  let base
  try {
    base = realpathSync(dir)
  } catch {
    return null
  }
  const file = normalize(join(base, rel))
  if (!file.startsWith(base + sep) || !existsSync(file)) return null
  let real
  try {
    real = realpathSync(file)
  } catch {
    return null
  }
  if (!real.startsWith(base + sep)) return null
  try {
    if (!statSync(real).isFile()) return null
  } catch {
    return null
  }
  return real
}

function send(res, status, headers, body) {
  const payload = body === undefined || body === null ? '' : String(body)
  const finalHeaders = { ...(headers || {}) }
  if (finalHeaders['content-length'] === undefined) {
    finalHeaders['content-length'] = Buffer.byteLength(payload, 'utf8')
  }
  res.writeHead(status, finalHeaders)
  const method = res.req && res.req.method ? String(res.req.method).toUpperCase() : 'GET'
  if (method === 'HEAD') return res.end()
  res.end(payload)
}

function notFound(res, message = 'Not found') {
  send(res, 404, { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' }, message)
}

function serveFile(req, res, file) {
  const type = MIME[extname(file).toLowerCase()] || 'application/octet-stream'
  let stat
  try {
    stat = statSync(file)
  } catch {
    return notFound(res)
  }
  res.writeHead(200, {
    'content-type': type,
    'content-length': stat.size,
    'cache-control': 'no-cache',
    'x-content-type-options': 'nosniff',
  })
  if (req.method === 'HEAD') return res.end()
  createReadStream(file).pipe(res)
}

let libraryHtmlCache = null

/** 论文库单页应用（内联 CSS/JS，无前端构建、无外链；数据走 /api/exports）。 */
function libraryHtml() {
  if (libraryHtmlCache !== null) return libraryHtmlCache
  try {
    libraryHtmlCache = readFileSync(join(ROOT, 'lib', 'library.html'), 'utf8')
  } catch (error) {
    libraryHtmlCache =
      '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>Paper2HTML 论文库</title></head>' +
      '<body style="font:14px -apple-system,sans-serif;padding:30px;color:#1c1a17;background:#f6f4ef">' +
      '<h1>Paper2HTML</h1><p>论文库页面文件缺失（lib/library.html），请重新安装插件。</p></body></html>'
  }
  return libraryHtmlCache
}

/** 只读 HTML 头部，拿 p2h-doc-id（用于批注计数，避免整篇大文件读入）。 */
function readDocIdFromFileHead(file) {
  try {
    const fd = openSync(file, 'r')
    try {
      const buffer = Buffer.alloc(32768)
      const read = readSync(fd, buffer, 0, buffer.length, 0)
      return extractDocIdFromHtml(buffer.subarray(0, read).toString('utf8'))
    } finally {
      closeSync(fd)
    }
  } catch {
    return ''
  }
}

/** /api/exports 的返回：登记表条目 + 每篇批注数（读 annotations store，损坏跳过）。 */
function buildExportsPayload() {
  const counts = new Map()
  try {
    for (const document of listDocuments()) counts.set(document.docId, document.count)
  } catch {
    // store 损坏时整体容错：批注计数全部为 0，不影响论文列表
  }
  const entries = Object.values(readRegistry())
    .filter((entry) => entry && typeof entry.file === 'string' && entry.file && existsSync(entry.file))
    .slice(0, 200)
    .map((entry) => {
      const docId = readDocIdFromFileHead(entry.file)
      return { ...entry, annotations: (docId && counts.get(docId)) || 0 }
    })
  return { entries, exportsDir: exportsDir(), files: listExports() }
}

function sendJson(res, status, payload, extraHeaders) {
  const body = JSON.stringify(payload)
  const headers = {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff',
    ...(extraHeaders || {}),
  }
  return send(res, status, headers, body)
}

/** 读请求体；超过上限（512KB）抛 {code:'too_large'}。 */
function readRequestBody(req, maxBytes) {
  return new Promise((resolve, reject) => {
    let size = 0
    let settled = false
    const chunks = []
    function fail(error) {
      if (settled) return
      settled = true
      reject(error)
    }
    req.on('data', (chunk) => {
      if (settled) return
      size += chunk.length
      if (size > maxBytes) {
        // 不要 destroy（客户端会收到 socket hang up）：停止累积，排空剩余 body，
        // 让 handler 能正常返回 413。
        chunks.length = 0
        fail(Object.assign(new Error('request body too large'), { code: 'too_large' }))
        try {
          req.resume()
        } catch {
          // ignore
        }
        return
      }
      chunks.push(chunk)
    })
    req.on('end', () => {
      if (settled) return
      settled = true
      resolve(Buffer.concat(chunks).toString('utf8'))
    })
    req.on('error', (error) => fail(error))
  })
}

/** 同源校验：带 Origin 时必须与 Host 同源（file:// 页面 fetch 会带 Origin: null → 拒绝）。 */
function isSameOrigin(req) {
  const origin = req.headers.origin
  if (!origin) return true
  if (origin === 'null') return false
  const host = String(req.headers.host || '')
  return origin.replace(/^https?:\/\//i, '') === host
}

/**
 * 批注同步 API：GET /paper2html/api/annotations/<docId>
 *                PUT 同上，body { annotations: [...] }
 */
async function handleAnnotationsApi(req, res, method, rawDocId) {
  if (!isSameOrigin(req)) {
    return sendJson(res, 403, { ok: false, error: '跨域请求被拒绝：批注 API 只允许同源页面调用' })
  }
  const docId = String(rawDocId || '')
  if (!isValidDocId(docId)) {
    return sendJson(res, 400, {
      ok: false,
      error: `docId 不合法（${JSON.stringify(docId)}）：只允许字母/数字开头，后续 A-Z a-z 0-9 . _ -，长度 1–128`,
    })
  }

  if (method === 'GET') {
    const record = readAnnotations(docId)
    return sendJson(res, 200, { docId, annotations: record.annotations, updatedAt: record.updatedAt })
  }
  if (method !== 'PUT') {
    return sendJson(res, 405, { ok: false, error: '只支持 GET / PUT' }, { allow: 'GET, PUT' })
  }

  const contentType = String(req.headers['content-type'] || '')
  if (!/^application\/json\b/i.test(contentType)) {
    return sendJson(res, 400, { ok: false, error: 'Content-Type 必须是 application/json' })
  }

  let rawBody
  try {
    rawBody = await readRequestBody(req, MAX_STORE_BYTES)
  } catch (error) {
    if (error && error.code === 'too_large') {
      return sendJson(res, 413, { ok: false, error: '批注数据过大：超过 512KB 上限' })
    }
    return sendJson(res, 400, { ok: false, error: `读取请求体失败：${error.message}` })
  }

  let parsed
  try {
    parsed = JSON.parse(rawBody || 'null')
  } catch {
    return sendJson(res, 400, { ok: false, error: '请求体不是合法 JSON' })
  }
  if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.annotations)) {
    return sendJson(res, 400, { ok: false, error: '请求体需要形如 { "annotations": [...] }' })
  }

  try {
    const result = writeAnnotations(docId, parsed.annotations)
    return sendJson(res, 200, { ok: true, count: result.count, updatedAt: result.updatedAt })
  } catch (error) {
    if (error instanceof AnnotationStoreError) {
      const status = error.code === 'too_large' ? 413 : 400
      return sendJson(res, status, { ok: false, error: error.message })
    }
    return sendJson(res, 500, { ok: false, error: `保存批注失败：${error.message}` })
  }
}

/** ctx.webServer.register({ kind:'prefix', path: BASE, handler }) */
export function createHandler() {
  return async function handler(req, res) {
    const method = String(req.method || 'GET').toUpperCase()
    let url
    try {
      url = new URL(req.url || '/', 'http://localhost')
    } catch {
      return notFound(res)
    }
    // 正常情况下 req.url 带完整前缀；万一被上层剥掉前缀，直接 404，不要误当成首页
    if (!url.pathname.startsWith(BASE)) return notFound(res)
    let rest
    try {
      rest = decodeURIComponent(url.pathname.slice(BASE.length))
    } catch {
      return notFound(res)
    }
    // 批注同步 API 必须先于静态文件分支（静态分支只接受 GET/HEAD）
    const apiMatch = rest.match(/^\/api\/annotations\/([^/]+)$/)
    if (apiMatch) {
      return handleAnnotationsApi(req, res, method, apiMatch[1])
    }
    if (method !== 'GET' && method !== 'HEAD') {
      return send(res, 405, { 'content-type': 'text/plain; charset=utf-8', allow: 'GET, HEAD' }, 'Method not allowed')
    }
    if (!rest || rest === '/' || rest === '/index.html') {
      return send(res, 200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' }, libraryHtml())
    }
    if (rest === '/api/exports') {
      return send(
        res,
        200,
        { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
        JSON.stringify(buildExportsPayload()),
      )
    }
    let match = rest.match(/^\/p\/([a-f0-9]{12})$/)
    if (match) {
      const entry = lookupPreview(match[1])
      if (!entry?.file) return notFound(res)
      let real
      try {
        real = realpathSync(entry.file)
      } catch {
        return notFound(res)
      }
      if (extname(real).toLowerCase() !== '.html') return notFound(res)
      return serveFile(req, res, real)
    }
    match = rest.match(/^\/([^/]+)$/)
    if (match && match[1].toLowerCase().endsWith('.html')) {
      const file = safeFile(exportsDir(), match[1])
      return file ? serveFile(req, res, file) : notFound(res)
    }
    return notFound(res)
  }
}
