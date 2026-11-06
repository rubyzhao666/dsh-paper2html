#!/usr/bin/env python3
"""
paper2html - 学术论文 → 可视化 HTML 阅读器（DSH 插件内置版）

与上游 rubyzhao666/paper2html（MIT）相比，这一版的关键改动：

1. 默认无 key 可跑：新增本地解析引擎（PyMuPDF），默认跳过 AI 理解层；
2. 云端引擎保留：有 DOC2X_APIKEY / PDF2X_APIKEY 时仍可走 Doc2X / PDF2X 解析，
   有 DEEPSEEK_APIKEY 时可走 AI 理解层；
3. 解析器惰性导入：本地模式不 import requests / pdfdeal / openai 等重依赖；
4. key 从环境变量或 $DSH_HOME/paper2html/config.json 读取，不写死；
5. 输出一行机器可读结果（PAPER2HTML_RESULT_JSON: {...}），方便 DSH 插件解析。

用法:
    python paper2html.py --input paper.pdf --output output.html --no-understand
    python paper2html.py --input https://arxiv.org/abs/1706.03762 --style clean_paper
    python paper2html.py --input paper.pdf --engine local --no-understand
    python paper2html.py --input paper.pdf --engine auto   # 有 key 用云端，无 key 本地

环境变量:
    DOC2X_APIKEY       Doc2X 解析 key（可选）
    PDF2X_APIKEY       PDF2X 解析 key（可选，Doc2X fallback）
    DEEPSEEK_APIKEY    DeepSeek 理解 key（可选，也可用 DEEPSEEK_API_KEY）
    DEEPSEEK_BASE_URL  默认 https://api.deepseek.com/v1
    LLM_MODEL          默认 deepseek-chat
    DSH_HOME           数据目录（默认 ~/.dsh）

作者: paper2html Team（上游） + DSH 插件改造
版本: 1.1.0-dsh
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("paper2html")

RESULT_PREFIX = "PAPER2HTML_RESULT_JSON:"
ERROR_PREFIX = "PAPER2HTML_ERROR_JSON:"

AVAILABLE_STYLES = ["dark_lab", "clean_paper", "neon_tech"]
AVAILABLE_ENGINES = ["auto", "local", "doc2x", "pdf2x"]

# 从 $DSH_HOME/paper2html/config.json 读取配置时可接受的字段别名
_CONFIG_ALIASES = {
    "doc2xKey": ("doc2xKey", "doc2xApiKey", "doc2x", "DOC2X_APIKEY"),
    "pdf2xKey": ("pdf2xKey", "pdf2xApiKey", "pdf2x", "PDF2X_APIKEY"),
    "deepseekKey": ("deepseekKey", "deepseekApiKey", "llmKey", "DEEPSEEK_APIKEY"),
    "deepseekBaseUrl": ("deepseekBaseUrl", "llmBaseUrl", "baseUrl"),
    "llmModel": ("llmModel", "model"),
}


# ============================================================================
# 配置
# ============================================================================

def dsh_home() -> Path:
    return Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))


def data_dir() -> Path:
    return dsh_home() / "paper2html"


def config_path() -> Path:
    return data_dir() / "config.json"


def load_config() -> Dict[str, Any]:
    """读取 $DSH_HOME/paper2html/config.json（不存在或损坏时返回空 dict）。"""
    path = config_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # pragma: no cover - 用户配置写坏
        logger.warning("读取 %s 失败（忽略）: %s", path, exc)
        return {}


def config_value(key: str) -> str:
    config = load_config()
    for alias in _CONFIG_ALIASES.get(key, (key,)):
        value = config.get(alias)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def env_value(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def read_api_keys() -> Dict[str, str]:
    """key 优先级：环境变量 > config.json。"""
    doc2x = env_value("DOC2X_APIKEY") or env_value("DOC2X_API_KEY") or config_value("doc2xKey")
    pdf2x = env_value("PDF2X_APIKEY") or env_value("PDF2X_API_KEY") or config_value("pdf2xKey")
    deepseek = (
        env_value("DEEPSEEK_APIKEY")
        or env_value("DEEPSEEK_API_KEY")
        or env_value("LLM_API_KEY")
        or config_value("deepseekKey")
    )
    base_url = (
        env_value("DEEPSEEK_BASE_URL")
        or env_value("LLM_BASE_URL")
        or config_value("deepseekBaseUrl")
        or "https://api.deepseek.com/v1"
    )
    model = env_value("LLM_MODEL") or config_value("llmModel") or "deepseek-chat"
    return {
        "doc2x": doc2x,
        "pdf2x": pdf2x,
        "deepseek": deepseek,
        "base_url": base_url,
        "model": model,
    }


def arxiv_cache_dir() -> Path:
    override = env_value("PAPER2HTML_CACHE_DIR")
    return Path(override) if override else data_dir() / "cache"


# ============================================================================
# Paper2HTML 类
# ============================================================================

class Paper2HTML:
    """学术论文 → 可视化 HTML 阅读器。

    解析层（本地 PyMuPDF / Doc2X / PDF2X）→ 理解层（可选 LLM）→ 渲染层（上游模板）。

    使用示例:
        >>> from paper2html import Paper2HTML
        >>> converter = Paper2HTML(style="dark_lab")
        >>> output_path = converter.convert("paper.pdf", "output.html", skip_understand=True)
    """

    AVAILABLE_STYLES = AVAILABLE_STYLES

    def __init__(
        self,
        style: str = "dark_lab",
        doc2x_api_key: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_model: Optional[str] = None,
        engine: str = "auto",
        extract_images: bool = True,
    ):
        if style not in AVAILABLE_STYLES:
            raise ValueError(
                f"未知样式: {style}。可选: {', '.join(AVAILABLE_STYLES)}"
            )
        if engine not in AVAILABLE_ENGINES:
            raise ValueError(
                f"未知解析引擎: {engine}。可选: {', '.join(AVAILABLE_ENGINES)}"
            )
        self.style = style
        self.engine = engine
        self.extract_images = extract_images

        keys = read_api_keys()
        self.doc2x_api_key = doc2x_api_key or keys["doc2x"]
        self.pdf2x_api_key = keys["pdf2x"]
        self.llm_api_key = llm_api_key or keys["deepseek"]
        self.llm_base_url = llm_base_url or keys["base_url"]
        self.llm_model = llm_model or keys["model"]

        self._parser = None
        self._arxiv_handler = None
        self._llm_client = None
        self._understander = None
        self._renderer = None
        self._output_path: Optional[str] = None
        self._warnings: List[str] = []

    # -- 懒加载 --------------------------------------------------------------

    @property
    def arxiv_handler(self):
        if self._arxiv_handler is None:
            from parsers.arxiv_handler import ArxivHandler

            self._arxiv_handler = ArxivHandler(cache_dir=str(arxiv_cache_dir()))
        return self._arxiv_handler

    @property
    def llm_client(self):
        if self._llm_client is None:
            from understanding.llm_client import LLMClient

            self._llm_client = LLMClient(
                api_key=self.llm_api_key,
                base_url=self.llm_base_url,
                model=self.llm_model,
            )
        return self._llm_client

    @property
    def understander(self):
        if self._understander is None:
            from understanding.llm_client import PaperUnderstanding

            self._understander = PaperUnderstanding(llm_client=self.llm_client)
        return self._understander

    @property
    def renderer(self):
        if self._renderer is None:
            from rendering.renderer import PaperRenderer

            self._renderer = PaperRenderer(style=self.style)
        return self._renderer

    # -- 主流程 --------------------------------------------------------------

    def convert(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        skip_understand: bool = False,
    ) -> str:
        """一站式转换：PDF/arXiv → HTML。失败时抛 RuntimeError。"""
        result = self.convert_with_report(input_path, output_path, skip_understand)
        return result["htmlPath"]

    def convert_with_report(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        skip_understand: bool = False,
    ) -> Dict[str, Any]:
        if not input_path or not str(input_path).strip():
            raise ValueError("input 不能为空：给本地 PDF 绝对路径或 arXiv URL/ID")
        input_path = str(input_path).strip()
        self._warnings = []
        if output_path is None:
            output_path = self._generate_output_path(input_path)
        output_path = str(Path(output_path).expanduser())
        self._output_path = output_path
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        logger.info("开始转换: %s", input_path)
        logger.info("样式: %s · 解析引擎: %s", self.style, self.engine)

        # Step 1: 解析
        parse_result = self.parse(input_path)
        if not parse_result.success:
            raise RuntimeError(parse_result.error_message or "解析失败（未知原因）")
        engine = str(parse_result.metadata.get("engine") or self.engine)
        for warning in parse_result.metadata.get("warnings") or []:
            self._warnings.append(str(warning))
        logger.info("解析完成: engine=%s, markdown=%d 字符", engine, len(parse_result.markdown))

        # Step 2: 理解（可选）
        did_understand = False
        if skip_understand:
            logger.info("跳过理解层（--no-understand）：只做解析 + 渲染")
            understanding_result = self._create_mock_understanding(parse_result)
        elif not self.llm_api_key:
            logger.warning(
                "未配置 DEEPSEEK_APIKEY，自动跳过 AI 理解层（页面仍可正常阅读）。"
                "需要 TL;DR/章节摘要时配置 key 后再试。"
            )
            self._warnings.append(
                "未配置 DeepSeek key：已跳过 AI 摘要。配置 DEEPSEEK_APIKEY 或 "
                "$DSH_HOME/paper2html/config.json 的 deepseekKey 后重跑可获得 TL;DR/关键发现/章节摘要。"
            )
            understanding_result = self._create_mock_understanding(parse_result)
        else:
            logger.info("AI 理解中...")
            understanding_result = self.understand(parse_result)
            if understanding_result.success:
                did_understand = True
            else:
                logger.warning("理解层失败，回退为无 AI 摘要页面: %s", understanding_result.error_message)
                self._warnings.append(f"AI 理解层失败，已回退为无摘要页面: {understanding_result.error_message}")
                understanding_result = self._create_mock_understanding(parse_result)

        # 理解层标题回填
        if understanding_result.structured is not None:
            structured_title = getattr(understanding_result.structured, "title", "") or ""
            structured_authors = getattr(understanding_result.structured, "authors", []) or []
            if structured_title and not parse_result.metadata.get("title"):
                parse_result.metadata["title"] = structured_title
            if structured_authors and not parse_result.metadata.get("authors"):
                parse_result.metadata["authors"] = structured_authors

        # Step 3: 渲染（docId 稳定：同一篇论文重转后批注仍能找回）
        doc_id = self._compute_doc_id(input_path, parse_result)
        output_stem = Path(output_path).stem
        html_path = self.renderer.render(
            parse_result,
            understanding_result,
            output_path,
            doc_id=doc_id,
            file_name=output_stem,
        )
        html_path = str(Path(html_path).resolve())
        size = os.path.getsize(html_path)
        logger.info("HTML 已生成: %s (%d bytes)", html_path, size)

        pages = parse_result.metadata.get("page_count")
        if not pages:
            pages = self._count_pages(parse_result.source_file)
        return {
            "htmlPath": html_path,
            "title": str(parse_result.metadata.get("title") or "Untitled Paper"),
            "authors": [str(a) for a in (parse_result.metadata.get("authors") or [])],
            "style": self.style,
            "engine": engine,
            "pages": int(pages or 0),
            "bytes": int(size),
            "understand": bool(did_understand),
            "source": parse_result.source_file,
            "warnings": self._warnings,
        }

    def parse(self, input_path: str):
        """按引擎策略解析输入，返回 ParseResult。"""
        if self._is_arxiv_input(input_path):
            return self._parse_arxiv(input_path)
        return self._parse_pdf(input_path)

    def understand(self, parse_result):
        from understanding.llm_client import (
            KeyFindingsResult,
            StructuredExtraction,
            UnderstandingResult,
        )

        try:
            return self.understander.understand(parse_result)
        except Exception as exc:
            logger.error("理解失败: %s", exc)
            return UnderstandingResult(
                tldr="",
                key_findings=KeyFindingsResult([], "", ""),
                section_summaries=[],
                structured=StructuredExtraction("", [], "", "", "", [], [], [], "", None),
                mermaid_code="",
                success=False,
                error_message=str(exc),
            )

    def render(self, parse_result, understanding_result, output_path: str,
               doc_id: Optional[str] = None, file_name: Optional[str] = None) -> str:
        return self.renderer.render(
            parse_result, understanding_result, output_path,
            doc_id=doc_id, file_name=file_name,
        )

    # -- 解析：输入类型 ------------------------------------------------------

    @staticmethod
    def _is_arxiv_input(value: str) -> bool:
        import re

        low = (value or "").lower().strip()
        if not low:
            return False
        if low.startswith(("http://", "https://")):
            return "arxiv.org" in low
        # 纯 arXiv ID：1706.03762 / 2402.19473v2
        return re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", low) is not None

    def _parse_arxiv(self, url_or_id: str):
        from parsers.models import ParseResult

        try:
            pdf_path, arxiv_id, arxiv_meta = self.arxiv_handler.download_and_prepare(url_or_id)
        except Exception as exc:
            return ParseResult(
                source_file=url_or_id,
                success=False,
                error_message=(
                    f"arXiv 下载失败: {exc}\n"
                    "请检查：1) arXiv ID / URL 是否正确（如 1706.03762）；"
                    "2) 网络能否访问 arxiv.org（可换 export.arxiv.org）；3) 稍后重试。"
                ),
            )

        result = self._parse_pdf(pdf_path, metadata_override=arxiv_meta)
        if result.success:
            result.metadata["arxiv_id"] = arxiv_id
            result.metadata["source"] = "arxiv"
            result.source_file = url_or_id
            if arxiv_meta.get("abs_url"):
                result.metadata["arxiv_url"] = arxiv_meta["abs_url"]
        return result

    # -- 解析：PDF 引擎策略 --------------------------------------------------

    def _parse_pdf(self, pdf_path: str, metadata_override: Optional[dict] = None):
        pdf_file = Path(pdf_path).expanduser()
        try:
            pdf_file = pdf_file.resolve()
        except Exception:
            pass

        local_override = dict(metadata_override or {})

        if self.engine == "doc2x":
            if not self.doc2x_api_key:
                return self._engine_key_error("doc2x")
            return self._parse_with_doc2x(pdf_file)
        if self.engine == "pdf2x":
            if not self.pdf2x_api_key:
                return self._engine_key_error("pdf2x")
            return self._parse_with_pdf2x(pdf_file)
        if self.engine == "local":
            return self._parse_locally(pdf_file, local_override)

        # auto：有 key 先云端，失败/无 key 一律回退本地
        if self.doc2x_api_key:
            result = self._parse_with_doc2x(pdf_file)
            if result.success and result.markdown.strip():
                return result
            reason = result.error_message or "返回空内容"
            logger.warning("Doc2X 解析不可用（%s），尝试 PDF2X...", reason)
            self._warnings.append(f"Doc2X 解析失败，已回退：{reason}")
        if self.pdf2x_api_key:
            result = self._parse_with_pdf2x(pdf_file)
            if result.success and result.markdown.strip():
                return result
            reason = result.error_message or "返回空内容"
            logger.warning("PDF2X 解析不可用（%s），回退本地解析...", reason)
            self._warnings.append(f"PDF2X 解析失败，已回退：{reason}")
        return self._parse_locally(pdf_file, local_override)

    def _engine_key_error(self, engine: str):
        from parsers.models import ParseResult

        env_name = "DOC2X_APIKEY" if engine == "doc2x" else "PDF2X_APIKEY"
        field = "doc2xKey" if engine == "doc2x" else "pdf2xKey"
        return ParseResult(
            source_file="",
            success=False,
            error_message=(
                f"--engine {engine} 需要 {env_name}（未检测到）。\n"
                f"配置方式：export {env_name}=your-key，或写入 {config_path()} 的 {field} 字段；\n"
                "不想配 key 就直接用 --engine local / --engine auto（本地 PyMuPDF 解析，无需 key）。"
            ),
        )

    def _parse_with_doc2x(self, pdf_file: Path):
        from parsers.models import ParseResult

        try:
            from parsers.doc2x_parser import Doc2XParser
        except Exception as exc:
            return ParseResult(
                source_file=str(pdf_file),
                success=False,
                error_message=f"Doc2X 解析器加载失败: {exc}",
            )
        try:
            parser = Doc2XParser(api_key=self.doc2x_api_key, use_sdk=False)
            result = parser.parse(str(pdf_file))
            if result.success:
                result.metadata.setdefault("engine", "doc2x")
                self._annotate_local_file(result, pdf_file)
            return result
        except Exception as exc:
            logger.error("Doc2X 解析失败: %s", exc)
            return ParseResult(
                source_file=str(pdf_file),
                success=False,
                error_message=f"Doc2X 解析失败: {exc}",
            )

    def _parse_with_pdf2x(self, pdf_file: Path):
        from parsers.models import ParseResult

        try:
            from parsers.pdf2x_parser import PDF2XParser
        except Exception as exc:
            return ParseResult(
                source_file=str(pdf_file),
                success=False,
                error_message=f"PDF2X 解析器加载失败: {exc}",
            )
        try:
            parser = PDF2XParser(api_key=self.pdf2x_api_key)
            result = parser.parse(str(pdf_file))
            if result.success:
                result.metadata.setdefault("engine", "pdf2x")
                self._annotate_local_file(result, pdf_file)
            return result
        except Exception as exc:
            logger.error("PDF2X 解析失败: %s", exc)
            return ParseResult(
                source_file=str(pdf_file),
                success=False,
                error_message=f"PDF2X 解析失败: {exc}",
            )

    def _annotate_local_file(self, result, pdf_file: Path) -> None:
        if not result.metadata:
            result.metadata = {}
        result.metadata.setdefault("source", "local_file")
        if not result.metadata.get("page_count"):
            result.metadata["page_count"] = self._count_pages(str(pdf_file))
        if not result.metadata.get("title"):
            result.metadata["title"] = pdf_file.stem.replace("_", " ")

    def _parse_locally(self, pdf_file: Path, metadata_override: dict):
        from parsers.models import ParseResult

        if not pdf_file.exists():
            return ParseResult(
                source_file=str(pdf_file),
                success=False,
                error_message=f"PDF 文件不存在: {pdf_file}",
            )
        if pdf_file.suffix.lower() != ".pdf":
            return ParseResult(
                source_file=str(pdf_file),
                success=False,
                error_message=f"不支持的文件格式 {pdf_file.suffix or '(无后缀)'}，只支持 .pdf",
            )
        try:
            from parsers.local_parser import LocalParser
        except Exception as exc:
            return ParseResult(
                source_file=str(pdf_file),
                success=False,
                error_message=(
                    "本地解析器不可用（PyMuPDF 未安装？）: "
                    f"{exc}\n请运行: python3 -m pip install pymupdf"
                ),
            )

        assets_dir = None
        if self._output_path:
            out = Path(self._output_path)
            assets_dir = out.parent / f"{out.stem}_assets"
        try:
            parser = LocalParser(extract_images=self.extract_images)
            result = parser.parse(
                str(pdf_file),
                output_dir=str(assets_dir) if assets_dir else None,
                metadata_override=metadata_override,
            )
            if result.success:
                result.metadata.setdefault("engine", "local")
                self._annotate_local_file(result, pdf_file)
                if metadata_override.get("title"):
                    result.metadata["title"] = metadata_override["title"]
                if metadata_override.get("authors"):
                    result.metadata["authors"] = metadata_override["authors"]
            return result
        except Exception as exc:
            logger.exception("本地解析失败")
            return ParseResult(
                source_file=str(pdf_file),
                success=False,
                error_message=(
                    f"本地解析失败: {exc}\n"
                    "可尝试换一份 PDF，或配置 DOC2X_APIKEY 走云端解析（--engine doc2x）。"
                ),
            )

    # -- 其他工具方法 --------------------------------------------------------

    @staticmethod
    def _count_pages(pdf_path: str) -> int:
        try:
            import fitz  # PyMuPDF

            with fitz.open(pdf_path) as doc:
                return int(doc.page_count)
        except Exception:
            pass
        try:
            from PyPDF2 import PdfReader

            with open(pdf_path, "rb") as f:
                return len(PdfReader(f).pages)
        except Exception:
            return 0

    @staticmethod
    def _compute_doc_id(input_path: str, parse_result) -> str:
        """给页面批注生成稳定的 document id。

        - arXiv 论文用 arXiv ID（同一篇论文的版本更新、重复下载都保持同一 id）；
        - 本地 PDF 用文件内容 SHA-1（移动/改名不丢批注）；
        - 都不可用时退回输入路径哈希。
        """
        import hashlib

        metadata = getattr(parse_result, "metadata", None) or {}
        arxiv_id = str(metadata.get("arxiv_id") or "").strip()
        if arxiv_id:
            return "arxiv-" + arxiv_id

        source_file = str(getattr(parse_result, "source_file", "") or input_path or "")
        candidate = Path(source_file)
        try:
            if candidate.is_file():
                digest = hashlib.sha1()
                with open(candidate, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                return "pdf-" + digest.hexdigest()[:16]
        except Exception:
            pass
        fallback = hashlib.sha1(source_file.encode("utf-8", "replace")).hexdigest()[:16]
        return "doc-" + fallback

    def _generate_output_path(self, input_path: str) -> str:
        import re

        if self._is_arxiv_input(input_path):
            m = re.search(r"(\d{4}\.\d{4,5})", input_path)
            stem = m.group(1) if m else "arxiv-paper"
            return str(data_dir() / "exports" / f"{stem}.html")
        pdf_file = Path(input_path).expanduser()
        return str(pdf_file.parent / f"{pdf_file.stem}.html")

    def _create_mock_understanding(self, parse_result):
        """无 AI 理解时的替代结果：从 Abstract 段抽一段做 TL;DR。"""
        from understanding.llm_client import (
            KeyFindingsResult,
            StructuredExtraction,
            UnderstandingResult,
        )

        tldr = ""
        markdown = parse_result.markdown or ""
        lines = markdown.split("\n")
        for i, line in enumerate(lines):
            if line.strip().lower().startswith(("## abstract", "# abstract", "abstract")):
                abstract_lines = []
                for nxt in lines[i + 1:]:
                    if nxt.startswith("#"):
                        break
                    if nxt.strip():
                        abstract_lines.append(nxt.strip())
                tldr = " ".join(abstract_lines)[:300]
                break
        return UnderstandingResult(
            tldr=tldr or "（本地模式未生成 AI 摘要，可直接阅读正文）",
            key_findings=KeyFindingsResult(key_findings=[], innovation="", significance=""),
            section_summaries=[],
            structured=StructuredExtraction(
                title=str(parse_result.metadata.get("title") or "Untitled Paper"),
                authors=list(parse_result.metadata.get("authors") or []),
                abstract_summary=tldr,
                research_question="",
                methodology="",
                contributions=[],
                experiment_results=[],
                limitations=[],
                future_work="",
                mermaid_architecture="",
                experiment_table=None,
            ),
            mermaid_code="",
            success=False,
        )


# ============================================================================
# 便捷函数
# ============================================================================

def convert_paper(
    input_path: str,
    output_path: Optional[str] = None,
    style: str = "dark_lab",
    skip_understand: bool = True,
    **kwargs,
) -> str:
    """便捷函数：一站式转换 PDF/arXiv → HTML，返回 HTML 路径。"""
    converter = Paper2HTML(style=style, **kwargs)
    return converter.convert(input_path, output_path, skip_understand)


# ============================================================================
# CLI
# ============================================================================

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper2html",
        description="学术论文 → 可视化 HTML 阅读器（无 key 也能跑）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python paper2html.py --input paper.pdf --output output.html --no-understand
  python paper2html.py --input https://arxiv.org/abs/1706.03762
  python paper2html.py --input paper.pdf --style neon_tech --no-understand
  python paper2html.py --input paper.pdf --engine local --no-understand

环境变量:
  DOC2X_APIKEY / PDF2X_APIKEY   云端 PDF 解析（可选）
  DEEPSEEK_APIKEY               AI 理解层（可选）
  DSH_HOME                      数据目录（默认 ~/.dsh）
        """,
    )
    parser.add_argument("--input", "-i", required=True, help="本地 PDF 路径或 arXiv URL/ID")
    parser.add_argument("--output", "-o", help="输出 HTML 路径（默认自动生成）")
    parser.add_argument("--style", "-s", choices=AVAILABLE_STYLES, default="dark_lab", help="样式预设（默认 dark_lab）")
    parser.add_argument(
        "--engine",
        choices=AVAILABLE_ENGINES,
        default="auto",
        help="解析引擎：auto（有 key 走云端，否则本地）/ local / doc2x / pdf2x，默认 auto",
    )
    parser.add_argument("--no-understand", action="store_true", help="跳过 AI 理解层（无 key 推荐）")
    parser.add_argument("--no-images", action="store_true", help="本地解析时不抽图片（HTML 更小）")
    parser.add_argument("--api-key", help="Doc2X/PDF2X key（默认从环境变量或 config.json 读取）")
    parser.add_argument("--llm-api-key", help="LLM key（默认从环境变量或 config.json 读取）")
    parser.add_argument("--llm-base-url", help="LLM API Base URL")
    parser.add_argument("--llm-model", help="LLM 模型名（默认 deepseek-chat）")
    parser.add_argument("--debug", action="store_true", help="调试日志")
    return parser


def _emit(obj: Dict[str, Any], prefix: str = RESULT_PREFIX) -> None:
    print(prefix + json.dumps(obj, ensure_ascii=False))


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )

    try:
        converter = Paper2HTML(
            style=args.style,
            doc2x_api_key=args.api_key,
            llm_api_key=args.llm_api_key,
            llm_base_url=args.llm_base_url,
            llm_model=args.llm_model,
            engine=args.engine,
            extract_images=not args.no_images,
        )
        report = converter.convert_with_report(
            input_path=args.input,
            output_path=args.output,
            skip_understand=args.no_understand,
        )
        report["ok"] = True
        _emit(report)
        print(f"OK {report['htmlPath']}", file=sys.stderr)
        return 0
    except ValueError as exc:
        _emit({"ok": False, "error": str(exc), "errorType": "invalid_input"}, ERROR_PREFIX)
        print(f"参数错误: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        _emit({"ok": False, "error": str(exc), "errorType": "file_not_found"}, ERROR_PREFIX)
        print(f"文件未找到: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 130
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        _emit({"ok": False, "error": message, "errorType": "convert_failed"}, ERROR_PREFIX)
        print(f"转换失败: {message}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
