"""
Prompt模板模块 - 定义论文理解的各类Prompt

包含4个核心Prompt：
1. TL;DR Prompt - 一句话核心贡献
2. 三分钟摘要 Prompt - 3点关键发现
3. 章节摘要 Prompt - 每个章节的精炼摘要
4. 结构化抽取 Prompt - 完整结构化信息

设计原则：
- 中文输出（便于中文读者）
- 专业但不过于学术，像一个懂行的朋友在讲解
- 公式保留LaTeX源码
- mermaid图用flowchart或sequenceDiagram
"""

# ============== 系统提示词 ==============

SYSTEM_PROMPT_TLDR = """你是一个专业的学术论文助手，帮助读者快速理解论文的核心贡献。

你的输出要求：
1. 一句话概括论文的核心贡献
2. 面向30秒快速浏览场景
3. 语言简洁有力，突出创新点
4. 格式：纯文本字符串，不需要JSON
5. 语言：中文"""

SYSTEM_PROMPT_THREE_MINUTES = """你是一个专业的学术论文助手，帮助读者在3分钟内把握论文的关键发现。

你的输出要求：
1. 提取3个关键发现
2. 说明核心创新点
3. 阐述研究意义
4. 格式：JSON
5. 语言：中文"""

SYSTEM_PROMPT_SECTION_SUMMARY = """你是一个专业的学术论文助手，为论文的每个章节生成精炼摘要。

你的输出要求：
1. 生成章节摘要
2. 提取关键要点（3-5个）
3. 识别重要公式（保留LaTeX源码）
4. 识别表格和图表
5. 格式：JSON
6. 语言：中文"""

SYSTEM_PROMPT_STRUCTURED = """你是一个专业的学术论文助手，从论文摘要和章节摘要中提取完整的结构化信息。

你的输出要求：
1. 提取论文元信息（标题、作者等）
2. 识别研究问题
3. 概括方法论
4. 列出主要贡献
5. 提取实验结果
6. 识别局限性和未来工作
7. 生成Mermaid架构图代码（描述论文方法的核心流程）
8. 格式：JSON
9. 语言：中文"""

# ============== TL;DR Prompt ==============

def get_tldr_prompt(abstract: str, conclusion: str = "") -> str:
    """
    生成TL;DR Prompt
    
    Args:
        abstract: 论文摘要
        conclusion: 结论部分（可选）
    
    Returns:
        完整的用户提示词
    """
    # 兼容 Python 3.9：f-string 表达式里不能出现反斜杠，先算好再插值
    conclusion_block = f"## 结论\n{conclusion}" if conclusion else ""
    content = f"""请阅读以下论文摘要，并生成一句话核心贡献（TL;DR）：

## 摘要
{abstract}

{conclusion_block}

要求：
- 一句话概括论文做了什么、有什么突破
- 突出创新点和实际价值
- 30秒内读完就能理解论文核心
- 直接输出字符串，不需要引号或JSON"""

    return content


# ============== 三分钟摘要 Prompt ==============

def get_three_minutes_prompt(tldr: str, full_text: str) -> str:
    """
    生成三分钟摘要Prompt
    
    Args:
        tldr: 已生成的TL;DR
        full_text: 论文完整文本（可选）
    
    Returns:
        完整的用户提示词
    """
    content = f"""基于以下TL;DR和论文内容，生成三分钟摘要：

## TL;DR
{tldr}

## 论文内容
{full_text[:15000] if len(full_text) > 15000 else full_text}...

请输出JSON格式：
```json
{{
  "key_findings": ["发现1（具体、可量化）", "发现2（具体、可量化）", "发现3（具体、可量化）"],
  "innovation": "核心创新点：用一句话说清楚创新在哪里",
  "significance": "研究意义：为什么这个工作重要，影响了哪些领域"
}}
```

要求：
- 发现要具体，避免空话套话
- 创新点要突出与现有工作的区别
- 意义要从读者角度说明价值"""

    return content


# ============== 章节摘要 Prompt ==============

def get_section_summary_prompt(section_title: str, content: str, 
                               level: int = 2, parent_title: str = "") -> str:
    """
    生成章节摘要Prompt
    
    Args:
        section_title: 章节标题
        content: 章节内容
        level: 层级 (2=H2, 3=H3, 4=H4)
        parent_title: 父级标题
    
    Returns:
        完整的用户提示词
    """
    full_title = f"{parent_title} - {section_title}" if parent_title else section_title
    
    content = f"""请为以下章节生成精炼摘要：

## 章节信息
- 标题：{full_title}
- 层级：H{level}

## 内容
{content}

请输出JSON格式：
```json
{{
  "section_title": "{section_title}",
  "summary": "100-200字的章节摘要，说明这一章在讲什么",
  "key_points": [
    "要点1：具体的技术细节或结论",
    "要点2：与其他部分的关系",
    "要点3：如果有实验，说明实验设置和结果"
  ],
  "formulas": [
    {{"latex": "公式LaTeX源码", "description": "公式含义说明"}}
  ],
  "tables": [
    {{"description": "表格内容描述", "key_data": "关键数据，如最好的指标"}}
  ],
  "figures": [
    {{"description": "图表描述，如'展示了X与Y的关系'"}}
  ]
}}
```

要求：
- summary要精炼，突出重点
- key_points要具体，避免泛泛而谈
- 公式保留完整LaTeX源码（如Attention(Q,K,V) = softmax(QK^T/sqrt(d_k))V）
- 表格只描述主要数据，不需要全部列举"""

    return content


# ============== 结构化抽取 Prompt ==============

