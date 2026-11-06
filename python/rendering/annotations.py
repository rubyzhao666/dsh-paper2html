"""
页面内批注 / 高亮 + 带批注导出分享（F3）

本模块只放「静态字符串 + 一个注入函数」：
- ANNOTATION_CSS：批注 UI 样式（复用页面已有的主题 CSS 变量，三主题自动适配）
- ANNOTATION_MARKUP：右下角入口按钮、批注侧栏、划词工具条、批注输入框
- ANNOTATION_JS：原生 JS（无依赖、无网络、file:// 可用），负责划词高亮、批注、
  localStorage 持久化、文本锚定（quote/prefix/suffix）、导出带内嵌批注 JSON 的单文件副本

由 rendering/renderer.py 在生成 HTML 后调用 inject_annotation_assets() 注入，
注入标记：<style id="p2h-annotation-style">、<script id="p2h-annotation-script">、
<meta name="p2h-doc-id">、<meta name="p2h-file-name">。

实现约束（与 FEATURE-SPECS-0.2.0 F3 对齐）：
- 纯前端、不发起任何网络请求、不新增外部 CDN；
- 无批注时页面视觉/行为与旧版一致（批注 UI 默认隐藏）；
- localStorage 坏 JSON / 不可用时不崩溃；
- KaTeX（.katex）、<pre>/<code>、批注 UI 自身不可标注。
"""

import hashlib
import html as _html
from typing import Optional

ANNOTATION_VERSION = "1.0.0"

