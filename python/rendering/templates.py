"""
HTML模板模块 - 生成单文件self-contained论文阅读器HTML

功能：
- 两栏布局（左导航+右内容）
- 阅读模式切换：速读/标准/精读
- KaTeX公式渲染
- Mermaid架构图渲染
- 图片base64内嵌
- 响应式设计
- 右侧Minimap导航
- 手风琴折叠面板
- ⌘K全文搜索
- 图表引用跳转
- 章节锚点链接
"""

from typing import Optional

# =============================================================================
# HTML模板
# =============================================================================

def generate_html_template(
    title: str,
    authors: list,
    tldr: str,
    key_findings: dict,
    section_summaries: list,
    structured: dict,
    mermaid_code: str,
    markdown_content: str,
    embedded_images: dict,
    style_css: str,
    responsive_css: str,
    current_style: str = "dark_lab",
    experiment_table: Optional[dict] = None
) -> str:
    """
    生成完整的HTML模板
    
    Args:
        title: 论文标题
        authors: 作者列表
        tldr: 一句话摘要
        key_findings: 关键发现字典
        section_summaries: 章节摘要列表
        structured: 结构化信息字典
        mermaid_code: Mermaid图代码
        markdown_content: 完整Markdown原文
        embedded_images: 图片名->base64的映射
        style_css: 样式预设CSS
        responsive_css: 响应式CSS
    
    Returns:
        完整的HTML字符串
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[TEMPLATE DEBUG] Received title='{title}'")
    
    # 构建作者字符串
    authors_html = ", ".join(authors) if authors else "Unknown Authors"
    
    # 构建关键发现HTML（仅列表）和核心贡献（独立区块，始终可见）
    key_findings_html, innovation, significance = _build_key_findings(key_findings)
    insight_html = _build_insight_section(innovation, significance)
    
    # 构建章节摘要HTML
    sections_html = _build_section_summaries(section_summaries, embedded_images)
    
    # 构建结构化信息面板HTML
    structured_html = _build_structured_panel(structured)
    
    # 构建实验数据图表HTML
    experiment_chart_html = _build_experiment_chart(experiment_table)
    
    # 替换Markdown中的图片引用为base64
    processed_markdown = _replace_images_in_markdown(markdown_content, embedded_images)
    
    # 构建Minimap内容块数据（用于JS初始化）
    minimap_blocks = _build_minimap_blocks()

    # 无 AI 理解（--no-understand / 本地模式）时，隐藏没有内容的区块，
    # 避免出现空白面板和空 Mermaid 代码导致的渲染错误。
    has_findings = _key_findings_count(key_findings) > 0
    has_insight = bool((innovation or "").strip() or (significance or "").strip())
    has_mermaid = bool((mermaid_code or "").strip())
    has_sections = bool((sections_html or "").strip())
    has_structured = bool((structured_html or "").strip())
    has_experiment = bool((experiment_chart_html or "").strip())

    toc_entries = [("paper-title", "论文信息"), ("tldr", "核心摘要")]
    if has_insight:
        toc_entries.append(("insight", "核心贡献"))
    if has_findings:
        toc_entries.append(("findings", "关键发现"))
    if has_mermaid:
        toc_entries.append(("architecture", "架构图"))
    if has_experiment:
        toc_entries.append(("experiment", "实验数据"))
    if has_sections:
        toc_entries.append(("sections", "章节阅读"))
    if has_structured:
        toc_entries.append(("structured", "结构化信息"))
    toc_entries.append(("full-text", "完整原文"))
    toc_items_html = "\n".join(
        f'<li class="toc-item"><a href="#{anchor}" class="toc-link">{label}</a></li>'
        for anchor, label in toc_entries
    )

    findings_section_html = "" if not has_findings else f"""
            <section class="accordion-card findings-card collapsed" id="findings" data-semantic="method">
                <div class="accordion-header" onclick="toggleAccordion(this.parentElement)">
                    <div class="accordion-header-left">
                        <div class="card-icon">🔍</div>
                        <h2 class="card-title">关键发现</h2>
                    </div>
                    <span class="accordion-toggle">▼</span>
                </div>
                <div class="accordion-hint">点击展开</div>
                <div class="accordion-content">
                    {key_findings_html}
                </div>
            </section>"""

    architecture_section_html = "" if not has_mermaid else f"""
            <section class="mermaid-container" id="architecture">
                <div class="mermaid">
{mermaid_code}
                </div>
            </section>"""

    sections_section_html = "" if not has_sections else f"""
            <section id="sections">
                {sections_html}
            </section>"""

    structured_section_html = "" if not has_structured else f"""
            <section class="card structured-panel" id="structured">
                <div class="card-header">
                    <div class="card-icon">📊</div>
                    <h2 class="card-title">结构化信息</h2>
                </div>
                <div class="structured-grid">
                    {structured_html}
                </div>
            </section>"""

    logger.info(f"[TEMPLATE DEBUG] Before f-string, title='{title}'")
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Paper2HTML</title>
    
    <style>
    /* ===========================================
       BASE STYLES
       =========================================== */
    * {{
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }}
    
    :root {{
        /* 布局变量 */
        --sidebar-width: 280px;
        --minimap-width: 58px;
        --header-height: 60px;
        --content-padding: 2rem;
        --card-padding: 1.5rem;
        
        /* 字体变量 - 使用clamp()实现响应式 */
        --title-size: clamp(1.5rem, 4vw, 2.5rem);
        --h2-size: clamp(1.25rem, 3vw, 1.75rem);
        --h3-size: clamp(1rem, 2.5vw, 1.25rem);
        --body-size: clamp(0.875rem, 1.5vw, 1rem);
        --small-size: clamp(0.75rem, 1vw, 0.875rem);
        
        /* 行高 */
        --line-height: 1.7;
        --line-height-heading: 1.3;
        
        /* 间距 */
        --spacing-xs: 0.25rem;
        --spacing-sm: 0.5rem;
        --spacing-md: 1rem;
        --spacing-lg: 1.5rem;
        --spacing-xl: 2rem;
        
        /* 圆角 */
        --radius-sm: 4px;
        --radius-md: 8px;
        --radius-lg: 12px;
        
        /* 语义色 */
        --semantic-abstract-bg: rgba(6, 95, 70, 0.09);
        --semantic-abstract-border: rgba(6, 95, 70, 0.3);
        --semantic-method-bg: rgba(76, 29, 149, 0.09);
        --semantic-method-border: rgba(76, 29, 149, 0.3);
        --semantic-experiment-bg: rgba(21, 94, 40, 0.09);
        --semantic-experiment-border: rgba(21, 94, 40, 0.3);
        --semantic-risk-bg: rgba(127, 29, 29, 0.09);
        --semantic-risk-border: rgba(127, 29, 29, 0.3);
    }}
    
    /* ===========================================
       CUSTOM CURSOR & TRAIL EFFECT
       =========================================== */
    .cursor-container {{
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: 99999;
        opacity: var(--cursor-enabled, 1);
        transition: opacity 0.3s ease;
    }}
    
    .cursor-container.disabled {{
        opacity: 0;
    }}
    
    /* 主光标 */
    .cursor-dot {{
        position: fixed;
        width: var(--cursor-size, 9px);
        height: var(--cursor-size, 9px);
        border-radius: 50%;
        background: var(--cursor-color, #58a6ff);
        pointer-events: none;
        transform: translate(-50%, -50%);
        mix-blend-mode: difference;
        box-shadow: 
            0 0 10px var(--cursor-glow, rgba(88, 166, 255, 0.6)),
            0 0 20px var(--cursor-glow, rgba(88, 166, 255, 0.4)),
            0 0 30px var(--cursor-glow, rgba(88, 166, 255, 0.2));
        transition: transform 0.1s ease, width 0.15s ease, height 0.15s ease;
        will-change: transform;
    }}
    
    .cursor-dot.hovering {{
        transform: translate(-50%, -50%) scale(1.5);
        width: calc(var(--cursor-size, 9px) * 1.5);
        height: calc(var(--cursor-size, 9px) * 1.5);
    }}
    
    /* 光标外环（hover效果） */
    .cursor-ring {{
        position: fixed;
        width: calc(var(--cursor-size, 9px) * 2);
        height: calc(var(--cursor-size, 9px) * 2);
        border-radius: 50%;
        border: 2px solid var(--cursor-color, #58a6ff);
        pointer-events: none;
        transform: translate(-50%, -50%);
        opacity: 0.5;
        mix-blend-mode: difference;
        transition: transform 0.2s ease, opacity 0.2s ease, width 0.2s ease, height 0.2s ease;
        will-change: transform;
    }}
    
    .cursor-ring.hovering {{
        opacity: 0.8;
        transform: translate(-50%, -50%) scale(1.3);
    }}
    
    /* 尾巴粒子 */
    .cursor-trail {{
        position: fixed;
        width: var(--cursor-trail-size, 4px);
        height: var(--cursor-trail-size, 4px);
        border-radius: 50%;
        background: var(--cursor-trail-color, #58a6ff);
        pointer-events: none;
        transform: translate(-50%, -50%);
        opacity: var(--cursor-trail-opacity, 0.7);
        mix-blend-mode: difference;
        box-shadow: 0 0 6px var(--cursor-trail-color, #58a6ff);
        will-change: transform, opacity;
    }}
    
    /* 隐藏默认光标（在内容区域） */
    .main-content,
    .sidebar,
    .minimap {{
        cursor: none;
    }}
    
    /* 触摸设备禁用光标效果 */
    @media (hover: none) and (pointer: coarse) {{
        .cursor-container {{
            display: none !important;
        }}
        .main-content,
        .sidebar,
        .minimap {{
            cursor: auto;
        }}
    }}
    
    /* 移动端禁用 */
    @media (max-width: 768px) {{
        .cursor-container {{
            display: none !important;
        }}
        .main-content,
        .sidebar,
        .minimap {{
            cursor: auto;
        }}
    }}
    
    /* 主题变量 - 由JS动态切换 */
    {style_css}
    
    /* ===========================================
       GLOBAL STYLES
       =========================================== */
    html {{
        scroll-behavior: smooth;
    }}
    
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        font-size: var(--body-size);
        line-height: var(--line-height);
        background-color: var(--bg-primary);
        color: var(--text-primary);
        min-height: 100vh;
    }}
    
    /* ===========================================
       LAYOUT
       =========================================== */
    .app-container {{
        display: flex;
        min-height: 100vh;
    }}
    
    /* 侧边栏 */
    .sidebar {{
        width: var(--sidebar-width);
        background: var(--bg-secondary);
        border-right: 1px solid var(--border-primary);
        position: fixed;
        top: 0;
        left: 0;
        height: 100vh;
        display: flex;
        flex-direction: column;
        z-index: 100;
        transition: transform 0.3s ease;
    }}
    
    .sidebar-header {{
        padding: var(--spacing-lg);
        border-bottom: 1px solid var(--border-primary);
    }}
    
    .sidebar-title {{
        font-size: var(--h3-size);
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: var(--spacing-sm);
    }}
    
    .sidebar-subtitle {{
        font-size: var(--small-size);
        color: var(--text-secondary);
    }}
    
    /* 进度条容器 */
    .progress-container {{
        padding: var(--spacing-md) var(--spacing-lg);
    }}
    
    /* 左侧导航进度条 */
    .sidebar-progress-wrapper {{
        position: relative;
        height: 4px;
        background: var(--progress-bg);
        border-radius: 2px;
        overflow: visible;
    }}
    
    .sidebar-progress-fill {{
        height: 100%;
        background: linear-gradient(90deg, #3b82f6, #8b5cf6);
        border-radius: 2px;
        width: 0%;
        transition: width 0.15s ease-out;
    }}
    
    .sidebar-progress-text {{
        position: absolute;
        top: 8px;
        right: 0;
        font-size: 10px;
        color: var(--text-secondary);
        font-weight: 500;
    }}
    
    /* 模式切换 */
    .mode-switcher {{
        padding: var(--spacing-md) var(--spacing-lg);
        display: flex;
        gap: var(--spacing-sm);
    }}
    
    .mode-btn {{
        flex: 1;
        padding: var(--spacing-sm) var(--spacing-md);
        border: 1px solid var(--border-primary);
        background: var(--bg-tertiary);
        color: var(--text-secondary);
        border-radius: var(--radius-sm);
        cursor: pointer;
        font-size: var(--small-size);
        transition: all 0.2s ease;
    }}
    
    .mode-btn:hover {{
        background: var(--bg-card);
        color: var(--text-primary);
    }}
    
    .mode-btn.active {{
        background: var(--accent);
        color: var(--bg-primary);
        border-color: var(--accent);
    }}
    
    /* TOC导航 - 升级版Scroll-Spy样式 */
    .toc-nav {{
        flex: 1;
        overflow-y: auto;
        padding: var(--spacing-md) var(--spacing-lg);
    }}
    
    .toc-list {{
        list-style: none;
    }}
    
    .toc-item {{
        margin-bottom: var(--spacing-xs);
    }}
    
    .toc-link {{
        display: block;
        padding: var(--spacing-sm) var(--spacing-md);
        color: #666;
        text-decoration: none;
        border-radius: var(--radius-sm);
        font-size: var(--small-size);
        transition: all 0.2s ease;
        border-left: 3px solid transparent;
    }}
    
    .toc-link:hover {{
        background: var(--bg-tertiary);
        color: var(--text-primary);
    }}
    
    /* P2: 升级的Active态 */
    .toc-link.active {{
        border-left-color: #3b82f6;
        background: rgba(59, 130, 246, 0.07);
        color: #3b82f6;
        font-weight: 500;
    }}
    
    /* 样式切换器 */
    .style-switcher {{
        padding: var(--spacing-md) var(--spacing-lg);
        border-top: 1px solid var(--border-primary);
    }}
    
    .style-switcher label {{
        display: block;
        font-size: var(--small-size);
        color: var(--text-secondary);
        margin-bottom: var(--spacing-sm);
    }}
    
    .style-select {{
        width: 100%;
        padding: var(--spacing-sm);
        background: var(--bg-tertiary);
        border: 1px solid var(--border-primary);
        color: var(--text-primary);
        border-radius: var(--radius-sm);
        font-size: var(--small-size);
        cursor: pointer;
    }}
    
    /* 主内容区 */
    .main-content {{
        flex: 1;
        margin-left: var(--sidebar-width);
        margin-right: var(--minimap-width);
        padding: var(--spacing-xl);
        max-width: calc(1200px - var(--minimap-width));
    }}
    
    /* P0: 右侧Minimap */
    .minimap {{
        position: fixed;
        top: 0;
        right: 0;
        width: var(--minimap-width);
        height: 100vh;
        background: #131313;
        border-left: 1px solid var(--border-primary);
        z-index: 99;
        overflow: hidden;
    }}
    
    .minimap-content {{
        position: relative;
        width: 100%;
        height: 100%;
    }}
    
    .minimap-block {{
        position: absolute;
        left: 4px;
        right: 4px;
        background: rgba(255, 255, 255, 0.15);
        border-radius: 2px;
        cursor: pointer;
        transition: background 0.2s;
    }}
    
    .minimap-block:hover {{
        background: rgba(255, 255, 255, 0.3);
    }}
    
    .minimap-block.active {{
        background: rgba(59, 130, 246, 0.4);
    }}
    
    /* 当前视口指示器 */
    .minimap-viewport {{
        position: absolute;
        left: 2px;
        right: 2px;
        height: 0;
        border: 1.5px solid #3b82f6;
        border-radius: 2px;
        box-shadow: 0 0 8px rgba(59, 130, 246, 0.5);
        pointer-events: none;
        transition: top 0.1s ease-out, height 0.1s ease-out;
    }}
    
    /* Function 1: 右侧阅读进度条 */
    .reading-progress-bar {{
        position: fixed;
        right: var(--minimap-width);
        top: 0;
        width: 3px;
        height: 100vh;
        background: var(--progress-bg);
        z-index: 100;
    }}
    
    .reading-progress-fill {{
        width: 100%;
        background: linear-gradient(to bottom, #3b82f6, #8b5cf6);
        height: 0%;
        transition: height 0.1s ease-out;
    }}
    
    /* 移动端导航切换按钮 */
    .mobile-nav-toggle {{
        display: none;
        position: fixed;
        bottom: 20px;
        right: 20px;
        width: 56px;
        height: 56px;
        background: var(--accent);
        color: var(--bg-primary);
        border: none;
        border-radius: 50%;
        font-size: 24px;
        cursor: pointer;
        z-index: 1001;
        box-shadow: var(--shadow-lg);
    }}
    
    .overlay {{
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        z-index: 99;
    }}
    
    /* ===========================================
       CONTENT CARDS
       =========================================== */
    
    /* 论文标题 */
    .paper-header {{
        margin-bottom: var(--spacing-xl);
        padding-bottom: var(--spacing-xl);
        border-bottom: 1px solid var(--border-primary);
    }}
    
    .paper-title {{
        font-size: var(--title-size);
        font-weight: 700;
        line-height: var(--line-height-heading);
        color: var(--text-primary);
        margin-bottom: var(--spacing-md);
    }}
    
    /* P5: 章节锚点链接 */
    .section-anchor {{
        opacity: 0;
        margin-left: 0.5rem;
        color: var(--text-muted);
        cursor: pointer;
        font-size: 0.8em;
        transition: opacity 0.2s;
    }}
    
    h1:hover .section-anchor,
    h2:hover .section-anchor,
    h3:hover .section-anchor {{
        opacity: 1;
    }}
    
    .anchor-copy-toast {{
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: var(--accent);
        color: white;
        padding: 8px 16px;
        border-radius: var(--radius-md);
        font-size: var(--small-size);
        z-index: 10000;
        opacity: 0;
        transition: opacity 0.3s;
        pointer-events: none;
    }}
    
    .anchor-copy-toast.show {{
        opacity: 1;
    }}
    
    .paper-authors {{
        font-size: var(--body-size);
        color: var(--text-secondary);
    }}
    
    /* P1: 手风琴卡片通用样式 */
    .accordion-card {{
        border-radius: var(--radius-lg);
        padding: var(--card-padding);
        margin-bottom: var(--spacing-lg);
        border: 1px solid;
        transition: all 0.3s ease;
    }}
    
    .accordion-card.collapsed .accordion-content {{
        display: none;
    }}
    
    .accordion-card.collapsed .accordion-header {{
        margin-bottom: 0;
    }}
    
    .accordion-card .accordion-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        cursor: pointer;
        margin-bottom: var(--spacing-lg);
    }}
    
    .accordion-header-left {{
        display: flex;
        align-items: center;
        gap: var(--spacing-md);
    }}
    
    .accordion-card .accordion-toggle {{
        color: var(--text-secondary);
        font-size: 18px;
        transition: transform 0.3s ease;
    }}
    
    .accordion-card.collapsed .accordion-toggle {{
        transform: rotate(-90deg);
    }}
    
    .accordion-hint {{
        font-size: var(--small-size);
        color: var(--text-muted);
        margin-top: var(--spacing-sm);
    }}
    
    /* P1: 语义色卡片 */
    /* TLDR - 摘要绿 */
    .tldr-card {{
        background: var(--semantic-abstract-bg);
        border-color: var(--semantic-abstract-border);
    }}
    
    .tldr-card .card-header {{
        background: none;
        padding: 0;
        margin-bottom: var(--spacing-lg);
    }}
    
    .tldr-card .card-icon {{
        background: #065f46;
    }}
    
    .tldr-card .card-title {{
        color: var(--text-primary);
    }}
    
    .tldr-content {{
        font-size: clamp(1rem, 2vw, 1.25rem);
        line-height: 1.6;
        font-weight: 500;
        color: var(--text-primary);
    }}
    
    /* 关键发现 - 核心方法紫 */
    .findings-card {{
        background: var(--semantic-method-bg);
        border-color: var(--semantic-method-border);
    }}
    
    .findings-card .card-icon {{
        background: #4c1d95;
    }}
    
    .findings-card .finding-item {{
        display: flex;
        gap: var(--spacing-md);
        margin-bottom: var(--spacing-lg);
        padding-bottom: var(--spacing-lg);
        border-bottom: 1px solid var(--border-secondary);
    }}
    
    .findings-card .finding-item:last-child {{
        margin-bottom: 0;
        padding-bottom: 0;
        border-bottom: none;
    }}
    
    .finding-number {{
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #4c1d95;
        color: white;
        border-radius: 50%;
        font-weight: 700;
        font-size: var(--small-size);
        flex-shrink: 0;
    }}
    
    .finding-content {{
        flex: 1;
    }}
    
    .finding-text {{
        color: var(--text-primary);
        margin-bottom: var(--spacing-sm);
    }}
    
    /* 创新点和研究意义 */
    .insight-section {{
        margin-top: var(--spacing-xl);
        padding-top: var(--spacing-xl);
        border-top: 1px solid var(--border-secondary);
    }}
    
    /* 核心贡献独立区块（始终可见） */
    .insight-always-visible {{
        margin-bottom: var(--spacing-lg);
    }}
    
    .insight-always-visible .insight-section {{
        margin-top: 0;
        padding-top: 0;
        border-top: none;
        background: var(--semantic-method-bg);
        border: 1px solid var(--semantic-method-border);
        border-radius: var(--radius-lg);
        padding: var(--card-padding);
    }}
    
    .insight-always-visible .insight-item {{
        margin-bottom: var(--spacing-md);
    }}
    
    .insight-always-visible .insight-item:last-child {{
        margin-bottom: 0;
    }}
    
    .insight-always-visible .insight-label {{
        color: var(--accent);
    }}
    
    .insight-always-visible .insight-text {{
        color: var(--text-primary);
        line-height: var(--line-height);
    }}
    
    .insight-item {{
        margin-bottom: var(--spacing-lg);
    }}
    
    .insight-label {{
        font-size: var(--small-size);
        font-weight: 600;
        color: #4c1d95;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: var(--spacing-sm);
    }}
    
    .insight-text {{
        color: var(--text-primary);
    }}
    
    /* Mermaid图容器 */
    .mermaid-container {{
        background: var(--bg-tertiary);
        border-radius: var(--radius-md);
        padding: var(--spacing-lg);
        margin-bottom: var(--spacing-xl);
        overflow-x: auto;
    }}
    
    .mermaid-container svg {{
        max-width: 100%;
        height: auto;
    }}
    
    /* 章节卡片 */
    .section-card {{
        margin-bottom: var(--spacing-lg);
    }}
    
    .section-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        cursor: pointer;
        padding: var(--spacing-md);
        background: var(--bg-tertiary);
        border-radius: var(--radius-md);
        transition: background 0.2s ease;
    }}
    
    .section-header:hover {{
        background: var(--border-primary);
    }}
    
    .section-title {{
        font-size: var(--h3-size);
        font-weight: 600;
        color: var(--text-primary);
    }}
    
    .section-toggle {{
        color: var(--text-secondary);
        font-size: 20px;
        transition: transform 0.3s ease;
    }}
    
    .section-card.collapsed .section-toggle {{
        transform: rotate(-90deg);
    }}
    
    .section-card.collapsed .section-content {{
        display: none;
    }}
    
    .section-summary {{
        color: var(--text-secondary);
        margin-bottom: var(--spacing-lg);
        line-height: 1.7;
    }}
    
    .section-points {{
        list-style: none;
        margin-bottom: var(--spacing-lg);
    }}
    
    .section-points li {{
        position: relative;
        padding-left: var(--spacing-lg);
        margin-bottom: var(--spacing-sm);
        color: var(--text-primary);
    }}
    
    .section-points li::before {{
        content: "•";
        position: absolute;
        left: 0;
        color: var(--accent);
        font-weight: bold;
    }}
    
    .section-formula, .section-table, .section-figure {{
        background: var(--bg-tertiary);
        padding: var(--spacing-md);
        border-radius: var(--radius-md);
        margin-bottom: var(--spacing-md);
    }}
    
    .formula-label, .table-label, .figure-label {{
        font-size: var(--small-size);
        color: var(--text-secondary);
        margin-bottom: var(--spacing-sm);
    }}
    
    /* P4: 图表引用 - 可点击 */
    .figure-ref {{
        color: var(--accent);
        cursor: pointer;
        text-decoration: none;
        border-bottom: 1px dashed var(--accent);
        transition: all 0.2s;
    }}
    
    .figure-ref:hover {{
        color: var(--accent-secondary);
        border-bottom-style: solid;
    }}
    
    .figure-ref.highlighted {{
        animation: figure-highlight 1.5s ease-out;
    }}
    
    @keyframes figure-highlight {{
        0% {{ box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.5); }}
        100% {{ box-shadow: 0 0 0 0px rgba(59, 130, 246, 0); }}
    }}
    
    /* 结构化信息面板 */
    .structured-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: var(--spacing-lg);
    }}
    
    .structured-item {{
        background: var(--bg-tertiary);
        padding: var(--spacing-lg);
        border-radius: var(--radius-md);
    }}
    
    .structured-item-title {{
        font-size: var(--small-size);
        font-weight: 600;
        color: var(--accent);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: var(--spacing-md);
    }}
    
    .structured-item-content {{
        color: var(--text-primary);
    }}
    
    .structured-item ul {{
        list-style: none;
    }}
    
    .structured-item li {{
        position: relative;
        padding-left: var(--spacing-lg);
        margin-bottom: var(--spacing-sm);
    }}
    
    .structured-item li::before {{
        content: "▹";
        position: absolute;
        left: 0;
        color: var(--accent);
    }}
    
    /* 完整Markdown原文 */
    .markdown-content {{
        line-height: 1.8;
    }}
    
    .markdown-content h1 {{
        font-size: var(--title-size);
        margin: var(--spacing-xl) 0 var(--spacing-lg);
        color: var(--text-primary);
    }}
    
    .markdown-content h2 {{
        font-size: var(--h2-size);
        margin: var(--spacing-xl) 0 var(--spacing-md);
        color: var(--text-primary);
        padding-bottom: var(--spacing-sm);
        border-bottom: 1px solid var(--border-primary);
    }}
    
    .markdown-content h3 {{
        font-size: var(--h3-size);
        margin: var(--spacing-lg) 0 var(--spacing-md);
        color: var(--text-primary);
    }}
    
    .markdown-content p {{
        margin-bottom: var(--spacing-md);
        color: var(--text-secondary);
    }}
    
    .markdown-content img {{
        max-width: 100%;
        height: auto;
        border-radius: var(--radius-md);
        margin: var(--spacing-lg) 0;
    }}
    
    .markdown-content pre {{
        background: var(--bg-tertiary);
        padding: var(--spacing-md);
        border-radius: var(--radius-md);
        overflow-x: auto;
        margin-bottom: var(--spacing-md);
    }}
    
    .markdown-content code {{
        font-family: 'SF Mono', 'Fira Code', monospace;
        font-size: 0.9em;
    }}
    
    .markdown-content pre code {{
        color: var(--text-primary);
    }}
    
    .markdown-content :not(pre) > code {{
        background: var(--bg-tertiary);
        padding: 2px 6px;
        border-radius: var(--radius-sm);
        color: var(--accent);
    }}
    
    /* 阅读模式控制（本地无 AI 摘要时「完整原文」就是主内容，因此任何模式都保留它） */
    .reading-mode[data-mode="quick"] .section-card,
    .reading-mode[data-mode="quick"] .structured-panel {{
        display: none !important;
    }}
    
    .reading-mode[data-mode="deep"] .tldr-card,
    .reading-mode[data-mode="deep"] .findings-card,
    .reading-mode[data-mode="deep"] .mermaid-container {{
        display: none !important;
    }}
    
    /* Function 2: 搜索高亮 */
    .search-highlight {{
        background: rgba(251, 191, 36, 0.35);
        border-radius: 2px;
        padding: 0 2px;
    }}
    
    /* ===========================================
       ECharts 实验数据图表样式
       =========================================== */
    .experiment-chart-section {{
        background: var(--semantic-experiment-bg);
        border: 1px solid var(--semantic-experiment-border);
        border-radius: var(--radius-lg);
        padding: var(--card-padding);
        margin-bottom: var(--spacing-xl);
    }}
    
    .experiment-chart-header {{
        display: flex;
        align-items: center;
        gap: var(--spacing-md);
        margin-bottom: var(--spacing-lg);
    }}
    
    .experiment-chart-container {{
        width: 100%;
        height: 400px;
        background: var(--bg-tertiary);
        border-radius: var(--radius-md);
        position: relative;
    }}
    
    .experiment-chart-loading,
    .experiment-chart-offline {{
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        color: var(--text-secondary);
        text-align: center;
        font-size: var(--small-size);
    }}
    
    .experiment-chart-offline {{
        background: var(--bg-secondary);
        padding: var(--spacing-lg);
        border-radius: var(--radius-md);
        border: 1px dashed var(--border-primary);
        max-width: 300px;
    }}
    
    .experiment-chart-table {{
        margin-top: var(--spacing-lg);
        overflow-x: auto;
    }}
    
    .experiment-chart-table table {{
        width: 100%;
        border-collapse: collapse;
        font-size: var(--small-size);
    }}
    
    .experiment-chart-table th,
    .experiment-chart-table td {{
        padding: var(--spacing-sm) var(--spacing-md);
        text-align: left;
        border-bottom: 1px solid var(--border-primary);
    }}
    
    .experiment-chart-table th {{
        background: var(--bg-tertiary);
        font-weight: 600;
        color: var(--text-primary);
    }}
    
    .experiment-chart-table td {{
        color: var(--text-secondary);
    }}
    
    .experiment-chart-table tr:hover td {{
        background: var(--bg-tertiary);
    }}
    
    /* 精读模式隐藏图表 */
    .reading-mode[data-mode="deep"] .experiment-chart-section {{
        display: none !important;
    }}
    
    /* ===========================================
       KATEX公式样式覆盖
       =========================================== */
    .katex {{
        font-size: 1.1em;
    }}
    
    .katex-display {{
        margin: var(--spacing-lg) 0;
        overflow-x: auto;
    }}
    
    /* ===========================================
       SCROLLBAR STYLES
       =========================================== */
    ::-webkit-scrollbar {{
        width: 8px;
        height: 8px;
    }}
    
    ::-webkit-scrollbar-track {{
        background: var(--scrollbar-track);
    }}
    
    ::-webkit-scrollbar-thumb {{
        background: var(--scrollbar-thumb);
        border-radius: 4px;
    }}
    
    ::-webkit-scrollbar-thumb:hover {{
        background: var(--scrollbar-thumb-hover);
    }}
    
    /* ===========================================
       REDUCED MOTION
       =========================================== */
    @media (prefers-reduced-motion: reduce) {{
        * {{
            animation-duration: 0.01ms !important;
            transition-duration: 0.2s !important;
        }}
    }}
    
    /* ===========================================
       RESPONSIVE STYLES
       =========================================== */
    {responsive_css}
    </style>
</head>
<body class="reading-mode {current_style}" data-mode="standard">
    
    <!-- Custom Cursor & Trail -->
    <div class="cursor-container" id="cursorContainer">
        <div class="cursor-ring" id="cursorRing"></div>
        <div class="cursor-dot" id="cursorDot"></div>
    </div>
    
    <!-- 锚点复制提示 -->
    <div class="anchor-copy-toast" id="anchorToast">已复制链接!</div>
    
    <!-- 移动端遮罩层 -->
    <div class="overlay" id="overlay"></div>
    
    <!-- 移动端导航按钮 -->
    <button class="mobile-nav-toggle" id="mobileToggle">☰</button>
    
    <!-- Function 1: 右侧阅读进度条 -->
    <div class="reading-progress-bar">
        <div class="reading-progress-fill" id="readingProgressFill"></div>
    </div>
    
    <div class="app-container">
        <!-- 侧边栏 -->
        <aside class="sidebar" id="sidebar">
            <div class="sidebar-header">
                <div class="sidebar-title">📄 Paper2HTML</div>
                <div class="sidebar-subtitle">论文阅读器</div>
            </div>
            
            <!-- 阅读进度 -->
            <div class="progress-container">
                <div class="sidebar-progress-wrapper">
                    <div class="sidebar-progress-fill" id="sidebarProgressFill"></div>
                </div>
                <div class="sidebar-progress-text" id="sidebarProgressText">0%</div>
            </div>
            
            <!-- 模式切换 -->
            <div class="mode-switcher">
                <button class="mode-btn" data-mode="quick">速读</button>
                <button class="mode-btn active" data-mode="standard">标准</button>
                <button class="mode-btn" data-mode="deep">精读</button>
            </div>
            
            <!-- 目录导航 -->
            <nav class="toc-nav">
                <ul class="toc-list" id="tocList">
{toc_items_html}
                </ul>
            </nav>
            
            <!-- 样式切换 -->
            <div class="style-switcher">
                <label for="styleSelect">主题样式</label>
                <select id="styleSelect" class="style-select">
                    <option value="dark_lab" {"selected" if current_style == "dark_lab" else ""}>🌙 Dark Lab</option>
                    <option value="clean_paper" {"selected" if current_style == "clean_paper" else ""}>📄 Clean Paper</option>
                    <option value="neon_tech" {"selected" if current_style == "neon_tech" else ""}>💜 Neon Tech</option>
                </select>
            </div>
        </aside>
        
        <!-- 主内容区 -->
        <main class="main-content">
            
            <!-- 论文标题 -->
            <header class="paper-header" id="paper-title">
                <h1 class="paper-title">
                    {title}
                    <span class="section-anchor" data-anchor="paper-title" title="复制链接">#</span>
                </h1>
                <p class="paper-authors">{authors_html}</p>
            </header>
            
            <!-- P1: TL;DR 手风琴卡片（默认展开） -->
            <section class="accordion-card tldr-card" id="tldr" data-semantic="abstract">
                <div class="accordion-header" onclick="toggleAccordion(this.parentElement)">
                    <div class="accordion-header-left">
                        <div class="card-icon">⚡</div>
                        <h2 class="card-title">TL;DR · 一句话核心贡献</h2>
                    </div>
                    <span class="accordion-toggle">▼</span>
                </div>
                <div class="accordion-content">
                    <p class="tldr-content">{tldr}</p>
                </div>
                <div class="accordion-hint" style="display:none;">点击展开</div>
            </section>
            
            <!-- P1: 核心贡献独立区块（始终可见，不参与手风琴折叠） -->
            {insight_html}
            
            <!-- P1: 关键发现手风琴卡片（默认折叠；无内容时整块省略） -->
            {findings_section_html}

            <!-- Mermaid架构图（无图时省略） -->
            {architecture_section_html}

            <!-- ECharts实验数据对比图 -->
            {experiment_chart_html}

            <!-- 章节阅读区（无章节摘要时省略） -->
            {sections_section_html}

            <!-- 结构化信息面板（无内容时省略） -->
            {structured_section_html}
            
            <!-- 完整Markdown原文 -->
            <section class="card markdown-section" id="full-text">
                <div class="card-header">
                    <div class="card-icon">📝</div>
                    <h2 class="card-title">完整原文</h2>
                </div>
                <div class="markdown-content" id="markdownContent">
                    {processed_markdown}
                </div>
            </section>
            
        </main>
        
        <!-- P0: 右侧Minimap -->
        <div class="minimap" id="minimap">
            <div class="minimap-content" id="minimapContent">
                <div class="minimap-viewport" id="minimapViewport"></div>
            </div>
        </div>
    </div>
    
    <!-- Function 2: ⌘K 搜索框 -->
    <div class="search-modal" id="searchModal" style="display:none;">
        <div class="search-overlay" onclick="closeSearch()"></div>
        <div class="search-box">
            <div class="search-input-wrapper">
                <input type="text" id="searchInput" placeholder="搜索全文..." autocomplete="off">
                <span class="search-shortcut">⌘K</span>
            </div>
            <div class="search-results-info" id="searchResultsInfo"></div>
            <div class="search-nav" id="searchNav" style="display:none;">
                <button class="search-nav-btn" onclick="prevMatch()">↑ 上一处</button>
                <span class="search-match-count" id="searchMatchCount"></span>
                <button class="search-nav-btn" onclick="nextMatch()">下一处 ↓</button>
            </div>
        </div>
    </div>
    
    <style>
    /* Function 2: 搜索框样式 */
    .search-modal {{
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 10000;
        display: flex;
        align-items: flex-start;
        justify-content: center;
        padding-top: 15vh;
    }}
    
    .search-overlay {{
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
    }}
    
    .search-box {{
        position: relative;
        width: 480px;
        max-width: 90vw;
        background: var(--bg-secondary);
        border: 1px solid var(--border-primary);
        border-radius: var(--radius-lg);
        box-shadow: var(--shadow-lg);
        overflow: hidden;
    }}
    
    .search-input-wrapper {{
        display: flex;
        align-items: center;
        padding: var(--spacing-md);
        border-bottom: 1px solid var(--border-primary);
    }}
    
    #searchInput {{
        flex: 1;
        background: transparent;
        border: none;
        outline: none;
        color: var(--text-primary);
        font-size: 1.1rem;
    }}
    
    #searchInput::placeholder {{
        color: var(--text-muted);
    }}
    
    .search-shortcut {{
        background: var(--bg-tertiary);
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        color: var(--text-muted);
    }}
    
    .search-results-info {{
        padding: var(--spacing-sm) var(--spacing-md);
        font-size: var(--small-size);
        color: var(--text-secondary);
    }}
    
    .search-nav {{
        display: flex;
        align-items: center;
        justify-content: center;
        gap: var(--spacing-md);
        padding: var(--spacing-sm) var(--spacing-md);
        border-top: 1px solid var(--border-primary);
    }}
    
    .search-nav-btn {{
        background: var(--bg-tertiary);
        border: 1px solid var(--border-primary);
        color: var(--text-secondary);
        padding: 6px 12px;
        border-radius: var(--radius-sm);
        cursor: pointer;
        font-size: var(--small-size);
    }}
    
    .search-nav-btn:hover {{
        background: var(--accent);
        color: white;
        border-color: var(--accent);
    }}
    
    .search-match-count {{
        color: var(--text-secondary);
        font-size: var(--small-size);
    }}
    </style>
    
    <!-- KaTeX CDN（可选，离线时降级） -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
    
    <!-- Mermaid CDN（可选，离线时降级） -->
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    
    <!-- ECharts CDN（可选，离线时显示提示） -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
    
    <script>
    /* ===========================================
       INITIALIZATION & INTERACTION
       =========================================== */
    document.addEventListener('DOMContentLoaded', function() {{
        // 初始化Mermaid
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'dark',
            securityLevel: 'loose',
            flowchart: {{ useMaxWidth: true, htmlLabels: true }}
        }});
        
        // 初始化KaTeX自动渲染
        if (typeof renderMathInElement !== 'undefined') {{
            renderMathInElement(document.body, {{
                delimiters: [
                    {{left: '$$', right: '$$', display: true}},
                    {{left: '$', right: '$', display: false}},
                    {{left: '\\\\[', right: '\\\\]', display: true}},
                    {{left: '\\\\(', right: '\\\\)', display: false}}
                ],
                throwOnError: false
            }});
        }}
        
        // 初始化阅读器
        initReader();
        
        // P6: 初始化光标效果
        initCursor();
        
        // Function 4: 处理图表引用
        initFigureRefs();
        
        // P0: 初始化Minimap
        initMinimap();
        
        // 初始化ECharts实验数据图表
        initExperimentCharts();
    }});
    
    function initReader() {{
        // 模式切换
        const modeBtns = document.querySelectorAll('.mode-btn');
        modeBtns.forEach(btn => {{
            btn.addEventListener('click', function() {{
                const mode = this.dataset.mode;
                modeBtns.forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                document.body.dataset.mode = mode;
            }});
        }});
        
        // P1: 手风琴互斥展开
        window.toggleAccordion = function(card) {{
            const wasCollapsed = card.classList.contains('collapsed');
            
            // 互斥模式：展开当前项时折叠其他卡片
            if (wasCollapsed) {{
                document.querySelectorAll('.accordion-card').forEach(c => {{
                    c.classList.add('collapsed');
                    const hint = c.querySelector('.accordion-hint');
                    if (hint) hint.style.display = 'block';
                }});
            }}
            
            card.classList.toggle('collapsed');
            const hint = card.querySelector('.accordion-hint');
            if (hint) hint.style.display = wasCollapsed ? 'none' : 'block';
        }};
        
        // P2: 进度条 - 使用requestAnimationFrame优化
        const progressFill = document.getElementById('progressFill');
        const sidebarProgressFill = document.getElementById('sidebarProgressFill');
        const sidebarProgressText = document.getElementById('sidebarProgressText');
        const readingProgressFill = document.getElementById('readingProgressFill');
        
        let ticking = false;
        
        function updateProgress() {{
            const scrollTop = window.scrollY;
            const docHeight = document.documentElement.scrollHeight - window.innerHeight;
            const progress = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
            const progressStr = Math.round(progress) + '%';
            
            if (progressFill) progressFill.style.width = progress + '%';
            if (sidebarProgressFill) sidebarProgressFill.style.width = progress + '%';
            if (sidebarProgressText) sidebarProgressText.textContent = progressStr;
            if (readingProgressFill) readingProgressFill.style.height = progress + '%';
            
            ticking = false;
        }}
        
        window.addEventListener('scroll', function() {{
            if (!ticking) {{
                requestAnimationFrame(updateProgress);
                ticking = true;
            }}
        }});
        
        // P2: TOC Scroll-Spy (IntersectionObserver)
        const tocLinks = document.querySelectorAll('.toc-link');
        const sections = document.querySelectorAll('section[id], header[id]');
        
        const observerOptions = {{
            rootMargin: '-20% 0px -80% 0px',
            threshold: 0
        }};
        
        const observer = new IntersectionObserver((entries) => {{
            entries.forEach(entry => {{
                if (entry.isIntersecting) {{
                    const id = entry.target.id;
                    tocLinks.forEach(link => {{
                        link.classList.remove('active');
                        if (link.getAttribute('href') === '#' + id) {{
                            link.classList.add('active');
                        }}
                    }});
                }}
            }});
        }}, observerOptions);
        
        sections.forEach(section => observer.observe(section));
        
        // P5: 章节锚点链接
        document.querySelectorAll('.section-anchor').forEach(anchor => {{
            anchor.addEventListener('click', function(e) {{
                e.stopPropagation();
                const anchorId = this.dataset.anchor;
                const url = window.location.origin + window.location.pathname + '#' + anchorId;
                navigator.clipboard.writeText(url).then(() => {{
                    const toast = document.getElementById('anchorToast');
                    toast.classList.add('show');
                    setTimeout(() => toast.classList.remove('show'), 2000);
                }});
            }});
        }});
        
        // Function 2: ⌘K 搜索
        document.addEventListener('keydown', function(e) {{
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {{
                e.preventDefault();
                openSearch();
            }}
            if (e.key === 'Escape') {{
                closeSearch();
            }}
        }});
        
        // 样式切换
        const styleSelect = document.getElementById('styleSelect');
        styleSelect.addEventListener('change', function() {{
            // 获取当前阅读模式
            const activeModeBtn = document.querySelector('.mode-btn.active');
            const currentMode = activeModeBtn ? activeModeBtn.dataset.mode : 'standard';
            
            // 只更新主题class，保留 reading-mode 和当前阅读模式
            document.body.className = 'reading-mode ' + this.value;
            document.body.dataset.mode = currentMode;
            
            // 重新渲染Mermaid（适应主题变化）
            if (this.value === 'dark_lab') {{
                mermaid.initialize({{ theme: 'dark' }});
            }} else if (this.value === 'clean_paper') {{
                mermaid.initialize({{ theme: 'default' }});
            }} else {{
                mermaid.initialize({{ theme: 'dark' }});
            }}
        }});
        
        // 移动端导航
        const mobileToggle = document.getElementById('mobileToggle');
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('overlay');
        
        mobileToggle.addEventListener('click', function() {{
            sidebar.classList.toggle('mobile-open');
            sidebar.classList.toggle('mobile-closed');
            overlay.classList.toggle('active');
        }});
        
        overlay.addEventListener('click', function() {{
            sidebar.classList.remove('mobile-open');
            sidebar.classList.add('mobile-closed');
            overlay.classList.remove('active');
        }});
    }}
    
    /* ===========================================
       ECharts 实验数据图表初始化
       =========================================== */
    function initExperimentCharts() {{
        const chartContainer = document.getElementById('experimentChart');
        if (!chartContainer) return;
        
        // 检查ECharts是否加载
        if (typeof echarts === 'undefined') {{
            chartContainer.querySelector('.experiment-chart-loading').style.display = 'none';
            chartContainer.querySelector('.experiment-chart-offline').style.display = 'block';
            return;
        }}
        
        const chartType = chartContainer.dataset.type || 'bar';
        let datasets = [];
        let metrics = [];
        
        try {{
            datasets = JSON.parse(chartContainer.dataset.datasets || '[]');
            metrics = JSON.parse(chartContainer.dataset.metrics || '[]');
        }} catch (e) {{
            console.warn('ECharts数据解析失败:', e);
            return;
        }}
        
        if (!datasets.length || !metrics.length) return;
        
        // 初始化图表
        const chart = echarts.init(chartContainer);
        
        // 获取当前主题颜色
        const styleSelect = document.getElementById('styleSelect');
        const currentStyle = styleSelect ? styleSelect.value : 'dark_lab';
        const isDark = currentStyle !== 'clean_paper';
        
        const textColor = isDark ? '#e6edf3' : '#1a1a1a';
        const bgColor = isDark ? '#21262d' : '#ffffff';
        
        // 颜色配置
        const colors = [
            '#58a6ff', '#3fb950', '#f78166', '#d29922', 
            '#a371f7', '#f778ba', '#79c0ff', '#7ee787'
        ];
        
        let option = {{}};
        
        if (chartType === 'bar') {{
            option = {{
                backgroundColor: bgColor,
                tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
                legend: {{
                    data: datasets.map(d => d.name),
                    textStyle: {{ color: textColor }}
                }},
                grid: {{ left: '3%', right: '4%', bottom: '3%', containLabel: true }},
                xAxis: {{ type: 'category', data: metrics, axisLabel: {{ color: textColor }} }},
                yAxis: {{ type: 'value', axisLabel: {{ color: textColor }} }},
                series: datasets.map((d, i) => ({{
                    name: d.name,
                    type: 'bar',
                    data: d.data,
                    itemStyle: {{ color: colors[i % colors.length] }}
                }}))
            }};
        }} else if (chartType === 'line') {{
            option = {{
                backgroundColor: bgColor,
                tooltip: {{ trigger: 'axis' }},
                legend: {{
                    data: datasets.map(d => d.name),
                    textStyle: {{ color: textColor }}
                }},
                grid: {{ left: '3%', right: '4%', bottom: '3%', containLabel: true }},
                xAxis: {{ type: 'category', data: metrics, axisLabel: {{ color: textColor }} }},
                yAxis: {{ type: 'value', axisLabel: {{ color: textColor }} }},
                series: datasets.map((d, i) => ({{
                    name: d.name,
                    type: 'line',
                    data: d.data,
                    itemStyle: {{ color: colors[i % colors.length] }},
                    lineStyle: {{ width: 2 }},
                    areaStyle: {{ opacity: 0.1 }}
                }}))
            }};
        }} else if (chartType === 'radar') {{
            // 雷达图需要归一化数据
            const maxValues = metrics.map((_, mi) => Math.max(...datasets.map(d => Math.abs(d.data[mi] || 0))));
            const normalizedDatasets = datasets.map(d => ({{
                name: d.name,
                value: d.data.map((v, i) => maxValues[i] ? v / maxValues[i] : 0)
            }}));
            
            option = {{
                backgroundColor: bgColor,
                tooltip: {{}},
                legend: {{
                    data: datasets.map(d => d.name),
                    textStyle: {{ color: textColor }}
                }},
                radar: {{
                    indicator: metrics.map((m, i) => ({{
                        name: m,
                        max: 1
                    }})),
                    axisLabel: {{ color: textColor }}
                }},
                series: [{{
                    type: 'radar',
                    data: normalizedDatasets.map((d, i) => ({{
                        name: d.name,
                        value: d.value,
                        lineStyle: {{ color: colors[i % colors.length] }},
                        areaStyle: {{ color: colors[i % colors.length], opacity: 0.2 }}
                    }}))
                }}]
            }};
        }}
        
        chart.setOption(option);
        
        // 响应式
        window.addEventListener('resize', () => {{
            chart.resize();
        }});
        
        // 隐藏加载提示
        chartContainer.querySelector('.experiment-chart-loading').style.display = 'none';
    }}
    
    /* ===========================================
       P0: Minimap 导航
       =========================================== */
    function initMinimap() {{
        const minimap = document.getElementById('minimap');
        const minimapContent = document.getElementById('minimapContent');
        const viewport = document.getElementById('minimapViewport');
        
        if (!minimap || !minimapContent) return;
        
        // 获取所有主要内容块
        const blocks = document.querySelectorAll('section[id], header[id], .card');
        const mainContent = document.querySelector('.main-content');
        
        if (!mainContent) return;
        
        // 清空现有minimap块（保留viewport）
        minimapContent.querySelectorAll('.minimap-block').forEach(b => b.remove());
        
        // 创建minimap块
        blocks.forEach(block => {{
            if (!block.id) return;
            
            const blockEl = document.createElement('div');
            blockEl.className = 'minimap-block';
            blockEl.dataset.target = block.id;
            blockEl.title = block.querySelector('.card-title, .paper-title, h2, h3')?.textContent || block.id;
            
            // 点击跳转
            blockEl.addEventListener('click', function() {{
                const target = document.getElementById(this.dataset.target);
                if (target) {{
                    target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                }}
            }});
            
            minimapContent.appendChild(blockEl);
        }});
        
        // 更新minimap
        function updateMinimap() {{
            const scrollTop = window.scrollY;
            const docHeight = document.documentElement.scrollHeight;
            const viewportHeight = window.innerHeight;
            
            // 更新视口指示器
            const viewportRatio = scrollTop / docHeight;
            const viewportHeightRatio = viewportHeight / docHeight;
            const viewportTop = viewportRatio * 100;
            const viewportH = viewportHeightRatio * 100;
            
            viewport.style.top = viewportTop + '%';
            viewport.style.height = Math.max(viewportH, 2) + '%';
            
            // 更新块位置
            const mainRect = mainContent.getBoundingClientRect();
            const mainTop = mainRect.top + scrollTop;
            const mainHeight = mainContent.scrollHeight;
            
            blocks.forEach(block => {{
                if (!block.id) return;
                const blockEl = minimapContent.querySelector(`[data-target="${{block.id}}"]`);
                if (!blockEl) return;
                
                const blockTop = block.offsetTop;
                const blockHeight = block.offsetHeight;
                
                const topPercent = (blockTop / docHeight) * 100;
                const heightPercent = (blockHeight / docHeight) * 100;
                
                blockEl.style.top = topPercent + '%';
                blockEl.style.height = Math.max(heightPercent, 1) + '%';
                
                // 高亮当前视口中的块
                const blockCenter = blockTop + blockHeight / 2;
                const viewportCenter = scrollTop + viewportHeight / 2;
                const inView = Math.abs(blockCenter - viewportCenter) < viewportHeight;
                
                blockEl.classList.toggle('active', inView);
            }});
        }}
        
        // 使用IntersectionObserver优化
        const minimapObserver = new IntersectionObserver((entries) => {{
            requestAnimationFrame(updateMinimap);
        }});
        
        blocks.forEach(block => minimapObserver.observe(block));
        window.addEventListener('scroll', () => requestAnimationFrame(updateMinimap));
        window.addEventListener('resize', () => requestAnimationFrame(updateMinimap));
        
        updateMinimap();
    }}
    
    /* ===========================================
       Function 2: ⌘K 全文搜索
       =========================================== */
    let searchMatches = [];
    let currentMatchIndex = -1;
    
    function openSearch() {{
        const modal = document.getElementById('searchModal');
        const input = document.getElementById('searchInput');
        modal.style.display = 'flex';
        input.value = '';
        input.focus();
        clearHighlights();
    }}
    
    function closeSearch() {{
        const modal = document.getElementById('searchModal');
        modal.style.display = 'none';
        clearHighlights();
    }}
    
    function clearHighlights() {{
        document.querySelectorAll('.search-highlight').forEach(el => {{
            const parent = el.parentNode;
            while (el.firstChild) parent.insertBefore(el.firstChild, el);
            parent.removeChild(el);
        }});
        searchMatches = [];
        currentMatchIndex = -1;
        document.getElementById('searchNav').style.display = 'none';
        document.getElementById('searchResultsInfo').textContent = '';
    }}
    
    function performSearch() {{
        const query = document.getElementById('searchInput').value.trim();
        if (!query) {{
            clearHighlights();
            return;
        }}
        
        clearHighlights();
        
        const content = document.getElementById('markdownContent') || document.querySelector('.main-content');
        if (!content) return;
        
        const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT, null, false);
        const textNodes = [];
        while (walker.nextNode()) textNodes.push(walker.currentNode);
        
        searchMatches = [];
        
        textNodes.forEach(node => {{
            const text = node.textContent;
            const lowerText = text.toLowerCase();
            const lowerQuery = query.toLowerCase();
            let index = 0;
            
            while ((index = lowerText.indexOf(lowerQuery, index)) !== -1) {{
                const range = document.createRange();
                range.setStart(node, index);
                range.setEnd(node, index + query.length);
                
                const mark = document.createElement('mark');
                mark.className = 'search-highlight';
                range.surroundContents(mark);
                
                searchMatches.push(mark);
                index += query.length;
            }}
        }});
        
        // 更新UI
        const count = searchMatches.length;
        document.getElementById('searchResultsInfo').textContent = 
            count > 0 ? `找到 ${{count}} 处匹配` : '未找到匹配';
        
        const nav = document.getElementById('searchNav');
        nav.style.display = count > 0 ? 'flex' : 'none';
        
        if (count > 0) {{
            currentMatchIndex = 0;
            scrollToMatch(0);
            updateMatchCount();
        }}
    }}
    
    function scrollToMatch(index) {{
        if (index < 0 || index >= searchMatches.length) return;
        
        searchMatches.forEach((m, i) => {{
            m.classList.toggle('current', i === index);
        }});
        
        searchMatches[index].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    }}
    
    function nextMatch() {{
        if (searchMatches.length === 0) return;
        currentMatchIndex = (currentMatchIndex + 1) % searchMatches.length;
        scrollToMatch(currentMatchIndex);
        updateMatchCount();
    }}
    
    function prevMatch() {{
        if (searchMatches.length === 0) return;
        currentMatchIndex = (currentMatchIndex - 1 + searchMatches.length) % searchMatches.length;
        scrollToMatch(currentMatchIndex);
        updateMatchCount();
    }}
    
    function updateMatchCount() {{
        document.getElementById('searchMatchCount').textContent = 
            `${{currentMatchIndex + 1}} / ${{searchMatches.length}}`;
    }}
    
    // 搜索输入事件
    document.getElementById('searchInput')?.addEventListener('input', performSearch);
    
    /* ===========================================
       Function 4: 图表引用跳转
       =========================================== */
    function initFigureRefs() {{
        const content = document.getElementById('markdownContent');
        if (!content) return;
        
        // 将 Figure X, Table X 转换为可点击链接
        const figurePattern = /(Figure|Table|Fig\\.|图|表)\\s*(\\d+[a-z]?)/gi;
        
        function processTextNode(textNode) {{
            const text = textNode.textContent;
            if (!figurePattern.test(text)) return;
            
            figurePattern.lastIndex = 0;
            const fragment = document.createDocumentFragment();
            let lastIndex = 0;
            let match;
            
            while ((match = figurePattern.exec(text)) !== null) {{
                // 添加匹配前的文本
                if (match.index > lastIndex) {{
                    fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
                }}
                
                // 创建链接
                const link = document.createElement('a');
                link.className = 'figure-ref';
                link.href = `#figure-${{match[2]}}`;
                link.textContent = match[0];
                
                link.addEventListener('click', function(e) {{
                    e.preventDefault();
                    const targetId = this.getAttribute('href').slice(1);
                    const target = document.getElementById(targetId);
                    if (target) {{
                        target.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        // 闪烁高亮
                        target.classList.add('highlighted');
                        setTimeout(() => target.classList.remove('highlighted'), 1500);
                    }}
                }});
                
                fragment.appendChild(link);
                lastIndex = match.index + match[0].length;
            }}
            
            // 添加剩余文本
            if (lastIndex < text.length) {{
                fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
            }}
            
            return fragment;
        }}
        
        const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT, null, false);
        const nodesToProcess = [];
        while (walker.nextNode()) nodesToProcess.push(walker.currentNode);
        
        nodesToProcess.forEach(node => {{
            if (node.parentNode.tagName !== 'MARK') {{
                const result = processTextNode(node);
                if (result) {{
                    node.parentNode.replaceChild(result, node);
                }}
            }}
        }});
    }}
    
    /* ===========================================
       P6: CUSTOM CURSOR & TRAIL EFFECT
       =========================================== */
    function initCursor() {{
        const container = document.getElementById('cursorContainer');
        const cursorDot = document.getElementById('cursorDot');
        const cursorRing = document.getElementById('cursorRing');
        
        if (!container || !cursorDot || !cursorRing) return;
        
        // 检测是否为触摸设备
        const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
        if (isTouchDevice) {{
            container.style.display = 'none';
            return;
        }}
        
        // 配置
        const config = {{
            trailMaxLength: 25,           // 最多25个尾巴粒子
            trailFadeSpeed: 0.03,         // 透明度衰减速度
            ringLerpFactor: 0.15,          // 外环跟随速度
            particleSpawnRate: 1,          // 每帧生成粒子数
            dotLerpFactor: 0.25           // 光点跟随速度
        }};
        
        // 状态
        let mouseX = 0, mouseY = 0;
        let dotX = 0, dotY = 0;
        let ringX = 0, ringY = 0;
        let trails = [];
        let isHovering = false;
        let isVisible = false;
        let animationId = null;
        
        // 获取可交互元素选择器
        const interactiveSelector = 'a, button, .toc-link, .mode-btn, .accordion-header, ' +
            '.minimap-block, .style-select, input, .search-input-wrapper, ' +
            '.card-header, .section-anchor, .finding-item';
        
        // 初始化位置（在屏幕中心外）
        dotX = window.innerWidth + 100;
        dotY = window.innerHeight + 100;
        ringX = dotX;
        ringY = dotY;
        
        // 鼠标移动处理
        function onMouseMove(e) {{
            mouseX = e.clientX;
            mouseY = e.clientY;
            
            if (!isVisible) {{
                isVisible = true;
                container.classList.remove('disabled');
            }}
            
            // 检查是否悬停在可交互元素上
            const target = e.target;
            isHovering = target.closest(interactiveSelector) !== null;
            
            cursorDot.classList.toggle('hovering', isHovering);
            cursorRing.classList.toggle('hovering', isHovering);
        }}
        
        // 鼠标离开窗口
        function onMouseLeave() {{
            isVisible = false;
            container.classList.add('disabled');
        }}
        
        function onMouseEnter() {{
            isVisible = true;
            container.classList.remove('disabled');
        }}
        
        // 点击效果
        function onMouseDown() {{
            cursorDot.style.transform = 'translate(-50%, -50%) scale(0.8)';
        }}
        
        function onMouseUp() {{
            cursorDot.style.transform = isHovering ? 
                'translate(-50%, -50%) scale(1.5)' : 
                'translate(-50%, -50%) scale(1)';
        }}
        
        // 创建尾巴粒子
        function createTrail(x, y) {{
            if (trails.length >= config.trailMaxLength) return;
            
            const particle = document.createElement('div');
            particle.className = 'cursor-trail';
            particle.style.left = x + 'px';
            particle.style.top = y + 'px';
            particle.style.opacity = getComputedStyle(document.documentElement)
                .getPropertyValue('--cursor-trail-opacity').trim() || '0.7';
            container.appendChild(particle);
            
            trails.push({{
                el: particle,
                x: x,
                y: y,
                opacity: parseFloat(particle.style.opacity),
                scale: 1
            }});
        }}
        
        // 动画循环
        function animate() {{
            // 使用lerp平滑跟随
            dotX += (mouseX - dotX) * config.dotLerpFactor;
            dotY += (mouseY - dotY) * config.dotLerpFactor;
            ringX += (mouseX - ringX) * config.ringLerpFactor;
            ringY += (mouseY - ringY) * config.ringLerpFactor;
            
            // 更新光标位置
            cursorDot.style.left = dotX + 'px';
            cursorDot.style.top = dotY + 'px';
            cursorRing.style.left = ringX + 'px';
            cursorRing.style.top = ringY + 'px';
            
            // 生成尾巴粒子（只在移动时）
            if (isVisible && (
                Math.abs(mouseX - dotX) > 2 || Math.abs(mouseY - dotY) > 2
            )) {{
                for (let i = 0; i < config.particleSpawnRate; i++) {{
                    createTrail(dotX, dotY);
                }}
            }}
            
            // 更新尾巴粒子
            for (let i = trails.length - 1; i >= 0; i--) {{
                const trail = trails[i];
                trail.opacity -= config.trailFadeSpeed;
                trail.scale -= 0.01;
                
                if (trail.opacity <= 0) {{
                    trail.el.remove();
                    trails.splice(i, 1);
                }} else {{
                    trail.el.style.opacity = trail.opacity;
                    trail.el.style.transform = `translate(-50%, -50%) scale(${{trail.scale}})`;
                }}
            }}
            
            animationId = requestAnimationFrame(animate);
        }}
        
        // 绑定事件
        document.addEventListener('mousemove', onMouseMove, {{ passive: true }});
        document.addEventListener('mouseleave', onMouseLeave);
        document.addEventListener('mouseenter', onMouseEnter);
        document.addEventListener('mousedown', onMouseDown);
        document.addEventListener('mouseup', onMouseUp);
        
        // 隐藏搜索框内的光标
        const searchModal = document.getElementById('searchModal');
        if (searchModal) {{
            searchModal.addEventListener('mouseenter', () => {{
                container.style.opacity = '0';
            }});
            searchModal.addEventListener('mouseleave', () => {{
                container.style.opacity = '';
            }});
        }}
        
        // 启动动画
        animate();
        
        // 清理函数（可选）
        window.cleanupCursor = function() {{
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseleave', onMouseLeave);
            document.removeEventListener('mouseenter', onMouseEnter);
            document.removeEventListener('mousedown', onMouseDown);
            document.removeEventListener('mouseup', onMouseUp);
            if (animationId) cancelAnimationFrame(animationId);
            trails.forEach(t => t.el.remove());
            trails = [];
        }};
    }}
    
    /* ===========================================
       TOGGLE CURSOR EFFECT (可通过控制台调用)
       =========================================== */
    window.toggleCursorEffect = function(enabled) {{
        const container = document.getElementById('cursorContainer');
        if (!container) return;
        
        if (enabled === undefined) {{
            enabled = container.classList.contains('disabled');
        }}
        
        if (enabled) {{
            container.classList.remove('disabled');
            document.documentElement.style.setProperty('--cursor-enabled', '1');
        }} else {{
            container.classList.add('disabled');
            document.documentElement.style.setProperty('--cursor-enabled', '0');
        }}
    }};
    </script>
</body>
</html>"""
    
    return html