def get_structured_extraction_prompt(
    title: str,
    authors: str,
    abstract: str,
    tldr: str,
    section_summaries: str
) -> str:
    """
    生成结构化抽取Prompt
    
    Args:
        title: 论文标题
        authors: 作者列表（可选）
        abstract: 摘要
        tldr: 一句话核心贡献
        section_summaries: 所有章节摘要的合并文本
    
    Returns:
        完整的用户提示词
    """
    content = f"""基于以下论文信息，提取完整的结构化数据：

## 论文信息
- 标题：{title}
- 作者：{authors if authors else '未知'}
- 摘要：{abstract[:500]}...

## TL;DR
{tldr}

## 章节摘要
{section_summaries[:8000]}

请输出JSON格式：
```json
{{
  "title": "论文完整标题",
  "authors": ["作者1", "作者2", "作者3"],
  "abstract_summary": "扩展后的摘要总结，200字以内",
  "research_question": "研究问题：作者想要解决什么问题",
  "methodology": "方法论概述：用简洁的话说明用了什么方法",
  "contributions": [
    "贡献1：具体的技术贡献",
    "贡献2：实验或理论贡献",
    "贡献3：实践或应用贡献"
  ],
  "experiment_results": [
    {{
      "name": "实验名称（如WMT英德翻译）",
      "result": "具体结果（如41.8 BLEU）",
      "metric": "评估指标（如BLEU）",
      "comparison": "与什么对比（如state-of-the-art）"
    }}
  ],
  "limitations": [
    "局限性1",
    "局限性2"
  ],
  "future_work": "未来工作方向",
  "mermaid_architecture": "Mermaid流程图代码，描述模型或方法的核心架构",
  "experiment_table": {{
    "title": "实验结果对比",
    "datasets": [
      {{
        "name": "模型A名称",
        "data": [28.4, 41.8, 0.65]
      }},
      {{
        "name": "模型B名称",
        "data": [26.3, 39.2, 0.71]
      }}
    ],
    "metrics": ["BLEU (EN-DE)", "BLEU (EN-FR)", "Training Cost (GPU-days)"],
    "chart_type": "bar"
  }}
}}

## experiment_table 说明
experiment_table 用于ECharts图表渲染，格式要求：
- title: 图表标题
- datasets: 数据集数组，每个数据集包含name(模型名)和data(数值数组)
- metrics: 指标名称数组，与data中的每个数值对应
- chart_type: 图表类型，可选"bar"(柱状图)、"line"(折线图)、"radar"(雷达图)
- 注意：只需提取表格中的关键对比数据，不需要全部数据
```

## Mermaid架构图要求
mermaid_architecture字段必须是一个完整的Mermaid流程图代码，描述论文方法的核心流程。

示例格式：
```
flowchart TD
    A[Input Text] --> B[Embedding Layer]
    B --> C[Encoder Stack]
    C --> D[Multi-Head Self-Attention]
    D --> E[Feed-Forward Network]
    E --> F[Decoder Stack]
    F --> G[Output Probabilities]
```

要求：
1. 使用flowchart TD或LR方向
2. 节点用[]包裹，简短描述
3. 用-->表示数据流向
4. 突出核心组件和它们之间的关系
5. 不要过于复杂，5-10个节点为宜
6. 确保语法正确，可以在Mermaid Live Editor直接渲染"""

    return content


# ============== Mermaid架构图生成Prompt ==============

def get_mermaid_prompt(methodology: str, section_summaries: str) -> str:
    """
    专门生成Mermaid架构图的Prompt
    
    Args:
        methodology: 方法论描述
        section_summaries: 章节摘要
    
    Returns:
        Mermaid代码
    """
    content = f"""基于以下方法论描述，生成Mermaid架构图代码：

## 方法论
{methodology}

## 相关章节摘要
{section_summaries}

请生成一个描述该方法核心流程的Mermaid流程图。

要求：
1. 语法正确，可直接在Mermaid Live Editor渲染
2. 5-10个核心节点
3. 用-->表示数据流向
4. 节点描述简洁（如"[Embedding]"）
5. 用subgraph表示模块组（如subgraph Encoder）

输出格式：纯Mermaid代码，不需要JSON包装"""

    return content


# ============== 辅助函数 ==============

def extract_json_from_response(response: str) -> dict:
    """
    从LLM响应中提取JSON
    
    策略：
    1. 查找```json代码块
    2. 如果没有，查找第一个{到最后一个}之间的内容
    3. 清理可能的markdown干扰
    
    Args:
        response: LLM响应文本
    
    Returns:
        解析后的dict
    """
    import json
    import re
    
    # 尝试从代码块提取
    json_block_pattern = r'```json\s*([\s\S]*?)\s*```'
    match = re.search(json_block_pattern, response)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # 尝试直接解析
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # 尝试提取{}之间的内容
    brace_pattern = r'\{[\s\S]*\}'
    match = re.search(brace_pattern, response)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"无法从响应中解析JSON: {response[:200]}...")


def build_section_summaries_text(summaries: list) -> str:
    """
    将章节摘要列表构建为文本
    
    Args:
        summaries: 章节摘要列表
    
    Returns:
        合并后的文本
    """
    lines = []
    for s in summaries:
        # 兼容dict和dataclass两种格式
        if isinstance(s, dict):
            title = s.get('section_title', 'Unknown')
            summary = s.get('summary', '')
            key_points = s.get('key_points', [])
        else:
            title = getattr(s, 'section_title', 'Unknown')
            summary = getattr(s, 'summary', '')
            key_points = getattr(s, 'key_points', [])
        lines.append(f"\n### {title}\n")
        lines.append(f"摘要：{summary}\n")
        if key_points:
            lines.append("要点：")
            for point in key_points:
                lines.append(f"- {point}")
        lines.append("")
    
    return '\n'.join(lines)
