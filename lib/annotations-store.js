// 批注 Host 侧存储（0.3.0 G3）
// 目录：$DSH_HOME/paper2html/annotations/<docId>.json
// 文件结构：{ version: 1, docId, updatedAt, annotations: [...] }
// - docId 白名单校验（拒绝路径分隔符 / 点文件）
// - 写入：临时文件 + rename 原子替换
// - 读取：损坏 / 超限 / JSON 非法 → 容错返回空数组，绝不抛未捕获异常
// - 校验：≤500 条；每条字段白名单；整体序列化 ≤512KB（超出抛 too_large，由 HTTP 层转 413）
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs'
import { randomBytes } from 'node:crypto'
import { join } from 'node:path'
import { dataDir } from './python-run.js'

export const ANNOTATION_COLORS = ['yellow', 'green', 'blue', 'pink']
export const MAX_ANNOTATIONS = 500
export const MAX_STORE_BYTES = 512 * 1024
export const DOC_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/

export class AnnotationStoreError extends Error {
  constructor(message, code) {
    super(message)
    this.name = 'AnnotationStoreError'
    this.code = code || 'invalid'
  }
}

export function annotationsDir() {
  return join(dataDir(), 'annotations')
}

/** docId 只允许字母数字开头、后续字母数字/._-；不允许路径分隔符。 */
export function isValidDocId(docId) {
  return typeof docId === 'string' && DOC_ID_PATTERN.test(docId) && !docId.includes('/') && !docId.includes('\\')
}

export function assertDocId(docId) {
  if (isValidDocId(docId)) return docId
  throw new AnnotationStoreError(
    `docId 不合法：${JSON.stringify(String(docId || ''))}。允许字母/数字开头，后续仅 A-Z a-z 0-9 . _ -，长度 1–128；` +
      '可从页面的 <meta name="p2h-doc-id"> 获取（如 arxiv-1706.03762、pdf-1a2b3c4d5e6f7890）。',
    'invalid_docid',
  )
}

function text(value, maxLength) {
  if (value === undefined || value === null) return ''
  if (typeof value !== 'string') return null
  if (value.length > maxLength) return null
  return value
}

/** 单条批注白名单归一化；不合法返回 null。 */
function normalizeAnnotation(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const id = text(raw.id, 64)
  if (!id) return null
  if (!ANNOTATION_COLORS.includes(raw.color)) return null
  const quote = raw.quote && typeof raw.quote === 'object' && !Array.isArray(raw.quote) ? raw.quote : null
  const exact = quote ? text(quote.exact, 2000) : null
  if (!exact) return null
  const prefix = quote ? text(quote.prefix, 2000) : ''
  const suffix = quote ? text(quote.suffix, 2000) : ''
  if (prefix === null || suffix === null) return null
  const note = text(raw.note, 2000)
  if (note === null) return null
  const sectionId = text(raw.sectionId, 200)
  if (sectionId === null) return null
  const createdAt = text(raw.createdAt, 80)
  if (createdAt === null) return null
  return { id, color: raw.color, note, quote: { exact, prefix, suffix }, sectionId, createdAt }
}

/** 批量校验并归一化；不合法 / 超条数抛 AnnotationStoreError('invalid')。 */
export function normalizeAnnotationList(list) {
  if (!Array.isArray(list)) {
    throw new AnnotationStoreError('annotations 必须是数组：{ annotations: [...] }', 'invalid')
  }
  if (list.length > MAX_ANNOTATIONS) {
    throw new AnnotationStoreError(`批注条数超过上限 ${MAX_ANNOTATIONS}（收到 ${list.length}）`, 'invalid')
  }
  const normalized = []
  for (let i = 0; i < list.length; i += 1) {
    const item = normalizeAnnotation(list[i])
    if (!item) {
      throw new AnnotationStoreError(
        `第 ${i + 1} 条批注字段不合法：需要 id(1–64)、color ∈ ${ANNOTATION_COLORS.join('|')}、` +
          'quote.exact(1–2000)、note(≤2000)、sectionId(≤200)、createdAt(≤80)',
        'invalid',
      )
    }
    normalized.push(item)
  }
  return normalized
}

function storePath(docId) {
  return join(annotationsDir(), `${docId}.json`)
}

function emptyRecord(docId) {
  return { docId, annotations: [], updatedAt: '' }
}

