// 本地测试 10：浏览器半边 client（0.5.0）—— package 声明 / node --check / 静态契约 /
// vm 加载后：slot 注册、主题推送、start-session → uiWorkspace.startSession + 回执、非法消息忽略。
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
const ORIGIN = 'http://127.0.0.1:7788'

function loadClient() {
  const source = readFileSync(CLIENT, 'utf8')
  const loaded = []
  const listeners = []
  const sandbox = {
    window: { __ModuleLoader__: { load(config) { loaded.push(config) } } },
    location: { origin: ORIGIN },
    addEventListener(type, handler) { listeners.push({ type, handler }) },
    removeEventListener() {},
    console,
  }
  vm.runInNewContext(source, sandbox, { filename: 'lib/client.js' })
  assert.equal(loaded.length, 1, 'client.js 应该调用一次 window.__ModuleLoader__.load')
  const React = {
    createElement(tag, props, ...children) {
      return { tag, props: props || {}, children }
    },
  }
  const moduleExports = loaded[0].factory((name) => {
    if (name === 'react') return React
    throw new Error(`client.js 不应 require 其它模块：${name}`)
  })
  return { config: loaded[0], exports: moduleExports, listeners, sandbox }
}

function makeThemeService(scheme) {
  const handlers = []
  const service = {
    snapshot: { active: { colorScheme: scheme } },
    getTheme() { return this.snapshot },
    on(event, handler) { if (event === 'theme/change') handlers.push(handler) },
  }
  return { service, handlers }
}

function makeHarness() {
  const registered = []
  const injected = []
  const starts = []
  const { service: themeService, handlers: themeHandlers } = makeThemeService('dark')
  const ctx = {
    slots: {
      inject(slotName, callback) { injected.push(slotName); callback(); return () => {} },
      register(meta, component) { registered.push({ meta, component }); return () => {} },
    },
    inject(deps, callback) { callback({ theme: themeService }) },
    uiWorkspace: {
      startSession(...args) { starts.push(args) },
    },
  }
  return { ctx, registered, injected, starts, themeService, themeHandlers }
}

function makeFrame() {
  const messages = []
  return {
    contentWindow: {
      postMessage(message, targetOrigin) { messages.push({ message, targetOrigin }) },
    },
    messages,
  }
}

function plain(value) {
  return JSON.parse(JSON.stringify(value))
}

function fireMessage(listeners, event) {
  for (const listener of listeners) {
    if (listener.type === 'message') listener.handler(event)
  }
}

test('package.json 声明 client 半边（dsh.client / exports["./client"] / files）', () => {
  assert.equal(PKG.dsh.client?.platform, 'web')
  assert.deepEqual(PKG.dsh.client?.inject, [])
  assert.equal(PKG.exports?.['./client'], './lib/client.js')
  const files = PKG.files || []
  assert.ok(files.includes('lib') || files.includes('lib/client.js'), 'files 应包含 lib 或 lib/client.js')
  assert.ok(existsSync(CLIENT), '缺少 lib/client.js')
})

test('client.js 通过 node --check', () => {
  execFileSync(process.execPath, ['--check', CLIENT], { stdio: 'pipe', timeout: 30_000 })
})

