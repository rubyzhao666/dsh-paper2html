// 本地测试 9：paper2html_annotations 工具（0.3.0 G3）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { annotationsTool } from '../lib/tools.js'
import { writeAnnotations } from '../lib/annotations-store.js'

const tempRoot = mkdtempSync(join(tmpdir(), 'p2h-tool-annotations-'))
// 每次测试前指向独立 DSH_HOME（tools/store 都是运行时读取 env）
function useFreshHome(name) {
  const home = join(tempRoot, name)
  mkdirSync(home, { recursive: true })
  process.env.DSH_HOME = home
  return home
}

function sampleAnnotation(overrides = {}) {
  return {
    id: 'p2h-note-1',
    color: 'pink',
    note: '这里提出了一个新架构',
    quote: { exact: 'The Transformer follows this overall architecture', prefix: '', suffix: '' },
    sectionId: '3 Model Architecture',
    createdAt: '2026-11-06T02:00:00.000Z',
    ...overrides,
  }
}

test('无参数：列出有批注的文档（空 → 可操作提示）', async () => {
  useFreshHome('empty')
  const empty = await annotationsTool.execute({})
  assert.equal(empty.count, 0)
  assert.deepEqual(empty.documents, [])
  const rendered = annotationsTool.output.render({}, empty)
  assert.match(rendered[0].text, /还没有同步的批注/)
  assert.match(rendered[0].text, /DSH Web 预览页/)

  useFreshHome('list')
  writeAnnotations('arxiv-1706.03762', [sampleAnnotation()])
  writeAnnotations('pdf-abc123', [
    sampleAnnotation({ id: 'p2h-note-2', color: 'blue', note: '第二条' }),
    sampleAnnotation({ id: 'p2h-note-3', color: 'yellow', note: '' }),
  ])
  const listed = await annotationsTool.execute({})
  assert.equal(listed.count, 2)
  assert.equal(listed.documents.length, 2)
  const byId = Object.fromEntries(listed.documents.map((item) => [item.docId, item]))
  assert.equal(byId['arxiv-1706.03762'].count, 1)
  assert.equal(byId['pdf-abc123'].count, 2)
  for (const item of listed.documents) assert.ok(item.updatedAt)
  const text = annotationsTool.output.render({}, listed)[0].text
  assert.match(text, /2 篇论文的批注/)
  assert.match(text, /传 docId 或 htmlPath/)
})

test('docId：读取批注（顺序、字段、limit）', async () => {
  useFreshHome('read')
  writeAnnotations('arxiv-1706.03762', [
    sampleAnnotation(),
    sampleAnnotation({ id: 'p2h-note-2', color: 'blue', note: '第二条批注', quote: { exact: 'We propose a new simple network architecture' } }),
    sampleAnnotation({ id: 'p2h-note-3', color: 'green', note: '', quote: { exact: 'Attention(Q, K, V )' } }),
  ])
  const full = await annotationsTool.execute({ docId: 'arxiv-1706.03762' })
  assert.equal(full.count, 3)
  assert.equal(full.docId, 'arxiv-1706.03762')
  assert.ok(full.updatedAt)
  assert.equal(full.annotations.length, 3)
  assert.equal(full.annotations[0].id, 'p2h-note-1')
  assert.equal(full.annotations[0].note, '这里提出了一个新架构')
  assert.equal(full.annotations[0].quoteExcerpt, 'The Transformer follows this overall architecture')
  assert.equal(full.annotations[0].sectionId, '3 Model Architecture')
  assert.ok(full.annotations[0].createdAt)

  const limited = await annotationsTool.execute({ docId: 'arxiv-1706.03762', limit: 1 })
  assert.equal(limited.count, 3)
  assert.equal(limited.annotations.length, 1)
  const rendered = annotationsTool.output.render({}, limited)[0].text
  assert.match(rendered, /共 3 条批注/)
  assert.match(rendered, /已列出前 1 条/)

  const renderedFull = annotationsTool.output.render({}, full)[0].text
  assert.match(renderedFull, /这里提出了一个新架构/)
  assert.match(renderedFull, /仅高亮/)
})

