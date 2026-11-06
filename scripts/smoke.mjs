#!/usr/bin/env node
// 手动冒烟脚本（Lead / 开发者用）：真实转换一篇论文并检查产物与预览登记。
//
// 用法：
//   node scripts/smoke.mjs                                  # 默认转 Transformer 论文
//   node scripts/smoke.mjs https://arxiv.org/abs/2402.19473
//   node scripts/smoke.mjs /abs/path/paper.pdf --style clean_paper
import { existsSync, statSync } from 'node:fs'
import { convertTool, previewUrl, statusTool } from '../lib/tools.js'
import { lookupPreview } from '../lib/preview.js'

function parseArgs(argv) {
  const args = { input: argv[0] || 'https://arxiv.org/abs/1706.03762', style: 'dark_lab', understand: false }
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--style' && argv[i + 1]) args.style = argv[++i]
    else if (argv[i] === '--understand') args.understand = true
    else if (argv[i].startsWith('http') || argv[i].endsWith('.pdf') || /^\d{4}\.\d{4,5}/.test(argv[i])) args.input = argv[i]
  }
  return args
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  console.log('=== paper2html smoke ===')
  console.log('input:', args.input, '· style:', args.style, '· understand:', args.understand)

  const status = await statusTool.execute({})
  console.log('\n[status] ready=', status.ready, '| python', status.pythonVersion, status.pythonMode)
  if (status.warnings.length) console.log('[status] warnings:', status.warnings.join('；'))

  const started = Date.now()
  const result = await convertTool.execute({ input: args.input, style: args.style, understand: args.understand })
  const seconds = ((Date.now() - started) / 1000).toFixed(1)

  console.log(`\n[convert] ${seconds}s · title=${result.title}`)
  console.log('  htmlPath :', result.htmlPath, `${(result.bytes / 1024).toFixed(0)} KB`)
  console.log('  engine   :', result.engine, '| pages:', result.pages, '| understand:', result.understand)
  console.log('  preview  :', result.previewUrl || result.previewPath)
  if (result.warnings.length) console.log('  warnings :', result.warnings.join('；'))

  if (!existsSync(result.htmlPath)) throw new Error('HTML 文件不存在')
  if (statSync(result.htmlPath).size < 10_000) throw new Error('HTML 文件过小，可能渲染失败')
  const id = result.previewPath.split('/').pop()
  const entry = lookupPreview(id)
  if (!entry) throw new Error('预览登记表里找不到这次转换')
  console.log('  registry :', entry.name, '->', entry.file)
  console.log('\n[render]', convertTool.output.render({}, result)[0].text)
  console.log('\n✅ smoke 通过:', previewUrl(result.previewPath))
}

main().catch((error) => {
  console.error('\n❌ smoke 失败:', error.message)
  process.exit(1)
})
