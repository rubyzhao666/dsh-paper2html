// 本地测试 4：端到端 —— 用 Python(PyMuPDF) 现场生成一个两页论文 PDF，
// 再通过 paper2html_convert 走完整本地解析 + 渲染链路。
// 没有可用 Python / PyMuPDF 时整组跳过（不影响其他测试）。
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, realpathSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { convertTool } from '../lib/tools.js'

const tempRoot = mkdtempSync(join(tmpdir(), 'p2h-e2e-'))
process.env.DSH_HOME = join(tempRoot, 'dsh')
delete process.env.DEEPSEEK_APIKEY
delete process.env.DEEPSEEK_API_KEY

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
  const pdf = join(tempRoot, 'fixture-paper.pdf')
  writeFileSync(
    script,
    `import pymupdf

doc = pymupdf.open()

def add_page(lines):
    page = doc.new_page()
    y = 80
    for text, size, gap in lines:
        page.insert_text((72, y), text, fontsize=size, fontname="helv")
        y += gap
    return page

abstract = "This paper studies whether a local PDF parser can produce a readable HTML page. " * 4
intro = "Recurrent networks process tokens sequentially. Attention lets models look at all positions at once. " * 5

add_page([
    ("Local Parser Test Paper", 20, 34),
    ("Alice Zhang, Bob Li, Carol Wang", 11, 26),
    ("Abstract", 13, 20),
    (abstract[:90], 10, 13),
    (abstract[90:180], 10, 13),
    (abstract[180:270], 10, 24),
    ("1 Introduction", 13, 20),
    (intro[:90], 10, 13),
    (intro[90:180], 10, 13),
    (intro[180:270], 10, 13),
])

add_page([
    ("2 Method", 13, 24),
    (intro[270:360], 10, 13),
    (intro[360:450], 10, 13),
    (intro[450:540], 10, 13),
])

doc.save("${pdf}")
print("${pdf}")
`,
  )
  execFileSync(python, [script], { stdio: 'ignore', timeout: 60_000 })
  return pdf
}

test('本地转换端到端：生成 HTML、登记预览、返回符合 schema', { skip, timeout: 180_000 }, async () => {
  const pdf = makeFixturePdf()
  const outDir = join(tempRoot, 'out')
  const result = await convertTool.execute({ input: pdf, outputDir: outDir, style: 'clean_paper' })

  assert.equal(result.engine, 'local')
  assert.equal(result.style, 'clean_paper')
  assert.equal(result.understand, false)
  assert.match(result.title, /Local Parser Test Paper/)
  assert.equal(result.pages, 2)
  assert.ok(result.bytes > 20_000, `HTML 体积过小: ${result.bytes}`)
  assert.ok(existsSync(result.htmlPath), 'HTML 文件不存在')
  assert.ok(realpathSync(result.htmlPath).startsWith(realpathSync(outDir)), 'HTML 应在指定输出目录')
  assert.match(result.previewPath, /^\/paper2html\/p\/[a-f0-9]{12}$/)
  assert.ok(Array.isArray(result.warnings))

  const html = readFileSync(result.htmlPath, 'utf8')
  assert.match(html, /Local Parser Test Paper/)
  assert.match(html, /<h2[^>]*>[^<]*Abstract/)
  assert.match(html, /<h2[^>]*>[^<]*1 Introduction/)
  assert.match(html, /clean_paper/)
  // 无 AI 摘要时不该出现空的「关键发现」卡片或空 Mermaid 错误
  assert.ok(!html.includes('Syntax error in text'))
  assert.ok(!html.includes('暂无关键发现'))

  // 输出 schema 里的字段都能对上
  const schema = convertTool.output.schema
  for (const key of schema.required) assert.ok(result[key] !== undefined, `缺少返回字段 ${key}`)
  for (const key of Object.keys(result)) assert.ok(schema.properties[key], `schema 未声明的返回字段 ${key}`)

  const rendered = convertTool.output.render({}, result)
  assert.equal(rendered[0].type, 'text')
  assert.match(rendered[0].text, /已生成论文阅读页/)
  assert.match(rendered[0].text, /paper2html/)
})

test('本地转换端到端：同一篇重复转换幂等（覆盖同名文件）', { skip, timeout: 180_000 }, async () => {
  const pdf = makeFixturePdf()
  const outDir = join(tempRoot, 'out-idempotent')
  const first = await convertTool.execute({ input: pdf, outputDir: outDir, style: 'dark_lab' })
  const second = await convertTool.execute({ input: pdf, outputDir: outDir, style: 'dark_lab' })
  assert.equal(first.htmlPath, second.htmlPath)
  assert.equal(first.previewPath, second.previewPath)
})

test('扫描件 / 无文本层 PDF 给出可操作错误', { skip, timeout: 120_000 }, async () => {
  const script = join(tempRoot, 'make_blank.py')
  const pdf = join(tempRoot, 'blank.pdf')
  writeFileSync(
    script,
    `import pymupdf\ndoc = pymupdf.open()\ndoc.new_page()\ndoc.new_page()\ndoc.save("${pdf}")\n`,
  )
  execFileSync(python, [script], { stdio: 'ignore', timeout: 60_000 })
  await assert.rejects(
    () => convertTool.execute({ input: pdf, outputDir: join(tempRoot, 'out-blank') }),
    (error) => {
      assert.match(error.message, /扫描件|没有可提取的文本层/)
      assert.match(error.message, /DOC2X|OCR|arXiv/)
      return true
    },
  )
})
