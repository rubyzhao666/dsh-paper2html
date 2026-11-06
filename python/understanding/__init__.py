"""
Paper2HTML Understanding Layer - 论文理解层

提供论文的深度理解能力：
- 智能分片：按章节将论文切分为可处理的单元
- 多粒度摘要：TL;DR / 3分钟 / 章节摘要
- 结构化抽取：标题、作者、方法、结果等
- Mermaid架构图：自动生成方法流程图

使用示例：
```python
from paper2html.understanding import PaperUnderstanding, LLMClient

# 方式1：使用默认配置
understander = PaperUnderstanding()

# 方式2：自定义LLM配置
llm = LLMClient(
    api_key="sk-xxx",
    base_url="https://api.deepseek.com/v1",
    model="deepseek-chat"
)
understander = PaperUnderstanding(llm_client=llm)

# 执行理解
result = understander.understand(parse_result)

# 访问结果
print(result.tldr)  # 一句话核心贡献
print(result.mermaid_code)  # Mermaid架构图
```

主要类和函数：
- LLMClient: LLM API客户端
- PaperUnderstanding: 论文理解主类
- chunk_markdown: Markdown分片函数
- UnderstandingResult: 理解结果数据结构
"""

from .chunker import (
    Chunk,
    chunk_markdown,
    extract_abstract,
    count_sections,
    get_chunk_tree,
    estimate_tokens,
    SectionLevel
)

from .llm_client import (
    LLMClient,
    LLMConfig,
    LLMResponse,
    PaperUnderstanding,
    SectionSummary,
    KeyFindingsResult,
    StructuredExtraction,
    UnderstandingResult
)

__all__ = [
    # Chunker
    "Chunk",
    "chunk_markdown", 
    "extract_abstract",
    "count_sections",
    "get_chunk_tree",
    "estimate_tokens",
    "SectionLevel",
    
    # LLM Client
    "LLMClient",
    "LLMConfig",
    "LLMResponse",
    
    # Paper Understanding
    "PaperUnderstanding",
    
    # Data Classes
    "SectionSummary",
    "KeyFindingsResult",
    "StructuredExtraction",
    "UnderstandingResult",
]

__version__ = "0.1.0"
