"""
LLM调用模块 - 封装与LLM API的交互

支持：
- OpenAI格式API（DeepSeek/GPT/Claude等）
- 环境变量配置
- 并发调用
- JSON响应解析
- 错误重试

API配置优先级：
1. 构造函数参数
2. 环境变量（LLM_API_KEY, LLM_BASE_URL, LLM_MODEL）
3. 默认值
"""

import os
import json
import logging
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM配置"""
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    timeout: int = 60  # 单次调用超时（秒）
    max_retries: int = 2
    temperature: float = 0.3
    
    def __post_init__(self):
        # 从环境变量加载
        if not self.api_key:
            self.api_key = os.environ.get("LLM_API_KEY", "")
        if not self.base_url:
            self.base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
        if not self.model:
            self.model = os.environ.get("LLM_MODEL", "deepseek-chat")


@dataclass
class LLMResponse:
    """LLM响应"""
    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    success: bool = True
    error: str = ""


class _UrllibNamespace:
    """极简对象容器（用来模仿 openai SDK 的 response 属性访问）。"""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _UrllibCompletions:
    """openai SDK `client.chat.completions` 的最小替代：一个 POST /chat/completions。"""

    def __init__(self, client):
        self._client = client

    def create(self, model=None, messages=None, temperature=0.3, timeout=None, **kwargs):
        import json as _json
        import urllib.error as _urllib_error
        import urllib.request as _urllib_request

        payload = {"model": model, "messages": messages or [], "temperature": temperature}
        payload.update({key: value for key, value in kwargs.items() if value is not None})
        request = _urllib_request.Request(
            self._client.base_url + "/chat/completions",
            data=_json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self._client.api_key,
            },
            method="POST",
        )
        try:
            with _urllib_request.urlopen(request, timeout=timeout or self._client.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except _urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError("LLM API HTTP {}: {}".format(exc.code, detail))
        except _urllib_error.URLError as exc:
            raise RuntimeError("LLM API 请求失败: {}".format(getattr(exc, "reason", exc)))
        data = _json.loads(body)
        choices = data.get("choices") or []
        content = ""
        if choices:
            content = ((choices[0] or {}).get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        return _UrllibNamespace(
            model=data.get("model") or model,
            choices=[_UrllibNamespace(message=_UrllibNamespace(content=content))],
            usage=_UrllibNamespace(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
        )


class _UrllibOpenAIClient:
    """openai SDK 不可用时的替代客户端（只实现 chat.completions.create）。"""

    def __init__(self, api_key="", base_url="https://api.deepseek.com/v1", timeout=60):
        self.api_key = api_key or ""
        self.base_url = (base_url or "https://api.deepseek.com/v1").rstrip("/")
        self.timeout = timeout
        self.chat = _UrllibNamespace(completions=_UrllibCompletions(self))


class LLMClient:
    """
    LLM API客户端
    
    支持OpenAI格式的API调用，包括DeepSeek、GPT、Claude等。
    """
    
    def __init__(self, api_key: Optional[str] = None, 
                 base_url: Optional[str] = None,
                 model: Optional[str] = None,
                 timeout: int = 60,
                 max_retries: int = 2):
        """
        初始化LLM客户端
        
        Args:
            api_key: API密钥，默认从LLM_API_KEY环境变量读取
            base_url: API基础URL，默认https://api.deepseek.com/v1
            model: 模型名称，默认deepseek-chat
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
        """
        self.config = LLMConfig(
            api_key=api_key or "",
            base_url=base_url or "",
            model=model or "",
            timeout=timeout,
            max_retries=max_retries
        )
        
        self._client = None
        self._lock = threading.Lock()
        
        # 检查配置
        if not self.config.api_key:
            logger.warning("LLM_API_KEY未设置，将使用模拟模式（mock mode）")
    
    def _get_client(self):
        """懒加载 OpenAI 客户端；没有安装 openai SDK 时退回内置 urllib 实现。"""
        if self._client is None:
            with self._lock:
                if self._client is None:
                    try:
                        from openai import OpenAI
                        self._client = OpenAI(
                            api_key=self.config.api_key,
                            base_url=self.config.base_url,
                            timeout=self.config.timeout
                        )
                        logger.info(f"LLM客户端初始化成功: {self.config.base_url}/{self.config.model}")
                    except ImportError:
                        # 上游依赖 openai SDK，但 AI 理解层不应该为了一个 HTTP 调用逼用户装包：
                        # 用标准库 urllib 调 OpenAI 兼容接口（DeepSeek 等）。
                        logger.info("openai SDK 未安装，使用内置 urllib 客户端调用 OpenAI 兼容 API")
                        self._client = _UrllibOpenAIClient(
                            api_key=self.config.api_key,
                            base_url=self.config.base_url,
                            timeout=self.config.timeout,
                        )
        return self._client
    
    def call(self, system_prompt: str, user_prompt: str, 
             temperature: float = 0.3) -> LLMResponse:
        """
        调用LLM API
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 温度参数（0-1）
        
        Returns:
            LLMResponse对象
        """
        if not self.config.api_key:
            return self._mock_response(user_prompt)
        
        client = self._get_client()
        retries = 0
        
        while retries <= self.config.max_retries:
            try:
                response = client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=temperature,
                    timeout=self.config.timeout
                )
                
                content = response.choices[0].message.content
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                }
                
                return LLMResponse(
                    content=content,
                    model=response.model,
                    usage=usage,
                    success=True
                )
                
            except Exception as e:
                retries += 1
                error_msg = str(e)
                
                if retries <= self.config.max_retries:
                    logger.warning(f"LLM调用失败（重试{retries}/{self.config.max_retries}）: {error_msg}")
                    time.sleep(1 * retries)  # 指数退避
                else:
                    logger.error(f"LLM调用最终失败: {error_msg}")
                    return LLMResponse(
                        content="",
                        model=self.config.model,
                        success=False,
                        error=error_msg
                    )
    
    def call_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        调用LLM并解析JSON响应
        
        如果JSON解析失败，会重试一次并给出更严格的格式要求
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
        
        Returns:
            解析后的dict
        
        Raises:
            ValueError: JSON解析失败
        """
        from .prompts import extract_json_from_response
        
        # 首次尝试
        response = self.call(system_prompt, user_prompt)
        
        if not response.success:
            raise ValueError(f"LLM调用失败: {response.error}")
        
        try:
            return extract_json_from_response(response.content)
        except ValueError as e:
            # 重试一次，给更严格的格式要求
            retry_prompt = user_prompt + "\n\n注意：请确保输出是有效的JSON格式，只输出JSON，不要其他内容。"
            response = self.call(system_prompt, retry_prompt)
            
            if not response.success:
                raise ValueError(f"LLM调用失败: {response.error}")
            
            try:
                return extract_json_from_response(response.content)
            except ValueError as e2:
                raise ValueError(f"JSON解析失败（已重试）: {e2}\n原始响应: {response.content[:500]}")
    
    def _mock_response(self, prompt: str) -> LLMResponse:
        """模拟响应（用于无API Key时）"""
        logger.debug("使用模拟响应模式")
        return LLMResponse(
            content="Mock response - 请设置LLM_API_KEY环境变量以启用真实调用",
            model="mock",
            success=True
        )
    
    def batch_call(self, tasks: List[Dict[str, str]], 
                   max_workers: int = 4) -> List[LLMResponse]:
        """
        批量并发调用LLM
        
        Args:
            tasks: 任务列表，每个任务包含system_prompt和user_prompt
            max_workers: 最大并发数
        
        Returns:
            响应列表（顺序与输入一致）
        """
        if not tasks:
            return []
        
        results = [None] * len(tasks)
        
        def call_task(index: int, task: Dict[str, str]) -> tuple:
            response = self.call(
                task["system_prompt"],
                task["user_prompt"],
                task.get("temperature", 0.3)
            )
            return index, response
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(call_task, i, task): i 
                for i, task in enumerate(tasks)
            }
            
            for future in as_completed(futures):
                try:
                    index, response = future.result()
                    results[index] = response
                except Exception as e:
                    index = futures[future]
                    logger.error(f"批量任务 {index} 执行失败: {e}")
                    results[index] = LLMResponse(
                        content="",
                        model=self.config.model,
                        success=False,
                        error=str(e)
                    )
        
        return results


