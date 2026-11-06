"""
样式预设模块 - 定义3套视觉主题的CSS变量

提供的主题：
1. Dark Lab：深色背景，绿色强调，适合夜间阅读
2. Clean Paper：白色背景，学术蓝强调，适合打印
3. Neon Tech：深紫背景，霓虹强调，科技感
"""

# =============================================================================
# 样式预设常量
# =============================================================================

# =============================================================================
# 语义色系统（暗色主题优化版）
# 所有背景色opacity控制在8-12%
# =============================================================================

SEMANTIC_COLORS = {
    "abstract": {
        "name": "摘要/结论",
        "bg": "rgba(6, 95, 70, 0.09)",      # #065f46 @ 9%
        "border": "rgba(6, 95, 70, 0.3)",    # #065f46 @ 30%
        "applicable": ["tldr", "conclusion"]
    },
    "method": {
        "name": "核心方法",
        "bg": "rgba(76, 29, 149, 0.09)",     # #4c1d95 @ 9%
        "border": "rgba(76, 29, 149, 0.3)",   # #4c1d95 @ 30%
        "applicable": ["core-ideas", "methodology"]
    },
    "experiment": {
        "name": "实验数据",
        "bg": "rgba(21, 94, 40, 0.09)",      # #155e28 @ 9%
        "border": "rgba(21, 94, 40, 0.3)",    # #155e28 @ 30%
        "applicable": ["experiments", "data"]
    },
    "risk": {
        "name": "局限性/风险",
        "bg": "rgba(127, 29, 29, 0.09)",     # #7f1d1d @ 9%
        "border": "rgba(127, 29, 29, 0.3)",   # #7f1d1d @ 30%
        "applicable": ["limitations", "risks"]
    }
}

# 为每个主题预设添加语义色变量
def _add_semantic_vars_to_preset(preset_vars: dict) -> dict:
    """为预设添加语义色变量"""
    # 深色主题适配
    for key, colors in SEMANTIC_COLORS.items():
        preset_vars[f"--semantic-{key}-bg"] = colors["bg"]
        preset_vars[f"--semantic-{key}-border"] = colors["border"]
    return preset_vars


def get_style_preset(style_name: str) -> dict:
    """
    获取指定名称的样式预设
    
    Args:
        style_name: 预设名称（dark_lab, clean_paper, neon_tech）
    
    Returns:
        预设字典，包含name、description和CSS变量
    """
    if style_name not in STYLE_PRESETS:
        raise ValueError(f"Unknown style preset: {style_name}. Available: {list(STYLE_PRESETS.keys())}")
    return STYLE_PRESETS[style_name]


def generate_all_themes_css(current_style: str) -> str:
    """
    生成所有三套主题的CSS变量，用 body.className 作用域区分
    
    Args:
        current_style: 当前选中的主题名称
    
    Returns:
        包含所有三套主题CSS变量的字符串
    """
    lines = []
    
    for style_name in ["dark_lab", "clean_paper", "neon_tech"]:
        preset = get_style_preset(style_name)
        variables = preset["variables"].copy()
        
        # 添加语义色变量
        variables = _add_semantic_vars_to_preset(variables)
        
        lines.append(f"body.{style_name} {{")
        for key, value in variables.items():
            lines.append(f"    {key}: {value};")
        lines.append("}")
        lines.append("")
    
    return "\n".join(lines)


def generate_css_variables(style_name: str) -> str:
    """
    生成CSS变量声明字符串（含语义色）- 兼容旧接口
    
    Args:
        style_name: 预设名称
    
    Returns:
        CSS :root {...} 字符串
    """
    preset = get_style_preset(style_name)
    variables = preset["variables"]
    
    # 添加语义色变量
    variables = _add_semantic_vars_to_preset(variables)
    
    lines = [":root {"]
    for key, value in variables.items():
        lines.append(f"    {key}: {value};")
    lines.append("}")
    
    return "\n".join(lines)


def get_all_style_names() -> list:
    """获取所有可用样式预设名称"""
    return list(STYLE_PRESETS.keys())


# =============================================================================
# 样式预设常量
# =============================================================================

