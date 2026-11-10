// 发布安全回归：确保插件包里没有作者的 API key / 私钥 / .env 配置。
// 这个测试会在每次 npm test 时运行；发现疑似密钥直接失败，防止误提交。
import test from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const SKIP_DIRS = new Set(['node_modules', '.git', 'test', 'dist', 'coverage', '.next', '.cache'])
const SKIP_EXT = /\.(?:tgz|zip|png|jpg|jpeg|webp|gif|pdf|woff2?|ttf|ico)$/i

const SECRET_PATTERNS = [
  ['OpenAI / DeepSeek 风格 key', /sk-[A-Za-z0-9]{20,}/],
  ['GitHub token', /gh[opsu]_[A-Za-z0-9]{20,}/],
  ['AWS access key', /AKIA[0-9A-Z]{16}/],
  ['私钥文件内容', /BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY/],
  ['赋值式密钥', /(?:api[_-]?key|apikey|secret|token)\s*[:=]\s*['"][A-Za-z0-9_\-]{16,}['"]/i],
]

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue
    const file = join(dir, name)
    const stat = statSync(file)
    if (stat.isDirectory()) walk(file, out)
    else if (!SKIP_EXT.test(name)) out.push(file)
  }
  return out
}

test('发布目录不包含 API key / 私钥 / .env（防止消耗作者的 key）', () => {
  const files = walk(ROOT)
  const hits = []
  for (const file of files) {
    const rel = relative(ROOT, file)
    if (/(^|\/)\.env(?:\.|$)/.test(rel) || /(^|\/)config\.json$/.test(rel)) {
      hits.push(`${rel}: 环境变量 / 密钥配置文件不应进入发布包`)
      continue
    }
    let text
    try {
      text = readFileSync(file, 'utf8')
    } catch {
      continue
    }
    for (const [name, pattern] of SECRET_PATTERNS) {
      const match = text.match(pattern)
      if (match) hits.push(`${rel}: ${name} → ${match[0].slice(0, 24)}…`)
    }
  }
  assert.deepEqual(hits, [], `发现疑似密钥（不要提交，也不要用作者自己的 key）：\n${hits.join('\n')}`)
  assert.ok(files.length >= 5, `扫描文件数异常：${files.length}`)
  console.log(`secret-scan: ${files.length} 个文件，0 命中`)
})
