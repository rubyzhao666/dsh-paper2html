// 插件注册给模型的三个工具：
//   paper2html_convert      把 PDF/arXiv 转成可分享的交互式 HTML 阅读页
//   paper2html_status       环境自检（Python / 依赖 / 导出目录 / key 是否就绪）
//   paper2html_annotations  读取用户在 DSH Web 预览页里做的批注/高亮（Host 侧同步存储）
// 工具在 Host 进程里执行，文件写到 $DSH_HOME/paper2html/ 或用户指定的导出目录。
import { closeSync, existsSync, mkdirSync, openSync, readFileSync, readSync, statSync } from 'node:fs'
import { basename, isAbsolute, join, resolve } from 'node:path'
import {
  extractDocIdFromHtml,
  isValidDocId,
  listDocuments,
  readAnnotations,
} from './annotations-store.js'
import { registerPreview } from './preview.js'
import {
  configPath,
  dataDir,
  exportsDir,
  inspectRuntime,
  listExports,
  readKeys,
  runConvert,
  slugify,
  venvDir,
} from './python-run.js'

const text = (value) => [{ type: 'text', text: value }]
const str = (description, extra = {}) => ({ type: 'string', description, ...extra })
const bool = (description) => ({ type: 'boolean', description })

// 参数校验：注册的是原始 JSON Schema，没有 defineTool 帮忙校验，这里自己挡住缺字段和类型错
function check(args, schema) {
  const errs = []
  const value = args && typeof args === 'object' ? args : {}
  for (const key of schema.required || []) {
    if (value[key] === undefined || value[key] === null || value[key] === '') errs.push(`缺少参数 ${key}`)
  }
  for (const [key, item] of Object.entries(value)) {
    const prop = schema.properties[key]
    if (!prop) {
      errs.push(`未知参数 ${key}（可用: ${Object.keys(schema.properties).join(', ')}）`)
      continue
    }
    if (item === undefined || item === null) continue
    if (prop.type === 'string' && typeof item !== 'string') errs.push(`${key} 应该是字符串`)
    if (prop.type === 'boolean' && typeof item !== 'boolean') errs.push(`${key} 应该是布尔值 true/false`)
    if (prop.type === 'array' && !Array.isArray(item)) errs.push(`${key} 应该是字符串数组`)
    if (prop.type === 'integer' && !Number.isInteger(item)) errs.push(`${key} 应该是整数`)
    if (prop.enum && typeof item === 'string' && !prop.enum.includes(item)) {
      errs.push(`${key} 只能是 ${prop.enum.join(' / ')}，收到 ${JSON.stringify(item)}`)
    }
  }
  if (errs.length) throw new Error(errs.join('；'))
  return value
}

const ARXIV_ID_RE = /^\d{4}\.\d{4,5}(v\d+)?$/
const ARXIV_URL_RE = /arxiv\.org\/(?:abs|pdf)\/(\d{4}\.\d{4,5})(v\d+)?/i

