// 定位 Python 运行时、懒建 venv、调用插件内置的 python/paper2html.py。
// 只依赖 Node 内置模块；Python 依赖只在第一次真正转换时联网安装。
import { execFile as execFileCb } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { homedir } from 'node:os'
import { isAbsolute, join, resolve } from 'node:path'
import { promisify } from 'node:util'
import { fileURLToPath } from 'node:url'

const execFile = promisify(execFileCb)

export const PLUGIN_ROOT = fileURLToPath(new URL('..', import.meta.url))
export const PY_DIR = join(PLUGIN_ROOT, 'python')
export const SCRIPT = join(PY_DIR, 'paper2html.py')
export const REQUIREMENTS = join(PY_DIR, 'requirements-minimal.txt')

export const dshHome = () => process.env.DSH_HOME || join(homedir(), '.dsh')
export const dataDir = () => join(dshHome(), 'paper2html')
export const exportsDir = () => join(dataDir(), 'exports')
export const cacheDir = () => join(dataDir(), 'cache')
export const venvDir = () => join(dataDir(), 'venv')
export const registryFile = () => join(dataDir(), 'preview-registry.json')

const CONVERT_TIMEOUT_MS = 300_000
const RESULT_PREFIX = 'PAPER2HTML_RESULT_JSON:'
const ERROR_PREFIX = 'PAPER2HTML_ERROR_JSON:'

// ---------------------------------------------------------------------------
// 配置（key 只读不写）
// ---------------------------------------------------------------------------

const CONFIG_ALIASES = {
  doc2x: ['doc2xKey', 'doc2xApiKey', 'doc2x', 'DOC2X_APIKEY'],
  pdf2x: ['pdf2xKey', 'pdf2xApiKey', 'pdf2x', 'PDF2X_APIKEY'],
  deepseek: ['deepseekKey', 'deepseekApiKey', 'llmKey', 'DEEPSEEK_APIKEY'],
}

export function configPath() {
  return join(dataDir(), 'config.json')
}