STYLE_PRESETS = {
    "dark_lab": {
        "name": "Dark Lab",
        "description": "深色背景，绿色强调，适合夜间阅读",
        "variables": {
            # 背景色
            "--bg-primary": "#0d1117",
            "--bg-secondary": "#161b22",
            "--bg-tertiary": "#21262d",
            "--bg-card": "#1c2128",
            
            # 文字色
            "--text-primary": "#e6edf3",
            "--text-secondary": "#8b949e",
            "--text-muted": "#6e7681",
            
            # 强调色
            "--accent": "#58a6ff",
            "--accent-secondary": "#3fb950",
            "--accent-tertiary": "#f78166",
            
            # 功能色
            "--success": "#3fb950",
            "--warning": "#d29922",
            "--error": "#f85149",
            "--info": "#58a6ff",
            
            # 边框
            "--border-primary": "#30363d",
            "--border-secondary": "#21262d",
            
            # 阴影
            "--shadow-sm": "0 1px 2px rgba(0,0,0,0.3)",
            "--shadow-md": "0 4px 12px rgba(0,0,0,0.4)",
            "--shadow-lg": "0 8px 24px rgba(0,0,0,0.5)",
            
            # 进度条
            "--progress-bg": "#21262d",
            "--progress-fill": "#58a6ff",
            
            # 滚动条
            "--scrollbar-track": "#161b22",
            "--scrollbar-thumb": "#30363d",
            "--scrollbar-thumb-hover": "#484f58",
            
            # 卡片背景
            "--card-bg": "rgba(31, 41, 55, 0.8)",
            "--card-border": "rgba(48, 54, 61, 0.8)",
            
            # 光标效果（鼠标尾巴）
            "--cursor-enabled": "1",  # 1=启用, 0=禁用
            "--cursor-color": "#58a6ff",
            "--cursor-size": "9px",
            "--cursor-glow": "rgba(88, 166, 255, 0.6)",
            "--cursor-trail-color": "#58a6ff",
            "--cursor-trail-size": "4px",
            "--cursor-trail-opacity": "0.7",
        }
    },
    
    "clean_paper": {
        "name": "Clean Paper",
        "description": "白色背景，深灰文字，学术蓝强调，适合打印",
        "variables": {
            # 背景色
            "--bg-primary": "#ffffff",
            "--bg-secondary": "#f8f9fa",
            "--bg-tertiary": "#f1f3f5",
            "--bg-card": "#ffffff",
            
            # 文字色
            "--text-primary": "#1a1a1a",
            "--text-secondary": "#495057",
            "--text-muted": "#868e96",
            
            # 强调色
            "--accent": "#1a73e8",
            "--accent-secondary": "#0d6efd",
            "--accent-tertiary": "#dc3545",
            
            # 功能色
            "--success": "#198754",
            "--warning": "#ffc107",
            "--error": "#dc3545",
            "--info": "#0dcaf0",
            
            # 边框
            "--border-primary": "#dee2e6",
            "--border-secondary": "#e9ecef",
            
            # 阴影
            "--shadow-sm": "0 1px 2px rgba(0,0,0,0.05)",
            "--shadow-md": "0 4px 12px rgba(0,0,0,0.08)",
            "--shadow-lg": "0 8px 24px rgba(0,0,0,0.12)",
            
            # 进度条
            "--progress-bg": "#e9ecef",
            "--progress-fill": "#1a73e8",
            
            # 滚动条
            "--scrollbar-track": "#f1f3f5",
            "--scrollbar-thumb": "#ced4da",
            "--scrollbar-thumb-hover": "#adb5bd",
            
            # 卡片背景
            "--card-bg": "rgba(255, 255, 255, 0.95)",
            "--card-border": "rgba(222, 226, 230, 0.8)",
            
            # 光标效果（鼠标尾巴）
            "--cursor-enabled": "1",
            "--cursor-color": "#1a73e8",
            "--cursor-size": "9px",
            "--cursor-glow": "rgba(26, 115, 232, 0.5)",
            "--cursor-trail-color": "#1a73e8",
            "--cursor-trail-size": "4px",
            "--cursor-trail-opacity": "0.6",
        }
    },
    
    "neon_tech": {
        "name": "Neon Tech",
        "description": "深紫背景，霓虹绿/粉强调，科技感十足",
        "variables": {
            # 背景色
            "--bg-primary": "#1a1a2e",
            "--bg-secondary": "#16213e",
            "--bg-tertiary": "#0f0f23",
            "--bg-card": "#1f1f3a",
            
            # 文字色
            "--text-primary": "#eaeaea",
            "--text-secondary": "#b8b8d1",
            "--text-muted": "#6c6c8a",
            
            # 强调色 - 霓虹色
            "--accent": "#00ff88",       # 霓虹绿
            "--accent-secondary": "#ff00ff",  # 霓虹粉
            "--accent-tertiary": "#00d4ff",   # 霓虹蓝
            
            # 功能色
            "--success": "#00ff88",
            "--warning": "#ffcc00",
            "--error": "#ff4757",
            "--info": "#00d4ff",
            
            # 边框
            "--border-primary": "#2a2a4a",
            "--border-secondary": "#1f1f3a",
            
            # 阴影 - 霓虹发光效果
            "--shadow-sm": "0 0 5px rgba(0, 255, 136, 0.2)",
            "--shadow-md": "0 0 15px rgba(0, 255, 136, 0.3), 0 4px 12px rgba(0,0,0,0.4)",
            "--shadow-lg": "0 0 25px rgba(0, 255, 136, 0.4), 0 8px 24px rgba(0,0,0,0.5)",
            
            # 进度条
            "--progress-bg": "#2a2a4a",
            "--progress-fill": "#00ff88",
            
            # 滚动条
            "--scrollbar-track": "#16213e",
            "--scrollbar-thumb": "#2a2a4a",
            "--scrollbar-thumb-hover": "#3a3a6a",
            
            # 卡片背景
            "--card-bg": "rgba(31, 31, 58, 0.9)",
            "--card-border": "rgba(0, 255, 136, 0.2)",
            
            # 光标效果（鼠标尾巴）- 霓虹风格
            "--cursor-enabled": "1",
            "--cursor-color": "#00ff88",
            "--cursor-size": "10px",
            "--cursor-glow": "rgba(0, 255, 136, 0.8)",
            "--cursor-trail-color": "#00ff88",
            "--cursor-trail-size": "4px",
            "--cursor-trail-opacity": "0.8",
        }
    }
}


