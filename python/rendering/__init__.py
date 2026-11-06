"""
Paper2HTML 渲染层 (Rendering Layer)

将解析层和理解层的产出渲染为可读的HTML论文阅读器。

功能特性：
- 两栏布局：左侧导航 + 右侧内容
- 阅读模式：速读 / 标准 / 精读
- 样式预设：Dark Lab / Clean Paper / Neon Tech
- KaTeX公式渲染
- Mermaid架构图渲染
- 图片base64内嵌（离线可用）
- 响应式设计（移动端适配）

使用示例：
    >>> from paper2html.rendering import PaperRenderer
    >>> 
    >>> # 初始化渲染器
    >>> renderer = PaperRenderer(style="dark_lab")
    >>> 
    >>> # 渲染HTML
    >>> output_path = renderer.render(parse_result, understanding_result, "output.html")
    >>> print(f"HTML已生成: {output_path}")

或使用便捷函数：
    >>> from paper2html.rendering import render_paper
    >>> output_path = render_paper(parse_result, understanding_result, "output.html")
"""

from .renderer import PaperRenderer, render_paper
from .styles import STYLE_PRESETS, get_style_preset, generate_css_variables, get_all_style_names
from .templates import generate_html_template

__all__ = [
    # 主渲染器
    "PaperRenderer",
    "render_paper",
    
    # 样式相关
    "STYLE_PRESETS",
    "get_style_preset",
    "generate_css_variables",
    "get_all_style_names",
    
    # 模板相关
    "generate_html_template",
]
