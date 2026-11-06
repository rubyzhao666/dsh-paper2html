// 本地测试 5：AI 理解层（有 key 路径）——用本地 mock LLM 服务验证整条链路，
// 不需要真的 DeepSeek key、不需要联网、也不需要安装 openai SDK（插件内置 urllib 客户端）。
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { createServer } from 'node:http'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { convertTool } from '../lib/tools.js'

const tempRoot = mkdtempSync(join(tmpdir(), 'p2h-understand-'))
process.env.DSH_HOME = join(tempRoot, 'dsh')

function findPython() {
  const candidates = [process.env.PAPER2HTML_PYTHON, '/opt/homebrew/bin/python3.11', '/usr/bin/python3', 'python3'].filter(Boolean)
  for (const python of candidates) {
    try {
      execFileSync(python, ['-c', 'import pymupdf'], { stdio: 'ignore', timeout: 20_000 })
      return python
    } catch {
      // 换下一个
    }
  }
  return ''
}

const python = findPython()
const skip = !python || process.env.PAPER2HTML_SKIP_E2E === '1'

function makeFixturePdf() {
  const script = join(tempRoot, 'make_fixture.py')
  const pdf = join(tempRoot, 'fixture-understand.pdf')
  writeFileSync(
    script,
    `import pymupdf
doc = pymupdf.open()
p = doc.new_page()
lines = [
    ("Understanding Mock Test Paper", 20, 34),
    ("Alice Zhang, Bob Li, Carol Wang", 11, 26),
    ("Abstract", 13, 20),
    ("This paper checks that the AI understanding layer works through an OpenAI-compatible endpoint. " * 3, 10, 13),
    ("1 Introduction", 13, 20),
    ("The pipeline extracts the paper locally and then asks the model for summaries. " * 4, 10, 13),
]
y = 80
for text, size, gap in lines:
    p.insert_text((72, y), text[:95], fontsize=size, fontname="helv")
    y += gap
p2 = doc.new_page()
p2.insert_text((72, 80), "2 Method", fontsize=13, fontname="helv")
p2.insert_text((72, 110), "More body text for the second page. " * 5, fontsize=10, fontname="helv")
doc.save("${pdf}")
`,
  )
  execFileSync(python, [script], { stdio: 'ignore', timeout: 60_000 })
  return pdf
}

function mockLlmContent(userPrompt) {
  if (userPrompt.includes('精炼摘要')) {
    return JSON.stringify({
      section_title: 'Abstract',
      summary: 'Mock section summary.',
      key_points: ['Mock point'],
      formulas: [],
      tables: [],
      figures: [],
    })
  }
  if (userPrompt.includes('生成三分钟摘要')) {
    return JSON.stringify({ key_findings: ['Mock finding 1', 'Mock finding 2'], innovation: 'Mock innovation', significance: 'Mock significance' })
  }
  if (userPrompt.includes('提取完整的结构化数据')) {
    return JSON.stringify({
      title: 'Understanding Mock Test Paper',
      authors: ['Alice Zhang'],
      abstract_summary: 'Mock abstract summary.',
      research_question: 'Mock research question',
      methodology: 'Mock methodology',
      contributions: ['Mock contribution'],
      experiment_results: [],
      limitations: [],
      future_work: '',
      mermaid_architecture: 'flowchart TD\n    A[Input] --> B[Output]',
      experiment_table: null,
    })
  }
  return 'Mock TL;DR: this paper tests the understanding pipeline.'
}

function startMockLlm() {
  const server = createServer((req, res) => {
    let body = ''
    req.on('data', (chunk) => {
      body += chunk
    })
    req.on('end', () => {
      let payload = {}
      try {
        payload = JSON.parse(body)
      } catch {
        return res.writeHead(400).end('bad json')
      }
      const userPrompt = (payload.messages || [])
        .filter((message) => message.role === 'user')
        .map((message) => message.content)
        .join('\n')
      const content = mockLlmContent(userPrompt)
      res.writeHead(200, { 'content-type': 'application/json' })
      res.end(
        JSON.stringify({
          id: 'mock',
          model: payload.model || 'mock',
          choices: [{ index: 0, message: { role: 'assistant', content } }],
          usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
        }),
      )
    })
  })
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }))
  })
}

test('understand=true：通过 OpenAI 兼容端点生成 AI 摘要（无需 openai SDK）', { skip, timeout: 180_000 }, async () => {
  const pdf = makeFixturePdf()
  const { server, port } = await startMockLlm()
  const saved = {
    key: process.env.DEEPSEEK_APIKEY,
    base: process.env.DEEPSEEK_BASE_URL,
  }
  process.env.DEEPSEEK_APIKEY = 'mock-key'
  process.env.DEEPSEEK_BASE_URL = `http://127.0.0.1:${port}/v1`
  try {
    const result = await convertTool.execute({
      input: pdf,
      outputDir: join(tempRoot, 'out'),
      understand: true,
      style: 'dark_lab',
    })
    assert.equal(result.understand, true, `AI 摘要没有生效，warnings: ${JSON.stringify(result.warnings)}`)
    assert.equal(result.engine, 'local')
    assert.ok(result.bytes > 20_000)

    const html = readFileSync(result.htmlPath, 'utf8')
    assert.match(html, /Mock TL;DR/, '页面里应该有 mock 的 TL;DR')
    assert.match(html, /Mock innovation/, '页面里应该有 mock 的关键发现/创新点')
    assert.match(html, /flowchart TD/, '页面里应该有 mock 生成的 Mermaid 代码')
    // AI 摘要生效后，原本空的关键发现卡片应该出现
    assert.match(html, /关键发现/)
  } finally {
    process.env.DEEPSEEK_APIKEY = saved.key
    process.env.DEEPSEEK_BASE_URL = saved.base
    if (saved.key === undefined) delete process.env.DEEPSEEK_APIKEY
    if (saved.base === undefined) delete process.env.DEEPSEEK_BASE_URL
    await new Promise((resolve) => server.close(resolve))
  }
})
