// dsh-paper2html · 浏览器半边（client）：左侧栏「Paper2HTML」入口 + 主区域 iframe。
// - 复用 Host 已有的 /paper2html/ 论文库单页（含预览、批注 API），不新增 Host 路由；
// - 主题：页面 ready 后把 DSH 当前 scheme 推给 iframe，并订阅 theme/change 持续同步；
// - 动作桥：页面发 paper2html:start-session → ctx.uiWorkspace.startSession，回执 session-started / session-failed；
// - 无外部资源、无前端构建。
window.__ModuleLoader__.load({
  id: 'dsh-paper2html',
  factory: (require) => {
    var module = { exports: {} }
    var exports = module.exports
    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' })

    const React = require('react')
    const h = React.createElement
    const PANEL = 'paper2html'
    const SRC = '/paper2html/'
    const MAX_PROMPT = 4000

    // 侧栏图标：一页带折角的论文纸（内联 SVG，跟随侧栏 currentColor）
    function PaperIcon(props) {
      const size = (props && props.size) || 18
      return h(
        'svg',
        {
          width: size,
          height: size,
          viewBox: '0 0 24 24',
          fill: 'none',
          stroke: 'currentColor',
          strokeWidth: 1.5,
          strokeLinecap: 'round',
          strokeLinejoin: 'round',
          'aria-hidden': 'true',
        },
        h('path', { d: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z' }),
        h('path', { d: 'M14 3v5h5' }),
        h('path', { d: 'M9 12h6' }),
        h('path', { d: 'M9 16h6' }),
      )
    }

    function apply(ctx) {
      const frames = new Set()
      let scheme = null

      function findFrame(source) {
        let found = null
        frames.forEach((frame) => {
          if (!found && frame && frame.contentWindow === source) found = frame
        })
        return found
      }

      function postToFrame(frame, message) {
        if (!frame || !frame.contentWindow) return
        try {
          frame.contentWindow.postMessage(message, location.origin)
        } catch (error) {
          /* iframe 已卸载或跨域：忽略 */
        }
      }

      function sendTheme(frame) {
        if (!scheme) return
        postToFrame(frame, { type: 'paper2html:theme', scheme })
      }

      function handlePageMessage(event) {
        if (!event || event.origin !== location.origin) return
        const data = event.data
        if (!data || typeof data !== 'object' || typeof data.type !== 'string') return
        const frame = findFrame(event.source)
        if (!frame) return

        if (data.type === 'paper2html:ready') {
          sendTheme(frame)
          return
        }
        if (data.type === 'paper2html:start-session') {
          const prompt = typeof data.prompt === 'string' ? data.prompt.trim() : ''
          if (prompt.length < 1 || prompt.length > MAX_PROMPT) {
            postToFrame(frame, {
              type: 'paper2html:session-failed',
              message: `提示词长度需要在 1–${MAX_PROMPT} 字之间`,
            })
            return
          }
          try {
            ctx.uiWorkspace.startSession(undefined, { prompt, whenDraftExists: 'replace' })
            postToFrame(frame, { type: 'paper2html:session-started' })
          } catch (error) {
            postToFrame(frame, {
              type: 'paper2html:session-failed',
              message: String((error && error.message) || error || '未知错误'),
            })
          }
        }
      }

      addEventListener('message', handlePageMessage)

      // 主题：页面 ready 时推当前 scheme，之后 theme/change 继续推
      if (typeof ctx.inject === 'function') {
        ctx.inject(['theme'], (services) => {
          const theme = services && services.theme
          if (!theme) return
          const push = (snapshot) => {
            scheme = snapshot && snapshot.active && snapshot.active.colorScheme ? snapshot.active.colorScheme : null
            frames.forEach(sendTheme)
          }
          try {
            push(typeof theme.getTheme === 'function' ? theme.getTheme() : null)
          } catch (error) {
            scheme = null
          }
          if (typeof theme.on === 'function') theme.on('theme/change', push)
        })
      }

      // 主区域：iframe 复用 /paper2html/ 论文库单页
      function PaperPanel() {
        return h('iframe', {
          src: SRC,
          title: 'Paper2HTML',
          allow: 'fullscreen',
          onLoad: (event) => {
            const frame = event && event.currentTarget
            if (!frame) return
            frames.add(frame)
            sendTheme(frame)
          },
          style: { width: '100%', height: '100%', border: 0, display: 'block' },
        })
      }

      ctx.slots.inject('sidebar.panellist', () =>
        ctx.slots.register(
          { name: 'sidebar.panellist', id: PANEL, order: 8, label: () => 'Paper2HTML' },
          PaperIcon,
        ),
      )
      ctx.slots.inject('main', () =>
        ctx.slots.register({ name: 'main', key: PANEL }, PaperPanel),
      )
    }

    exports.isPlugin = true
    exports.inject = ['slots', 'uiWorkspace']
    exports.apply = apply
    return module.exports
  },
})