@dataclass
class SectionSummary:
    """章节摘要数据结构"""
    section_title: str
    summary: str
    key_points: List[str] = field(default_factory=list)
    formulas: List[Dict[str, str]] = field(default_factory=list)
    tables: List[Dict[str, str]] = field(default_factory=list)
    figures: List[Dict[str, str]] = field(default_factory=list)
    token_estimate: int = 0


@dataclass
class KeyFindingsResult:
    """三分钟摘要结果"""
    key_findings: List[str]
    innovation: str
    significance: str


@dataclass
class StructuredExtraction:
    """结构化抽取结果"""
    title: str
    authors: List[str]
    abstract_summary: str
    research_question: str
    methodology: str
    contributions: List[str]
    experiment_results: List[Dict[str, Any]]
    limitations: List[str]
    future_work: str
    mermaid_architecture: str
    experiment_table: Optional[Dict] = None  # ECharts配置数据，包含datasets和metrics


@dataclass 
class UnderstandingResult:
    """论文理解完整结果"""
    tldr: str
    key_findings: KeyFindingsResult
    section_summaries: List[SectionSummary]
    structured: StructuredExtraction
    mermaid_code: str
    success: bool
    error_message: str = ""


class PaperUnderstanding:
    """
    论文理解主类
    
    执行完整的论文理解流程：
    1. 分片
    2. 并行生成各章节摘要
    3. 生成TL;DR
    4. 生成3分钟摘要
    5. 结构化抽取
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        初始化论文理解器
        
        Args:
            llm_client: LLM客户端，默认创建新实例
        """
        self.llm = llm_client or LLMClient()
        self._chunker = None
        self._prompts = None
    
    @property
    def chunker(self):
        """懒加载chunker"""
        if self._chunker is None:
            from .chunker import chunk_markdown, extract_abstract, Chunk
            self._chunker = {"chunk": chunk_markdown, "abstract": extract_abstract, "Chunk": Chunk}
        return self._chunker
    
    @property
    def prompts(self):
        """懒加载prompts"""
        if self._prompts is None:
            from . import prompts
            self._prompts = prompts
        return self._prompts
    
    def understand(self, parse_result) -> UnderstandingResult:
        """
        执行完整的理解流程
        
        Args:
            parse_result: ParseResult对象（来自Doc2XParser.parse）
        
        Returns:
            UnderstandingResult对象
        """
        from .chunker import (
            chunk_markdown, extract_abstract, Chunk,
            get_chunk_tree, estimate_tokens
        )
        from .prompts import (
            SYSTEM_PROMPT_TLDR, SYSTEM_PROMPT_THREE_MINUTES,
            SYSTEM_PROMPT_SECTION_SUMMARY, SYSTEM_PROMPT_STRUCTURED,
            get_tldr_prompt, get_three_minutes_prompt,
            get_section_summary_prompt, get_structured_extraction_prompt,
            build_section_summaries_text
        )
        
        markdown = parse_result.markdown
        if not markdown:
            return UnderstandingResult(
                tldr="",
                key_findings=KeyFindingsResult([], "", ""),
                section_summaries=[],
                structured=StructuredExtraction("", [], "", "", "", [], [], [], "", None),
                mermaid_code="",
                success=False,
                error_message="Markdown内容为空"
            )
        
        try:
            # Step 1: 分片
            logger.info("Step 1: 分片...")
            chunks = chunk_markdown(markdown)
            abstract = extract_abstract(markdown)
            
            # 过滤掉References
            content_chunks = [c for c in chunks if not c.is_references]
            logger.info(f"  分片完成：{len(content_chunks)} 个内容chunk（不含References）")
            
            # Step 2: 并行生成章节摘要
            logger.info("Step 2: 生成章节摘要...")
            section_summaries = self._generate_section_summaries(content_chunks)
            logger.info(f"  章节摘要完成：{len(section_summaries)} 个摘要")
            
            # Step 3: 生成TL;DR
            logger.info("Step 3: 生成TL;DR...")
            tldr = self._generate_tldr(abstract, chunks)
            logger.info(f"  TL;DR: {tldr[:50]}...")
            
            # Step 4: 生成3分钟摘要
            logger.info("Step 4: 生成三分钟摘要...")
            key_findings = self._generate_three_minutes(tldr, section_summaries)
            logger.info(f"  关键发现: {len(key_findings.key_findings)} 个")
            
            # Step 5: 结构化抽取
            logger.info("Step 5: 结构化抽取...")
            structured = self._generate_structured(
                parse_result.metadata.get("title", ""),
                parse_result.metadata.get("authors", ""),
                abstract,
                tldr,
                section_summaries
            )
            logger.info(f"  结构化完成: title={structured.title[:30]}...")
            
            return UnderstandingResult(
                tldr=tldr,
                key_findings=key_findings,
                section_summaries=section_summaries,
                structured=structured,
                mermaid_code=structured.mermaid_architecture,
                success=True
            )
            
        except Exception as e:
            logger.error(f"理解流程失败: {e}")
            return UnderstandingResult(
                tldr="",
                key_findings=KeyFindingsResult([], "", ""),
                section_summaries=[],
                structured=StructuredExtraction("", [], "", "", "", "", [], [], "", ""),
                mermaid_code="",
                success=False,
                error_message=str(e)
            )
    
    def _generate_section_summaries(self, chunks: List) -> List[SectionSummary]:
        """生成所有章节摘要（并行）"""
        from .prompts import SYSTEM_PROMPT_SECTION_SUMMARY, get_section_summary_prompt
        
        # 准备任务
        tasks = []
        for chunk in chunks:
            if chunk.is_references:
                continue
            task = {
                "system_prompt": SYSTEM_PROMPT_SECTION_SUMMARY,
                "user_prompt": get_section_summary_prompt(
                    chunk.section_title,
                    chunk.content[:8000],  # 限制长度
                    chunk.section_level,
                    chunk.parent_title
                ),
                "chunk": chunk
            }
            tasks.append(task)
        
        # 并行调用
        if len(tasks) <= 3:
            # 小任务串行执行
            results = []
            for task in tasks:
                resp = self.llm.call_json(task["system_prompt"], task["user_prompt"])
                results.append((task["chunk"], resp))
        else:
            # 大任务并行执行
            batch_tasks = [
                {"system_prompt": t["system_prompt"], "user_prompt": t["user_prompt"]}
                for t in tasks
            ]
            responses = self.llm.batch_call(batch_tasks, max_workers=4)
            results = list(zip([t["chunk"] for t in tasks], responses))
        
        # 解析结果
        summaries = []
        for chunk, response in results:
            if isinstance(response, dict):
                summary = SectionSummary(
                    section_title=response.get("section_title", chunk.section_title),
                    summary=response.get("summary", ""),
                    key_points=response.get("key_points", []),
                    formulas=response.get("formulas", []),
                    tables=response.get("tables", []),
                    figures=response.get("figures", []),
                    token_estimate=chunk.token_estimate
                )
                summaries.append(summary)
            elif hasattr(response, 'content'):
                # LLMResponse对象，尝试解析
                try:
                    from .prompts import extract_json_from_response
                    data = extract_json_from_response(response.content)
                    summary = SectionSummary(
                        section_title=data.get("section_title", chunk.section_title),
                        summary=data.get("summary", ""),
                        key_points=data.get("key_points", []),
                        formulas=data.get("formulas", []),
                        tables=data.get("tables", []),
                        figures=data.get("figures", []),
                        token_estimate=chunk.token_estimate
                    )
                    summaries.append(summary)
                except:
                    logger.warning(f"无法解析章节摘要: {chunk.section_title}")
        
        return summaries
    
    def _generate_tldr(self, abstract: str, chunks: List) -> str:
        """生成TL;DR"""
        from .prompts import SYSTEM_PROMPT_TLDR, get_tldr_prompt
        from .chunker import Chunk
        
        # 获取结论部分
        conclusion = ""
        for chunk in chunks:
            if chunk.section_title.lower() in ["conclusion", "conclusions", "结论"]:
                conclusion = chunk.content[:2000]
                break
        
        # 检测模板占位符的正则
        import re as _re
        placeholder_pattern = _re.compile(r'\[.+?\]')
        
        for attempt in range(3):
            response = self.llm.call(
                SYSTEM_PROMPT_TLDR,
                get_tldr_prompt(abstract, conclusion)
            )
            
            if response.success:
                result = response.content.strip()
                # 检测是否是模板占位符响应（如"基于[核心方法/模型]"）
                if placeholder_pattern.search(result) and len(result) < 200:
                    logger.warning(f"TL;DR返回模板占位符(第{attempt+1}次)，重试...")
                    continue
                return result
            else:
                if attempt < 2:
                    logger.warning(f"TL;DR生成失败(第{attempt+1}次)，重试...")
                    continue
                return f"TL;DR生成失败: {response.error}"
        
        return response.content.strip() if response.success else f"TL;DR生成失败: {response.error}"
    
    def _generate_three_minutes(self, tldr: str, section_summaries: List[SectionSummary]) -> KeyFindingsResult:
        """生成三分钟摘要"""
        from .prompts import SYSTEM_PROMPT_THREE_MINUTES, get_three_minutes_prompt
        
        summaries_text = "\n".join([
            f"- {s.section_title}: {s.summary[:200]}"
            for s in section_summaries if s.summary
        ])
        
        try:
            result = self.llm.call_json(
                SYSTEM_PROMPT_THREE_MINUTES,
                get_three_minutes_prompt(tldr, summaries_text)
            )
            
            return KeyFindingsResult(
                key_findings=result.get("key_findings", []),
                innovation=result.get("innovation", ""),
                significance=result.get("significance", "")
            )
        except Exception as e:
            logger.warning(f"三分钟摘要生成失败: {e}")
            return KeyFindingsResult([], "", "")
    
    def _generate_structured(self, title: str, authors: str, 
                              abstract: str, tldr: str,
                              section_summaries: List[SectionSummary]) -> StructuredExtraction:
        """生成结构化信息"""
        from .prompts import SYSTEM_PROMPT_STRUCTURED, get_structured_extraction_prompt, build_section_summaries_text
        
        summaries_text = build_section_summaries_text(section_summaries)
        
        try:
            result = self.llm.call_json(
                SYSTEM_PROMPT_STRUCTURED,
                get_structured_extraction_prompt(title, authors, abstract, tldr, summaries_text)
            )
            
            return StructuredExtraction(
                title=result.get("title", title),
                authors=result.get("authors", []),
                abstract_summary=result.get("abstract_summary", ""),
                research_question=result.get("research_question", ""),
                methodology=result.get("methodology", ""),
                contributions=result.get("contributions", []),
                experiment_results=result.get("experiment_results", []),
                limitations=result.get("limitations", []),
                future_work=result.get("future_work", ""),
                mermaid_architecture=result.get("mermaid_architecture", ""),
                experiment_table=result.get("experiment_table", None)
            )
        except Exception as e:
            logger.warning(f"结构化抽取生成失败: {e}")
            return StructuredExtraction(
                title=title,
                authors=authors.split(",") if authors else [],
                abstract_summary=abstract[:500] if abstract else "",
                research_question="",
                methodology="",
                contributions=[],
                experiment_results=[],
                limitations=[],
                future_work="",
                mermaid_architecture="",
                experiment_table=None
            )
