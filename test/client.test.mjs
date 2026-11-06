// 本地测试 10：浏览器半边 client（0.4.0 H2）—— package 声明 / node --check / 静态契约 / 加载后注册两个 slot
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'

const ROOT = dirname(fileURLToPath(new URL('.', import.meta.url)))
const CLIENT = join(ROOT, 'lib', 'client.js')
const PKG = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'))

function loadClient() {
  const source = readFileSync(CLIENT, 'utf8')
  const loaded = []
  const sandbox = {
    window: { __ModuleLoader__: { load(config) { loaded.push(config) } } },
    console,
  }
  vm.runInNewContext(source, sandbox, { filename: 'lib/client.js' })
  assert.equal(loaded.length, 1, 'client.js 应该调用一次 window.__ModuleLoader__.load')
  const factory = loaded[0].factory
  const React = {
    createElement(tag, props, ...children) {
      return { tag, props: props || {}, children }
    },
  }
  const moduleExports = factory((name) => {
    if (name === 'react') return React
    throw new Error(`client.js 不应 require 其它模块：${name}`)
  })
  return { config: loaded[0], exports: moduleExports }
}

test('package.json 声明 client 半边（dsh.client / exports["./client"] / files）', () => {
  assert.equal(PKG.dsh.client?.platform, 'web')
  assert.deepEqual(PKG.dsh.client?.inject, [])
  assert.equal(PKG.exports?.['./client'], './lib/client.js')
  const files = PKG.files || []
  assert.ok(files.includes('lib') || files.includes('lib/client.js'), 'files 应包含 lib 或 lib/client.js')
  assert.ok(existsSync(CLIENT), '缺少 lib/client.js')
  assert.ok(existsSync(join(ROOT, 'cordis.patch.yml')), '缺少 cordis.patch.yml')
})

test('client.js 通过 node --check', () => {
  execFileSync(process.execPath, ['--check', CLIENT], { stdio: 'pipe', timeout: 30_000 })
})

test('client.js 静态契约：ModuleLoader / slot / iframe / 无外部资源', () => {
  const source = readFileSync(CLIENT, 'utf8')
  const required = [
    'window.__ModuleLoader__.load',
    "id: 'dsh-paper2html'",
    'exports.isPlugin = true',
    "exports.inject = ['slots']",
    'exports.apply = apply',
    "ctx.slots.inject('sidebar.panellist'",
    "name: 'sidebar.panellist', id: 'paper2html', order: 8",
    "label: () => '论文阅读'",
    "name: 'main', key: 'paper2html'",
    "src: '/paper2html/'",
    "title: 'Paper2HTML 论文阅读'",
    "'svg'",
  ]
  for (const needle of required) {
    assert.ok(source.includes(needle), `client.js 缺少静态契约片段：${needle}`)
  }
  assert.ok(!/https?:\/\//.test(source), 'client.js 不应包含外部 URL')
  for (const forbidden of ['fetch(', 'XMLHttpRequest', 'importScripts', 'new WebSocket', 'document.write']) {
    assert.ok(!source.includes(forbidden), `client.js 不应包含 ${forbidden}`)
  }
  assert.ok(!/\brequire\(['"](?!react['"])/.test(source), 'client.js 只应 require("react")')
})

test('client.js 加载后：isPlugin / inject / apply 注册 sidebar + main 两个 slot', () => {
  const { config, exports } = loadClient()
  assert.equal(config.id, 'dsh-paper2html')
  assert.equal(typeof config.factory, 'function')
  assert.equal(exports.isPlugin, true)
  assert.deepEqual([...exports.inject], ['slots'])
  assert.equal(typeof exports.apply, 'function')

  const registered = []
  const injected = []
  const ctx = {
    slots: {
      inject(slotName, callback) {
        injected.push(slotName)
        callback()
        return () => {}
      },
      register(meta, component) {
        registered.push({ meta, component })
        return () => {}
      },
    },
  }
  exports.apply(ctx)
  assert.deepEqual(injected.sort(), ['main', 'sidebar.panellist'])
  assert.equal(registered.length, 2)

  const sidebar = registered.find((item) => item.meta.name === 'sidebar.panellist')
  assert.ok(sidebar, '缺少 sidebar.panellist 注册')
  assert.equal(sidebar.meta.id, 'paper2html')
  assert.equal(sidebar.meta.order, 8)
  assert.equal(sidebar.meta.label(), '论文阅读')
  assert.equal(typeof sidebar.component, 'function')
  const icon = sidebar.component({ size: 20 })
  assert.equal(icon.tag, 'svg')
  assert.equal(icon.props.width, 20)
  assert.equal(icon.props.height, 20)
  assert.match(String(icon.props.viewBox), /^0 0 /)
  assert.equal(icon.props.stroke, 'currentColor')

  const main = registered.find((item) => item.meta.name === 'main')
  assert.ok(main, '缺少 main 注册')
  assert.equal(main.meta.key, 'paper2html')
  assert.equal(typeof main.component, 'function')
  const panel = main.component({})
  assert.equal(panel.tag, 'iframe')
  assert.equal(panel.props.src, '/paper2html/')
  assert.equal(panel.props.title, 'Paper2HTML 论文阅读')
  assert.equal(panel.props.style.width, '100%')
  assert.equal(panel.props.style.height, '100%')
  assert.equal(panel.props.style.border, 0)
})
