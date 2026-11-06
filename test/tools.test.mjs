// 本地测试 2：工具参数校验 / 输入分类 / 错误信息（不跑真实转换）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { classifyInput, convertTool, statusTool } from '../lib/tools.js'

const tempRoot = mkdtempSync(join(tmpdir(), 'p2h-tools-'))
// 隔离 $DSH_HOME，避免读到本机真实 config.json / 已有 key
process.env.DSH_HOME = join(tempRoot, 'dsh-home')
delete process.env.DEEPSEEK_APIKEY
delete process.env.DEEPSEEK_API_KEY
delete process.env.LLM_API_KEY
delete process.env.DOC2X_APIKEY
delete process.env.PDF2X_APIKEY

function makePdf(name = 'dummy.pdf', bytes = 4096) {
  const file = join(tempRoot, name)
  const head = Buffer.from('%PDF-1.5\n')
  const body = Buffer.alloc(Math.max(0, bytes - head.length), 0x20)
  writeFileSync(file, Buffer.concat([head, body]))
  return file
}

test('classifyInput：空输入报可操作的错误', () => {
  assert.throws(() => classifyInput(''), /input 不能为空/)
  assert.throws(() => classifyInput('   '), /input 不能为空/)
})

test('classifyInput：接受 arXiv 的三种写法', () => {
  const a = classifyInput('https://arxiv.org/abs/1706.03762')
  assert.equal(a.kind, 'arxiv')
  assert.equal(a.arxivId, '1706.03762')
  const b = classifyInput('https://arxiv.org/pdf/2402.19473v2')
  assert.equal(b.kind, 'arxiv')
  assert.equal(b.arxivId, '2402.19473')
  const c = classifyInput('1706.03762')
  assert.equal(c.kind, 'arxiv')
  assert.equal(c.stem, '1706.03762')
})

test('classifyInput：arXiv 链接解析不出 ID 时给出支持形式', () => {
  assert.throws(() => classifyInput('https://arxiv.org/list/cs.CL/recent'), /解析不出 arXiv ID/)
})

test('classifyInput：相对路径 / 不存在的文件 / 非 PDF / 过小文件', () => {
  assert.throws(() => classifyInput('papers/attention.pdf'), /需要绝对路径/)
  assert.throws(() => classifyInput(join(tempRoot, 'nope.pdf')), /找不到 PDF 文件/)
  const txt = join(tempRoot, 'note.txt')
  writeFileSync(txt, 'x'.repeat(2000))
  assert.throws(() => classifyInput(txt), /只支持 \.pdf 文件/)
  const tiny = join(tempRoot, 'tiny.pdf')
  writeFileSync(tiny, '%PDF-1.5\n')
  assert.throws(() => classifyInput(tiny), /PDF 文件过小/)
  const dir = join(tempRoot, 'dir.pdf')
  mkdirSync(dir, { recursive: true })
  assert.throws(() => classifyInput(dir), /应该是文件而不是目录/)
})

test('classifyInput：有效 PDF 返回绝对路径', () => {
  const file = makePdf()
  const target = classifyInput(file)
  assert.equal(target.kind, 'pdf')
  assert.equal(target.value, file)
  assert.equal(target.stem, 'dummy')
})

test('paper2html_convert：缺参数 / 未知参数 / 类型错 / 枚举错', async () => {
  await assert.rejects(() => convertTool.execute({}), /缺少参数 input/)
  await assert.rejects(() => convertTool.execute({ input: '1706.03762', foo: 1 }), /未知参数 foo/)
  await assert.rejects(() => convertTool.execute({ input: '1706.03762', understand: 'yes' }), /understand 应该是布尔值/)
  await assert.rejects(
    () => convertTool.execute({ input: '1706.03762', style: 'paper' }),
    /style 只能是 dark_lab \/ clean_paper \/ neon_tech/,
  )
})

test('paper2html_convert：understand=true 且没有 key 时说明怎么配', async () => {
  await assert.rejects(
    () => convertTool.execute({ input: '1706.03762', understand: true }),
    (error) => {
      assert.match(error.message, /需要 DeepSeek key/)
      assert.match(error.message, /keep|保持|understand=false/)
      assert.match(error.message, /config\.json/)
      return true
    },
  )
})

test('paper2html_convert：outputDir 必须是绝对路径', async () => {
  const file = makePdf('for-outdir.pdf')
  await assert.rejects(
    () => convertTool.execute({ input: file, outputDir: 'relative/out' }),
    /outputDir 必须是绝对路径/,
  )
})

test('paper2html_status：返回结构完整且可读', async () => {
  const value = await statusTool.execute({})
  assert.equal(typeof value.ready, 'boolean')
  assert.equal(typeof value.summary, 'string')
  assert.ok(value.summary.length > 10)
  assert.equal(typeof value.exportCount, 'number')
  assert.equal(typeof value.hasDeepseekKey, 'boolean')
  assert.match(value.exportsDir, /paper2html[/\\]exports$/)
  const rendered = statusTool.output.render({}, value)
  assert.equal(rendered[0].type, 'text')
  assert.equal(rendered[0].text, value.summary)
})

test('paper2html_status：未知参数直接报错', async () => {
  await assert.rejects(() => statusTool.execute({ verbose: true }), /未知参数 verbose/)
})