/**
 * 读取某文档的批注（容错）。返回 { docId, annotations, updatedAt }；
 * 文件不存在 / JSON 损坏 / 结构异常 / 超过 512KB → annotations: []（不抛错）。
 */
export function readAnnotations(docId) {
  if (!isValidDocId(docId)) return emptyRecord(String(docId || ''))
  const file = storePath(docId)
  let rawText = ''
  try {
    if (!existsSync(file)) return emptyRecord(docId)
    if (statSync(file).size > MAX_STORE_BYTES) return emptyRecord(docId)
    rawText = readFileSync(file, 'utf8')
  } catch {
    return emptyRecord(docId)
  }
  let parsed
  try {
    parsed = JSON.parse(rawText)
  } catch {
    return emptyRecord(docId)
  }
  if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.annotations)) {
    return emptyRecord(docId)
  }
  const annotations = []
  for (const item of parsed.annotations) {
    const normalized = normalizeAnnotation(item)
    if (normalized) annotations.push(normalized)
    if (annotations.length >= MAX_ANNOTATIONS) break
  }
  const updatedAt = typeof parsed.updatedAt === 'string' ? parsed.updatedAt : ''
  return { docId, annotations, updatedAt }
}

/**
 * 覆盖写入某文档的全部批注（原子替换）。
 * @returns {{count:number, updatedAt:string, path:string}}
 * @throws {AnnotationStoreError} invalid_docid / invalid / too_large
 */
export function writeAnnotations(docId, list) {
  assertDocId(docId)
  const annotations = normalizeAnnotationList(list)
  const updatedAt = new Date().toISOString()
  const payload = { version: 1, docId, updatedAt, annotations }
  let serialized
  try {
    serialized = `${JSON.stringify(payload, null, 2)}\n`
  } catch {
    throw new AnnotationStoreError('批注数据无法序列化为 JSON', 'invalid')
  }
  const bytes = Buffer.byteLength(serialized, 'utf8')
  if (bytes > MAX_STORE_BYTES) {
    throw new AnnotationStoreError(
      `批注数据过大：${(bytes / 1024).toFixed(0)}KB，超过 ${Math.round(MAX_STORE_BYTES / 1024)}KB 上限。请删掉一些批注后再试。`,
      'too_large',
    )
  }
  const dir = annotationsDir()
  mkdirSync(dir, { recursive: true })
  const file = storePath(docId)
  const tmp = join(dir, `.${docId}.${process.pid}.${randomBytes(4).toString('hex')}.tmp`)
  try {
    writeFileSync(tmp, serialized, 'utf8')
    renameSync(tmp, file)
  } catch (error) {
    try {
      if (existsSync(tmp)) unlinkSync(tmp)
    } catch {
      // 清理失败不掩盖原始错误
    }
    throw new AnnotationStoreError(`保存批注失败：${error.message}`, 'invalid')
  }
  return { count: annotations.length, updatedAt, path: file }
}

/** 列出「有批注的文档」：按 updatedAt 降序；损坏文件跳过。 */
export function listDocuments({ max = 500 } = {}) {
  const dir = annotationsDir()
  let names = []
  try {
    names = readdirSync(dir)
  } catch {
    return []
  }
  const documents = []
  for (const name of names) {
    if (!name.endsWith('.json') || name.startsWith('.')) continue
    const docId = name.slice(0, -'.json'.length)
    if (!isValidDocId(docId)) continue
    const record = readAnnotations(docId)
    if (!record.annotations.length) continue
    documents.push({ docId, count: record.annotations.length, updatedAt: record.updatedAt })
    if (documents.length >= max) break
  }
  documents.sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')))
  return documents
}

/** 从 HTML 里读取 <meta name="p2h-doc-id" content="...">；取不到返回 ''。 */
export function extractDocIdFromHtml(html) {
  if (typeof html !== 'string' || !html) return ''
  const tags = html.match(/<meta\b[^>]*>/gi) || []
  for (const tag of tags) {
    const nameMatch = tag.match(/\bname\s*=\s*["']([^"']*)["']/i)
    if (!nameMatch || nameMatch[1].toLowerCase() !== 'p2h-doc-id') continue
    const contentMatch = tag.match(/\bcontent\s*=\s*["']([^"']*)["']/i)
    if (contentMatch) return contentMatch[1]
  }
  return ''
}

/** 供测试/诊断：存储文件绝对路径。 */
export function annotationFilePath(docId) {
  return storePath(docId)
}
