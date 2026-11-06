// 本地测试 7：批注 Host 侧存储（0.3.0 G3）—— docId 校验 / 原子读写 / 损坏容错 / 上限
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  AnnotationStoreError,
  DOC_ID_PATTERN,
  MAX_ANNOTATIONS,
  annotationFilePath,
  annotationsDir,
  assertDocId,
  extractDocIdFromHtml,
  isValidDocId,
  listDocuments,
  normalizeAnnotationList,
  readAnnotations,
  writeAnnotations,
} from '../lib/annotations-store.js'

const tempRoot = mkdtempSync(join(tmpdir(), 'p2h-store-'))
process.env.DSH_HOME = join(tempRoot, 'dsh')

function sampleAnnotation(overrides = {}) {
  return {
    id: 'p2h-test-1',
    color: 'yellow',
    note: '这是一条测试批注',
    quote: { exact: 'The Transformer follows this overall architecture', prefix: 'prefix-', suffix: '-suffix' },
    sectionId: '3 Model Architecture',
    createdAt: '2026-11-06T02:00:00.000Z',
    ...overrides,
  }
}

test('docId 校验规则', () => {
  assert.ok(isValidDocId('arxiv-1706.03762'))
  assert.ok(isValidDocId('pdf-1a2b3c4d5e6f7890'))
  assert.ok(isValidDocId('a'))
  assert.ok(isValidDocId('A_b.c-9'))
  assert.ok(!isValidDocId(''))
  assert.ok(!isValidDocId('.hidden'))
  assert.ok(!isValidDocId('-abc'))
  assert.ok(!isValidDocId('a/b'))
  assert.ok(!isValidDocId('a\\b'))
  assert.ok(!isValidDocId('a'.repeat(129)))
  assert.ok(!isValidDocId(null))
  assert.ok(!isValidDocId(42))
  assert.ok(DOC_ID_PATTERN.test('arxiv-1706.03762'))
  assert.throws(() => assertDocId('../etc/passwd'), (error) => {
    assert.ok(error instanceof AnnotationStoreError)
    assert.equal(error.code, 'invalid_docid')
    assert.match(error.message, /docId 不合法/)
    return true
  })
})

test('写入 / 读取往返 + 原子写（无临时文件残留）', () => {
  const docId = 'arxiv-1706.03762'
  assert.deepEqual(readAnnotations(docId), { docId, annotations: [], updatedAt: '' })
  const result = writeAnnotations(docId, [sampleAnnotation()])
  assert.equal(result.count, 1)
  assert.ok(result.updatedAt)
  assert.ok(existsSync(annotationFilePath(docId)), '存储文件应该存在')
  const onDisk = JSON.parse(readFileSync(annotationFilePath(docId), 'utf8'))
  assert.equal(onDisk.version, 1)
  assert.equal(onDisk.docId, docId)
  assert.ok(Array.isArray(onDisk.annotations) && onDisk.annotations.length === 1)

  const record = readAnnotations(docId)
  assert.equal(record.docId, docId)
  assert.equal(record.annotations.length, 1)
  assert.deepEqual(record.annotations[0], sampleAnnotation())
  assert.equal(record.updatedAt, result.updatedAt)

  const leftovers = readdirSync(annotationsDir()).filter((name) => name.endsWith('.tmp'))
  assert.deepEqual(leftovers, [], '不应有临时文件残留')
})

test('覆盖写：第二次写入替换全部批注', () => {
  const docId = 'pdf-coverwrite'
  writeAnnotations(docId, [sampleAnnotation({ id: 'a1' }), sampleAnnotation({ id: 'a2' })])
  assert.equal(readAnnotations(docId).annotations.length, 2)
  writeAnnotations(docId, [sampleAnnotation({ id: 'a3', color: 'blue', note: '改过' })])
  const record = readAnnotations(docId)
  assert.equal(record.annotations.length, 1)
  assert.equal(record.annotations[0].id, 'a3')
  assert.equal(record.annotations[0].color, 'blue')
  assert.equal(record.annotations[0].note, '改过')
})