# =============================================================================
# 辅助函数
# =============================================================================

def _key_findings_count(key_findings) -> int:
    """判断关键发现是否为空（模型是否真的生成了内容）。"""
    if key_findings is None:
        return 0
    if hasattr(key_findings, "get"):
        findings_list = key_findings.get("key_findings") or []
        innovation = key_findings.get("innovation") or ""
        significance = key_findings.get("significance") or ""
    else:
        findings_list = getattr(key_findings, "key_findings", None) or []
        innovation = getattr(key_findings, "innovation", "") or ""
        significance = getattr(key_findings, "significance", "") or ""
    try:
        count = len(findings_list)
    except TypeError:
        count = 0
    if innovation or significance:
        count = max(count, 1)
    return count


def _build_key_findings(key_findings) -> tuple:
    """构建关键发现HTML
    
    Args:
        key_findings: KeyFindingsResult对象或字典
        
    Returns:
        tuple: (findings_html_str, innovation, significance)
    """
    findings_html = []
    
    # 兼容对象和字典两种格式
    if hasattr(key_findings, 'get'):
        findings_list = key_findings.get("key_findings", [])
        innovation = key_findings.get("innovation", "")
        significance = key_findings.get("significance", "")
    else:
        findings_list = getattr(key_findings, 'key_findings', [])
        innovation = getattr(key_findings, 'innovation', "")
        significance = getattr(key_findings, 'significance', "")
    
    # 3个关键发现
    for i, finding in enumerate(findings_list[:3], 1):
        findings_html.append(f'''
            <div class="finding-item">
                <div class="finding-number">{i}</div>
                <div class="finding-content">
                    <p class="finding-text">{finding}</p>
                </div>
            </div>
        ''')
    
    # 创新点和研究意义 - 独立区块，始终可见，不参与手风琴折叠
    return "\n".join(findings_html) if findings_html else "<p>暂无关键发现</p>", innovation, significance


