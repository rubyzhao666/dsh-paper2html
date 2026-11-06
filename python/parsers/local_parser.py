"""
本地解析器（Local Parser）—— 无 API Key 也能跑的 PDF 解析路径

用 PyMuPDF（import fitz）在本地把 PDF 抽成 Markdown：
- 标题 / 作者启发式识别（arXiv 元数据可覆盖）
- 正文按块还原段落，修复跨行连字符
- 标题层级（1 / 1.1 / 1.1.1）、项目符号列表
- 论文里的插图抽出到 <output_dir>/images/ 并在 Markdown 中引用
- 过滤页眉页脚 / 页码 / arXiv 水印 / 旋转页上的乱序文本

产出适配上游 `parsers.models.ParseResult`，可直接喂给 `rendering.PaperRenderer`。

能力边界（也是 skill references/local-parser.md 的内容）：
- 不还原公式语义：公式以文本形式出现，KaTeX 可能识别不完整；
- 不还原表格结构：表格会退化成段落文本；
- 不还原双栏精确阅读顺序（做了左右栏分栏的启发式处理，复杂版式仍可能串行）；
- 扫描件（没有文本层）无法解析，需要 OCR 或 Doc2X/PDF2X key。

上游 paper2html 为 MIT 许可；本文件是 DSH 插件新增代码。
"""

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from .models import ParseResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 参数
# ---------------------------------------------------------------------------

MIN_IMAGE_SIDE = 64          # 像素：过滤 logo / 小图标
MAX_IMAGES = 80              # 单篇最多内嵌图片数
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 20 * 1024 * 1024
MIN_TOTAL_TEXT_CHARS = 300   # 低于此值认为是扫描件 / 无文本层

