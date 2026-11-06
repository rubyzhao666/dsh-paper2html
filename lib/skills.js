// 把插件自带的 skills/<name>/SKILL.md 注册进 DSH 的 skill 目录（ctx.skills）。
// 每个插件独立发布，所以这段实现按包复制一份，不要跨包 import。
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const RANK = 600
const INVOCATION = { modelInvocable: true, userInvocable: true }

// 解析 SKILL.md 的 YAML frontmatter，只取 name / description。
// description 支持单行、引号包裹，以及 `>` / `|` 折叠块（上游 skill 常见写法）。
export function parseSkillFile(file) {
  const text = readFileSync(file, 'utf8')
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/)
  if (!m) return null
  const field = (key) => {
    const one = m[1].match(new RegExp(`^${key}:[ \\t]*(.+)$`, 'm'))
    if (one) return one[1].trim().replace(/^(["'])(.*)\1$/, '$2')
    const block = m[1].match(new RegExp(`^${key}:[ \\t]*[>|][-+]?[ \\t]*\\n((?:[ \\t]+.*(?:\\n|$))+)`, 'm'))
    if (!block) return undefined
    return block[1].split('\n').map((l) => l.trim()).filter(Boolean).join(' ')
  }
  const name = field('name')
  const description = field('description')
  return name && description ? { name, description, body: text.slice(m[0].length) } : null
}

function readDir(dir) {
  if (!existsSync(dir)) return []
  return readdirSync(dir, { withFileTypes: true })
    .filter((d) => d.isDirectory() && existsSync(join(dir, d.name, 'SKILL.md')))
    .map((d) => ({ dir: join(dir, d.name), file: join(dir, d.name, 'SKILL.md'), ...parseSkillFile(join(dir, d.name, 'SKILL.md')) }))
    .filter((s) => s.name)
}

export function readSkills(dirs) {
  return [].concat(dirs).flatMap(readDir)
}

// providerName / dirs 由调用方给出；skill 正文里的 <SKILL_ROOT> 会被替换成该 skill 的实际目录。
export function createSkillProvider({ providerName, dirs, pluginRoot }) {
  const all = () => readSkills(dirs)
  const candidate = (s) => ({
    name: s.name,
    description: s.description,
    path: s.file,
    invocation: INVOCATION,
    source: 'bundled',
    provider: providerName,
    rank: RANK,
    locator: s.dir,
    resourceBase: { kind: 'directory', path: s.dir },
  })
  return {
    name: providerName,
    async list() {
      return all().map(candidate)
    },
    async get(c) {
      const s = all().find((x) => x.dir === c.locator && x.name === c.name)
      if (!s) return undefined
      const content = s.body.replaceAll('<SKILL_ROOT>', s.dir).replaceAll('<PLUGIN_ROOT>', pluginRoot)
      const { rank: _rank, locator: _locator, ...summary } = candidate(s)
      return { ...summary, content }
    },
  }
}
