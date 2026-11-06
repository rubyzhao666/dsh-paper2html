"""
paper2html 数据模型
定义解析层和理解层使用的数据结构
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ParseResult:
    """解析结果数据结构"""
    markdown: str = ""           # 完整Markdown文本（公式用$...$）
    json_data: dict = field(default_factory=dict)  # 结构化JSON
    images: List[str] = field(default_factory=list)  # 提取的图片路径列表
    metadata: dict = field(default_factory=dict)   # 元数据
    raw_output_dir: str = ""     # 原始输出目录
    source_file: str = ""        # 源PDF文件路径
    success: bool = False        # 解析是否成功
    error_message: str = ""      # 错误信息（如有）


@dataclass
class UnderstandingResult:
    """AI理解结果数据结构"""
    tldr: str = ""               # 一句话总结
    key_findings: Optional[Dict[str, Any]] = None  # 核心发现
    section_summaries: List[Dict[str, str]] = field(default_factory=list)  # 章节摘要
    structured: Optional[Dict[str, Any]] = None   # 结构化数据
    mermaid_code: str = ""       # Mermaid图表代码
    success: bool = False
    error_message: str = ""


@dataclass
class LLMResponse:
    """LLM调用响应"""
    content: str = ""
    success: bool = False
    error_message: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