# =============================================================================
# CSS —— 复用页面已有主题变量（--bg-card / --text-primary / --accent ...），
# 每个变量都带兜底值，保证三套主题下都可读。
# =============================================================================
ANNOTATION_CSS = r"""
/* ===== Paper2HTML annotations (F3) ===== */
mark.p2h-hl {
  background: rgba(255, 213, 0, 0.34);
  color: inherit;
  border-radius: 3px;
  padding: 0 1px;
  cursor: pointer;
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
  transition: background 0.15s ease, box-shadow 0.15s ease;
}
mark.p2h-hl[data-p2h-color="green"] { background: rgba(63, 185, 80, 0.34); }
mark.p2h-hl[data-p2h-color="blue"]  { background: rgba(88, 166, 255, 0.34); }
mark.p2h-hl[data-p2h-color="pink"]  { background: rgba(236, 72, 153, 0.32); }
mark.p2h-hl:hover { box-shadow: 0 0 0 2px rgba(88, 166, 255, 0.45); }
mark.p2h-hl.p2h-hl-flash { animation: p2h-hl-flash 1.3s ease 1; }
@keyframes p2h-hl-flash {
  0%   { box-shadow: 0 0 0 0 rgba(88, 166, 255, 0.85); }
  40%  { box-shadow: 0 0 0 4px rgba(88, 166, 255, 0.55); }
  100% { box-shadow: 0 0 0 0 rgba(88, 166, 255, 0); }
}

#p2h-annotate-toggle {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2147482500;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border-radius: 999px;
  border: 1px solid var(--border-primary, #30363d);
  background: var(--bg-card, #1c2128);
  color: var(--text-primary, #e6edf3);
  font: inherit;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
  transition: transform 0.15s ease, border-color 0.15s ease;
}
#p2h-annotate-toggle:hover {
  transform: translateY(-1px);
  border-color: var(--accent, #58a6ff);
}
body.p2h-panel-open #p2h-annotate-toggle { right: 372px; }
#p2h-annotate-toggle .p2h-annotation-count {
  display: inline-flex;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--accent, #58a6ff);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}
#p2h-annotate-toggle .p2h-annotation-count[hidden] { display: none; }

#p2h-annotation-panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 2147482000;
  width: 348px;
  max-width: 94vw;
  display: flex;
  flex-direction: column;
  background: var(--bg-card, #1c2128);
  color: var(--text-primary, #e6edf3);
  border-left: 1px solid var(--border-primary, #30363d);
  box-shadow: -16px 0 40px rgba(0, 0, 0, 0.35);
  transform: translateX(105%);
  visibility: hidden;
  transition: transform 0.22s ease, visibility 0.22s ease;
  font-family: inherit;
}
#p2h-annotation-panel.p2h-open {
  transform: translateX(0);
  visibility: visible;
}
.p2h-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-primary, #30363d);
  background: var(--bg-secondary, #161b22);
}
.p2h-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #e6edf3);
}
.p2h-panel-title .p2h-panel-total {
  color: var(--text-secondary, #8b949e);
  font-weight: 400;
  font-size: 12px;
  margin-left: 4px;
}
.p2h-icon-btn {
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-secondary, #8b949e);
  border-radius: 6px;
  width: 28px;
  height: 28px;
  line-height: 1;
  font-size: 14px;
  cursor: pointer;
}
.p2h-icon-btn:hover {
  color: var(--text-primary, #e6edf3);
  border-color: var(--border-primary, #30363d);
}
#p2h-share-banner {
  margin: 10px 14px 2px;
  padding: 9px 11px;
  border-radius: 8px;
  border: 1px solid var(--accent, #58a6ff);
  background: color-mix(in srgb, var(--accent, #58a6ff) 14%, transparent);
  color: var(--text-primary, #e6edf3);
  font-size: 12px;
  line-height: 1.5;
}
.p2h-sync-status {
  margin: 9px 14px 0;
  padding: 6px 10px;
  border-radius: 7px;
  border-left: 3px solid var(--border-primary, #30363d);
  background: var(--bg-secondary, #161b22);
  color: var(--text-secondary, #8b949e);
  font-size: 11px;
  line-height: 1.55;
}
.p2h-sync-status[data-p2h-sync="synced"] {
  border-left-color: var(--accent-secondary, #3fb950);
  color: var(--text-primary, #e6edf3);
}
.p2h-sync-status[data-p2h-sync="failed"] {
  border-left-color: #ef4444;
  color: #ef4444;
}

#p2h-annotation-list {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.p2h-empty {
  color: var(--text-secondary, #8b949e);
  font-size: 13px;
  line-height: 1.7;
  margin: 12px 2px;
}
.p2h-annotation-item {
  display: flex;
  gap: 9px;
  padding: 10px 11px;
  border-radius: 9px;
  border: 1px solid var(--border-primary, #30363d);
  background: var(--bg-secondary, #161b22);
  cursor: pointer;
  transition: border-color 0.15s ease, transform 0.15s ease;
}
.p2h-annotation-item:hover {
  border-color: var(--accent, #58a6ff);
  transform: translateY(-1px);
}
.p2h-annotation-item.p2h-unresolved { opacity: 0.72; }
.p2h-color-bar {
  flex: 0 0 auto;
  width: 4px;
  border-radius: 999px;
  background: rgba(255, 213, 0, 0.9);
}
.p2h-color-bar[data-color="green"] { background: rgba(63, 185, 80, 0.95); }
.p2h-color-bar[data-color="blue"]  { background: rgba(88, 166, 255, 0.95); }
.p2h-color-bar[data-color="pink"]  { background: rgba(236, 72, 153, 0.95); }
.p2h-item-body { flex: 1 1 auto; min-width: 0; }
.p2h-quote {
  margin: 0 0 6px;
  padding: 0;
  border: 0;
  color: var(--text-secondary, #8b949e);
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}
.p2h-note {
  margin: 0 0 6px;
  color: var(--text-primary, #e6edf3);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.p2h-note.p2h-note-empty {
  color: var(--text-muted, #6e7681);
  font-style: italic;
}
.p2h-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-muted, #6e7681);
}
.p2h-section-label {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.p2h-badge {
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 10px;
  border: 1px solid var(--border-primary, #30363d);
  color: var(--text-secondary, #8b949e);
}
.p2h-badge.p2h-badge-warn {
  border-color: rgba(239, 68, 68, 0.6);
  color: #ef4444;
}
.p2h-badge.p2h-badge-shared {
  border-color: var(--accent, #58a6ff);
  color: var(--accent, #58a6ff);
}
.p2h-delete-btn {
  margin-left: auto;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted, #6e7681);
  font-size: 11px;
  cursor: pointer;
  padding: 1px 5px;
  border-radius: 5px;
}
.p2h-delete-btn:hover {
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.45);
}
.p2h-panel-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px 16px;
  border-top: 1px solid var(--border-primary, #30363d);
  background: var(--bg-secondary, #161b22);
}
.p2h-panel-actions button {
  width: 100%;
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-primary, #30363d);
  background: var(--bg-card, #1c2128);
  color: var(--text-primary, #e6edf3);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.p2h-panel-actions button:hover { border-color: var(--accent, #58a6ff); }
#p2h-export-annotated {
  border-color: var(--accent, #58a6ff);
  background: color-mix(in srgb, var(--accent, #58a6ff) 16%, transparent);
}
#p2h-clear-annotations { color: var(--text-secondary, #8b949e); }

#p2h-selection-toolbar {
  position: fixed;
  z-index: 2147483000;
  display: none;
  align-items: center;
  gap: 6px;
  padding: 7px 9px;
  border-radius: 10px;
  border: 1px solid var(--border-primary, #30363d);
  background: var(--bg-card, #1c2128);
  color: var(--text-primary, #e6edf3);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35);
}
#p2h-selection-toolbar.p2h-visible { display: flex; }
.p2h-color-dot {
  width: 20px;
  height: 20px;
  padding: 0;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.35);
  background: rgba(255, 213, 0, 0.95);
  cursor: pointer;
  transition: transform 0.12s ease;
}
.p2h-color-dot:hover { transform: scale(1.12); }
.p2h-color-dot[data-p2h-color="yellow"] { background: #ffd400; }
.p2h-color-dot[data-p2h-color="green"]  { background: #3fb950; }
.p2h-color-dot[data-p2h-color="blue"]   { background: #58a6ff; }
.p2h-color-dot[data-p2h-color="pink"]   { background: #ec4899; }
#p2h-add-note {
  margin-left: 2px;
  padding: 5px 10px;
  border-radius: 7px;
  border: 1px solid var(--border-primary, #30363d);
  background: var(--bg-secondary, #161b22);
  color: var(--text-primary, #e6edf3);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
#p2h-add-note:hover { border-color: var(--accent, #58a6ff); }

#p2h-note-editor {
  position: fixed;
  z-index: 2147483000;
  display: none;
  flex-direction: column;
  gap: 8px;
  width: 292px;
  max-width: 92vw;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border-primary, #30363d);
  background: var(--bg-card, #1c2128);
  color: var(--text-primary, #e6edf3);
  box-shadow: 0 14px 36px rgba(0, 0, 0, 0.4);
}
#p2h-note-editor.p2h-visible { display: flex; }
#p2h-note-editor label {
  font-size: 12px;
  color: var(--text-secondary, #8b949e);
}
#p2h-note-input {
  width: 100%;
  min-height: 74px;
  resize: vertical;
  padding: 8px 9px;
  border-radius: 8px;
  border: 1px solid var(--border-primary, #30363d);
  background: var(--bg-secondary, #161b22);
  color: var(--text-primary, #e6edf3);
  font: inherit;
  font-size: 13px;
  line-height: 1.5;
  box-sizing: border-box;
}
#p2h-note-input:focus { outline: none; border-color: var(--accent, #58a6ff); }
.p2h-note-actions { display: flex; justify-content: flex-end; gap: 8px; }
.p2h-note-actions button {
  padding: 6px 14px;
  border-radius: 7px;
  border: 1px solid var(--border-primary, #30363d);
  background: var(--bg-secondary, #161b22);
  color: var(--text-primary, #e6edf3);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
#p2h-note-save {
  border-color: var(--accent, #58a6ff);
  background: color-mix(in srgb, var(--accent, #58a6ff) 18%, transparent);
}

@media (max-width: 640px) {
  #p2h-annotation-panel { width: 100vw; }
  #p2h-annotate-toggle { right: 14px; bottom: 14px; }
  body.p2h-panel-open #p2h-annotate-toggle { opacity: 0; pointer-events: none; }
}
@media print {
  #p2h-annotate-toggle,
  #p2h-annotation-panel,
  #p2h-selection-toolbar,
  #p2h-note-editor { display: none !important; }
}
"""