test('client.js 静态契约：ModuleLoader / slot / theme / start-session / 无外部资源', () => {
  const source = readFileSync(CLIENT, 'utf8')
  const required = [
    'window.__ModuleLoader__.load',
    "id: 'dsh-paper2html'",
    'exports.isPlugin = true',
    "exports.inject = ['slots', 'uiWorkspace']",
    'exports.apply = apply',
    "ctx.slots.inject('sidebar.panellist'",
    "name: 'sidebar.panellist', id: PANEL, order: 8",
    "label: () => 'Paper2HTML'",
    "name: 'main', key: PANEL",
    'src: SRC',
    "'/paper2html/'",
    "type: 'paper2html:theme'",
    "'paper2html:ready'",
    "'paper2html:start-session'",
    "type: 'paper2html:session-started'",
    "type: 'paper2html:session-failed'",
    'uiWorkspace.startSession',
    "whenDraftExists: 'replace'",
  ]
  for (const needle of required) {
    assert.ok(source.includes(needle), `client.js 缺少静态契约片段：${needle}`)
  }
  assert.ok(!/https?:\/\//.test(source), 'client.js 不应包含外部 URL')
  for (const forbidden of ['fetch(', 'XMLHttpRequest', 'importScripts', 'document.write']) {
    assert.ok(!source.includes(forbidden), `client.js 不应包含 ${forbidden}`)
  }
})

test('client.js 加载：isPlugin / inject / apply 注册 sidebar + main 两个 slot', () => {
  const { config, exports } = loadClient()
  assert.equal(config.id, 'dsh-paper2html')
  assert.equal(exports.isPlugin, true)
  assert.deepEqual([...exports.inject], ['slots', 'uiWorkspace'])
  assert.equal(typeof exports.apply, 'function')

  const { ctx, registered, injected, themeHandlers, themeService } = makeHarness()
  exports.apply(ctx)
  assert.deepEqual(injected, ['sidebar.panellist', 'main'])
  assert.equal(registered.length, 2)

  const sidebar = registered.find((item) => item.meta.name === 'sidebar.panellist')
  assert.ok(sidebar, '缺少 sidebar.panellist 注册')
  assert.equal(sidebar.meta.id, 'paper2html')
  assert.equal(sidebar.meta.order, 8)
  assert.equal(sidebar.meta.label(), 'Paper2HTML')
  const icon = sidebar.component({ size: 20 })
  assert.equal(icon.tag, 'svg')
  assert.equal(icon.props.width, 20)
  assert.equal(icon.props.height, 20)
  assert.equal(icon.props.stroke, 'currentColor')

  const main = registered.find((item) => item.meta.name === 'main')
  assert.equal(main.meta.key, 'paper2html')
  const panel = main.component({})
  assert.equal(panel.tag, 'iframe')
  assert.equal(panel.props.src, '/paper2html/')
  assert.equal(panel.props.title, 'Paper2HTML')
  assert.equal(panel.props.style.width, '100%')
  assert.ok(themeHandlers.length >= 1, '应订阅 theme/change')
  void themeService
})

test('client.js：theme 推送（onLoad / ready / theme change）', () => {
  const { exports, listeners } = loadClient()
  const { ctx, registered, themeService, themeHandlers } = makeHarness()
  exports.apply(ctx)
  const main = registered.find((item) => item.meta.name === 'main')
  const panel = main.component({})
  const frame = makeFrame()
  panel.props.onLoad({ currentTarget: frame })
  assert.equal(frame.messages.length >= 1, true, 'onLoad 后应收到主题消息')
  assert.deepEqual(plain(frame.messages[0].message), { type: 'paper2html:theme', scheme: 'dark' })
  assert.equal(frame.messages[0].targetOrigin, ORIGIN)

  const before = frame.messages.length
  fireMessage(listeners, { origin: ORIGIN, source: frame.contentWindow, data: { type: 'paper2html:ready' } })
  assert.equal(frame.messages.length, before + 1)
  assert.equal(frame.messages[before].message.type, 'paper2html:theme')

  themeService.snapshot = { active: { colorScheme: 'light' } }
  themeHandlers[0](themeService.snapshot)
  const themeMessage = frame.messages.filter((item) => item.message.type === 'paper2html:theme').pop()
  assert.deepEqual(plain(themeMessage.message), { type: 'paper2html:theme', scheme: 'light' })
})

test('client.js：start-session → uiWorkspace.startSession + 回执；非法消息忽略', () => {
  const { exports, listeners } = loadClient()
  const { ctx, registered, starts } = makeHarness()
  exports.apply(ctx)
  const main = registered.find((item) => item.meta.name === 'main')
  const frame = makeFrame()
  main.component({}).props.onLoad({ currentTarget: frame })

  function send(data, overrides = {}) {
    fireMessage(listeners, { origin: ORIGIN, source: frame.contentWindow, data, ...overrides })
  }

  send({ type: 'paper2html:start-session', prompt: '  把这篇论文转成阅读页：1706.03762  ' })
  assert.equal(starts.length, 1, '应调用 uiWorkspace.startSession')
  assert.deepEqual(plain(starts[0]), [null, { prompt: '把这篇论文转成阅读页：1706.03762', whenDraftExists: 'replace' }])
  let last = frame.messages[frame.messages.length - 1]
  assert.deepEqual(plain(last.message), { type: 'paper2html:session-started' })

  // 非法：来源 origin 不对 / source 不认识 / prompt 非法 → 不调用 startSession
  send({ type: 'paper2html:start-session', prompt: 'hello' }, { origin: 'http://evil.example' })
  send({ type: 'paper2html:start-session', prompt: 'hello' }, { source: {} })
  send({ type: 'paper2html:start-session', prompt: '   ' })
  send({ type: 'paper2html:start-session', prompt: 'x'.repeat(4001) })
  assert.equal(starts.length, 1, '非法消息不应触发 startSession')
  const failedMessages = frame.messages.filter((item) => item.message.type === 'paper2html:session-failed')
  assert.ok(failedMessages.length >= 2, '非法 prompt 应有 session-failed 回执')

  // 未知类型 / 非对象消息忽略，不抛错
  send({ type: 'paper2html:unknown' })
  send(null)
  send('not-an-object')

  // startSession 抛错 → session-failed 带原因
  ctx.uiWorkspace.startSession = () => { throw new Error('workspace unavailable') }
  send({ type: 'paper2html:start-session', prompt: 'hello' })
  last = frame.messages[frame.messages.length - 1]
  assert.equal(last.message.type, 'paper2html:session-failed')
  assert.match(last.message.message, /workspace unavailable/)
})