/** 判断 input 是 arXiv 还是本地 PDF，并做可操作的前置校验。 */
export function classifyInput(input) {
  const raw = String(input || '').trim()
  if (!raw) throw new Error('input 不能为空：给本地 PDF 的绝对路径，或 arXiv URL/ID（如 1706.03762）。')
  if (/arxiv\.org/i.test(raw)) {
    const match = raw.match(ARXIV_URL_RE)
    if (!match) {
      throw new Error(
        `看起来是 arXiv 链接，但解析不出 arXiv ID：${raw}\n` +
          '支持的形式：https://arxiv.org/abs/1706.03762、https://arxiv.org/pdf/1706.03762、或纯 ID 1706.03762。',
      )
    }
    return { kind: 'arxiv', value: raw, arxivId: match[1], stem: match[1] }
  }
  if (ARXIV_ID_RE.test(raw)) {
    return { kind: 'arxiv', value: raw, arxivId: raw.replace(/v\d+$/, ''), stem: raw.replace(/v\d+$/, '') }
  }
  if (!isAbsolute(raw)) {
    throw new Error(
      `本地 PDF 需要绝对路径（收到相对路径或未知输入：${raw}）。\n` +
        '例如 /Users/you/Papers/paper.pdf；arXiv 论文可以直接传 https://arxiv.org/abs/1706.03762。',
    )
  }
  const file = resolve(raw)
  if (!existsSync(file)) {
    throw new Error(
      `找不到 PDF 文件：${file}\n` +
        '请确认路径存在（macOS 可以右键文件 → 按住 Option 复制路径），或改用 arXiv 链接/ID。',
    )
  }
  let stat
  try {
    stat = statSync(file)
  } catch (error) {
    throw new Error(`无法读取 PDF 文件：${file}（${error.message}）`)
  }
  if (!stat.isFile()) throw new Error(`input 应该是文件而不是目录：${file}`)
  if (!file.toLowerCase().endsWith('.pdf')) {
    throw new Error(`只支持 .pdf 文件，收到：${file}\n扫描版 PDF 也能转，但需要 OCR 或配置 DOC2X_APIKEY 走云端解析。`)
  }
  if (stat.size < 100) throw new Error(`PDF 文件过小（${stat.size} 字节），可能不是有效 PDF：${file}`)
  let header = Buffer.alloc(0)
  try {
    const fd = openSync(file, 'r')
    header = Buffer.alloc(8)
    const read = readSync(fd, header, 0, 8, 0)
    closeSync(fd)
    header = header.subarray(0, read)
  } catch (error) {
    throw new Error(`无法读取 PDF 文件头：${file}（${error.message}）`)
  }
  if (!header.subarray(0, 4).equals(Buffer.from('%PDF'))) {
    throw new Error(
      `不是有效的 PDF（文件头不是 %PDF）：${file}\n` +
        '如果这是网页/Word 改名成 .pdf，请先导出为真正的 PDF；扫描件 PDF 可以转，但需要 OCR 或 DOC2X_APIKEY。',
    )
  }
  return { kind: 'pdf', value: file, stem: basename(file, '.pdf') }
}

export function previewUrl(previewPath) {
  const base = process.env.DSH_WEB_URL || ''
  if (!base) return previewPath
  try {
    return new URL(previewPath, base.endsWith('/') ? base : `${base}/`).toString()
  } catch {
    return previewPath
  }
}

const CONVERT_PARAMS = {
  type: 'object',
  additionalProperties: false,
  required: ['input'],
  properties: {
    input: str('要转换的论文：本地 PDF 的绝对路径，或 arXiv URL/ID（如 https://arxiv.org/abs/1706.03762 或 1706.03762）'),
    outputDir: str('HTML 输出目录的绝对路径（可选；默认 $DSH_HOME/paper2html/exports）'),
    style: str('视觉主题（可选，默认 dark_lab）', { enum: ['dark_lab', 'clean_paper', 'neon_tech'] }),
    understand: bool('是否用 DeepSeek key 生成 AI 摘要（默认 false：无 key 也能跑，只排版不摘要）'),
  },
}