# =============================================================================
# Markup —— 契约要求的 DOM id / class（Lead 的浏览器测试直接按这些选择器操作）
# =============================================================================
ANNOTATION_MARKUP = r"""
<button id="p2h-annotate-toggle" type="button" aria-haspopup="dialog" aria-controls="p2h-annotation-panel" aria-expanded="false" title="打开批注侧栏">✍️ 批注<span class="p2h-annotation-count" id="p2h-annotation-count" hidden>0</span></button>

<aside id="p2h-annotation-panel" role="dialog" aria-label="批注侧栏" aria-hidden="true">
  <div class="p2h-panel-head">
    <div class="p2h-panel-title">✍️ 批注<span class="p2h-panel-total" id="p2h-annotation-total"></span></div>
    <button id="p2h-panel-close" class="p2h-icon-btn" type="button" title="关闭批注侧栏" aria-label="关闭批注侧栏">✕</button>
  </div>
  <div id="p2h-sync-status" class="p2h-sync-status" data-p2h-sync="local" role="status"></div>
  <div id="p2h-share-banner" style="display:none;"></div>
  <div id="p2h-annotation-list"></div>
  <div class="p2h-panel-actions">
    <button id="p2h-export-annotated" type="button" title="下载包含批注的单文件 HTML">导出带批注版</button>
    <button id="p2h-clear-annotations" type="button" title="清空本机保存的批注">清空我的批注</button>
  </div>
</aside>

<div id="p2h-selection-toolbar" role="toolbar" aria-label="标注选中文字">
  <button class="p2h-color-dot" type="button" data-p2h-color="yellow" title="黄色高亮" aria-label="黄色高亮"></button>
  <button class="p2h-color-dot" type="button" data-p2h-color="green" title="绿色高亮" aria-label="绿色高亮"></button>
  <button class="p2h-color-dot" type="button" data-p2h-color="blue" title="蓝色高亮" aria-label="蓝色高亮"></button>
  <button class="p2h-color-dot" type="button" data-p2h-color="pink" title="粉色高亮" aria-label="粉色高亮"></button>
  <button id="p2h-add-note" type="button" title="为选中文字写批注">写批注…</button>
</div>

<div id="p2h-note-editor" role="dialog" aria-label="写批注">
  <label for="p2h-note-input">批注</label>
  <textarea id="p2h-note-input" rows="3" placeholder="写点想法…（Cmd/Ctrl + Enter 保存）"></textarea>
  <div class="p2h-note-actions">
    <button id="p2h-note-cancel" type="button">取消</button>
    <button id="p2h-note-save" type="button">保存</button>
  </div>
</div>
"""

