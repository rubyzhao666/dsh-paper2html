// 本地测试 1：插件形状 / 工具注册 / skill 注册（不需要 DSH 进程、不发起转换）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { apply, inject, name } from '../lib/index.js'
import { TOOLS } from '../lib/tools.js'
import { createHandler } from '../lib/preview.js'

const ROOT = dirname(fileURLToPath(new URL('.', import.meta.url)))
const SKILL_DIR = join(ROOT, 'skills', 'paper2html')

function fakeCtx() {
  const tools = new Map()
  const providers = []
  const routes = []
  const effects = []
  const ctx = {
    effect(fn) {
      const cleanup = fn()
      effects.push(cleanup)
      return () => {}
    },
    tools: {
      register(tool) {
        tools.set(tool.name, tool)
        return () => tools.delete(tool.name)
      },
    },
    skills: {
      registerProvider(factory) {
        providers.push(factory())
        return () => {}
      },
    },
    webServer: {
      register(route) {
        routes.push(route)
        return () => {}
      },
    },
    logger: { info() {}, warn() {}, error() {} },
  }
  return { ctx, tools, providers, routes, effects }
}

test('exports a host plugin shape', () => {
  assert.equal(name, 'paper2html')
  assert.ok(Array.isArray(inject))
  assert.deepEqual([...inject].sort(), ['skills', 'tools', 'webServer'])
  assert.equal(typeof apply, 'function')
})

test('registers every tool', () => {
  const { ctx, tools } = fakeCtx()
  apply(ctx)
  assert.equal(TOOLS.length, 3)
  for (const tool of TOOLS) {
    assert.ok(tools.get(tool.name), `missing tool ${tool.name}`)
    assert.equal(typeof tools.get(tool.name).execute, 'function')
  }
  assert.ok(tools.get('paper2html_convert'))
  assert.ok(tools.get('paper2html_status'))
  assert.ok(tools.get('paper2html_annotations'))
})

test('registers the bundled skill', async () => {
  const { ctx, providers } = fakeCtx()
  apply(ctx)
  assert.equal(providers.length, 1)
  const listed = await providers[0].list()
  assert.equal(listed.length, 1)
  const skill = listed[0]
  assert.equal(skill.name, 'paper2html')
  assert.match(skill.name, /^[a-z0-9-]+$/)
  assert.ok(skill.description.length > 20)
  const fetched = await providers[0].get(skill)
  assert.equal(typeof fetched.content, 'string')
  assert.ok(!fetched.content.startsWith('---'), 'frontmatter 应该被剥离')
})

test('registers the /paper2html/ read-only preview route', () => {
  const { ctx, routes } = fakeCtx()
  apply(ctx)
  assert.equal(routes.length, 1)
  assert.equal(routes[0].kind, 'prefix')
  assert.equal(routes[0].path, '/paper2html')
  assert.equal(typeof routes[0].handler, 'function')
  assert.equal(typeof createHandler(), 'function')
})

test('tools declare valid raw JSON schemas and render text', () => {
  for (const tool of TOOLS) {
    assert.match(tool.name, /^[a-z][a-z0-9_]+$/)
    assert.ok(tool.description.length > 20)
    assert.equal(tool.parameters.type, 'object')
    assert.equal(tool.parameters.additionalProperties, false)
    assert.equal(tool.output.schema.type, 'object')
    assert.equal(typeof tool.output.render, 'function')
    assert.equal(typeof tool.timeoutMs, 'number')
    for (const [key, prop] of Object.entries(tool.parameters.properties)) {
      assert.ok(prop.type || prop.enum, `参数 ${key} 缺少 type`)
    }
  }
})

test('skill 里引用的工具名和 references 都存在', () => {
  const skillFile = join(SKILL_DIR, 'SKILL.md')
  assert.ok(existsSync(skillFile), '缺少 SKILL.md')
  const text = readFileSync(skillFile, 'utf8')
  const toolNames = new Set(TOOLS.map((tool) => tool.name))
  const mentioned = [...text.matchAll(/`(paper2html_[a-z_]+)`/g)].map((match) => match[1])
  assert.ok(mentioned.length > 0, 'SKILL.md 没有提到任何工具')
  for (const toolName of new Set(mentioned)) {
    assert.ok(toolNames.has(toolName), `SKILL.md 提到不存在的工具 ${toolName}`)
  }
  const refs = [...text.matchAll(/`references\/([\w.-]+\.md)`/g)].map((match) => match[1])
  assert.ok(refs.length >= 4, `references 引用过少: ${refs.length}`)
  for (const ref of new Set(refs)) {
    assert.ok(existsSync(join(SKILL_DIR, 'references', ref)), `缺少 references/${ref}`)
  }
})

test('skill frontmatter description 具体且包含工具名', () => {
  const text = readFileSync(join(SKILL_DIR, 'SKILL.md'), 'utf8')
  const match = text.match(/^---\n([\s\S]*?)\n---\n/)
  assert.ok(match, '缺少 frontmatter')
  const description = (match[1].match(/^description:\s*(.+)$/m) || [])[1] || ''
  assert.ok(description.length >= 40)
  assert.ok(description.includes('paper2html_convert'))
})
