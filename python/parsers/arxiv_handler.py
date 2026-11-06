"""
arXiv链接处理器
下载arXiv论文PDF并准备解析
"""

import html as html_lib
import re
import os
import tempfile
import logging
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ArxivHandler:
    """
    arXiv论文下载处理器
    
    支持的URL格式:
    - https://arxiv.org/abs/XXXXX.XXXXX  (Abstract页面)
    - https://arxiv.org/pdf/XXXXX.XXXXX  (PDF直接链接)
    - https://arxiv.org/pdf/XXXXX.XXXXX.pdf  (带.pdf后缀)
    
    示例ID:
    - 2402.19473 (LightRAG)
    - 2312.12456 (Mamba)
    - 1706.03762 (Attention is All You Need)
    """
    
    # arXiv API和下载基础URL
    ARXIV_ABSTRACT_PATTERN = re.compile(r"arxiv\.org/abs/(\d+\.\d+)")
    ARXIV_PDF_PATTERN = re.compile(r"arxiv\.org/pdf/(\d+\.\d+)")
    
    # 备用域名
    ARXIV_ORG_URLS = [
        "https://arxiv.org",
        "https://export.arxiv.org",  # 备用
    ]
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        初始化处理器
        
        Args:
            cache_dir: PDF缓存目录，默认为系统临时目录
        """
        if cache_dir:
            self.cache_dir = Path(cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.cache_dir = None
    
    def extract_arxiv_id(self, url_or_id: str) -> Optional[str]:
        """
        从URL或ID字符串中提取arXiv ID
        
        Args:
            url_or_id: arXiv URL或纯ID
            
        Returns:
            提取的arXiv ID (如 "2402.19473")，失败返回None
        """
        url_or_id = url_or_id.strip()
        
        # 尝试从URL提取
        abs_match = self.ARXIV_ABSTRACT_PATTERN.search(url_or_id)
        if abs_match:
            return abs_match.group(1)
        
        pdf_match = self.ARXIV_PDF_PATTERN.search(url_or_id)
        if pdf_match:
            # 去掉可能的 .pdf 后缀
            return pdf_match.group(1).replace(".pdf", "")
        
        # 尝试直接作为ID处理（格式：数字.数字）
        if re.match(r"^\d+\.\d+$", url_or_id):
            return url_or_id
        
        return None
    
    def get_pdf_url(self, arxiv_id: str) -> str:
        """
        根据arXiv ID生成PDF下载URL
        
        Args:
            arxiv_id: arXiv ID (如 "2402.19473")
            
        Returns:
            PDF下载URL
        """
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    
    def download(self, url_or_id: str, output_path: Optional[str] = None) -> Tuple[str, str]:
        """
        下载arXiv论文PDF
        
        Args:
            url_or_id: arXiv URL或ID
            output_path: 输出文件路径，默认为缓存目录下的 PDFID.pdf
            
        Returns:
            Tuple[str, str]: (本地PDF路径, arXiv ID)
            
        Raises:
            ValueError: 无效的URL或ID
            RuntimeError: 下载失败
        """
        import requests
        
        # 提取arXiv ID
        arxiv_id = self.extract_arxiv_id(url_or_id)
        if not arxiv_id:
            raise ValueError(f"无法从 '{url_or_id}' 提取arXiv ID")
        
        # 确定输出路径
        if output_path is None:
            if self.cache_dir:
                output_path = self.cache_dir / f"{arxiv_id}.pdf"
            else:
                output_path = Path(tempfile.gettempdir()) / f"arxiv_{arxiv_id}.pdf"
        else:
            output_path = Path(output_path)
        
        # 如果文件已存在，直接返回
        if output_path.exists() and output_path.stat().st_size > 10000:
            logger.info(f"使用缓存: {output_path}")
            return str(output_path), arxiv_id
        
        # 下载PDF
        pdf_url = self.get_pdf_url(arxiv_id)
        logger.info(f"正在下载: {pdf_url}")
        
        try:
            response = requests.get(
                pdf_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; paper2html-Skill/1.0)"
                },
                timeout=120,
                stream=True
            )
            
            if response.status_code == 404:
                raise RuntimeError(f"arXiv论文不存在: {arxiv_id}")
            elif response.status_code != 200:
                raise RuntimeError(f"下载失败: HTTP {response.status_code}")
            
            # 检查内容类型
            content_type = response.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and not response.content[:4].startswith(b"%PDF"):
                raise RuntimeError(f"下载内容不是PDF: {content_type}")
            
            # 保存文件
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = output_path.stat().st_size
            logger.info(f"下载完成: {output_path} ({file_size / 1024 / 1024:.2f} MB)")
            
            return str(output_path), arxiv_id
            
        except requests.exceptions.Timeout:
            raise RuntimeError(f"下载超时: {pdf_url}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"下载请求失败: {str(e)}")
    
    def download_and_prepare(self, url_or_id: str, output_dir: Optional[str] = None) -> Tuple[str, str, dict]:
        """
        下载PDF并准备解析所需的所有信息
        
        Args:
            url_or_id: arXiv URL或ID
            output_dir: 输出目录
            
        Returns:
            Tuple[str, str, dict]: (本地PDF路径, arXiv ID, 元数据字典)
        """
        import requests
        
        arxiv_id = self.extract_arxiv_id(url_or_id)
        if not arxiv_id:
            raise ValueError(f"无法从 '{url_or_id}' 提取arXiv ID")
        
        # 下载PDF
        pdf_path, _ = self.download(url_or_id)
        
        # 获取arXiv元数据
        metadata = {
            "arxiv_id": arxiv_id,
            "pdf_url": self.get_pdf_url(arxiv_id),
            "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
            "title": "",
            "authors": [],
            "abstract": "",
            "categories": [],
            "published": "",
            "updated": "",
        }
        
        # 尝试获取arXiv API元数据
        try:
            api_url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
            response = requests.get(api_url, timeout=30)
            
            if response.status_code == 200:
                # 用正则解析 Atom XML：注意 feed 级别的 <title> 是 "arXiv Query..."，
                # 论文标题在 <entry> 里，不能直接取第一个 <title>。
                content = response.text
                entry_match = re.search(r"<entry>(.*?)</entry>", content, re.DOTALL)
                entry = entry_match.group(1) if entry_match else content

                def _clean(value: str) -> str:
                    return re.sub(r"\s+", " ", html_lib.unescape(value or "").strip())

                title_match = re.search(r"<title>(.+?)</title>", entry, re.DOTALL)
                if title_match:
                    metadata["title"] = _clean(title_match.group(1))

                author_matches = re.findall(r"<name>(.+?)</name>", entry, re.DOTALL)
                metadata["authors"] = [_clean(name) for name in author_matches if _clean(name)]

                summary_match = re.search(r"<summary>(.+?)</summary>", entry, re.DOTALL)
                if summary_match:
                    metadata["abstract"] = _clean(summary_match.group(1))

                cat_matches = re.findall(r"<category term=\"([^\"]+)\"", entry)
                metadata["categories"] = cat_matches

                published_match = re.search(r"<published>(.+?)</published>", entry)
                if published_match:
                    metadata["published"] = published_match.group(1)

                updated_match = re.search(r"<updated>(.+?)</updated>", entry)
                if updated_match:
                    metadata["updated"] = updated_match.group(1)
                    
        except Exception as e:
            logger.warning(f"获取arXiv元数据失败: {e}")
        
        return pdf_path, arxiv_id, metadata


# 便捷函数
def download_arxiv(url_or_id: str, output_path: Optional[str] = None) -> Tuple[str, str]:
    """
    便捷函数：下载arXiv论文PDF
    
    Args:
        url_or_id: arXiv URL或ID
        output_path: 输出文件路径
        
    Returns:
        Tuple[str, str]: (本地PDF路径, arXiv ID)
    """
    handler = ArxivHandler()
    return handler.download(url_or_id, output_path)


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    # 测试
    test_urls = [
        "https://arxiv.org/abs/2402.19473",
        "https://arxiv.org/pdf/2312.12456",
        "1706.03762",
    ]
    
    for url in test_urls:
        print(f"\n测试: {url}")
        try:
            handler = ArxivHandler(cache_dir="./output")
            pdf_path, arxiv_id, metadata = handler.download_and_prepare(url)
            print(f"  PDF路径: {pdf_path}")
            print(f"  arXiv ID: {arxiv_id}")
            print(f"  标题: {metadata.get('title', 'N/A')[:60]}...")
            print(f"  作者: {', '.join(metadata.get('authors', [])[:3])}")
        except Exception as e:
            print(f"  错误: {e}")