# =============================================================================
# JS —— 原生、无依赖、无网络；所有外部输入（localStorage / 内嵌 JSON）都容错解析
# =============================================================================
ANNOTATION_JS = r"""
(function () {
  'use strict';

  var READY_FLAG = '__P2H_ANNOTATIONS_READY__';
  if (window[READY_FLAG]) { return; }

  var COLORS = ['yellow', 'green', 'blue', 'pink'];
  var COLOR_LABELS = { yellow: '黄色高亮', green: '绿色高亮', blue: '蓝色高亮', pink: '粉色高亮' };
  var DEFAULT_COLOR = 'yellow';
  var MAX_QUOTE = 80;
  var ANCHOR_CONTEXT = 48;
  // 批注同步（0.3.0 G3）：http(s) 预览页把批注同步到 Host；file:// 保持 0.2.0 的 localStorage 行为。
  var SERVER_MODE = !!(window.location && (window.location.protocol === 'http:' || window.location.protocol === 'https:'));
  var API_BASE = '/paper2html/api/annotations/';
  var SYNC_DEBOUNCE_MS = 400;

  var IGNORE_SELECTOR = '.katex, .katex-display, .katex-mathml, pre, code, ' +
    '#p2h-annotation-panel, #p2h-selection-toolbar, #p2h-note-editor, #p2h-annotate-toggle, ' +
    'script, style, textarea, noscript, [contenteditable="true"]';
  var UI_SELECTOR = '#p2h-annotation-panel, #p2h-selection-toolbar, #p2h-note-editor, #p2h-annotate-toggle';

  var state = {
    embedded: [],
    local: [],
    all: [],
    index: null,
    headings: [],
    resolved: {},
    pendingRange: null,
    noteRange: null,
    pendingRect: null,
    lastColor: DEFAULT_COLOR,
    syncTimer: null,
    syncFailed: false,
    syncLoaded: false
  };

  // ---------------------------------------------------------------- utils ---
  function byId(id) { return document.getElementById(id); }
  function all(selector, rootEl) {
    return Array.prototype.slice.call((rootEl || document).querySelectorAll(selector));
  }
  function getRoot() { return document.querySelector('.main-content') || document.body; }
  function rootEl() { return getRoot(); }

  function docId() {
    var meta = document.querySelector('meta[name="p2h-doc-id"]');
    return meta ? (meta.getAttribute('content') || '') : '';
  }
  function storageKey() { return 'p2h-annotations:' + docId(); }

  function normalizeAnnotation(raw) {
    if (!raw || typeof raw !== 'object') { return null; }
    if (typeof raw.id !== 'string' || !raw.id) { return null; }
    if (COLORS.indexOf(raw.color) === -1) { return null; }
    var quote = raw.quote && typeof raw.quote === 'object' ? raw.quote : {};
    var exact = typeof quote.exact === 'string' ? quote.exact : '';
    if (!exact) { return null; }
    return {
      id: raw.id,
      color: raw.color,
      note: typeof raw.note === 'string' ? raw.note : '',
      quote: {
        exact: exact,
        prefix: typeof quote.prefix === 'string' ? quote.prefix : '',
        suffix: typeof quote.suffix === 'string' ? quote.suffix : ''
      },
      sectionId: typeof raw.sectionId === 'string' ? raw.sectionId : '',
      createdAt: typeof raw.createdAt === 'string' ? raw.createdAt : ''
    };
  }

  function parseAnnotationList(text) {
    var data;
    try { data = JSON.parse(text); } catch (err) { return []; }
    if (!Array.isArray(data)) { return []; }
    var out = [];
    for (var i = 0; i < data.length; i += 1) {
      var item = normalizeAnnotation(data[i]);
      if (item) { out.push(item); }
    }
    return out;
  }

  function readStorage() {
    try {
      var raw = window.localStorage.getItem(storageKey());
      return raw ? parseAnnotationList(raw) : [];
    } catch (err) {
      return [];
    }
  }
  function writeStorage(list) {
    try {
      window.localStorage.setItem(storageKey(), JSON.stringify(list));
    } catch (err) {
      /* localStorage 被禁用 / 配额满：静默降级，页面照常可用 */
    }
  }
  function readEmbedded() {
    var el = byId('p2h-annotations');
    if (!el) { return []; }
    return parseAnnotationList(el.textContent || '');
  }
  function mergeLists(a, b) {
    var seen = {};
    var out = [];
    function push(list) {
      for (var i = 0; i < list.length; i += 1) {
        var ann = list[i];
        if (!ann || seen[ann.id]) { continue; }
        seen[ann.id] = true;
        out.push(ann);
      }
    }
    push(a || []);
    push(b || []);
    return out;
  }

  // ------------------------------------------------------- server sync ---
  function syncStatusEl() { return byId('p2h-sync-status'); }

  function updateSyncStatus(explicitMode) {
    var el = syncStatusEl();
    if (!el) { return; }
    var mode = explicitMode;
    if (!mode) {
      if (!SERVER_MODE) { mode = 'local'; }
      else if (state.syncFailed) { mode = 'failed'; }
      else if (state.syncLoaded) { mode = 'synced'; }
      else { mode = 'local'; }
    }
    el.setAttribute('data-p2h-sync', mode);
    if (mode === 'synced') {
      el.textContent = '☁ 批注已同步到本机（$DSH_HOME/paper2html/annotations）';
    } else if (mode === 'failed') {
      el.textContent = '⚠ 同步失败：批注仅保存在本浏览器（本地保存不受影响）';
    } else {
      el.textContent = '💾 批注保存在本浏览器；分享请用「导出带批注版」';
    }
  }

  function apiUrl() {
    return API_BASE + encodeURIComponent(docId());
  }

  function scheduleSync() {
    if (!SERVER_MODE) { return; }
    if (state.syncTimer) { window.clearTimeout(state.syncTimer); }
    state.syncTimer = window.setTimeout(syncNow, SYNC_DEBOUNCE_MS);
  }

  function syncNow() {
    state.syncTimer = null;
    if (!SERVER_MODE || typeof window.fetch !== 'function') { return; }
    var payload = mergeLists(state.embedded, state.local);
    var body;
    try {
      body = JSON.stringify({ annotations: payload });
    } catch (err) {
      state.syncFailed = true;
      updateSyncStatus();
      return;
    }
    try {
      window.fetch(apiUrl(), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: body,
        cache: 'no-store'
      }).then(function (response) {
        if (!response.ok) { throw new Error('HTTP ' + response.status); }
        state.syncLoaded = true;
        state.syncFailed = false;
        updateSyncStatus();
      }).catch(function () {
        state.syncFailed = true;
        updateSyncStatus();
      });
    } catch (err) {
      state.syncFailed = true;
      updateSyncStatus();
    }
  }

  function mergeServerAnnotations(serverList) {
    if (!serverList || !serverList.length) { return; }
    var serverById = {};
    for (var i = 0; i < serverList.length; i += 1) { serverById[serverList[i].id] = true; }
    var merged = [];
    // 服务端优先：同 id 用服务端版本，本地独有的追加在后面
    for (var s = 0; s < serverList.length; s += 1) { merged.push(serverList[s]); }
    for (var j = 0; j < state.local.length; j += 1) {
      if (serverById[state.local[j].id]) { continue; }
      merged.push(state.local[j]);
    }
    state.local = merged;
    writeStorage(state.local);
    rerender();
  }

  function loadServerAnnotations() {
    if (typeof window.fetch !== 'function') {
      state.syncFailed = true;
      return Promise.resolve();
    }
    return window.fetch(apiUrl(), {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      cache: 'no-store'
    }).then(function (response) {
      if (!response.ok) { throw new Error('HTTP ' + response.status); }
      return response.json();
    }).then(function (data) {
      var raw = data && Array.isArray(data.annotations) ? data.annotations : [];
      var server = [];
      for (var i = 0; i < raw.length; i += 1) {
        var item = normalizeAnnotation(raw[i]);
        if (item) { server.push(item); }
      }
      state.syncLoaded = true;
      state.syncFailed = false;
      mergeServerAnnotations(server);
    }).catch(function () {
      state.syncFailed = true;
    });
  }

  function newId() {
    return 'p2h-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 7);
  }
  function nowIso() {
    try { return new Date().toISOString(); } catch (err) { return ''; }
  }
  function normalizeSpace(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
  }
  function excerpt(text, limit) {
    var t = normalizeSpace(text);
    if (t.length <= limit) { return t; }
    return t.slice(0, limit - 1) + '…';
  }
  function commonPrefix(a, b) {
    var n = Math.min(a.length, b.length);
    var i = 0;
    while (i < n && a.charAt(i) === b.charAt(i)) { i += 1; }
    return i;
  }
  function commonSuffix(a, b) {
    var n = Math.min(a.length, b.length);
    var i = 0;
    while (i < n && a.charAt(a.length - 1 - i) === b.charAt(b.length - 1 - i)) { i += 1; }
    return i;
  }

  // ------------------------------------------------------------ text index ---
  function buildIndex() {
    var index = { text: '', nodes: [], lookup: new WeakMap() };
    var walker = document.createTreeWalker(rootEl(), NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        if (!node.nodeValue || !node.nodeValue.length) { return NodeFilter.FILTER_REJECT; }
        var parent = node.parentElement;
        if (!parent) { return NodeFilter.FILTER_REJECT; }
        if (parent.closest(IGNORE_SELECTOR)) { return NodeFilter.FILTER_REJECT; }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var node = walker.nextNode();
    while (node) {
      var entry = { node: node, start: index.text.length, text: node.nodeValue };
      index.nodes.push(entry);
      index.lookup.set(node, entry);
      index.text += node.nodeValue;
      node = walker.nextNode();
    }
    return index;
  }

  function firstPosIn(node) {
    if (!node) { return null; }
    if (node.nodeType === 3) {
      var info = state.index.lookup.get(node);
      return info ? info.start : null;
    }
    for (var i = 0; i < node.childNodes.length; i += 1) {
      var pos = firstPosIn(node.childNodes[i]);
      if (pos !== null) { return pos; }
    }
    return null;
  }
  function lastPosIn(node) {
    if (!node) { return null; }
    if (node.nodeType === 3) {
      var info = state.index.lookup.get(node);
      return info ? info.start + info.text.length : null;
    }
    for (var i = node.childNodes.length - 1; i >= 0; i -= 1) {
      var pos = lastPosIn(node.childNodes[i]);
      if (pos !== null) { return pos; }
    }
    return null;
  }
  function resolvePos(container, offset, isEnd) {
    if (!container) { return null; }
    if (container.nodeType === 3) {
      var info = state.index.lookup.get(container);
      if (!info) { return null; }
      var local = Math.max(0, Math.min(offset, info.text.length));
      return info.start + local;
    }
    var children = container.childNodes || [];
    if (isEnd) {
      for (var i = Math.min(offset, children.length) - 1; i >= 0; i -= 1) {
        var endPos = lastPosIn(children[i]);
        if (endPos !== null) { return endPos; }
      }
    } else {
      for (var j = Math.max(0, offset); j < children.length; j += 1) {
        var startPos = firstPosIn(children[j]);
        if (startPos !== null) { return startPos; }
      }
    }
    return null;
  }

  function inIgnored(node) {
    var el = node && (node.nodeType === 3 ? node.parentElement : node);
    return !!(el && el.closest && el.closest(IGNORE_SELECTOR));
  }

  function selectionRangeInfo() {
    var sel = window.getSelection ? window.getSelection() : null;
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) { return null; }
    var range = sel.getRangeAt(0);
    var root = rootEl();
    try {
      if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) { return null; }
    } catch (err) {
      return null;
    }
    if (inIgnored(range.startContainer) || inIgnored(range.endContainer)) { return null; }
    var start = resolvePos(range.startContainer, range.startOffset, false);
    var end = resolvePos(range.endContainer, range.endOffset, true);
    if (start === null || end === null || end <= start) { return null; }
    var exact = state.index.text.slice(start, end);
    if (normalizeSpace(exact).length < 2) { return null; }
    var prefix = state.index.text.slice(Math.max(0, start - ANCHOR_CONTEXT), start);
    var suffix = state.index.text.slice(end, end + ANCHOR_CONTEXT);
    return {
      start: start,
      end: end,
      exact: exact,
      prefix: prefix,
      suffix: suffix,
      rect: range.getBoundingClientRect()
    };
  }

  function overlapsExisting(start, end) {
    var ids = Object.keys(state.resolved || {});
    for (var i = 0; i < ids.length; i += 1) {
      var pos = state.resolved[ids[i]];
      var ann = null;
      for (var j = 0; j < state.all.length; j += 1) {
        if (state.all[j].id === ids[i]) { ann = state.all[j]; break; }
      }
      if (!ann) { continue; }
      var annEnd = pos + ann.quote.exact.length;
      if (start < annEnd && end > pos) { return true; }
    }
    return false;
  }

  // -------------------------------------------------------------- sections ---
  function collectHeadings() {
    var list = [];
    var headings = all('h1, h2, h3, h4, h5, h6', rootEl());
    for (var i = 0; i < headings.length; i += 1) {
      var pos = firstPosIn(headings[i]);
      if (pos === null) { continue; }
      var text = normalizeSpace(headings[i].textContent || '');
      if (text) { list.push({ pos: pos, text: excerpt(text, 60) }); }
    }
    list.sort(function (a, b) { return a.pos - b.pos; });
    return list;
  }
  function sectionAt(pos) {
    var label = '';
    for (var i = 0; i < state.headings.length; i += 1) {
      if (state.headings[i].pos <= pos) { label = state.headings[i].text; } else { break; }
    }
    return label;
  }

  // --------------------------------------------------------------- locate ---
  function locateAnnotation(quote) {
    var exact = quote && quote.exact ? quote.exact : '';
    if (!exact) { return null; }
    var text = state.index.text;
    var positions = [];
    var from = 0;
    while (positions.length < 400) {
      var found = text.indexOf(exact, from);
      if (found === -1) { break; }
      positions.push(found);
      from = found + 1;
    }
    if (!positions.length) { return null; }
    if (positions.length === 1) { return positions[0]; }
    var prefix = quote.prefix || '';
    var suffix = quote.suffix || '';
    var best = null;
    var bestScore = -1;
    for (var i = 0; i < positions.length; i += 1) {
      var pos = positions[i];
      var score = 0;
      if (prefix) {
        var before = text.slice(Math.max(0, pos - prefix.length), pos);
        score += before === prefix ? Math.min(prefix.length, 24) : Math.min(commonSuffix(before, prefix), 8);
      }
      if (suffix) {
        var after = text.slice(pos + exact.length, pos + exact.length + suffix.length);
        score += after === suffix ? Math.min(suffix.length, 24) : Math.min(commonPrefix(after, suffix), 8);
      }
      if (score > bestScore) {
        bestScore = score;
        best = pos;
      }
    }
    return best;
  }

  // ---------------------------------------------------------------- marks ---
  function unwrapMarks() {
    var marks = all('mark.p2h-hl', rootEl());
    for (var i = 0; i < marks.length; i += 1) {
      var mark = marks[i];
      var parent = mark.parentNode;
      if (!parent) { continue; }
      while (mark.firstChild) { parent.insertBefore(mark.firstChild, mark); }
      parent.removeChild(mark);
      try { parent.normalize(); } catch (err) { /* ignore */ }
    }
  }

  function wrapRange(start, end, ann) {
    var targets = [];
    for (var i = 0; i < state.index.nodes.length; i += 1) {
      var entry = state.index.nodes[i];
      var nodeEnd = entry.start + entry.text.length;
      if (nodeEnd <= start || entry.start >= end) { continue; }
      targets.push({
        node: entry.node,
        start: Math.max(start, entry.start) - entry.start,
        end: Math.min(end, nodeEnd) - entry.start
      });
    }
    for (var j = targets.length - 1; j >= 0; j -= 1) {
      var target = targets[j];
      var node = target.node;
      if (!node || !node.parentNode) { continue; }
      if (target.start > 0) { node = node.splitText(target.start); }
      var length = target.end - target.start;
      if (length < node.nodeValue.length) {
        // 只切掉目标区间后面的尾巴，保留 node 本身（目标区间）用于包裹
        node.splitText(length);
      }
      var mark = document.createElement('mark');
      mark.className = 'p2h-hl';
      mark.setAttribute('data-p2h-id', ann.id);
      mark.setAttribute('data-p2h-color', ann.color);
      mark.setAttribute('title', ann.note ? ('批注：' + excerpt(ann.note, 40)) : (COLOR_LABELS[ann.color] || '高亮'));
      node.parentNode.insertBefore(mark, node);
      mark.appendChild(node);
    }
  }

  function rerender() {
    unwrapMarks();
    state.index = buildIndex();
    state.headings = collectHeadings();
    state.all = mergeLists(state.embedded, state.local);
    state.resolved = {};
    for (var i = 0; i < state.all.length; i += 1) {
      var ann = state.all[i];
      var pos = locateAnnotation(ann.quote);
      if (pos === null) {
        ann.__resolved = false;
        ann.__start = null;
        continue;
      }
      ann.__resolved = true;
      ann.__start = pos;
      state.resolved[ann.id] = pos;
      wrapRange(pos, pos + ann.quote.exact.length, ann);
    }
    renderPanel();
  }

  // ---------------------------------------------------------------- panel ---
  function annotationCountLabel() {
    return String(state.all.length);
  }

  function renderPanel() {
    var list = byId('p2h-annotation-list');
    var banner = byId('p2h-share-banner');
    var total = byId('p2h-annotation-total');
    var toggleCount = byId('p2h-annotation-count');

    if (toggleCount) {
      toggleCount.textContent = annotationCountLabel();
      toggleCount.hidden = state.all.length === 0;
    }
    if (total) {
      total.textContent = state.all.length ? '（' + state.all.length + ' 条）' : '';
    }
    if (banner) {
      if (state.embedded.length > 0) {
        banner.style.display = '';
        banner.textContent = '分享版：含 ' + state.embedded.length + ' 条批注（可继续添加自己的批注，再次导出会合并）';
      } else {
        banner.style.display = 'none';
        banner.textContent = '';
      }
    }
    if (!list) { return; }
    list.textContent = '';

    if (!state.all.length) {
      var empty = document.createElement('p');
      empty.className = 'p2h-empty';
      empty.textContent = '还没有批注。选中正文里的文字，就可以高亮或写批注。';
      list.appendChild(empty);
      return;
    }

    var sorted = state.all.slice().sort(function (a, b) {
      var aStart = a.__resolved && typeof a.__start === 'number' ? a.__start : Number.MAX_SAFE_INTEGER;
      var bStart = b.__resolved && typeof b.__start === 'number' ? b.__start : Number.MAX_SAFE_INTEGER;
      if (aStart !== bStart) { return aStart - bStart; }
      return String(a.createdAt || '').localeCompare(String(b.createdAt || ''));
    });

    var embeddedIds = {};
    for (var i = 0; i < state.embedded.length; i += 1) { embeddedIds[state.embedded[i].id] = true; }

    for (var j = 0; j < sorted.length; j += 1) {
      list.appendChild(buildItem(sorted[j], embeddedIds[sorted[j].id]));
    }
  }

  function buildItem(ann, isShared) {
    var item = document.createElement('div');
    item.className = 'p2h-annotation-item' + (ann.__resolved ? '' : ' p2h-unresolved');
    item.setAttribute('data-p2h-annid', ann.id);
    item.setAttribute('role', 'button');
    item.setAttribute('tabindex', '0');

    var bar = document.createElement('span');
    bar.className = 'p2h-color-bar';
    bar.setAttribute('data-color', ann.color);
    item.appendChild(bar);

    var body = document.createElement('div');
    body.className = 'p2h-item-body';

    var quote = document.createElement('blockquote');
    quote.className = 'p2h-quote';
    quote.textContent = '“' + excerpt(ann.quote.exact, MAX_QUOTE) + '”';
    body.appendChild(quote);

    var note = document.createElement('p');
    note.className = 'p2h-note' + (ann.note ? '' : ' p2h-note-empty');
    note.textContent = ann.note || '（仅高亮，没有批注文字）';
    body.appendChild(note);

    var meta = document.createElement('div');
    meta.className = 'p2h-meta';
    var section = document.createElement('span');
    section.className = 'p2h-section-label';
    section.textContent = ann.sectionId ? '📍 ' + ann.sectionId : '📍 全文';
    meta.appendChild(section);

    if (!ann.__resolved) {
      var warn = document.createElement('span');
      warn.className = 'p2h-badge p2h-badge-warn';
      warn.textContent = '未找到原文位置';
      meta.appendChild(warn);
    }
    if (isShared) {
      var shared = document.createElement('span');
      shared.className = 'p2h-badge p2h-badge-shared';
      shared.textContent = '分享';
      meta.appendChild(shared);
    }

    if (!isShared) {
      var del = document.createElement('button');
      del.type = 'button';
      del.className = 'p2h-delete-btn';
      del.textContent = '删除';
      del.setAttribute('aria-label', '删除这条批注');
      del.addEventListener('click', function (event) {
        event.stopPropagation();
        removeLocal(ann.id);
      });
      meta.appendChild(del);
    }

    body.appendChild(meta);
    item.appendChild(body);

    item.addEventListener('click', function () { focusAnnotation(ann.id); });
    item.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        focusAnnotation(ann.id);
      }
    });
    return item;
  }

  function focusAnnotation(id) {
    var marks = all('mark.p2h-hl[data-p2h-id="' + id + '"]', rootEl());
    if (!marks.length) { return; }
    var first = marks[0];
    try {
      first.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } catch (err) {
      first.scrollIntoView();
    }
    for (var i = 0; i < marks.length; i += 1) {
      marks[i].classList.remove('p2h-hl-flash');
      /* 强制 reflow，保证重复点击还能再闪一次 */
      void marks[i].offsetWidth;
      marks[i].classList.add('p2h-hl-flash');
    }
  }

  function removeLocal(id) {
    var next = [];
    for (var i = 0; i < state.local.length; i += 1) {
      if (state.local[i].id !== id) { next.push(state.local[i]); }
    }
    state.local = next;
    writeStorage(state.local);
    rerender();
    scheduleSync();
  }

  function clearLocal() {
    if (!state.local.length) { return; }
    var ok = true;
    try {
      ok = window.confirm('清空你在本页添加的 ' + state.local.length + ' 条批注？（分享版内嵌的批注不会被删除）');
    } catch (err) {
      ok = true;
    }
    if (!ok) { return; }
    state.local = [];
    writeStorage([]);
    rerender();
    scheduleSync();
  }

  function openPanel() {
    var panel = byId('p2h-annotation-panel');
    var toggle = byId('p2h-annotate-toggle');
    if (!panel) { return; }
    panel.classList.add('p2h-open');
    panel.setAttribute('aria-hidden', 'false');
    document.body.classList.add('p2h-panel-open');
    if (toggle) { toggle.setAttribute('aria-expanded', 'true'); }
  }
  function closePanel() {
    var panel = byId('p2h-annotation-panel');
    var toggle = byId('p2h-annotate-toggle');
    if (!panel) { return; }
    panel.classList.remove('p2h-open');
    panel.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('p2h-panel-open');
    if (toggle) { toggle.setAttribute('aria-expanded', 'false'); }
  }
  function togglePanel() {
    var panel = byId('p2h-annotation-panel');
    if (panel && panel.classList.contains('p2h-open')) { closePanel(); } else { openPanel(); }
  }

  // -------------------------------------------------------------- toolbar ---
  function showToolbar(rect) {
    var toolbar = byId('p2h-selection-toolbar');
    if (!toolbar) { return; }
    state.pendingRect = rect;
    toolbar.classList.add('p2h-visible');
    var width = toolbar.offsetWidth || 240;
    var height = toolbar.offsetHeight || 40;
    var left = (rect && rect.left ? rect.left + rect.width / 2 : window.innerWidth / 2) - width / 2;
    var top = rect && rect.bottom ? rect.bottom + 8 : window.innerHeight / 2;
    if (top + height > window.innerHeight - 10) {
      top = (rect && rect.top ? rect.top : top) - height - 8;
    }
    left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
    top = Math.max(8, Math.min(top, window.innerHeight - height - 8));
    toolbar.style.left = Math.round(left) + 'px';
    toolbar.style.top = Math.round(top) + 'px';
  }
  function hideToolbar() {
    var toolbar = byId('p2h-selection-toolbar');
    if (toolbar) { toolbar.classList.remove('p2h-visible'); }
    state.pendingRange = null;
    state.pendingRect = null;
  }

  function showEditor() {
    var editor = byId('p2h-note-editor');
    var input = byId('p2h-note-input');
    if (!editor) { return; }
    editor.classList.add('p2h-visible');
    var rect = state.pendingRect;
    var width = 292;
    var height = editor.offsetHeight || 170;
    var left = (rect && rect.left ? rect.left + rect.width / 2 : window.innerWidth / 2) - width / 2;
    var top = rect && rect.bottom ? rect.bottom + 10 : window.innerHeight / 2;
    if (top + height > window.innerHeight - 10) {
      top = (rect && rect.top ? rect.top : top) - height - 10;
    }
    left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
    top = Math.max(8, Math.min(top, window.innerHeight - height - 8));
    editor.style.left = Math.round(left) + 'px';
    editor.style.top = Math.round(top) + 'px';
    if (input) {
      input.value = '';
      try { input.focus(); } catch (err) { /* ignore */ }
    }
  }
  function hideEditor() {
    var editor = byId('p2h-note-editor');
    if (editor) { editor.classList.remove('p2h-visible'); }
    state.noteRange = null;
  }
  function editorVisible() {
    var editor = byId('p2h-note-editor');
    return !!(editor && editor.classList.contains('p2h-visible'));
  }

  function clearSelection() {
    try {
      var sel = window.getSelection ? window.getSelection() : null;
      if (sel && sel.removeAllRanges) { sel.removeAllRanges(); }
    } catch (err) { /* ignore */ }
  }

  function createAnnotation(color, note, rangeInfo) {
    var pending = rangeInfo || state.pendingRange || state.noteRange;
    if (!pending) { return; }
    var ann = {
      id: newId(),
      color: COLORS.indexOf(color) === -1 ? DEFAULT_COLOR : color,
      note: typeof note === 'string' ? note : '',
      quote: { exact: pending.exact, prefix: pending.prefix, suffix: pending.suffix },
      sectionId: sectionAt(pending.start),
      createdAt: nowIso()
    };
    state.local.push(ann);
    writeStorage(state.local);
    state.lastColor = ann.color;
    state.noteRange = null;
    hideToolbar();
    hideEditor();
    clearSelection();
    rerender();
    scheduleSync();
  }

  // --------------------------------------------------------------- export ---
  function exportFileName() {
    var meta = document.querySelector('meta[name="p2h-file-name"]');
    var base = meta ? (meta.getAttribute('content') || '') : '';
    if (!base) {
      try {
        base = decodeURIComponent(((window.location && window.location.pathname) || '').split('/').pop() || '');
      } catch (err) {
        base = '';
      }
      base = base.replace(/\.html?$/i, '');
    }
    base = String(base || 'paper').replace(/[\\/:*?"<>|\s]+/g, '-').replace(/^-+|-+$/g, '');
    base = base.replace(/-(annotated)$/i, '');
    return (base || 'paper') + '-annotated.html';
  }

  function buildExportHtml() {
    var merged = mergeLists(state.embedded, state.local);
    var json;
    try {
      json = JSON.stringify(merged).replace(/</g, '\\u003c');
    } catch (err) {
      json = '[]';
    }

    // 导出当前页面的副本：静态 <mark> 一并带上（对方打开即见高亮），
    // 但清掉侧栏/工具条/输入框的临时打开状态，避免把「正在编辑」的样子带出去。
    var clone = document.documentElement.cloneNode(true);
    function pick(selector) { return clone.querySelector ? clone.querySelector(selector) : null; }
    function pickAll(selector) { return clone.querySelectorAll ? clone.querySelectorAll(selector) : []; }

    var oldJson = pick('#p2h-annotations');
    if (oldJson && oldJson.parentNode) { oldJson.parentNode.removeChild(oldJson); }

    var body = pick('body');
    if (body) { body.classList.remove('p2h-panel-open'); }

    var panel = pick('#p2h-annotation-panel');
    if (panel) {
      panel.classList.remove('p2h-open');
      panel.setAttribute('aria-hidden', 'true');
      var list = panel.querySelector('#p2h-annotation-list');
      if (list) { list.textContent = ''; }
      var banner = panel.querySelector('#p2h-share-banner');
      if (banner) { banner.style.display = 'none'; banner.textContent = ''; }
    }
    var toolbar = pick('#p2h-selection-toolbar');
    if (toolbar) {
      toolbar.classList.remove('p2h-visible');
      toolbar.style.left = '';
      toolbar.style.top = '';
    }
    var editor = pick('#p2h-note-editor');
    if (editor) {
      editor.classList.remove('p2h-visible');
      editor.style.left = '';
      editor.style.top = '';
    }
    var textarea = pick('#p2h-note-input');
    if (textarea) {
      textarea.value = '';
      if (textarea.textContent) { textarea.textContent = ''; }
    }
    var toggle = pick('#p2h-annotate-toggle');
    if (toggle) { toggle.setAttribute('aria-expanded', 'false'); }
    var flashes = pickAll('mark.p2h-hl-flash');
    for (var i = 0; i < flashes.length; i += 1) { flashes[i].classList.remove('p2h-hl-flash'); }

    var html = '<!DOCTYPE html>\n' + clone.outerHTML;
    var openTag = '<script type="application/json" id="p2h-annotations">';
    var closeTag = '</scr' + 'ipt>';
    var block = openTag + json + closeTag;
    var bodyClose = html.lastIndexOf('</body>');
    if (bodyClose !== -1) {
      return html.slice(0, bodyClose) + block + html.slice(bodyClose);
    }
    var htmlClose = html.lastIndexOf('</html>');
    if (htmlClose !== -1) {
      return html.slice(0, htmlClose) + block + html.slice(htmlClose);
    }
    return html + block;
  }

  function exportAnnotated() {
    var html = buildExportHtml();
    var blob;
    try {
      blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    } catch (err) {
      return;
    }
    var url;
    try {
      url = URL.createObjectURL(blob);
    } catch (err) {
      return;
    }
    var link = document.createElement('a');
    link.href = url;
    link.download = exportFileName();
    link.rel = 'noopener';
    link.style.display = 'none';
    document.body.appendChild(link);
    try { link.click(); } catch (err) { /* ignore */ }
    document.body.removeChild(link);
    window.setTimeout(function () {
      try { URL.revokeObjectURL(url); } catch (err) { /* ignore */ }
    }, 4000);
  }

  // ---------------------------------------------------------------- events ---
  function handleSelection() {
    if (!state.index) { return; }
    var info = selectionRangeInfo();
    if (!info) { hideToolbar(); return; }
    if (overlapsExisting(info.start, info.end)) { hideToolbar(); return; }
    state.pendingRange = info;
    showToolbar(info.rect);
  }

  function bindEvents() {
    document.addEventListener('mouseup', function (event) {
      var target = event.target;
      if (target && target.closest && target.closest(UI_SELECTOR)) { return; }
      window.setTimeout(handleSelection, 10);
    });
    document.addEventListener('mousedown', function (event) {
      var target = event.target;
      if (target && target.closest && target.closest('#p2h-selection-toolbar, #p2h-note-editor')) { return; }
      if (!(target && target.closest && target.closest(UI_SELECTOR))) {
        hideToolbar();
        hideEditor();
      }
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        hideToolbar();
        hideEditor();
        closePanel();
      }
    });

    var toolbar = byId('p2h-selection-toolbar');
    if (toolbar) {
      toolbar.addEventListener('mousedown', function (event) { event.preventDefault(); });
      var dots = all('[data-p2h-color]', toolbar);
      for (var i = 0; i < dots.length; i += 1) {
        dots[i].addEventListener('click', function (event) {
          var color = this.getAttribute('data-p2h-color');
          if (COLORS.indexOf(color) === -1) { color = DEFAULT_COLOR; }
          createAnnotation(color, '');
        });
      }
      var addNote = byId('p2h-add-note');
      if (addNote) {
        addNote.addEventListener('click', function () {
          if (!state.pendingRange) { return; }
          state.noteRange = state.pendingRange;
          hideToolbar();
          showEditor();
        });
      }
    }

    var save = byId('p2h-note-save');
    if (save) {
      save.addEventListener('click', function () {
        var input = byId('p2h-note-input');
        createAnnotation(state.lastColor || DEFAULT_COLOR, input ? input.value : '', state.noteRange);
      });
    }
    var cancel = byId('p2h-note-cancel');
    if (cancel) {
      cancel.addEventListener('click', function () {
        state.noteRange = null;
        hideEditor();
        clearSelection();
      });
    }
    var noteInput = byId('p2h-note-input');
    if (noteInput) {
      noteInput.addEventListener('keydown', function (event) {
        if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
          event.preventDefault();
          var input = byId('p2h-note-input');
          createAnnotation(state.lastColor || DEFAULT_COLOR, input ? input.value : '', state.noteRange);
        }
      });
    }

    var toggle = byId('p2h-annotate-toggle');
    if (toggle) { toggle.addEventListener('click', togglePanel); }
    var close = byId('p2h-panel-close');
    if (close) { close.addEventListener('click', closePanel); }
    var exportBtn = byId('p2h-export-annotated');
    if (exportBtn) { exportBtn.addEventListener('click', exportAnnotated); }
    var clearBtn = byId('p2h-clear-annotations');
    if (clearBtn) { clearBtn.addEventListener('click', clearLocal); }

    document.addEventListener('click', function (event) {
      var target = event.target;
      if (!target || !target.closest) { return; }
      var mark = target.closest('mark.p2h-hl');
      if (!mark) { return; }
      var id = mark.getAttribute('data-p2h-id');
      if (!id) { return; }
      openPanel();
      var item = document.querySelector('.p2h-annotation-item[data-p2h-annid="' + id + '"]');
      if (item && item.scrollIntoView) {
        try { item.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } catch (err) { item.scrollIntoView(); }
      }
    });
  }

  // ------------------------------------------------------------------ init ---
  function markReady() {
    window[READY_FLAG] = true;
  }

  function init() {
    try {
      state.embedded = readEmbedded();
      state.local = readStorage();
      bindEvents();
      rerender();
      if (state.embedded.length > 0) { openPanel(); }
    } catch (err) {
      if (window.console && window.console.warn) {
        window.console.warn('[p2h-annotations] 初始化失败（页面其余功能不受影响）:', err);
      }
    }
    if (SERVER_MODE) {
      // http(s) 预览：先把本地渲染出来，再拉服务端批注合并；失败静默降级并提示。
      updateSyncStatus('local');
      loadServerAnnotations().then(function () {
        updateSyncStatus();
        markReady();
      });
    } else {
      updateSyncStatus('local');
      markReady();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
"""


