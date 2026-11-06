// dsh-paper2html · Host 半边：
// 1. 注册模型工具 paper2html_convert / paper2html_status；
// 2. 注册随包 skill paper2html；
// 3. 注册 /paper2html/ 只读预览服务（导出的 HTML 在 DSH Web 里直接看）。
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { BASE, createHandler } from './preview.js'
import { createSkillProvider } from './skills.js'
import { TOOLS } from './tools.js'

const ROOT = fileURLToPath(new URL('..', import.meta.url))

export const name = 'paper2html'
export const inject = ['tools', 'skills', 'webServer']

export function apply(ctx) {
  // 工具在 Host 进程里执行，不受模型 bash 的沙箱限制。
  for (const tool of TOOLS) ctx.effect(() => ctx.tools.register(tool))

  // 随包 skill：模型通过 skill 工具加载。
  ctx.effect(() =>
    ctx.skills.registerProvider(() =>
      createSkillProvider({
        providerName: 'paper2html',
        dirs: [join(ROOT, 'skills')],
        pluginRoot: ROOT,
      }),
    ),
  )

  // 只读预览：文件写到 $DSH_HOME/paper2html/exports（或用户指定目录后登记），
  // handler 只服务 .html、拒绝路径穿越与目录外软链。
  ctx.effect(() =>
    ctx.webServer.register({
      kind: 'prefix',
      path: BASE,
      handler: createHandler(),
    }),
  )
}