export const convertTool = {
  name: 'paper2html_convert',
  description:
    '把学术论文（本地 PDF 或 arXiv 链接/ID）转换成单文件、可分享的交互式 HTML 阅读页（三套主题、公式/图表/目录导航）。不需要任何 API key；配置了 DeepSeek key 时可选生成 AI 摘要。返回 HTML 文件路径和 DSH Web 预览地址。',
  parameters: CONVERT_PARAMS,
  timeoutMs: 320_000,
  output: {
    schema: {
      type: 'object',
      additionalProperties: false,
      required: ['htmlPath', 'title', 'style', 'engine', 'previewPath'],
      properties: {
        htmlPath: { type: 'string', description: '生成的 HTML 文件绝对路径（单个文件，可直接分享）' },
        title: { type: 'string' },
        style: { type: 'string' },
        engine: { type: 'string', description: '解析引擎：local / doc2x / pdf2x' },
        pages: { type: 'integer' },
        bytes: { type: 'integer' },
        previewPath: { type: 'string', description: 'DSH Web 预览路径，如 /paper2html/p/abcdef123456' },
        previewUrl: { type: 'string', description: '完整预览地址（能探测到 DSH Web 地址时）' },
        understand: { type: 'boolean', description: '本次是否真的生成了 AI 摘要' },
        warnings: { type: 'array', items: { type: 'string' } },
      },
    },
    render: (_args, value) => {
      const lines = [
        `已生成论文阅读页：《${value.title}》`,
        `· 主题 ${value.style} · 解析引擎 ${value.engine}${value.pages ? ` · ${value.pages} 页` : ''} · ${(value.bytes / 1024).toFixed(0)} KB`,
        `· 预览：${value.previewUrl || value.previewPath}（DSH Web 里直接打开）`,
        `· 文件：${value.htmlPath}（单文件，可发给别人/离线打开）`,
        value.understand ? '· AI 摘要：已生成（TL;DR/关键发现/章节摘要）' : '· AI 摘要：未启用（无 key 的本地模式，正文和排版完整可用）',
      ]
      if (value.warnings?.length) lines.push(`· 提示：${value.warnings.join('；')}`)
      lines.push('下一步：把预览链接和文件路径告诉用户；需要讲解论文时直接基于正文回答，不必再读 HTML。')
      return text(lines.join('\n'))
    },
  },
  async execute(args) {
    const params = check(args, CONVERT_PARAMS)
    const target = classifyInput(params.input)
    const style = params.style || 'dark_lab'
    const understand = params.understand === true

    const keys = readKeys()
    if (understand && !keys.deepseek) {
      throw new Error(
        'understand=true 需要 DeepSeek key（未检测到 DEEPSEEK_APIKEY / config.json 的 deepseekKey）。\n' +
          '两种选择：\n' +
          '1) 保持 understand=false（默认）——无 key 本地模式，只排版不生成 AI 摘要，页面依然完整可读；\n' +
          '2) 配置 key 后重试：export DEEPSEEK_APIKEY=your-key，或写进 ' +
          `${configPath()} 的 {"deepseekKey": "your-key"}。`,
      )
    }

    if (params.outputDir && !isAbsolute(params.outputDir)) {
      throw new Error(`outputDir 必须是绝对路径（收到相对路径：${params.outputDir}）。例如 /Users/you/Papers/out。`)
    }
    const outDir = params.outputDir ? resolve(params.outputDir) : exportsDir()
    if (existsSync(outDir) && !statSync(outDir).isDirectory()) {
      throw new Error(`outputDir 已存在但不是目录：${outDir}。请换一个目录路径，或先把该文件移走。`)
    }
    try {
      mkdirSync(outDir, { recursive: true })
    } catch (error) {
      throw new Error(`无法创建输出目录 ${outDir}：${error.message}`)
    }

    const file = join(outDir, `${slugify(target.stem)}-${style}.html`)
    const report = await runConvert({ input: target.value, output: file, style, understand })
    const { previewPath } = registerPreview({
      file: report.htmlPath,
      title: report.title,
      style: report.style,
      engine: report.engine,
      pages: report.pages,
      bytes: report.bytes,
    })
    return {
      htmlPath: report.htmlPath,
      title: report.title || 'Untitled Paper',
      style: report.style || style,
      engine: report.engine || 'local',
      pages: Number(report.pages) || 0,
      bytes: Number(report.bytes) || 0,
      previewPath,
      previewUrl: previewUrl(previewPath),
      understand: Boolean(report.understand),
      warnings: Array.isArray(report.warnings) ? report.warnings.map(String) : [],
    }
  },
}

const STATUS_PARAMS = { type: 'object', additionalProperties: false, properties: {} }

