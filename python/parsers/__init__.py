"""
paper2html 解析层

- models / local_parser / arxiv_handler 只依赖标准库（PyMuPDF 在 parse 时才 import），
  所以「本地无 key」模式不需要 requests / pdfdeal / openai；
- Doc2X / PDF2X / PPX 通过模块级 __getattr__ 惰性导入，只有真的走云端引擎时才加载。
"""

from .models import ParseResult, UnderstandingResult, LLMResponse
from .local_parser import LocalParser, parse_pdf_local
from .arxiv_handler import ArxivHandler

__all__ = [
    "ParseResult",
    "UnderstandingResult",
    "LLMResponse",
    "LocalParser",
    "parse_pdf_local",
    "ArxivHandler",
    "Doc2XParser",
    "PDF2XParser",
    "PPXParser",
]

__version__ = "1.1.0-dsh"

_LAZY = {
    "Doc2XParser": (".doc2x_parser", "Doc2XParser"),
    "PDF2XParser": (".pdf2x_parser", "PDF2XParser"),
    "PPXParser": (".ppx_parser", "PPXParser"),
}


def __getattr__(name):
    if name in _LAZY:
        import importlib

        module_name, attr = _LAZY[name]
        module = importlib.import_module(module_name, __name__)
        value = getattr(module, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(list(globals().keys()) + list(_LAZY.keys()))