export function readConfig() {
  try {
    const parsed = JSON.parse(readFileSync(configPath(), 'utf8'))
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function configValue(config, aliases) {
  for (const key of aliases) {
    const value = config[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}

/** key 优先级：环境变量 > $DSH_HOME/paper2html/config.json。只返回是否配置，不回传密钥。 */
export function readKeys() {
  const config = readConfig()
  const doc2x =
    process.env.DOC2X_APIKEY || process.env.DOC2X_API_KEY || configValue(config, CONFIG_ALIASES.doc2x)
  const pdf2x =
    process.env.PDF2X_APIKEY || process.env.PDF2X_API_KEY || configValue(config, CONFIG_ALIASES.pdf2x)
  const deepseek =
    process.env.DEEPSEEK_APIKEY ||
    process.env.DEEPSEEK_API_KEY ||
    process.env.LLM_API_KEY ||
    configValue(config, CONFIG_ALIASES.deepseek)
  return { doc2x: Boolean(doc2x), pdf2x: Boolean(pdf2x), deepseek: Boolean(deepseek) }
}

// ---------------------------------------------------------------------------
// Python 探测
// ---------------------------------------------------------------------------

let cachedRuntime = null

function candidateList() {
  const list = []
  if (process.env.PAPER2HTML_PYTHON) list.push({ file: process.env.PAPER2HTML_PYTHON, mode: 'env' })
  const venvPython = join(venvDir(), 'bin', 'python')
  if (existsSync(venvPython)) list.push({ file: venvPython, mode: 'venv' })
  list.push({ file: '/opt/homebrew/bin/python3.11', mode: 'system' })
  list.push({ file: '/opt/homebrew/bin/python3', mode: 'system' })
  list.push({ file: '/usr/local/bin/python3', mode: 'system' })
  list.push({ file: '/usr/bin/python3', mode: 'system' })
  list.push({ file: 'python3', mode: 'system' })
  const seen = new Set()
  return list.filter((item) => {
    const key = item.file
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

async function probePython(file) {
  // 返回 {file, version, deps} 或 null
  if (file.includes('/') && !isAbsolute(file)) return null
  if (isAbsolute(file) && !existsSync(file)) return null
  try {
    const { stdout } = await execFile(
      file,
      [
        '-c',
        [
          'import sys, json',
          'info = {"version": sys.version_info[:3]}',
          'try:',
          '    import pymupdf',
          '    info["pymupdf"] = True',
          'except Exception:',
          '    try:',
          '        import fitz',
          '        info["pymupdf"] = True',
          '    except Exception:',
          '        info["pymupdf"] = False',
          'try:',
          '    import markdown',
          '    info["markdown"] = True',
          'except Exception:',
          '    info["markdown"] = False',
          'print(json.dumps(info))',
        ].join('\n'),
      ],
      { timeout: 20_000, env: { ...process.env, PYTHONIOENCODING: 'utf-8' } },
    )
    const info = JSON.parse(stdout.trim().split('\n').pop() || '{}')
    const [major, minor] = info.version || [0, 0]
    return {
      file,
      version: `${major}.${minor}`,
      pythonOk: major > 3 || (major === 3 && minor >= 9),
      deps: { pymupdf: Boolean(info.pymupdf), markdown: Boolean(info.markdown) },
    }
  } catch {
    return null
  }
}

function manualInstallHint() {
  return [
    '本地模式需要 Python 3.9+ 和 pymupdf / markdown（首次转换会自动在',
    `${venvDir()} 建 venv 并联网安装，约 50MB）。`,
    '如果自动安装失败，可手动执行：',
    `  python3 -m venv "${venvDir()}"`,
    `  "${join(venvDir(), 'bin', 'pip')}" install -r "${REQUIREMENTS}"`,
    '或者：直接用系统/Homebrew Python 装好依赖后，把解释器路径写进环境变量',
    '  PAPER2HTML_PYTHON=/path/to/python3（或用 $DSH_HOME/paper2html/config.json 的 python 字段）。',
  ].join('\n')
}

async function createVenv(basePython) {
  if (!existsSync(venvDir())) mkdirSync(dataDir(), { recursive: true })
  try {
    await execFile(basePython, ['-m', 'venv', venvDir()], { timeout: 180_000 })
  } catch (error) {
    throw new Error(
      `创建 Python venv 失败（${basePython}）: ${error.message}\n` +
        `可以手动执行：\n  ${basePython} -m venv "${venvDir()}"\n或者装好依赖后用 PAPER2HTML_PYTHON 指定解释器。`,
    )
  }
  return join(venvDir(), 'bin', 'python')
}

async function installDeps(python) {
  try {
    await execFile(
      python,
      ['-m', 'pip', 'install', '--disable-pip-version-check', '--quiet', '-r', REQUIREMENTS],
      { timeout: 300_000, env: { ...process.env, PIP_DISABLE_PIP_VERSION_CHECK: '1' } },
    )
  } catch (error) {
    throw new Error(
      `自动安装 Python 依赖失败（首次使用需要联网）：${error.message}\n${manualInstallHint()}`,
    )
  }
}

/**
 * 找到一个能跑本地解析的 Python。
 * - 有 PAPER2HTML_PYTHON 就用它（缺依赖时报错，不偷偷换）；
 * - 有 venv 且依赖齐全就用 venv；
 * - 系统/Homebrew Python 依赖齐全就直接用（本机常见，省掉首次下载）；
 * - 都没有：install=true 时懒建 venv 并装最小依赖。
 * @returns {Promise<{python: string, mode: 'env'|'venv'|'system', version: string}>}
 */
export async function ensurePython({ install = true } = {}) {
  if (cachedRuntime && existsSync(cachedRuntime.python)) return cachedRuntime

  const forced = process.env.PAPER2HTML_PYTHON
  if (forced) {
    const probed = await probePython(forced)
    if (!probed) {
      throw new Error(
        `PAPER2HTML_PYTHON 指向的 Python 不可用：${forced}\n` +
          '请确认路径正确且可执行；或删掉这个环境变量让插件自动探测。',
      )
    }
    if (!probed.pythonOk) {
      throw new Error(`PAPER2HTML_PYTHON 指向的 Python 版本过低（${probed.version}，需要 3.9+）：${forced}`)
    }
    if (!probed.deps.pymupdf || !probed.deps.markdown) {
      const missing = [!probed.deps.pymupdf && 'pymupdf', !probed.deps.markdown && 'markdown'].filter(Boolean)
      throw new Error(
        `PAPER2HTML_PYTHON 指向的 Python 缺依赖: ${missing.join(', ')}（${forced}）\n` +
          `在该解释器里安装即可：\n  "${forced}" -m pip install -r "${REQUIREMENTS}"\n或删掉 PAPER2HTML_PYTHON 让插件用 venv。`,
      )
    }
    cachedRuntime = { python: forced, mode: 'env', version: probed.version }
    return cachedRuntime
  }

  for (const candidate of candidateList()) {
    const probed = await probePython(candidate.file)
    if (!probed || !probed.pythonOk) continue
    if (probed.deps.pymupdf && probed.deps.markdown) {
      cachedRuntime = { python: candidate.file, mode: candidate.mode, version: probed.version }
      return cachedRuntime
    }
  }

  if (!install) return null

  // 没有现成可用的解释器：挑一个能用的基础 Python 建 venv
  const bases = ['/opt/homebrew/bin/python3.11', '/opt/homebrew/bin/python3', '/usr/bin/python3', 'python3']
  let base = ''
  for (const candidate of bases) {
    const probed = await probePython(candidate)
    if (probed && probed.pythonOk) {
      base = candidate
      break
    }
  }
  if (!base) {
    throw new Error(
      '没有找到可用的 Python 3.9+ 解释器。\n' +
        '请先安装 Python 3（macOS: brew install python3），或把已有解释器写进 PAPER2HTML_PYTHON。',
    )
  }

  let venvPython = join(venvDir(), 'bin', 'python')
  if (!existsSync(venvPython)) venvPython = await createVenv(base)
  const probedVenv = await probePython(venvPython)
  if (probedVenv && probedVenv.deps.pymupdf && probedVenv.deps.markdown) {
    cachedRuntime = { python: venvPython, mode: 'venv', version: probedVenv.version }
    return cachedRuntime
  }
  await installDeps(venvPython)
  const probedAfter = await probePython(venvPython)
  if (!probedAfter || !probedAfter.deps.pymupdf || !probedAfter.deps.markdown) {
    throw new Error(`venv 依赖安装后仍不完整（pymupdf/markdown 不可用）。\n${manualInstallHint()}`)
  }
  cachedRuntime = { python: venvPython, mode: 'venv', version: probedAfter.version }
  return cachedRuntime
}

/** 状态自检：不创建 venv、不装依赖、不发起转换。 */
export async function inspectRuntime() {
  const result = { python: null, venv: { exists: existsSync(join(venvDir(), 'bin', 'python')), path: venvDir() } }
  const candidates = candidateList()
  for (const candidate of candidates) {
    const probed = await probePython(candidate.file)
    if (!probed) continue
    if (!result.python) result.python = { ...probed, mode: candidate.mode }
    if (candidate.mode !== 'env' && probed.deps.pymupdf && probed.deps.markdown && probed.pythonOk) {
      result.python = { ...probed, mode: candidate.mode, ready: true }
      break
    }
  }
  if (result.python) {
    result.python = {
      ...result.python,
      ready: Boolean(result.python.pythonOk && result.python.deps.pymupdf && result.python.deps.markdown),
    }
  }
  return result
}

// ---------------------------------------------------------------------------
// 调用转换脚本
// ---------------------------------------------------------------------------

function parseMarker(stdout, prefix) {
  const lines = String(stdout || '').split('\n')
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i].trim()
    if (line.startsWith(prefix)) {
      try {
        return JSON.parse(line.slice(prefix.length))
      } catch {
        return null
      }
    }
  }
  return null
}

export function slugify(value, { maxLength = 80 } = {}) {
  const base = String(value || '')
    .replace(/\.pdf$/i, '')
    .replace(/[^\p{L}\p{N}._-]+/gu, '-')
    .replace(/-+/g, '-')
    .replace(/^[-.]+|[-.]+$/g, '')
  return (base || 'paper').slice(0, maxLength)
}

export function hashOf(value) {
  return createHash('sha1').update(String(value)).digest('hex').slice(0, 12)
}

/**
 * 跑一次转换。input 已由工具层校验；output 为绝对路径。
 * @returns {Promise<object>} python 输出报告 + {python, pythonMode, stderrTail}
 */
export async function runConvert({ input, output, style = 'dark_lab', understand = false }) {
  const runtime = await ensurePython()
  const args = [
    SCRIPT,
    '--input',
    input,
    '--output',
    output,
    '--style',
    style,
    '--engine',
    'auto',
  ]
  if (!understand) args.push('--no-understand')

  const env = {
    ...process.env,
    DSH_HOME: dshHome(),
    PYTHONIOENCODING: 'utf-8',
    PYTHONUNBUFFERED: '1',
    PYTHONWARNINGS: 'ignore',
  }

  let stdout = ''
  let stderr = ''
  try {
    const result = await execFile(runtime.python, args, {
      cwd: PY_DIR,
      timeout: CONVERT_TIMEOUT_MS,
      maxBuffer: 32 * 1024 * 1024,
      env,
    })
    stdout = result.stdout || ''
    stderr = result.stderr || ''
  } catch (error) {
    stdout = error.stdout || ''
    stderr = error.stderr || ''
    const parsedError = parseMarker(stdout, ERROR_PREFIX) || parseMarker(stdout, RESULT_PREFIX)
    if (parsedError && parsedError.error) {
      const wrapped = new Error(parsedError.error)
      wrapped.code = parsedError.errorType || 'convert_failed'
      throw wrapped
    }
    if (error.killed || error.signal === 'SIGTERM' || /ETIMEDOUT/.test(String(error.code))) {
      throw new Error(
        `转换超时（超过 ${Math.round(CONVERT_TIMEOUT_MS / 1000)} 秒）。\n` +
          '大 PDF 建议换 --style 不变但先压缩/拆分 PDF，或改用 arXiv 版本（文件通常更小）。',
      )
    }
    const tail = String(stderr || stdout || error.message || '').trim().split('\n').slice(-8).join('\n')
    throw new Error(
      `Python 转换进程失败（exit=${error.code ?? 'unknown'}）:\n${tail || error.message}`,
    )
  }

  const report = parseMarker(stdout, RESULT_PREFIX)
  if (!report || report.ok !== true || !report.htmlPath) {
    const tail = String(stderr || stdout).trim().split('\n').slice(-8).join('\n')
    throw new Error(`转换没有返回有效结果。\n${tail || '（没有输出）'}`)
  }
  if (!existsSync(report.htmlPath)) {
    throw new Error(`转换结果文件不存在: ${report.htmlPath}`)
  }
  return {
    ...report,
    python: runtime.python,
    pythonMode: runtime.mode,
    stderrTail: String(stderr || '').trim().split('\n').slice(-3).join('\n'),
  }
}

/** 统计导出目录里的 HTML 数量（状态与首页用）。 */
export function listExports(dir = exportsDir()) {
  try {
    return readdirSync(dir)
      .filter((name) => name.endsWith('.html') && !name.startsWith('.'))
      .map((name) => {
        const file = join(dir, name)
        let bytes = 0
        try {
          bytes = statSync(file).size
        } catch {
          bytes = 0
        }
        return { name, path: resolve(file), bytes }
      })
      .sort((a, b) => b.name.localeCompare(a.name))
      .slice(0, 200)
  } catch {
    return []
  }
}

export { CONVERT_TIMEOUT_MS }