export async function collectStatus() {
  const runtime = await inspectRuntime()
  const keys = readKeys()
  const exports = listExports()
  const warnings = []
  if (!runtime.python || !runtime.python.ready) {
    warnings.push('本地 Python 依赖未就绪：第一次转换会尝试自动创建 venv 并联网安装 pymupdf/markdown（失败会给出手动命令）。')
  }
  return {
    ready: Boolean(runtime.python && runtime.python.ready),
    python: runtime.python
      ? {
          path: runtime.python.file,
          version: runtime.python.version,
          mode: runtime.python.mode,
          pymupdf: runtime.python.deps?.pymupdf ?? false,
          markdown: runtime.python.deps?.markdown ?? false,
        }
      : null,
    venvExists: Boolean(runtime.venv?.exists),
    venvPath: venvDir(),
    keys,
    dataDir: dataDir(),
    exportsDir: exportsDir(),
    exportCount: exports.length,
    exportsBytes: exports.reduce((sum, item) => sum + (item.bytes || 0), 0),
    configPath: configPath(),
    warnings,
  }
}

export const statusTool = {
  name: 'paper2html_status',
  description:
    '检查 Paper2HTML 的运行环境是否就绪：Python 解释器、pymupdf/markdown 依赖、venv、DeepSeek/Doc2X/PDF2X key 是否配置、导出目录与已生成文件数量。只读，不安装依赖、不发起转换。',
  parameters: STATUS_PARAMS,
  timeoutMs: 60_000,
  output: {
    schema: {
      type: 'object',
      additionalProperties: false,
      required: ['ready'],
      properties: {
        ready: { type: 'boolean', description: '本地模式当前是否可直接转换' },
        pythonPath: { type: 'string' },
        pythonVersion: { type: 'string' },
        pythonMode: { type: 'string' },
        hasPymupdf: { type: 'boolean' },
        hasMarkdown: { type: 'boolean' },
        venvExists: { type: 'boolean' },
        venvPath: { type: 'string' },
        hasDoc2xKey: { type: 'boolean' },
        hasPdf2xKey: { type: 'boolean' },
        hasDeepseekKey: { type: 'boolean' },
        dataDir: { type: 'string' },
        exportsDir: { type: 'string' },
        exportCount: { type: 'integer' },
        configPath: { type: 'string' },
        warnings: { type: 'array', items: { type: 'string' } },
        summary: { type: 'string' },
      },
    },
    render: (_args, value) => text(value.summary),
  },
  async execute(args) {
    check(args, STATUS_PARAMS)
    const status = await collectStatus()
    const pythonLine = status.python
      ? `Python ${status.python.version}（${status.python.path}，${status.python.mode === 'venv' ? '插件 venv' : status.python.mode === 'env' ? 'PAPER2HTML_PYTHON' : '系统解释器'}）pymupdf=${status.python.pymupdf ? '✓' : '✗'} markdown=${status.python.markdown ? '✓' : '✗'}`
      : '未找到可用 Python'
    const summary = [
      `${status.ready ? '✅ 本地模式可用' : '⚠️ 本地模式尚未就绪'}`,
      `· ${pythonLine}`,
      `· venv：${status.venvExists ? `已存在 ${status.venvPath}` : '未创建（首次转换时自动创建）'}`,
      `· key：DeepSeek ${status.keys.deepseek ? '已配置' : '未配置（无 key 也能转，只是没有 AI 摘要）'} · Doc2X ${status.keys.doc2x ? '已配置' : '未配置'} · PDF2X ${status.keys.pdf2x ? '已配置' : '未配置'}`,
      `· 已生成 ${status.exportCount} 个页面，目录 ${status.exportsDir}`,
      status.warnings.length ? `· 提示：${status.warnings.join('；')}` : '',
      status.ready
        ? '下一步：调用 paper2html_convert 转换论文即可。'
        : '下一步：调用 paper2html_convert 会自动尝试建 venv 并安装依赖；失败时按报错里的手动命令处理。',
    ]
      .filter(Boolean)
      .join('\n')
    return {
      ready: status.ready,
      pythonPath: status.python?.path || '',
      pythonVersion: status.python?.version || '',
      pythonMode: status.python?.mode || '',
      hasPymupdf: Boolean(status.python?.pymupdf),
      hasMarkdown: Boolean(status.python?.markdown),
      venvExists: status.venvExists,
      venvPath: status.venvPath,
      hasDoc2xKey: status.keys.doc2x,
      hasPdf2xKey: status.keys.pdf2x,
      hasDeepseekKey: status.keys.deepseek,
      dataDir: status.dataDir,
      exportsDir: status.exportsDir,
      exportCount: status.exportCount,
      configPath: status.configPath,
      warnings: status.warnings,
      summary,
    }
  },
}