def inject_annotation_assets(html: str, doc_id: Optional[str] = None, file_name: Optional[str] = None) -> str:
    """把批注 CSS / DOM / JS 注入到渲染好的 HTML 中。

    Args:
        html: renderer 生成的完整 HTML 字符串
        doc_id: 稳定的文档 id（localStorage key 用），为空时按 file_name 哈希兜底
        file_name: 源文件名（不含路径），作为导出文件名前缀；为空时用 "paper"

    Returns:
        注入后的 HTML
    """
    if not doc_id:
        fallback = str(file_name or "paper")
        doc_id = "doc-" + hashlib.sha1(fallback.encode("utf-8")).hexdigest()[:16]
    safe_doc_id = _html.escape(str(doc_id), quote=True)
    safe_file_name = _html.escape(str(file_name or "paper"), quote=True)

    head_block = (
        '<meta name="p2h-doc-id" content="%s">\n'
        '<meta name="p2h-file-name" content="%s">\n'
        '<style id="p2h-annotation-style">\n%s\n</style>\n'
        % (safe_doc_id, safe_file_name, ANNOTATION_CSS)
    )
    body_block = (
        "<!-- Paper2HTML annotations (F3): 页面内批注/高亮 + 带批注导出（无网络、无依赖） -->\n"
        "%s\n"
        '<script id="p2h-annotation-script">\n%s\n</script>\n'
        % (ANNOTATION_MARKUP, ANNOTATION_JS)
    )

    if "</head>" in html:
        html = html.replace("</head>", head_block + "</head>", 1)
    else:
        html = head_block + html
    if "</body>" in html:
        html = html.replace("</body>", body_block + "</body>", 1)
    else:
        html = html + body_block
    return html