test('损坏 / 非法内容容错返回空数组，不抛异常', () => {
  const docId = 'pdf-corrupt'
  const file = annotationFilePath(docId)
  writeAnnotations(docId, [sampleAnnotation()])
  writeFileSync(file, '{this is not json', 'utf8')
  assert.deepEqual(readAnnotations(docId), { docId, annotations: [], updatedAt: '' })
  writeFileSync(file, '{"version":1,"annotations":"not-array"}', 'utf8')
  assert.deepEqual(readAnnotations(docId), { docId, annotations: [], updatedAt: '' })
  writeFileSync(file, '[]', 'utf8')
  assert.equal(readAnnotations(docId).annotations.length, 0)
  // 部分条目损坏：保留合法条目
  writeFileSync(
    file,
    JSON.stringify({
      version: 1,
      docId,
      updatedAt: '2026-01-01T00:00:00.000Z',
      annotations: [sampleAnnotation(), { id: 'bad', color: 'red' }, sampleAnnotation({ id: 'ok-2' })],
    }),
    'utf8',
  )
  const record = readAnnotations(docId)
  assert.deepEqual(record.annotations.map((item) => item.id), ['p2h-test-1', 'ok-2'])
})

test('超限：>500 条拒绝；>512KB 拒绝为 too_large', () => {
  const docId = 'pdf-limits'
  const tooMany = Array.from({ length: MAX_ANNOTATIONS + 1 }, (_, index) => sampleAnnotation({ id: `a-${index}` }))
  assert.throws(() => writeAnnotations(docId, tooMany), (error) => {
    assert.equal(error.code, 'invalid')
    assert.match(error.message, /超过上限 500/)
    return true
  })
  assert.throws(() => normalizeAnnotationList('not-array'), /annotations 必须是数组/)

  const bigNotes = Array.from({ length: 400 }, (_, index) =>
    sampleAnnotation({ id: `big-${index}`, note: 'x'.repeat(1800), quote: { exact: 'y'.repeat(1500) } }),
  )
  assert.throws(() => writeAnnotations(docId, bigNotes), (error) => {
    assert.equal(error.code, 'too_large')
    assert.match(error.message, /512KB/)
    return true
  })
})

test('条目字段校验：非法 color / 缺 quote.exact / note 超长都拒绝', () => {
  const docId = 'pdf-validate'
  for (const bad of [
    sampleAnnotation({ color: 'red' }),
    sampleAnnotation({ quote: { exact: '' } }),
    sampleAnnotation({ note: 'x'.repeat(2001) }),
    sampleAnnotation({ id: 'x'.repeat(65) }),
    { id: 'no-color', quote: { exact: 'abc' } },
  ]) {
    assert.throws(() => writeAnnotations(docId, [bad]), (error) => {
      assert.equal(error.code, 'invalid')
      return true
    })
  }
})

test('listDocuments：只列有批注的文档、按 updatedAt 降序、跳过损坏文件', () => {
  const root = join(tempRoot, 'list-dsh')
  process.env.DSH_HOME = root
  writeAnnotations('arxiv-old', [sampleAnnotation({ id: 'old-1' })])
  writeAnnotations('arxiv-new', [sampleAnnotation({ id: 'new-1' }), sampleAnnotation({ id: 'new-2' })])
  writeAnnotations('pdf-empty', [])
  writeFileSync(annotationFilePath('pdf-broken'), '{broken', 'utf8')
  const documents = listDocuments()
  assert.deepEqual(documents.map((item) => item.docId).sort(), ['arxiv-new', 'arxiv-old'])
  const byId = Object.fromEntries(documents.map((item) => [item.docId, item]))
  assert.equal(byId['arxiv-new'].count, 2)
  assert.equal(byId['arxiv-old'].count, 1)
  for (const item of documents) assert.ok(item.updatedAt)
  process.env.DSH_HOME = join(tempRoot, 'dsh')
})

test('extractDocIdFromHtml：取 meta p2h-doc-id，缺失/异常返回空串', () => {
  assert.equal(
    extractDocIdFromHtml('<html><head><meta name="p2h-doc-id" content="arxiv-1706.03762"><meta charset="utf-8"></head></html>'),
    'arxiv-1706.03762',
  )
  assert.equal(extractDocIdFromHtml("<meta content='pdf-abc.def' name='p2h-doc-id'>"), 'pdf-abc.def')
  assert.equal(extractDocIdFromHtml('<html><head><meta charset="utf-8"></head></html>'), '')
  assert.equal(extractDocIdFromHtml(''), '')
})
