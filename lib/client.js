// dsh-paper2html · 浏览器半边（client）：左侧栏「论文阅读」入口 + 主区域 iframe。
// 复用 Host 已有的只读页面 /paper2html/（导出列表、论文预览、批注同步 API 都在那个页面里），
// 这里不新增路由、不发起网络请求、不引入外部资源。
window.__ModuleLoader__.load({
  id: 'dsh-paper2html',
  factory: (require) => {
    var module = { exports: {} }
    var exports = module.exports
    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' })

    const React = require('react')
    const h = React.createElement

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

    // 主区域：直接 iframe 复用 /paper2html/ 库页面（无需前端构建）
    function PaperPanel() {
      return h('iframe', {
        src: '/paper2html/',
        title: 'Paper2HTML',
        allow: 'fullscreen',
        style: { width: '100%', height: '100%', border: 0, display: 'block' },
      })
    }

    function apply(ctx) {
      ctx.slots.inject('sidebar.panellist', () =>
        ctx.slots.register(
          { name: 'sidebar.panellist', id: 'paper2html', order: 8, label: () => 'Paper2HTML' },
          PaperIcon,
        ),
      )
      ctx.slots.inject('main', () =>
        ctx.slots.register({ name: 'main', key: 'paper2html' }, PaperPanel),
      )
    }

    exports.isPlugin = true
    exports.inject = ['slots']
    exports.apply = apply
    return module.exports
  },
})