def _build_insight_section(innovation: str, significance: str) -> str:
    """构建核心贡献独立区块（始终可见，不参与手风琴折叠）"""
    if not innovation and not significance:
        return ""
    
    items = []
    if innovation:
        items.append(f"<div class='insight-item'><div class='insight-label'>💡 核心创新点</div><p class='insight-text'>{innovation}</p></div>")
    if significance:
        items.append(f"<div class='insight-item'><div class='insight-label'>🎯 研究意义</div><p class='insight-text'>{significance}</p></div>")
    
    return f"""
        <div class="insight-always-visible" id="insight">
            <div class="insight-section">
                {"".join(items)}
            </div>
        </div>
    """





def _build_section_summaries(section_summaries: list, embedded_images: dict) -> str:
    """构建章节摘要HTML
    
    支持 dataclass 对象或字典格式的 section_summaries
    """
    sections_html = []
    
    for section in section_summaries:
        # 兼容 dataclass 和 dict
        if hasattr(section, '__dict__'):
            # dataclass 对象
            section_title = getattr(section, 'section_title', '未知章节')
            summary = getattr(section, 'summary', '')
            key_points = getattr(section, 'key_points', []) or []
            formulas = getattr(section, 'formulas', []) or []
            tables = getattr(section, 'tables', []) or []
            figures = getattr(section, 'figures', []) or []
        else:
            # 字典
            section_title = section.get("section_title", "未知章节")
            summary = section.get("summary", "")
            key_points = section.get("key_points", [])
            formulas = section.get("formulas", [])
            tables = section.get("tables", [])
            figures = section.get("figures", [])
        
        # 构建关键点
        points_html = ""
        if key_points:
            points_list = "\n".join([f"<li>{point}</li>" for point in key_points[:5]])
            points_html = f"<ul class='section-points'>{points_list}</ul>"
        
        # 构建公式
        formulas_html = ""
        if formulas:
            formula_items = []
            for formula in formulas[:3]:
                latex = formula.get("latex", "")
                desc = formula.get("description", "")
                formula_items.append(f"<div class='section-formula'><div class='formula-label'>{desc}</div><div class='formula-katex'>${latex}$</div></div>")
            formulas_html = "\n".join(formula_items)
        
        # 构建图表
        figures_html = ""
        if figures:
            figure_items = []
            for i, figure in enumerate(figures[:3], 1):
                desc = figure.get("description", "")
                # 尝试从embedded_images中获取图片
                fig_key = list(embedded_images.keys())[0] if embedded_images else None
                if fig_key:
                    img_data = embedded_images[fig_key]
                    figure_items.append(f"<div class='section-figure' id='figure-{i}'><div class='figure-label'>Figure {i}: {desc}</div><img src='{img_data}' alt='{desc}' style='max-width:100%;border-radius:8px;'/></div>")
            figures_html = "\n".join(figure_items)
        
        section_html = f'''
            <div class="card section-card">
                <div class="section-header">
                    <h3 class="section-title">
                        {section_title}
                        <span class="section-anchor" data-anchor="section-{hash(section_title) % 10000}">#</span>
                    </h3>
                    <span class="section-toggle">▼</span>
                </div>
                <div class="section-content">
                    {"<p class='section-summary'>" + summary + "</p>" if summary else ""}
                    {points_html}
                    {formulas_html}
                    {figures_html}
                </div>
            </div>
        '''
        sections_html.append(section_html)
    
    return "\n".join(sections_html) if sections_html else ""


