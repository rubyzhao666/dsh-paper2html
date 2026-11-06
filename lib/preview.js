// /paper2html/ 只读预览服务 + 导出登记表。
// - 只读 GET/HEAD；只服务 .html
// - 只允许导出目录内的文件（拒绝 ..、点文件、目录外软链）
// - 用户指定了导出目录时，用登记表按 id 服务那一个具体文件
import { createReadStream, existsSync, mkdirSync, readFileSync, realpathSync, renameSync, statSync, writeFileSync } from 'node:fs'
import { extname, join, normalize, sep } from 'node:path'
import { exportsDir, hashOf, listExports, registryFile } from './python-run.js'

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
  res.writeHead(status, headers)
  res.end(body)
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

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, (char) => {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
    return map[char]
  })
}

function indexPage() {
  const entries = Object.values(readRegistry()).sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)))
  const seen = new Set()
  const rows = []
  for (const entry of entries) {
    if (!entry?.file || seen.has(entry.file)) continue
    seen.add(entry.file)
    if (!existsSync(entry.file)) continue
    let size = 0
    try {
      size = statSync(entry.file).size
    } catch {
      size = 0
    }
    rows.push(
      `<tr><td><a href="${BASE}/p/${escapeHtml(entry.id)}">${escapeHtml(entry.title || entry.name)}</a></td>` +
        `<td>${escapeHtml(entry.style || '-')}</td><td>${Number(entry.pages) || '-'}</td>` +
        `<td>${(size / 1024).toFixed(0)} KB</td><td>${escapeHtml(entry.updatedAt || '')}</td></tr>`,
    )
  }
  const body = rows.length
    ? `<table><thead><tr><th>标题</th><th>主题</th><th>页数</th><th>体积</th><th>生成时间</th></tr></thead><tbody>${rows.join('')}</tbody></table>`
    : '<p>还没有转换过论文。让 agent 运行 <code>paper2html_convert</code> 生成第一份。</p>'
  return `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paper2HTML 预览</title>
<style>body{font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;padding:24px 32px;background:#0d1117;color:#e6edf3}
h1{font-size:22px;margin:0 0 4px}p{color:#8b949e}table{border-collapse:collapse;width:100%;margin-top:16px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #21262d;white-space:nowrap}th{color:#8b949e;font-weight:600}
a{color:#58a6ff;text-decoration:none}a:hover{text-decoration:underline}code{background:#161b22;padding:1px 5px;border-radius:4px}</style>
</head><body><h1>📄 Paper2HTML 预览</h1><p>这里只读展示本机转换过的论文页面。文件本身可以单独发给别人。</p>${body}</body></html>`
}

/** ctx.webServer.register({ kind:'prefix', path: BASE, handler }) */
export function createHandler() {
  return function handler(req, res) {
    const method = String(req.method || 'GET').toUpperCase()
    if (method !== 'GET' && method !== 'HEAD') {
      return send(res, 405, { 'content-type': 'text/plain; charset=utf-8', allow: 'GET, HEAD' }, 'Method not allowed')
    }
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
    if (!rest || rest === '/' || rest === '/index.html') {
      return send(res, 200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' }, indexPage())
    }
    if (rest === '/api/exports') {
      const entries = Object.values(readRegistry()).filter((entry) => entry?.file && existsSync(entry.file))
      return send(
        res,
        200,
        { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
        JSON.stringify({ entries: entries.slice(0, 200), exportsDir: exportsDir(), files: listExports() }),
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