# =============================================================================
# 响应式断点
# =============================================================================

RESPONSIVE_BREAKPOINTS = """
/* 移动端适配：768px以下隐藏Minimap、切换为单栏 */
@media (max-width: 768px) {
    :root {
        --sidebar-width: 0px;
        --minimap-width: 0px;
        --content-padding: 1rem;
        --title-size: clamp(1.25rem, 5vw, 2rem);
        --h2-size: clamp(1.1rem, 4vw, 1.5rem);
        --h3-size: clamp(1rem, 3vw, 1.25rem);
        --body-size: clamp(0.85rem, 2.5vw, 1rem);
    }
    
    /* 隐藏Minimap */
    .minimap {
        display: none !important;
    }
    
    /* 隐藏右侧进度条 */
    .reading-progress-bar {
        right: 0 !important;
    }
    
    .sidebar {
        display: none;
    }
    
    .sidebar.mobile-open {
        display: flex;
        position: fixed;
        top: 0;
        left: 0;
        width: 280px;
        height: 100vh;
        z-index: 1000;
        transform: translateX(0);
    }
    
    .sidebar.mobile-closed {
        transform: translateX(-100%);
    }
    
    .main-content {
        width: 100%;
        margin-right: 0;
    }
    
    .mobile-nav-toggle {
        display: flex !important;
    }
    
    .overlay {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        z-index: 999;
    }
    
    .overlay.active {
        display: block;
    }
}

/* 超小屏幕 */
@media (max-width: 480px) {
    :root {
        --content-padding: 0.75rem;
        --card-padding: 1rem;
    }
    
    .card {
        border-radius: 8px;
    }
    
    .tldr-card, .findings-card {
        padding: 1rem;
    }
}
"""


# =============================================================================
# 辅助函数已移至上方，靠近SEMANTIC_COLORS定义
# 此处保留空的占位区域保持文件结构兼容
# =============================================================================

# 辅助函数定义在 styles.py 开头部分（与SEMANTIC_COLORS一起）
# - get_style_preset(style_name)
# - generate_css_variables(style_name) 
# - get_all_style_names()