def _build_structured_panel(structured: dict) -> str:
    """构建结构化信息面板HTML"""
    items_html = []
    
    # 研究问题
    research_question = structured.get("research_question", "")
    if research_question:
        items_html.append(f'''
            <div class="structured-item">
                <div class="structured-item-title">研究问题</div>
                <div class="structured-item-content">
                    <p>{research_question}</p>
                </div>
            </div>
        ''')
    
    # 方法论
    methodology = structured.get("methodology", "")
    if methodology:
        items_html.append(f'''
            <div class="structured-item">
                <div class="structured-item-title">方法论</div>
                <div class="structured-item-content">
                    <p>{methodology}</p>
                </div>
            </div>
        ''')
    
    # 核心贡献
    contributions = structured.get("contributions", [])
    if contributions:
        contrib_list = "\n".join([f"<li>{c}</li>" for c in contributions[:5]])
        items_html.append(f'''
            <div class="structured-item">
                <div class="structured-item-title">核心贡献</div>
                <div class="structured-item-content">
                    <ul>{contrib_list}</ul>
                </div>
            </div>
        ''')
    
    # 实验结果
    experiment_results = structured.get("experiment_results", [])
    if experiment_results:
        results_list = []
        for result in experiment_results[:5]:
            if isinstance(result, dict):
                metric = result.get("metric", "")
                value = result.get("value", "")
                if metric and value:
                    results_list.append(f"<li>{metric}: {value}</li>")
            elif isinstance(result, str):
                results_list.append(f"<li>{result}</li>")
        if results_list:
            items_html.append(f'''
                <div class="structured-item">
                    <div class="structured-item-title">实验结果</div>
                    <div class="structured-item-content">
                        <ul>{"".join(results_list)}</ul>
                    </div>
                </div>
            ''')
    
    # 局限性
    limitations = structured.get("limitations", [])
    if limitations:
        limit_list = "\n".join([f"<li>{l}</li>" for l in limitations[:3]])
        items_html.append(f'''
            <div class="structured-item">
                <div class="structured-item-title">局限性</div>
                <div class="structured-item-content">
                    <ul>{limit_list}</ul>
                </div>
            </div>
        ''')
    
    # 未来工作
    future_work = structured.get("future_work", "")
    if future_work:
        items_html.append(f'''
            <div class="structured-item">
                <div class="structured-item-title">未来工作</div>
                <div class="structured-item-content">
                    <p>{future_work}</p>
                </div>
            </div>
        ''')
    
    return "\n".join(items_html) if items_html else ""


