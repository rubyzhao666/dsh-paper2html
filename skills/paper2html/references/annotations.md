# 批注读取（`paper2html_annotations`）

> 0.3.0 起：在 **DSH Web 预览页**（`http://127.0.0.1:<端口>/paper2html/…`）打开的论文，页面内批注会同步到
> Host 侧 `$DSH_HOME/paper2html/annotations/<docId>.json`，agent 可以读出来做总结/答疑。
> 用 `file://` 直接打开 HTML 时批注只存在浏览器 localStorage（0.2.0 行为），agent 读不到——需要让用户改用
> DSH Web 预览链接打开，或让他导出带批注版文件。

## 什么时候用

用户问这些时调用 `paper2html_annotations`：

- 「我在这篇论文里标注了什么？」「我标了哪些重点？」
- 「把我标的部分总结一下 / 按我的批注整理成笔记」
- 「我批注里提了哪些问题？」「根据我的高亮给我出几道复习题」
- 「我刚才在预览页标的怎么没了？」（先帮查是否有同步记录）

不适用：用户还没做过批注、或只在 `file://` 里标过（此时说明原因并给替代方案）。

## 工作流

1. **不确定是哪篇** → 先无参数调用，列出本机所有有批注的文档：
   ```
   paper2html_annotations({})
   → { count: N, documents: [{ docId, count, updatedAt }] }
   ```
   - 空列表 → 告诉用户「还没有同步的批注」：批注需要在 DSH Web 预览页打开论文后添加；
     `file://` 打开的页面批注只在本浏览器，可用页面里的「导出带批注版」分享，但工具读不到。
2. **知道是哪篇** → 二选一：
   - 有 docId：`paper2html_annotations({ docId: "arxiv-1706.03762" })`
   - 有 HTML 路径：`paper2html_annotations({ htmlPath: "/abs/paper.html" })`
     （工具会从 `<meta name="p2h-doc-id">` 读 docId；旧页面没有这个 meta 会报错）
   - 可选 `limit`（1–200，默认 100）控制返回条数；`count` 始终是总数。
3. **基于返回内容工作**：每条批注有 `color`、`quoteExcerpt`（被高亮的原文摘录）、`note`（用户写的批注）、
   `sectionId`（所在章节）、`createdAt`。
   - 总结时按文档顺序（返回顺序即页面顺序）组织，引用摘录时用引号标出。
   - 只高亮没有文字的条目标「（仅高亮）」，不要编造批注意图。
   - 用户问「我标的部分」时，**只基于返回的批注**，不要假装读过全文；需要结合正文再用 `pdf` skill / `read`。
4. **回答里带上 docId**，方便用户确认是哪篇；条数很多时说明只展开了前 N 条（可调 `limit`）。

## 同步机制与边界

| 打开方式 | 批注存哪 | agent 能读 |
|---|---|---|
| DSH Web 预览（`http://…/paper2html/…`） | localStorage + Host JSON（400ms 防抖 PUT） | ✅ |
| `file://` 直接打开 HTML | 仅浏览器 localStorage | ❌（让用户导出带批注版，或改用预览链接） |

- Host 存储位置：`$DSH_HOME/paper2html/annotations/<docId>.json`；
- 上限：单文档 ≤500 条、整体 ≤512KB；超出时页面会提示同步失败（仍保存在本地），工具读不到超出部分；
- 同步是「全量覆盖」：页面里删除/清空会同步删除 Host 侧记录；
- 页面面板顶部会显示同步状态：`已同步到本机` / `仅保存在本浏览器` / `同步失败`；
- 批注内容属于用户隐私：只用于回答用户的问题，不要主动外传、不要写入无关文件；
- 工具没有写/删接口；不要声称能修改用户批注。

## 错误处理

| 工具返回/报错 | 你该做什么 |
|---|---|
| `docId 不合法` | 从页面 HTML 的 meta 复制正确 docId（形如 `arxiv-1706.03762` / `pdf-<16 位 hash>`） |
| `找不到 HTML 文件` / `没有 <meta name="p2h-doc-id">` | 确认路径正确、是 0.2.0+ 插件生成的页面；或改用 docId |
| `count: 0` | 说明没有同步记录；引导用户在 DSH Web 预览页批注，或确认之前是否用 file:// 打开的 |
| `docId 和 htmlPath 只能给一个` | 只传一个 |