// ---------------------------------------------------------------------------
// paper2html_annotations：读取 Host 侧同步的页面批注（0.3.0 G3）
// ---------------------------------------------------------------------------

const ANNOTATIONS_PARAMS = {
  type: 'object',
  additionalProperties: false,
  properties: {
    docId: str('文档 id（页面的 <meta name="p2h-doc-id">，如 arxiv-1706.03762）；与 htmlPath 二选一'),
    htmlPath: str('已生成论文 HTML 的绝对路径（自动从 meta[name=p2h-doc-id] 读取文档 id）；与 docId 二选一'),
    limit: {
      type: 'integer',
      minimum: 1,
      maximum: 200,
      description: '最多返回多少条批注（默认 100，最大 200）',
    },
  },
}

function quoteExcerpt(exact, limit = 160) {
  const normalized = String(exact || '').replace(/\s+/g, ' ').trim()
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, limit - 1)}…`
}

function annotationRecordToPublic(annotation) {
  return {
    id: annotation.id,
    color: annotation.color,
    note: annotation.note || '',
    quoteExcerpt: quoteExcerpt(annotation.quote && annotation.quote.exact),
    sectionId: annotation.sectionId || '',
    createdAt: annotation.createdAt || '',
  }
}

function renderAnnotationsText(value) {
  const lines = []
  if (Array.isArray(value.documents)) {
    if (!value.documents.length) {
      lines.push('本机还没有同步的批注。')
      lines.push(
        '提示：批注需要在 DSH Web 预览页（http://127.0.0.1:<端口>/paper2html/…）里打开论文后添加；' +
          'file:// 打开的页面批注只存在浏览器本地，不会同步到这里。',
      )
      return lines.join('\n')
    }
    lines.push(`本机有 ${value.documents.length} 篇论文的批注：`)
    for (const doc of value.documents) {
      lines.push(`- ${doc.docId} · ${doc.count} 条${doc.updatedAt ? ` · 更新于 ${doc.updatedAt}` : ''}`)
    }
    lines.push('下一步：传 docId 或 htmlPath 读取某篇的具体批注内容。')
    return lines.join('\n')
  }
  if (value.count === 0) {
    lines.push(`《${value.docId}》目前没有同步的批注。`)
    lines.push(
      '提示：让用户在 DSH Web 预览页打开这篇论文并添加批注后同步；file:// 页面添加的批注只存在浏览器本地。',
    )
    return lines.join('\n')
  }
  lines.push(`《${value.docId}》共 ${value.count} 条批注${value.updatedAt ? `（更新于 ${value.updatedAt}）` : ''}：`)
  const listed = value.annotations || []
  for (let i = 0; i < listed.length; i += 1) {
    const item = listed[i]
    const note = item.note ? ` — ${item.note}` : ' —（仅高亮，没有批注文字）'
    const section = item.sectionId ? `（${item.sectionId}）` : ''
    lines.push(`${i + 1}. [${item.color}] “${item.quoteExcerpt}”${note}${section}`)
  }
  if (value.count > listed.length) {
    lines.push(`…已列出前 ${listed.length} 条（共 ${value.count} 条，可用 limit 调整，单次最多 200 条）。`)
  }
  lines.push('这些是用户在论文阅读页里做的高亮/批注，可直接据此总结或回答。')
  return lines.join('\n')
}

export const annotationsTool = {
  name: 'paper2html_annotations',
  description:
    '读取用户在论文阅读页里做的高亮/批注（来自 DSH Web 预览页的批注同步存储）。无参数时列出本机所有有批注的文档；传 docId 或 htmlPath 读取某篇论文的批注内容（摘录、颜色、批注文字、所在章节）。用户问「我标注了什么」「把我标的部分总结一下」「批注里有哪些问题」时使用。',
  parameters: ANNOTATIONS_PARAMS,
  timeoutMs: 15_000,
  output: {
    schema: {
      type: 'object',
      additionalProperties: false,
      required: ['count'],
      properties: {
        count: { type: 'integer', description: '文档数（列表模式）或批注总数（单文档模式）' },
        docId: { type: 'string' },
        updatedAt: { type: 'string' },
        annotations: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['id', 'color', 'note', 'quoteExcerpt'],
            properties: {
              id: { type: 'string' },
              color: { type: 'string' },
              note: { type: 'string' },
              quoteExcerpt: { type: 'string' },
              sectionId: { type: 'string' },
              createdAt: { type: 'string' },
            },
          },
        },
        documents: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['docId', 'count'],
            properties: {
              docId: { type: 'string' },
              count: { type: 'integer' },
              updatedAt: { type: 'string' },
            },
          },
        },
      },
    },
    render: (_args, value) => text(renderAnnotationsText(value)),
  },
  async execute(args) {
    const params = check(args, ANNOTATIONS_PARAMS)
    let limit = 100
    if (params.limit !== undefined) {
      if (!Number.isInteger(params.limit) || params.limit < 1 || params.limit > 200) {
        throw new Error(`limit 需要是 1–200 的整数（收到 ${JSON.stringify(params.limit)}）`)
      }
      limit = params.limit
    }
    if (params.docId && params.htmlPath) {
      throw new Error('docId 和 htmlPath 只能给一个：知道 HTML 路径就传 htmlPath，否则传 docId。')
    }

    let docId = ''
    if (params.htmlPath) {
      const file = String(params.htmlPath).trim()
      if (!isAbsolute(file)) {
        throw new Error(`htmlPath 需要绝对路径（收到相对路径：${file}）。例如 /Users/you/paper.html。`)
      }
      if (!existsSync(file)) {
        throw new Error(`找不到 HTML 文件：${file}\n请确认路径存在；也可以改用 docId（形如 arxiv-1706.03762）。`)
      }
      let stat
      try {
        stat = statSync(file)
      } catch (error) {
        throw new Error(`无法读取 HTML 文件：${file}（${error.message}）`)
      }
      if (!stat.isFile()) throw new Error(`htmlPath 应该是文件而不是目录：${file}`)
      let html = ''
      try {
        html = readFileSync(file, 'utf8')
      } catch (error) {
        throw new Error(`读取 HTML 失败：${file}（${error.message}）`)
      }
      docId = extractDocIdFromHtml(html)
      if (!docId) {
        throw new Error(
          `这个 HTML 里没有 <meta name="p2h-doc-id">：${file}\n` +
            '请确认它是 0.2.0 及以上版本的 Paper2HTML 生成的页面；旧版本页面无法定位批注。',
        )
      }
    } else if (params.docId) {
      docId = String(params.docId).trim()
    }

    if (!docId) {
      const documents = listDocuments()
      return { count: documents.length, documents }
    }
    if (!isValidDocId(docId)) {
      throw new Error(
        `docId 不合法：${JSON.stringify(docId)}。允许字母/数字开头，后续仅 A-Z a-z 0-9 . _ -，长度 1–128；` +
          '可从页面 HTML 的 <meta name="p2h-doc-id"> 获取。',
      )
    }
    const record = readAnnotations(docId)
    const annotations = record.annotations.slice(0, limit).map(annotationRecordToPublic)
    return {
      count: record.annotations.length,
      docId,
      updatedAt: record.updatedAt,
      annotations,
    }
  },
}

export const TOOLS = [convertTool, statusTool, annotationsTool]