def _build_minimap_blocks() -> str:
    """构建Minimap块数据（用于JS初始化）"""
    return ""


def _build_experiment_chart(experiment_table: Optional[dict]) -> str:
    """
    构建实验数据图表HTML
    
    Args:
        experiment_table: 实验数据配置字典，包含:
            - title: 图表标题
            - datasets: 数据集列表，每个包含name和data
            - metrics: 指标名称列表
            - chart_type: 图表类型（bar/line/radar）
    
    Returns:
        实验数据图表HTML字符串
    """
    if not experiment_table:
        return ""
    
    # 安全地提取数据
    chart_title = experiment_table.get("title", "实验结果对比")
    datasets = experiment_table.get("datasets", [])
    metrics = experiment_table.get("metrics", [])
    chart_type = experiment_table.get("chart_type", "bar")
    
    if not datasets or not metrics:
        return ""
    
    # 将数据转换为JSON并转义（用于JS）
    import json
    datasets_json = json.dumps(datasets, ensure_ascii=False)
    metrics_json = json.dumps(metrics, ensure_ascii=False)
    
    # 唯一ID
    chart_id = "experimentChart"
    
    return f'''
            <!-- ECharts实验数据图表 -->
            <section class="experiment-chart-section" id="experiment-chart">
                <div class="experiment-chart-header">
                    <div class="card-icon">📈</div>
                    <h2 class="card-title">{chart_title}</h2>
                </div>
                <div class="experiment-chart-container" id="{chart_id}" data-type="{chart_type}" data-datasets='{datasets_json}' data-metrics='{metrics_json}'>
                    <div class="experiment-chart-loading">加载图表组件中...</div>
                    <div class="experiment-chart-offline" style="display:none;">
                        需要网络连接加载图表组件。离线状态下可查看下方数据表格。
                    </div>
                </div>
                <div class="experiment-chart-table">
                    <table>
                        <thead>
                            <tr>
                                <th>模型</th>
                                {"".join(f"<th>{m}</th>" for m in metrics)}
                            </tr>
                        </thead>
                        <tbody>
                            {"".join(
                                f'<tr>{"".join(f"<td>{d}</td>" for d in [ds.get("name", "")] + ds.get("data", []))}</tr>'
                                for ds in datasets
                            )}
                        </tbody>
                    </table>
                </div>
            </section>
    '''


def _replace_images_in_markdown(markdown: str, embedded_images: dict) -> str:
    """
    将Markdown中的图片引用替换为base64内嵌
    
    Args:
        markdown: Markdown原文
        embedded_images: 图片名->base64的映射
    
    Returns:
        处理后的Markdown
    """
    import re
    
    # 匹配 ![alt](images/xxx.jpg) 格式
    pattern = r'!\[([^\]]*)\]\(([^)]+\.(jpg|jpeg|png|gif))\)'
    
    def replace_func(match):
        alt_text = match.group(1)
        full_path = match.group(2)
        filename = full_path.split('/')[-1]
        
        # 查找对应的base64数据
        for key, data_url in embedded_images.items():
            if filename in key or key in full_path:
                return f'![{alt_text}]({data_url})'
        
        # 如果没找到，返回原文（可能离线无法显示）
        return match.group(0)
    
    return re.sub(pattern, replace_func, markdown)
