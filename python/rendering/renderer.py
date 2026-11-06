"""
渲染器主模块 - PaperRenderer论文HTML渲染器

功能：
- 将ParseResult和UnderstandingResult渲染为可读的HTML文件
- 支持3种样式预设切换
- 支持3种阅读模式
- 图片base64内嵌
- KaTeX公式渲染
- Mermaid架构图渲染
"""

import base64
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

import markdown

from .styles import STYLE_PRESETS, generate_all_themes_css, RESPONSIVE_BREAKPOINTS
from .templates import generate_html_template


class PaperRenderer:
    """
    论文HTML渲染器
    
    将解析层(ParseResult)和理解层(UnderstandingResult)的产出
    渲染为单文件self-contained HTML阅读器。
    
    使用示例:
        >>> from paper2html.rendering import PaperRenderer
        >>> renderer = PaperRenderer(style="dark_lab")
        >>> output_path = renderer.render(parse_result, understanding_result, "output.html")
    """
    
    # 默认样式预设
    DEFAULT_STYLE = "dark_lab"
    
    # 支持的图片格式
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    
    def __init__(self, style: str = "dark_lab"):
        """
        初始化渲染器，选择样式预设
        
        Args:
            style: 样式预设名称，可选值：
                   - "dark_lab": 深色背景，绿色强调（默认）
                   - "clean_paper": 白色背景，学术蓝强调
                   - "neon_tech": 深紫背景，霓虹强调
                   
        Raises:
            ValueError: 当style不在支持列表中时
        """
        if style not in STYLE_PRESETS:
            raise ValueError(
                f"Unknown style: {style}. "
                f"Available styles: {list(STYLE_PRESETS.keys())}"
            )
        self.style = style
    
    def render(
        self,
        parse_result: Any,
        understanding_result: Any,
        output_path: str
    ) -> str:
        """
        渲染为HTML文件
        
        Args:
            parse_result: 解析层产出（ParseResult对象或等效字典）
                          包含：
                          - markdown: 完整Markdown文本
                          - images: 图片路径列表
                          - metadata: 元数据字典
                          - source_file: 源文件路径
            understanding_result: 理解层产出（UnderstandingResult对象或等效字典）
                                  包含：
                                  - tldr: 一句话核心贡献
                                  - key_findings: 关键发现字典
                                  - section_summaries: 章节摘要列表
                                  - structured: 结构化信息字典
                                  - mermaid_code: Mermaid图代码
            output_path: 输出HTML文件路径
            
        Returns:
            生成的HTML文件路径
            
        Raises:
            IOError: 当写入文件失败时
        """
        import html as _html

        # 提取数据
        markdown = self._extract_markdown(parse_result)
        image_paths = self._extract_images(parse_result)
        metadata = self._extract_metadata(parse_result)
        
        tldr = _html.escape(str(self._extract_tldr(understanding_result) or ""))
        key_findings = self._extract_key_findings(understanding_result)
        section_summaries = self._extract_section_summaries(understanding_result)
        structured = self._extract_structured(understanding_result)
        mermaid_code = self._extract_mermaid(understanding_result)
        experiment_table = self._extract_experiment_table(understanding_result)
        
        # 获取标题和作者（论文标题里可能出现 & < > 等字符，先做 HTML 转义，避免破坏页面结构）
        import logging
        logger = logging.getLogger(__name__)
        logger.debug("[RENDER] metadata = %s", metadata)
        title = _html.escape(str(metadata.get("title", "Untitled Paper") or "Untitled Paper"))
        logger.debug("[RENDER] extracted title = %r", title)
        raw_authors = metadata.get("authors", []) or []
        if isinstance(raw_authors, str):
            raw_authors = [raw_authors]
        authors = [_html.escape(str(author)) for author in raw_authors if str(author).strip()]
        
        # 内嵌图片为base64
        embedded_images = self._embed_images_as_base64(image_paths)
        
        # 处理Markdown中的图片引用
        processed_markdown = self._replace_images_in_markdown(markdown, embedded_images)

        # 将Markdown转换为HTML
        html_content = self._markdown_to_html(processed_markdown)

        # 生成样式CSS（包含所有三套主题，用body.className作用域区分）
        style_css = generate_all_themes_css(self.style)
        
        # 生成完整HTML
        logger.info(f"[RENDER DEBUG] Calling generate_html_template with title='{title}'")
        html = generate_html_template(
            title=title,
            authors=authors,
            tldr=tldr,
            key_findings=key_findings,
            section_summaries=section_summaries,
            structured=structured,
            mermaid_code=mermaid_code,
            markdown_content=html_content,
            embedded_images=embedded_images,
            style_css=style_css,
            responsive_css=RESPONSIVE_BREAKPOINTS,
            current_style=self.style,  # 传入当前主题
            experiment_table=experiment_table
        )
        
        # 写入文件
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return str(output_path)
    
    def _extract_markdown(self, parse_result: Any) -> str:
        """提取Markdown内容"""
        if isinstance(parse_result, dict):
            return parse_result.get("markdown", "")
        return getattr(parse_result, "markdown", "")
    
    def _extract_images(self, parse_result: Any) -> List[str]:
        """提取图片路径列表"""
        if isinstance(parse_result, dict):
            return parse_result.get("images", [])
        return getattr(parse_result, "images", [])
    
    def _extract_metadata(self, parse_result: Any) -> dict:
        """提取元数据"""
        if isinstance(parse_result, dict):
            return parse_result.get("metadata", {})
        return getattr(parse_result, "metadata", {})
    
    def _extract_tldr(self, understanding_result: Any) -> str:
        """提取TL;DR摘要"""
        if isinstance(understanding_result, dict):
            return understanding_result.get("tldr", "暂无摘要")
        return getattr(understanding_result, "tldr", "暂无摘要")
    
    def _extract_key_findings(self, understanding_result: Any) -> dict:
        """提取关键发现"""
        if isinstance(understanding_result, dict):
            key_findings = understanding_result.get("key_findings", {})
            if isinstance(key_findings, dict):
                return key_findings
            return {}
        return getattr(understanding_result, "key_findings", {})
    
    def _extract_section_summaries(self, understanding_result: Any) -> list:
        """提取章节摘要"""
        if isinstance(understanding_result, dict):
            return understanding_result.get("section_summaries", [])
        return getattr(understanding_result, "section_summaries", [])
    
    def _extract_structured(self, understanding_result: Any) -> dict:
        """提取结构化信息"""
        if isinstance(understanding_result, dict):
            structured = understanding_result.get("structured", {})
            if isinstance(structured, dict):
                return structured
            return {}
        if hasattr(understanding_result, "structured"):
            return getattr(understanding_result.structured, "__dict__", {})
        return {}
    
    def _extract_mermaid(self, understanding_result: Any) -> str:
        """提取Mermaid代码"""
        if isinstance(understanding_result, dict):
            return understanding_result.get("mermaid_code", "")
        return getattr(understanding_result, "mermaid_code", "")
    
    def _extract_experiment_table(self, understanding_result: Any) -> Optional[Dict]:
        """提取实验数据表格（ECharts配置）"""
        if isinstance(understanding_result, dict):
            structured = understanding_result.get("structured", {})
            if isinstance(structured, dict):
                return structured.get("experiment_table", None)
            return None
        if hasattr(understanding_result, "structured"):
            structured = understanding_result.structured
            # structured 可能是 dict 或 dataclass
            if isinstance(structured, dict):
                return structured.get("experiment_table", None)
            elif hasattr(structured, "experiment_table"):
                return getattr(structured, "experiment_table", None)
        return None
    
    def _embed_images_as_base64(self, image_paths: List[str]) -> Dict[str, str]:
        """
        将图片路径列表转换为base64内嵌的字典
        
        Args:
            image_paths: 图片文件路径列表
            
        Returns:
            文件名 -> data:image/xxx;base64,xxxx 的映射字典
        """
        embedded = {}
        
        for path in image_paths:
            path_obj = Path(path)
            
            # 检查文件是否存在
            if not path_obj.exists():
                continue
            
            # 检查是否为支持的图片格式
            if path_obj.suffix.lower() not in self.IMAGE_EXTENSIONS:
                continue
            
            try:
                # 读取图片并转为base64
                with open(path_obj, 'rb') as f:
                    image_data = f.read()
                
                # 编码为base64
                b64_data = base64.b64encode(image_data).decode('utf-8')
                
                # 确定MIME类型
                mime_type = self._get_mime_type(path_obj.suffix)
                
                # 创建data URL
                data_url = f"data:{mime_type};base64,{b64_data}"
                
                # 使用绝对路径和文件名作为key
                embedded[str(path_obj)] = data_url
                embedded[path_obj.name] = data_url
                
            except Exception as e:
                print(f"Warning: Failed to embed image {path}: {e}")
                continue
        
        return embedded
    
    def _get_mime_type(self, extension: str) -> str:
        """根据文件扩展名获取MIME类型"""
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        return mime_types.get(extension.lower(), 'image/jpeg')
    
    def _replace_images_in_markdown(self, markdown: str, embedded_images: Dict[str, str]) -> str:
        """
        将Markdown中的图片引用替换为base64内嵌
        
        Args:
            markdown: Markdown原文
            embedded_images: 图片名->base64的映射
            
        Returns:
            处理后的Markdown
        """
        # 匹配 ![alt](images/xxx.jpg) 格式
        pattern = r'!\[([^\]]*)\]\(([^)]+\.(jpg|jpeg|png|gif|webp))\)'
        
        def replace_func(match):
            alt_text = match.group(1)
            full_path = match.group(2)
            filename = Path(full_path).name
            
            # 查找对应的base64数据
            # 尝试多种匹配方式
            for key, data_url in embedded_images.items():
                if filename == key or filename in key or key in full_path:
                    return f'![{alt_text}]({data_url})'
            
            # 如果没找到，返回原文（可能离线无法显示）
            return match.group(0)
        
        return re.sub(pattern, replace_func, markdown)

    def _markdown_to_html(self, markdown_text: str) -> str:
        """
        将Markdown文本转换为HTML

        使用 Python-Markdown 库，启用表格、代码块、语法高亮等扩展。
        转换后的 HTML 保留公式 $...$ 标记供 KaTeX 渲染。

        Args:
            markdown_text: 处理过图片引用的 Markdown 文本

        Returns:
            HTML 字符串
        """
        if not markdown_text.strip():
            return ""

        try:
            html = markdown.markdown(
                markdown_text,
                extensions=[
                    "tables",           # GitHub 风格表格
                    "fenced_code",      # ``` 代码块
                    "nl2br",            # 换行转 <br>
                    "sane_lists",       # 健壮列表解析
                ],
            )
            return html
        except Exception as e:
            logger = __import__("logging").getLogger(__name__)
            logger.warning(f"Markdown→HTML 转换失败，回退到原始文本: {e}")
            # 回退：将换行转为 <br>，至少保证基本可读性
            return markdown_text.replace("\n", "<br>\n")

    @staticmethod
    def from_parsed_content(
        markdown: str,
        images: List[str],
        output_path: str,
        style: str = "dark_lab",
        **metadata
    ) -> str:
        """
        从已解析的内容直接渲染（无需理解层）
        
        Args:
            markdown: Markdown原文
            images: 图片路径列表
            output_path: 输出路径
            style: 样式预设
            **metadata: 其他元数据（title, authors等）
            
        Returns:
            生成的HTML文件路径
        """
        # 创建最小化的理解结果
        understanding_result = {
            "tldr": metadata.get("tldr", "学术论文"),
            "key_findings": {
                "key_findings": metadata.get("key_findings", []),
                "innovation": metadata.get("innovation", ""),
                "significance": metadata.get("significance", "")
            },
            "section_summaries": metadata.get("section_summaries", []),
            "structured": {
                "research_question": metadata.get("research_question", ""),
                "methodology": metadata.get("methodology", ""),
                "contributions": metadata.get("contributions", []),
                "experiment_results": metadata.get("experiment_results", []),
                "limitations": metadata.get("limitations", []),
                "future_work": metadata.get("future_work", "")
            },
            "mermaid_code": metadata.get("mermaid_code", "")
        }
        
        # 创建解析结果
        parse_result = {
            "markdown": markdown,
            "images": images,
            "metadata": {
                "title": metadata.get("title", "Untitled Paper"),
                "authors": metadata.get("authors", [])
            }
        }
        
        renderer = PaperRenderer(style=style)
        return renderer.render(parse_result, understanding_result, output_path)


# =============================================================================
# 便捷函数
# =============================================================================

def render_paper(
    parse_result: Any,
    understanding_result: Any,
    output_path: str,
    style: str = "dark_lab"
) -> str:
    """
    渲染论文为HTML的便捷函数
    
    Args:
        parse_result: 解析层产出
        understanding_result: 理解层产出
        output_path: 输出HTML文件路径
        style: 样式预设
        
    Returns:
        生成的HTML文件路径
    """
    renderer = PaperRenderer(style=style)
    return renderer.render(parse_result, understanding_result, output_path)
