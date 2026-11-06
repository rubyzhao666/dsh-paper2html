"""
论文分片模块 - 按章节将Markdown论文切分为可处理的单元

分片策略：
1. 按 ##, ###, #### 层级切分
2. Abstract 单独成片
3. References 单独成片（不参与摘要）
4. 每片不超过4000 tokens
5. 超长章节二次切分（按段落或固定长度）

Token估算：1 token ≈ 4字符（英文），中文约2字符/token
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class SectionLevel(Enum):
    """章节层级枚举"""
    H1 = 1
    H2 = 2
    H3 = 3
    H4 = 4
    ABSTRACT = 0  # 特殊：摘要
    REFERENCES = -1  # 特殊：参考文献


@dataclass
class Chunk:
    """
    论文分片数据结构
    
    Attributes:
        section_title: 章节标题（不含#符号）
        section_level: 层级 (1=H1, 2=H2, 3=H3, 4=H4, 0=Abstract, -1=References)
        content: 内容文本（不含标题行）
        position: 在原文中的位置（0-based，用于保持顺序）
        is_abstract: 是否是摘要
        is_references: 是否是参考文献
        is_appendix: 是否是附录
        token_estimate: 预估token数
        parent_title: 父级标题（用于构建层级关系）
    """
    section_title: str
    section_level: int
    content: str
    position: int
    is_abstract: bool = False
    is_references: bool = False
    is_appendix: bool = False
    token_estimate: int = 0
    parent_title: str = ""
    
    def __post_init__(self):
        """计算token估算"""
        if self.token_estimate == 0:
            self.token_estimate = estimate_tokens(self.content)
    
    @property
    def level_name(self) -> str:
        """获取层级名称"""
        level_map = {
            0: "Abstract",
            1: "H1",
            2: "H2", 
            3: "H3",
            4: "H4",
            -1: "References"
        }
        return level_map.get(self.section_level, f"H{self.section_level}")


def estimate_tokens(text: str) -> int:
    """
    估算文本的token数量
    
    策略：
    - 英文：1 token ≈ 4字符
    - 中文：1 token ≈ 2字符（考虑到tokenizer对中文的处理）
    - 混合文本：取加权平均
    
    Args:
        text: 输入文本
    
    Returns:
        预估token数量
    """
    if not text:
        return 0
    
    # 统计中英文字符
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    total_chars = len(text)
    
    # 非字母中文字符（如标点、数字、空格）
    other_chars = total_chars - chinese_chars - english_chars
    
    # 估算：英文4字符/token，中文2字符/token，标点等粗略估算
    english_tokens = english_chars / 4.0
    chinese_tokens = chinese_chars / 2.0
    other_tokens = other_chars / 6.0  # 标点等字符token密度较低
    
    return int(english_tokens + chinese_tokens + other_tokens)


def split_into_sentences(text: str) -> List[str]:
    """
    将文本切分为句子（用于二次切分）
    
    Args:
        text: 输入文本
    
    Returns:
        句子列表
    """
    # 按常见句末标点切分
    sentence_pattern = r'(?<=[。！？.!?])\s+'
    sentences = re.split(sentence_pattern, text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_markdown(markdown: str, max_tokens: int = 4000) -> List[Chunk]:
    """
    将Markdown论文按章节切分为Chunk列表
    
    切分规则：
    1. ## Abstract 单独成片
    2. ## References 或 Acknowledgements 单独成片
    3. 其他章节按 ##, ###, #### 层级切分
    4. 超长章节按段落二次切分
    
    Args:
        markdown: 完整的Markdown文本
        max_tokens: 每个chunk的最大token数，默认4000
    
    Returns:
        Chunk列表，按position排序
    """
    if not markdown:
        return []
    
    chunks: List[Chunk] = []
    lines = markdown.split('\n')
    
    # 匹配标题行：^#... 标题内容
    heading_pattern = re.compile(r'^(#{1,4})\s+(.+)$')
    # 识别参考文献开始：## References 或 Acknowledgements（可能在同一行）
    references_pattern = re.compile(r'^(?:##\s+)?.*?\b(References|Acknowledgements)\b', re.IGNORECASE)
    
    current_section = ""
    current_level = 0
    current_content_lines: List[str] = []
    current_parent = ""
    position = 0
    first_heading_found = False
    in_references = False  # 标记是否进入References部分
    
    def save_chunk(title: str, level: int, content_lines: List[str], 
                   is_abstract: bool = False, is_ref: bool = False, 
                   is_appendix: bool = False, parent: str = ""):
        """保存当前chunk"""
        nonlocal position
        
        # 清理内容：去除空行
        content_lines = [l for l in content_lines if l.strip()]
        
        # 跳过空内容
        if not content_lines:
            return
            
        content = '\n'.join(content_lines)
        
        # 跳过纯标题（无实际内容）
        if not content.strip():
            return
        
        token_est = estimate_tokens(content)
        
        # 超长章节二次切分
        if token_est > max_tokens and level > 2:
            # 按段落切分
            sub_chunks = split_long_chunk(title, level, content, max_tokens, 
                                         is_abstract, is_ref, is_appendix, parent)
            chunks.extend(sub_chunks)
        elif token_est > max_tokens and level <= 2:
            # 大章节按段落切分
            sub_chunks = split_by_paragraphs(title, level, content, max_tokens,
                                             is_abstract, is_ref, is_appendix, parent)
            chunks.extend(sub_chunks)
        else:
            chunk = Chunk(
                section_title=title,
                section_level=level,
                content=content,
                position=position,
                is_abstract=is_abstract,
                is_references=is_ref,
                is_appendix=is_appendix,
                token_estimate=token_est,
                parent_title=parent
            )
            chunks.append(chunk)
            position += 1
    
    for i, line in enumerate(lines):
        heading_match = heading_pattern.match(line)
        
        # 检查是否进入References部分（适用于任何行，包括正文）
        if references_pattern.search(line) and not in_references:
            # 保存之前的内容
            if current_content_lines:
                save_chunk(current_section, current_level, current_content_lines,
                          is_abstract=(current_section.lower() == 'abstract'),
                          is_ref=False,
                          parent=current_parent)
            # 进入References模式
            in_references = True
            current_section = "References"
            current_level = -1
            current_content_lines = []
            # 跳过References关键词所在位置，获取剩余内容
            # 只保留第一个References关键词之后的内容
            ref_pos = references_pattern.search(line).end()
            remaining = line[ref_pos:].strip()
            if remaining:
                current_content_lines.append(remaining)
            continue
        
        if heading_match:
            # 如果是第一个标题，且之前有内容（前导文本），保存为无标题chunk
            if not first_heading_found and current_content_lines:
                save_chunk("Preamble", 1, current_content_lines)
                current_content_lines = []
            
            first_heading_found = True
            
            # 保存之前的章节
            if current_section or current_content_lines:
                save_chunk(current_section, current_level, current_content_lines,
                          is_abstract=(current_section.lower() == 'abstract'),
                          is_ref=False,
                          parent=current_parent)
            
            # 解析新标题
            hashes, title = heading_match.groups()
            level = len(hashes)
            current_level = level
            current_section = title.strip()
            current_content_lines = []
            
            # 检查是否是特殊章节（References或Acknowledgement在行中任何位置）
            if references_pattern.search(line) and not in_references:
                # 保存之前的内容
                if current_content_lines:
                    save_chunk(current_section, current_level, current_content_lines,
                              is_abstract=(current_section.lower() == 'abstract'),
                              is_ref=False,
                              parent=current_parent)
                # 进入References模式
                in_references = True
                current_section = "References"
                current_level = -1
                current_content_lines = []
                continue
            
            # 更新父级标题
            if level == 3:
                current_parent = current_section
            elif level > 3:
                # 保持上一级父标题
                pass
            elif level <= 2:
                current_parent = ""
                
        elif in_references:
            # 在References部分，累加所有内容行
            current_content_lines.append(line)
        else:
            # 非标题行，累加到当前内容
            current_content_lines.append(line)
    
    # 处理末尾内容
    if not first_heading_found and current_content_lines:
        # 整个文档没有标题，作为整体chunk
        save_chunk("Document", 1, current_content_lines)
    elif first_heading_found and current_content_lines:
        # 有标题的文档，保存最后一个章节
        save_chunk(current_section, current_level, current_content_lines,
                  is_abstract=(current_section.lower() == 'abstract'),
                  is_ref=in_references,
                  parent=current_parent)
    
    # 按position排序
    chunks.sort(key=lambda x: x.position)
    
    logger.info(f"分片完成：共 {len(chunks)} 个chunk")
    for chunk in chunks:
        logger.debug(f"  [{chunk.level_name}] {chunk.section_title}: ~{chunk.token_estimate} tokens")
    
    return chunks


def split_long_chunk(title: str, level: int, content: str, max_tokens: int,
                     is_abstract: bool, is_ref: bool, is_appendix: bool,
                     parent: str = "") -> List[Chunk]:
    """
    将超长章节切分为多个子chunk
    
    策略：按段落边界切分，尽量保持语义完整
    
    Args:
        title: 章节标题
        level: 层级
        content: 内容
        max_tokens: 最大token数
        is_abstract: 是否是摘要
        is_ref: 是否是参考文献
        is_appendix: 是否是附录
        parent: 父级标题
    
    Returns:
        子chunk列表
    """
    # 按双换行符（段落）切分
    paragraphs = content.split('\n\n')
    
    sub_chunks: List[Chunk] = []
    current_text = ""
    position = 0
    
    for para in paragraphs:
        if not para.strip():
            continue
            
        para_tokens = estimate_tokens(para)
        current_tokens = estimate_tokens(current_text)
        
        if current_tokens + para_tokens <= max_tokens:
            current_text += '\n\n' + para if current_text else para
        else:
            # 保存当前chunk
            if current_text:
                chunk = Chunk(
                    section_title=title,
                    section_level=level,
                    content=current_text.strip(),
                    position=position,
                    is_abstract=is_abstract,
                    is_references=is_ref,
                    is_appendix=is_appendix,
                    token_estimate=estimate_tokens(current_text),
                    parent_title=parent
                )
                sub_chunks.append(chunk)
                position += 1
            
            # 检查单个段落是否超长
            if para_tokens > max_tokens:
                # 按句子切分
                sentences = split_into_sentences(para)
                for sent in sentences:
                    sent_tokens = estimate_tokens(sent)
                    current_text = ""
                    if estimate_tokens(sent) > max_tokens:
                        # 超长句子，继续按字符切分
                        chunk = Chunk(
                            section_title=title,
                            section_level=level,
                            content=sent[:max_tokens*4],  # 粗略截断
                            position=position,
                            is_abstract=is_abstract,
                            is_references=is_ref,
                            is_appendix=is_appendix,
                            parent_title=parent
                        )
                        sub_chunks.append(chunk)
                        position += 1
                    else:
                        current_text = sent
            else:
                current_text = para
    
    # 保存最后一个
    if current_text.strip():
        chunk = Chunk(
            section_title=title,
            section_level=level,
            content=current_text.strip(),
            position=position,
            is_abstract=is_abstract,
            is_references=is_ref,
            is_appendix=is_appendix,
            token_estimate=estimate_tokens(current_text),
            parent_title=parent
        )
        sub_chunks.append(chunk)
    
    return sub_chunks


def split_by_paragraphs(title: str, level: int, content: str, max_tokens: int,
                        is_abstract: bool, is_ref: bool, is_appendix: bool,
                        parent: str = "") -> List[Chunk]:
    """
    将大章节（如实验章节）按段落切分为多个chunk
    
    适用于 Introduction, Experiment, Results 等可能很长的章节
    
    Args:
        title: 章节标题
        level: 层级
        content: 内容
        max_tokens: 最大token数
        is_abstract: 是否是摘要
        is_ref: 是否是参考文献
        is_appendix: 是否是附录
        parent: 父级标题
    
    Returns:
        chunk列表
    """
    # 按段落和子标题切分
    paragraphs: List[Tuple[str, str]] = []  # (title, content)
    current_title = title
    current_content = ""
    
    lines = content.split('\n')
    
    subheading_pattern = re.compile(r'^#{1,4}\s+(.+)$')
    
    for line in lines:
        match = subheading_pattern.match(line)
        if match:
            # 保存当前段落
            if current_content.strip():
                paragraphs.append((current_title, current_content.strip()))
            current_title = f"{title} - {match.group(1)}"
            current_content = ""
        else:
            current_content += '\n' + line if current_content else line
    
    # 保存最后一段
    if current_content.strip():
        paragraphs.append((current_title, current_content.strip()))
    
    # 创建chunk
    chunks: List[Chunk] = []
    position = 0
    
    for p_title, p_content in paragraphs:
        token_est = estimate_tokens(p_content)
        
        if token_est > max_tokens:
            # 递归切分
            sub = split_long_chunk(p_title, level + 1, p_content, max_tokens,
                                  is_abstract, is_ref, is_appendix, title)
            for s in sub:
                s.position = position
                chunks.append(s)
                position += 1
        else:
            chunk = Chunk(
                section_title=p_title,
                section_level=level,
                content=p_content,
                position=position,
                is_abstract=is_abstract,
                is_references=is_ref,
                is_appendix=is_appendix,
                token_estimate=token_est,
                parent_title=parent
            )
            chunks.append(chunk)
            position += 1
    
    return chunks


def get_chunk_tree(chunks: List[Chunk]) -> dict:
    """
    将chunk列表转换为层级树结构
    
    用于构建论文的目录树视图
    
    Args:
        chunks: chunk列表
    
    Returns:
        树结构字典
    """
    root = {"title": "Root", "children": [], "level": 0}
    
    stack = [root]
    
    for chunk in chunks:
        node = {
            "title": chunk.section_title,
            "level": chunk.section_level,
            "tokens": chunk.token_estimate,
            "is_abstract": chunk.is_abstract,
            "is_references": chunk.is_references,
            "children": []
        }
        
        # 找到正确的父节点
        while stack and stack[-1]["level"] >= chunk.section_level:
            stack.pop()
        
        if stack:
            stack[-1]["children"].append(node)
        
        stack.append(node)
    
    return root


def extract_abstract(markdown: str) -> str:
    """
    快速提取摘要部分
    
    Args:
        markdown: 完整markdown
    
    Returns:
        摘要文本
    """
    # 匹配 ## Abstract 或 # Abstract（不同解析器输出标题级别不同）
    abstract_pattern = re.compile(r'#{1,2}\s*[Aa]bstract\s*\n+(.+?)(?=\n#{1,3}\s|\Z)', re.DOTALL)
    match = abstract_pattern.search(markdown)
    if match:
        return match.group(1).strip()
    return ""


def count_sections(markdown: str) -> dict:
    """
    统计论文章节信息
    
    Args:
        markdown: 完整markdown
    
    Returns:
        统计信息字典
    """
    h1 = len(re.findall(r'^#\s+', markdown, re.MULTILINE))
    h2 = len(re.findall(r'^##\s+', markdown, re.MULTILINE))
    h3 = len(re.findall(r'^###\s+', markdown, re.MULTILINE))
    h4 = len(re.findall(r'^####\s+', markdown, re.MULTILINE))
    
    return {
        "h1": h1,
        "h2": h2,
        "h3": h3,
        "h4": h4,
        "total_lines": len(markdown.split('\n')),
        "total_chars": len(markdown),
        "total_tokens": estimate_tokens(markdown)
    }