test('htmlPath：从 meta[name=p2h-doc-id] 读 docId', async () => {
  useFreshHome('html')
  writeAnnotations('arxiv-html-path', [sampleAnnotation({ note: '来自 htmlPath' })])
  const dir = join(tempRoot, 'html-files')
  mkdirSync(dir, { recursive: true })
  const html = join(dir, 'paper.html')
  writeFileSync(
    html,
    '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="p2h-doc-id" content="arxiv-html-path"></head><body>x</body></html>',
  )
  const result = await annotationsTool.execute({ htmlPath: html })
  assert.equal(result.count, 1)
  assert.equal(result.docId, 'arxiv-html-path')
  assert.equal(result.annotations[0].note, '来自 htmlPath')
})

test('错误路径：非法 docId / 缺失 htmlPath / 无 meta / 相对路径 / 参数冲突都报可操作错误', async () => {
  useFreshHome('errors')
  await assert.rejects(() => annotationsTool.execute({ docId: '../etc/passwd' }), /docId 不合法/)
  await assert.rejects(() => annotationsTool.execute({ htmlPath: '/no/such/file.html' }), /找不到 HTML 文件/)
  await assert.rejects(() => annotationsTool.execute({ htmlPath: 'relative.html' }), /绝对路径/)

  const dir = join(tempRoot, 'error-files')
  mkdirSync(dir, { recursive: true })
  const noMeta = join(dir, 'no-meta.html')
  writeFileSync(noMeta, '<html><body>no meta</body></html>')
  await assert.rejects(() => annotationsTool.execute({ htmlPath: noMeta }), /没有 <meta name="p2h-doc-id">/)

  await assert.rejects(
    () => annotationsTool.execute({ docId: 'arxiv-x', htmlPath: noMeta }),
    /docId 和 htmlPath 只能给一个/,
  )
})

test('参数校验：limit 范围 / 类型错误 / 未知参数', async () => {
  useFreshHome('params')
  for (const limit of [0, -1, 201, 3.5, '10']) {
    await assert.rejects(
      () => annotationsTool.execute({ docId: 'arxiv-x', limit }),
      /limit/,
      `limit=${JSON.stringify(limit)} 应该报错`,
    )
  }
  await assert.rejects(() => annotationsTool.execute({ unknown: 1 }), /未知参数 unknown/)
  const ok = await annotationsTool.execute({ docId: 'arxiv-ok', limit: 5 })
  assert.equal(ok.count, 0)
})

test('损坏存储容错：读取返回 0 条而不崩溃', async () => {
  const home = useFreshHome('corrupt')
  mkdirSync(join(home, 'paper2html', 'annotations'), { recursive: true })
  writeFileSync(join(home, 'paper2html', 'annotations', 'arxiv-broken.json'), '{broken json', 'utf8')
  const result = await annotationsTool.execute({ docId: 'arxiv-broken' })
  assert.equal(result.count, 0)
  assert.deepEqual(result.annotations, [])
})

test('返回结构符合 output.schema（声明字段/必填项）', async () => {
  useFreshHome('schema')
  writeAnnotations('arxiv-schema', [sampleAnnotation()])
  const schema = annotationsTool.output.schema
  assert.equal(schema.type, 'object')
  assert.deepEqual(schema.required, ['count'])
  const docResult = await annotationsTool.execute({ docId: 'arxiv-schema' })
  for (const key of Object.keys(docResult)) {
    assert.ok(schema.properties[key], `返回字段 ${key} 未在 schema 中声明`)
  }
  for (const key of schema.required) assert.notEqual(docResult[key], undefined, `缺少必填返回字段 ${key}`)
  const itemSchema = schema.properties.annotations.items
  for (const item of docResult.annotations) {
    for (const key of Object.keys(item)) {
      assert.ok(itemSchema.properties[key], `批注字段 ${key} 未在 schema 中声明`)
    }
    for (const key of itemSchema.required) assert.notEqual(item[key], undefined, `批注缺少必填字段 ${key}`)
  }
  const listResult = await annotationsTool.execute({})
  for (const key of Object.keys(listResult)) {
    assert.ok(schema.properties[key], `列表返回字段 ${key} 未在 schema 中声明`)
  }
  for (const doc of listResult.documents) {
    for (const key of Object.keys(doc)) {
      assert.ok(schema.properties.documents.items.properties[key], `文档字段 ${key} 未在 schema 中声明`)
    }
  }
})