_PAGE_NUMBER_RE = re.compile(r"^\s*(?:[ivxlcdm]{1,6}|\d{1,4})\s*$", re.IGNORECASE)
_ARXIV_STAMP_RE = re.compile(r"^arXiv:\S+\s+\[[^\]]+\]\s+\d{1,2}\s+\w+\s+\d{4}", re.IGNORECASE)
# "1 Introduction" / "3.1 Encoder..."（编号后可以没有空格，PDF 常见）
_NUMBERED_HEADING_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*)\.?\s*(?=\S)")
# "I. Introduction" / "IV. EXPERIMENTS"（IEEE 风格罗马数字）
_ROMAN_HEADING_RE = re.compile(r"^([IVXLC]{1,6})\.\s+(?=\S)")
# "A. Background"
_LETTER_HEADING_RE = re.compile(r"^([A-Z])\.\s+(?=\S)")
# "1) Audio Generation"
_PAREN_HEADING_RE = re.compile(r"^(\d{1,2})\)\s+(?=\S)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_RE = re.compile(r"https?://\S+")
_FOOTER_MARKERS = (
    "provided proper attribution",
    "permission to make digital",
    "copyright ©",
    "copyright (c)",
    "all rights reserved",
    "proceedings of the",
    "under a creative commons",
    "licensed under a creative commons",
    "preprint. under review",
    "work in progress",
)
# 常见一级章节名（大小写不敏感、可带编号）
_SECTION_NAMES = {
    "abstract", "introduction", "background", "related work", "related works",
    "method", "methods", "methodology", "approach", "experiments",
    "experimental setup", "evaluation", "results", "discussion",
    "conclusion", "conclusions", "future work", "limitations",
    "references", "acknowledgments", "acknowledgements", "acknowledgment",
    "appendix", "supplementary material", "bibliography",
    "摘要", "引言", "介绍", "相关工作", "方法", "实验", "结论", "参考文献", "致谢",
}
_BULLET_RE = re.compile(r"^[•●▪◦·‣∙●○■□◆◇→\-–—]\s*")


# ---------------------------------------------------------------------------
# 文本工具
# ---------------------------------------------------------------------------

def _norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _looks_like_sentence(text: str) -> bool:
    """标题里不该出现句中断句（". " 后跟小写字母）。"""
    return re.search(r"[a-z\u4e00-\u9fff][.!?。！？]\s+[a-z\u4e00-\u9fff]", text) is not None


def _heading_prefix(text: str):
    """返回 (类型, 层级)；类型用于定层级。"""
    if _ROMAN_HEADING_RE.match(text):
        return "roman", 2
    if _LETTER_HEADING_RE.match(text):
        return "letter", 3
    if _PAREN_HEADING_RE.match(text):
        rest = _PAREN_HEADING_RE.sub("", text)
        if len(text) <= 90 and len(rest) >= 2 and not _looks_like_sentence(rest):
            return "paren", 4
    m = _NUMBERED_HEADING_RE.match(text)
    if m:
        rest = text[m.end():].strip()
        first_ok = bool(rest) and (
            rest[0].isupper() or rest[0].isdigit() or "\u4e00" <= rest[0] <= "\u9fff"
        )
        if first_ok and len(rest) >= 3 and len(text) <= 90 and not rest.endswith(".") and not _looks_like_sentence(rest):
            depth = len(m.group(1).split("."))
            return "numbered", min(depth + 1, 4)
    return "", 0


def _looks_like_heading_numbered(text: str) -> bool:
    return bool(_heading_prefix(text)[0])


def _needs_span_space(prev: str, cur: str) -> bool:
    """PDF 里相邻 span 之间常丢失空格（"for" + "AI-Generated"），在这里补回来。"""
    if not prev or not cur:
        return False
    if prev[-1] in " -−/([{'\"":
        return False
    if not (prev[-1].isalnum()):
        return False
    return cur[0].isupper() or cur[0].isdigit()


def _join_spans(spans: List[str]) -> str:
    out = ""
    for text in spans:
        if not text:
            continue
        if out and _needs_span_space(out, text):
            out += " "
        out += text
    return out


def _join_lines(lines: List[str]) -> str:
    """把 PDF 的一个文本块（通常是一个段落）的若干行拼成一行。"""
    out = ""
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        if not out:
            out = line.strip()
            continue
        # 行尾连字符：英文断词，直接拼；公式/连字符本身保留空格
        if out.endswith("-") and len(out) >= 2 and line[:1].islower():
            out = out[:-1] + line.lstrip()
        elif out.endswith(("−", "=", "+", "/")) or line[:1] in "=+−/":
            out = out + " " + line.lstrip()
        else:
            out = out + " " + line.lstrip()
    return _norm_space(out)


def _escape_markdown_paragraph(text: str) -> str:
    """让普通段落不会被 Markdown 误当成标题/引用/列表。"""
    if not text:
        return text
    if text.startswith(("#", ">", "+", "=")) and not text.startswith("\\"):
        text = "\\" + text
    # 行内下划线容易触发斜体，做最小保护
    text = re.sub(r"(?<=[A-Za-z0-9])_(?=[A-Za-z0-9])", r"\\_", text)
    return text


_NAME_TOKEN = r"[A-ZŁŚŻŹĆŃÓ][\w'’.-]+"
_NAME_PATTERN = _NAME_TOKEN + r"(?:\s+[A-Z]\.)?\s+" + _NAME_TOKEN
_NON_AUTHOR_TOKENS = {
    "google brain", "google research", "university", "institute", "department",
    "college", "school", "labs", "inc", "abstract", "introduction",
}


def _clean_authors(raw_lines: List[str]) -> List[str]:
    """从作者块里尽量抽出人名。抽不出来时退化为清理过的整行。"""
    names: List[str] = []
    for line in raw_lines:
        line = _norm_space(line)
        if not line or _EMAIL_RE.fullmatch(line):
            continue
        text = _EMAIL_RE.sub(" ", line)
        text = re.sub(r"[∗†‡§¶*#]+", " ", text)
        text = _norm_space(text)
        if not text:
            continue
        parts = [p.strip() for p in re.split(r"[,;]", text) if p.strip()] or [text]
        for part in parts:
            # 取行首的 "First [M.] Last"，丢掉后面的机构名
            m = re.match(r"^(" + _NAME_TOKEN + r"(?:\s+[A-Z]\.)?\s+" + _NAME_TOKEN + r")", _norm_space(part))
            if m:
                name = _norm_space(m.group(1))
            else:
                found = re.findall(_NAME_PATTERN, part)
                name = _norm_space(found[0]) if found else ""
            if name and name.lower() not in _NON_AUTHOR_TOKENS and 3 <= len(name) <= 50 and name not in names:
                names.append(name)
    return names[:30]


def _guess_ext(image_bytes: bytes) -> str:
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if image_bytes[:2] == b"\xff\xd8":
        return "jpg"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "webp"
    return "png"


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------

class LocalParser:
    """用 PyMuPDF 在本地把 PDF 解析成 ParseResult。"""

    def __init__(
        self,
        extract_images: bool = True,
        max_pages: Optional[int] = None,
        min_image_side: int = MIN_IMAGE_SIDE,
    ):
        self.extract_images = extract_images
        self.max_pages = max_pages
        self.min_image_side = min_image_side
        # IEEE 风格 "A. / B. / C." 子章节序号（与罗马数字 I/V/X 等有歧义，按出现顺序消歧）
        self._heading_seq = "A"

    # -- 对外入口 -----------------------------------------------------------

    def parse(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        metadata_override: Optional[dict] = None,
    ) -> ParseResult:
        try:
            try:
                import pymupdf as fitz  # PyMuPDF >= 1.24 的新模块名
            except Exception:
                import fitz  # 旧版 PyMuPDF
        except Exception as exc:  # pragma: no cover - 环境问题
            return ParseResult(
                source_file=str(pdf_path),
                success=False,
                error_message=(
                    "本地解析器需要 PyMuPDF。请运行: python3 -m pip install pymupdf\n"
                    f"（原始错误: {exc}）"
                ),
            )

        path = Path(pdf_path).expanduser()
        try:
            path = path.resolve()
        except Exception:
            pass
        if not path.exists():
            return ParseResult(
                source_file=str(path),
                success=False,
                error_message=f"PDF 文件不存在: {path}",
            )
        if path.suffix.lower() != ".pdf":
            return ParseResult(
                source_file=str(path),
                success=False,
                error_message=f"不支持的格式 {path.suffix or '(无后缀)'}，本地解析只支持 .pdf",
            )

        meta_override = dict(metadata_override or {})
        out_dir = Path(output_dir) if output_dir else path.parent / f"{path.stem}_p2h_assets"
        image_dir = out_dir / "images"

        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            return ParseResult(
                source_file=str(path),
                success=False,
                error_message=f"PDF 打不开（可能已损坏或格式异常）: {exc}",
            )

        try:
            if doc.needs_pass:
                return ParseResult(
                    source_file=str(path),
                    success=False,
                    error_message="PDF 已加密，本地解析无法读取；请先解密，或配置 DOC2X_APIKEY 走 Doc2X 解析。",
                )
            return self._parse_doc(fitz, doc, path, image_dir, meta_override)
        finally:
            try:
                doc.close()
            except Exception:
                pass

    # -- 内部实现 -----------------------------------------------------------

    def _parse_doc(self, fitz, doc, path: Path, image_dir: Path, meta_override: dict) -> ParseResult:
        warnings: List[str] = []
        page_count = doc.page_count
        pages = list(range(page_count))
        if self.max_pages:
            pages = pages[: self.max_pages]

        # 第一遍：逐页取 block 信息，同时统计正文字号
        page_infos = []
        size_weight = {}
        for pno in pages:
            page = doc[pno]
            try:
                raw = page.get_text("dict")
            except Exception as exc:
                warnings.append(f"第 {pno + 1} 页文本提取失败: {exc}")
                continue
            width = float(page.rect.width) or 1.0
            height = float(page.rect.height) or 1.0
            blocks = list(raw.get("blocks") or [])
            for b in blocks:
                if b.get("type") == 0:
                    for line in b.get("lines") or []:
                        for span in line.get("spans") or []:
                            size = round(float(span.get("size") or 0), 1)
                            if size <= 0:
                                continue
                            size_weight[size] = size_weight.get(size, 0) + len(span.get("text") or "")
            page_infos.append((pno, page, strip_blocks(blocks), width, height))

        body_size = max(size_weight.items(), key=lambda kv: kv[1])[0] if size_weight else 10.0
        if body_size <= 0:
            body_size = 10.0

        # 跨页重复文本（页眉页脚 / 版权声明）统计
        repeated = {}
        for _pno, _page, blocks, _w, _h in page_infos:
            seen = set()
            for b in blocks:
                if b.get("type") != 0:
                    continue
                text = _norm_space(_block_text(b))
                if not text or len(text) > 120:
                    continue
                key = text.lower()
                if key in seen:
                    continue
                seen.add(key)
                repeated[key] = repeated.get(key, 0) + 1
        repeat_threshold = max(3, len(page_infos) // 2)

        # 第一页：标题 / 作者
        title, authors, skip_keys = self._detect_front_matter(page_infos, body_size, path)
        if meta_override.get("title"):
            title = _norm_space(str(meta_override["title"])) or title
        if meta_override.get("authors"):
            raw_authors = meta_override["authors"]
            if isinstance(raw_authors, str):
                raw_authors = [raw_authors]
            authors = [_norm_space(str(a)) for a in raw_authors if _norm_space(str(a))][:30]
        if not title:
            meta = doc.metadata or {}
            title = _norm_space(meta.get("title") or "")
        if not authors:
            meta = doc.metadata or {}
            raw_author = _norm_space(meta.get("author") or "")
            if raw_author:
                authors = [a.strip() for a in re.split(r"[;,]", raw_author) if a.strip()][:30]
        if not title:
            title = re.sub(r"[_]+", " ", path.stem).strip() or "Untitled Paper"

        # 第二遍：按阅读顺序组装 Markdown，同时抽图片
        self._heading_seq = "A"
        md_parts: List[str] = []
        images: List[str] = []
        seen_image_xrefs = set()
        total_image_bytes = 0
        text_chars = 0
        skipped_images = 0

        for pno, page, blocks, width, height in page_infos:
            items = []
            for b in blocks:
                btype = b.get("type")
                bbox = b.get("bbox") or (0, 0, 0, 0)
                try:
                    y0 = float(bbox[1])
                    x0 = float(bbox[0])
                    x1 = float(bbox[2])
                    y1 = float(bbox[3])
                except Exception:
                    y0 = x0 = x1 = y1 = 0.0

                if btype == 0:
                    text = _block_text(b)
                    if not text:
                        continue
                    norm = _norm_space(text)
                    key = norm.lower()
                    if key in skip_keys:
                        continue
                    if self._should_skip_text(norm, b, pno, page_count, width, height, repeated, repeat_threshold):
                        continue
                    lines = [_line_text(line) for line in (b.get("lines") or [])]
                    lines = [ln for ln in lines if ln]
                    if not lines:
                        continue
                    max_size, bold = _block_style(b)
                    items.append(
                        {
                            "kind": "text",
                            "text": norm,
                            "lines": lines,
                            "max_size": max_size,
                            "bold": bold,
                            "line_count": len(lines),
                            "y0": y0,
                            "x0": x0,
                            "x1": x1,
                            "y1": y1,
                        }
                    )
                elif btype == 1 and self.extract_images:
                    if len(images) >= MAX_IMAGES:
                        skipped_images += 1
                        continue
                    img_bytes = b.get("image")
                    xref = b.get("xref")
                    key = xref if xref is not None else (len(img_bytes) if isinstance(img_bytes, (bytes, bytearray)) else None)
                    if not img_bytes or key is None or key in seen_image_xrefs:
                        continue
                    img_w = int(b.get("width") or 0)
                    img_h = int(b.get("height") or 0)
                    if img_w < self.min_image_side or img_h < self.min_image_side:
                        continue
                    if len(img_bytes) > MAX_IMAGE_BYTES or total_image_bytes + len(img_bytes) > MAX_TOTAL_IMAGE_BYTES:
                        skipped_images += 1
                        continue
                    ext = str(b.get("ext") or _guess_ext(img_bytes)).lower()
                    ext = {"jpeg": "jpg"}.get(ext, ext)
                    if ext not in ("png", "jpg", "gif", "webp"):
                        ext = _guess_ext(img_bytes)
                    seen_image_xrefs.add(key)
                    try:
                        image_dir.mkdir(parents=True, exist_ok=True)
                        img_name = f"fig_p{pno + 1}_{len(images) + 1}.{ext}"
                        (image_dir / img_name).write_bytes(img_bytes)
                        total_image_bytes += len(img_bytes)
                        images.append(str(image_dir / img_name))
                        items.append(
                            {
                                "kind": "image",
                                "path": str(image_dir / img_name),
                                "name": img_name,
                                "y0": y0,
                                "x0": x0,
                                "x1": x1,
                                "y1": y1,
                            }
                        )
                    except Exception as exc:
                        warnings.append(f"第 {pno + 1} 页图片保存失败: {exc}")

            ordered = _order_items(items, width, height)
            page_md: List[str] = []
            for item in ordered:
                if item["kind"] == "image":
                    page_md.append(f"![Figure]({_posix(Path(item['path']).relative_to(image_dir.parent))})")
                    continue
                level = self._heading_level(
                    item["text"], item.get("max_size", body_size), body_size, item.get("bold", False), item.get("line_count", 1)
                )
                if level:
                    heading = self._format_heading(item["text"], level, body_size)
                    if heading:
                        page_md.append(heading)
                    continue
                para = self._format_paragraph(item["lines"])
                if not para:
                    continue
                inline = _split_inline_abstract(para)
                if inline is not None:
                    page_md.append("## Abstract")
                    para = inline
                    if not para:
                        continue
                text_chars += len(para)
                page_md.append(para)
            if page_md:
                md_parts.append("\n\n".join(page_md))

        markdown = "\n\n".join([part for part in md_parts if part.strip()]).strip()
        if skipped_images:
            warnings.append(f"为控制 HTML 体积，跳过了 {skipped_images} 张图片")
        if not markdown or text_chars < MIN_TOTAL_TEXT_CHARS:
            return ParseResult(
                source_file=str(path),
                success=False,
                error_message=(
                    "这个 PDF 没有可提取的文本层，可能是扫描件。\n"
                    "本地模式不支持 OCR，请任选其一：\n"
                    "1) 用 OCR 工具（如 OCRmyPDF / Adobe）先把 PDF 变成可选中文字的版本；\n"
                    "2) 配置 DOC2X_APIKEY 或 PDF2X_APIKEY（写入环境变量或 "
                    "$DSH_HOME/paper2html/config.json），改走云端解析；\n"
                    "3) 换一份带文本层的 PDF / arXiv 版本。"
                ),
            )

        metadata = {
            "title": title,
            "authors": authors,
            "page_count": page_count,
            "engine": "local",
            "parser": "pymupdf",
            "source": "local_pdf",
            "text_chars": text_chars,
            "image_count": len(images),
            "warnings": warnings,
        }
        return ParseResult(
            markdown=markdown,
            json_data={"page_count": page_count},
            images=images,
            metadata=metadata,
            raw_output_dir=str(image_dir.parent) if images else "",
            source_file=str(path),
            success=True,
        )

    # -- 规则判断 -----------------------------------------------------------

    def _detect_front_matter(self, page_infos, body_size, path: Path):
        """从第一页找出标题 / 作者块，并返回这些块应跳过的 key 集合。"""
        title = ""
        authors: List[str] = []
        skip_keys = set()
        if not page_infos:
            return title, authors, skip_keys

        pno, _page, blocks, width, height = page_infos[0]
        text_blocks = []
        for b in blocks:
            if b.get("type") != 0:
                continue
            text = _norm_space(_block_text(b))
            if not text:
                continue
            lines = [_line_text(line) for line in (b.get("lines") or [])]
            lines = [ln for ln in lines if ln]
            if not lines:
                continue
            if all(_is_rotated_line(line) for line in (b.get("lines") or [])):
                continue
            max_size, bold = _block_style(b)
            bbox = b.get("bbox") or (0, 0, 0, 0)
            y0 = float(bbox[1])
            text_blocks.append(
                {"text": text, "lines": lines, "size": max_size, "bold": bold, "y0": y0, "key": text.lower()}
            )
        text_blocks.sort(key=lambda it: it["y0"])

        # 标题：第一页上半部分、字号明显大于正文、长度合理
        candidates = [
            it
            for it in text_blocks
            if it["y0"] < height * 0.6
            and 6 <= len(it["text"]) <= 300
            and not _is_boilerplate(it["text"])
            and not _is_author_block(it["text"])
        ]
        if candidates:
            biggest = max(candidates, key=lambda it: it["size"])
            if not title and biggest["size"] >= body_size * 1.25 and biggest["size"] / max(body_size, 1) >= 1.2:
                title = _normalize_title(biggest["text"])
                skip_keys.add(biggest["key"])

        # 作者：标题下方、Abstract 上方、字号小于标题
        abstract_y = None
        for it in text_blocks:
            if _headingish(it["text"]) in _SECTION_NAMES or it["text"].strip().lower().startswith("abstract"):
                abstract_y = it["y0"]
                break
        author_lines: List[str] = []
        for it in text_blocks:
            if it["key"] in skip_keys:
                continue
            if abstract_y is not None and it["y0"] >= abstract_y:
                break
            if it["y0"] > height * 0.72:
                break
            if _is_author_block(it["text"]) or (_EMAIL_RE.search(it["text"]) is not None):
                author_lines.append(it["text"])
                skip_keys.add(it["key"])
        if author_lines:
            authors = _clean_authors(author_lines)

        # 再兜底一次：标题紧邻作者块上方的最大字号块
        if not title:
            for it in text_blocks:
                if _is_boilerplate(it["text"]) or _EMAIL_RE.search(it["text"]):
                    continue
                if it["size"] >= body_size * 1.15:
                    title = _normalize_title(it["text"])
                    skip_keys.add(it["key"])
                    break
        return title, authors, skip_keys

    def _should_skip_text(self, norm, block, pno, page_count, width, height, repeated, repeat_threshold) -> bool:
        if not norm:
            return True
        if len(norm) <= 6 and _PAGE_NUMBER_RE.match(norm):
            return True
        if len(norm) <= 6 and re.fullmatch(r"[\W\d_]+", norm):
            return True
        if _ARXIV_STAMP_RE.match(norm):
            return True
        low = norm.lower()
        if low in repeated and repeated[low] >= repeat_threshold and len(norm) <= 120:
            return True
        # 版权 / 免责声明等样板文字：不管多长都跳过（通常在页首或页脚）
        bbox = block.get("bbox") or (0, 0, 0, 0)
        try:
            b_y0, b_y1 = float(bbox[1]), float(bbox[3])
        except Exception:
            b_y0, b_y1 = 0.0, 0.0
        if _is_boilerplate(norm) and (b_y0 < 140 or b_y1 > height - 120):
            return True
        if len(norm) <= 160 and any(marker in low for marker in _FOOTER_MARKERS):
            if b_y0 < 140 or b_y1 > height - 120:
                return True
        # 整块旋转（最后一页的竖排免责声明等）
        lines = block.get("lines") or []
        if lines and all(_is_rotated_line(line) for line in lines):
            return True
        return False

    def _advance_heading_seq(self):
        if len(self._heading_seq) == 1 and self._heading_seq < "Z":
            self._heading_seq = chr(ord(self._heading_seq) + 1)
        else:
            self._heading_seq = "A"

    def _heading_level(self, text: str, max_size: float, body_size: float, bold: bool, line_count: int) -> int:
        if not text or len(text) > 140 or line_count > 4:
            return 0
        plain = _norm_space(text)
        low = plain.lower().strip(" :：.0123456789")
        is_named = low in _SECTION_NAMES
        # "A. Background" 类子章节；I/V/X/L/C/D/M 同时是罗马数字，按序列消歧
        letter_m = _LETTER_HEADING_RE.match(plain)
        if letter_m:
            letter = letter_m.group(1)
            if letter == self._heading_seq:
                self._advance_heading_seq()
                return 3
            if letter not in "IVXLCDM":
                self._advance_heading_seq()
                return 3
            # 落回罗马数字分支
        kind, prefix_level = _heading_prefix(plain)
        if kind:
            self._heading_seq = "A"
            return prefix_level
        if is_named and len(plain) <= 80:
            self._heading_seq = "A"
            return 2
        ratio = max_size / max(body_size, 1.0)
        if ratio >= 1.35 and len(plain) <= 90:
            self._heading_seq = "A"
            return 1 if ratio >= 1.5 else 2
        # 无编号的加粗小标题：只认全大写（"CONCLUSION"），避免把图里的
        # 粗体标签（"New York" / "RAG for Knowledge"）误认成标题
        if bold and len(plain) <= 80 and not re.search(r"[.!?;:,)]$", plain) and line_count <= 3:
            letters = [c for c in plain if c.isalpha()]
            if letters and all(c.isupper() for c in letters):
                self._heading_seq = "A"
                return 3
        return 0

    def _format_heading(self, text: str, level: int, body_size: float) -> str:
        text = _norm_space(text)
        if not text:
            return ""
        # "1Introduction" / "3.1Encoder..." → 补空格
        text = re.sub(r"^(\d{1,2}(?:\.\d{1,2})*)(?=[A-Z\u4e00-\u9fff])", r"\1 ", text)
        # PDF 里小型大写字常被拆成 "I" + "NTRODUCTION"，合并回来
        text = re.sub(r"\b([A-Z])\s+([A-Z]{2,})(?=\s|$)", r"\1\2", text)
        # 全大写标题转成 Title Case（"IV. APPLICATIONS" → "IV. Applications"）
        letters_only = re.sub(r"[^A-Za-z]", "", text)
        if letters_only and letters_only.isupper() and len(letters_only) > 3:
            text = text.title()
            # 罗马数字前缀保持大写（"Ii." → "II."）
            m_roman = re.match(r"^([IVXLC]+)(\.)", text)
            if m_roman:
                text = m_roman.group(1).upper() + text[m_roman.end(1):]
        level = max(1, min(int(level or 1), 4))
        return "#" * level + " " + text

    def _format_paragraph(self, lines: List[str]) -> str:
        cleaned = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if _ARXIV_STAMP_RE.match(line):
                continue
            cleaned.append(line)
        if not cleaned:
            return ""
        # 项目符号列表
        if _BULLET_RE.match(cleaned[0]):
            items = []
            for line in cleaned:
                if _BULLET_RE.match(line):
                    items.append("- " + _BULLET_RE.sub("", line).strip())
                else:
                    if items:
                        items[-1] = items[-1] + " " + line
                    else:
                        items.append(line)
            return "\n".join(items)
        text = _join_lines(cleaned)
        if not text:
            return ""
        return _escape_markdown_paragraph(text)


# ---------------------------------------------------------------------------
# 模块级工具
# ---------------------------------------------------------------------------

def strip_blocks(blocks):
    """只保留后续步骤需要的字段，减少内存占用。"""
    out = []
    for b in blocks or []:
        item = {"type": b.get("type"), "bbox": b.get("bbox")}
        if item["type"] == 0:
            item["lines"] = [
                {"dir": line.get("dir"), "spans": [{"text": s.get("text"), "size": s.get("size"), "flags": s.get("flags")} for s in (line.get("spans") or [])]}
                for line in (b.get("lines") or [])
            ]
        else:
            for key in ("width", "height", "xref", "ext", "image"):
                if key in b:
                    item[key] = b[key]
        out.append(item)
    return out


def _block_text(block) -> str:
    """把 block 的所有行拼成分析用文本（行间补空格，span 边界按需补空格）。"""
    line_texts = [_line_text(line) for line in (block.get("lines") or [])]
    line_texts = [t for t in line_texts if t]
    return _join_lines(line_texts)


def _line_text(line) -> str:
    spans = [span.get("text") or "" for span in (line.get("spans") or [])]
    return _join_spans(spans)


def _block_style(block) -> Tuple[float, bool]:
    max_size = 0.0
    bold = False
    for line in block.get("lines") or []:
        for span in line.get("spans") or []:
            size = float(span.get("size") or 0)
            max_size = max(max_size, size)
            flags = int(span.get("flags") or 0)
            if flags & 16:  # PyMuPDF: bit 4 = bold
                bold = True
    return max_size, bold


def _is_rotated_line(line) -> bool:
    direction = line.get("dir") or (1.0, 0.0)
    try:
        dx, dy = float(direction[0]), float(direction[1])
    except Exception:
        return False
    return abs(dy) > 0.5 or dx < 0


def _headingish(text: str) -> str:
    text = _norm_space(text).lower()
    text = _ROMAN_HEADING_RE.sub("", text)
    text = _LETTER_HEADING_RE.sub("", text)
    text = _PAREN_HEADING_RE.sub("", text)
    text = _NUMBERED_HEADING_RE.sub("", text)
    return text.strip(" :：.")


def _is_boilerplate(text: str) -> bool:
    low = _norm_space(text).lower()
    return any(low.startswith(marker) for marker in _FOOTER_MARKERS)


def _split_inline_abstract(paragraph: str):
    """把 "Abstract—正文……" / "ABSTRACT: 正文" 拆成正文；不是摘要则返回 None。"""
    if not paragraph:
        return None
    m = re.match(r"^(?i:abstract)\s*[—–:：-]\s*(.+)$", paragraph, re.DOTALL)
    if m and len(m.group(1).strip()) > 30:
        return m.group(1).strip()
    m = re.match(r"^(?i:abstract)\s+(.{60,})$", paragraph, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


def _normalize_title(text: str) -> str:
    """标题排版修正：补回 PDF 丢失的空格（"forAI-Generated" → "for AI-Generated"）。"""
    title = _norm_space(text)
    title = re.sub(r"(?<=[a-z])(?=[A-Z]{2,})", " ", title)
    title = re.sub(r"(?<=[a-z])(?=[A-Z][a-z]{2,})", " ", title)
    return _norm_space(title)


def _is_author_block(text: str) -> bool:
    clean = _norm_space(text)
    if not clean:
        return False
    if _EMAIL_RE.search(clean):
        return True
    low = clean.lower()
    if any(
        marker in low
        for marker in ("university", "institute", "department", "google brain", "google research", "inc.", "labs", "college")
    ):
        return True
    if len(clean) > 400:
        return False
    names = re.findall(_NAME_PATTERN, clean)
    if len(names) >= 3 and ("∗" in clean or "†" in clean or "," in clean):
        return True
    if len(names) >= 2 and ("∗" in clean or "†" in clean):
        return True
    return False


def _posix(rel_path) -> str:
    return str(rel_path).replace("\\", "/")


def _is_two_column(items, width: float) -> bool:
    """粗判本页是否双栏：窄块分居左右两侧，且各不少于 3 块。"""
    left = right = 0
    for item in items:
        if item["kind"] == "image":
            continue
        w = max(0.0, item["x1"] - item["x0"])
        if w <= 0 or w > width * 0.62:
            continue
        if item["x0"] < width * 0.45:
            left += 1
        elif item["x0"] > width * 0.45:
            right += 1
    return left >= 3 and right >= 3


def _order_items(items, width: float, height: float):
    """按阅读顺序排序：优先双栏（左栏→右栏，跨栏块按 y 插入），否则按 y 再按 x。"""
    if not items:
        return []
    if not _is_two_column(items, width):
        return sorted(items, key=lambda it: (round(it["y0"] / 3.0), it["x0"]))

    full = [it for it in items if (it["x1"] - it["x0"]) > width * 0.62]
    narrow = [it for it in items if (it["x1"] - it["x0"]) <= width * 0.62]
    full.sort(key=lambda it: (it["y0"], it["x0"]))

    def column_order(rows):
        # 先左栏（x0 较小）按 y，再右栏按 y
        return sorted(rows, key=lambda it: (0 if it["x0"] < width * 0.45 else 1, it["y0"], it["x0"]))

    def center_y(item):
        return (item["y0"] + item["y1"]) / 2.0

    ordered = []
    cursor_y = -1.0
    for block in full:
        band = [it for it in narrow if cursor_y < center_y(it) < center_y(block)]
        ordered.extend(column_order(band))
        ordered.append(block)
        cursor_y = center_y(block)
    ordered.extend(column_order([it for it in narrow if center_y(it) >= cursor_y]))
    return ordered


# 便捷函数 -----------------------------------------------------------------

def parse_pdf_local(pdf_path: str, output_dir: Optional[str] = None, **kwargs) -> ParseResult:
    """便捷函数：本地解析 PDF。"""
    parser = LocalParser(**kwargs)
    return parser.parse(pdf_path, output_dir=output_dir)


if __name__ == "__main__":  # pragma: no cover
    import sys

    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("用法: python -m parsers.local_parser <pdf_path> [output_dir]")
        sys.exit(1)
    result = parse_pdf_local(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print("成功:", result.success)
    print("标题:", result.metadata.get("title"))
    print("作者:", result.metadata.get("authors"))
    print("页数:", result.metadata.get("page_count"))
    print("正文长度:", len(result.markdown))
    print("图片:", len(result.images))
    print("错误:", result.error_message)
    print("--- markdown head ---")
    print(result.markdown[:1500])
