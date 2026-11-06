"""
本地PPX解析器
作为Doc2X API不可用时的备选方案
"""

import os
import subprocess
import json
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

from .models import ParseResult




class PPXParser:
    """
    本地PPX解析器
    
    使用 memect-ppx 进行本地PDF解析
    需要Python 3.12+
    
    安装:
        pip install memect-ppx
        ppx install
        ppx download
    
    用法:
        ppx parse paper.pdf -o output/
    """
    
    PPX_CMD = "ppx"
    
    def __init__(
        self,
        max_retries: int = 2,
        timeout: int = 300,
    ):
        """
        初始化解析器
        
        Args:
            max_retries: 最大重试次数
            timeout: 单次解析超时（秒）
        """
        self.max_retries = max_retries
        self.timeout = timeout
    
    def _check_ppx_available(self) -> bool:
        """检查PPX是否可用"""
        try:
            result = subprocess.run(
                [self.PPX_CMD, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _install_ppx(self) -> bool:
        """尝试安装PPX"""
        try:
            logger.info("正在安装 memect-ppx...")
            subprocess.run(
                ["pip", "install", "memect-ppx"],
                check=True,
                capture_output=True,
                timeout=60
            )
            
            # 初始化
            subprocess.run([self.PPX_CMD, "install"], check=True, timeout=120)
            subprocess.run([self.PPX_CMD, "download"], check=True, timeout=300)
            
            return True
        except Exception as e:
            logger.error(f"PPX安装失败: {e}")
            return False
    
    def parse(self, pdf_path: str, output_dir: Optional[str] = None) -> ParseResult:
        """
        使用PPX解析PDF文件
        
        Args:
            pdf_path: PDF文件路径
            output_dir: 输出目录
            
        Returns:
            ParseResult: 解析结果
        """
        pdf_path = Path(pdf_path).resolve()
        
        if not pdf_path.exists():
            return ParseResult(
                source_file=str(pdf_path),
                success=False,
                error_message=f"PDF文件不存在: {pdf_path}"
            )
        
        if output_dir is None:
            output_dir = pdf_path.parent / f"{pdf_path.stem}_ppx"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查PPX可用性
        if not self._check_ppx_available():
            logger.warning("PPX不可用，尝试安装...")
            if not self._install_ppx():
                return ParseResult(
                    source_file=str(pdf_path),
                    success=False,
                    error_message="PPX不可用且安装失败，请确保Python 3.12+环境"
                )
        
        # 构建命令
        cmd = [
            self.PPX_CMD,
            "parse",
            str(pdf_path),
            "-o", str(output_dir),
            "--format", "markdown",  # 输出Markdown格式
        ]
        
        logger.info(f"执行命令: {' '.join(cmd)}")
        
        for attempt in range(self.max_retries):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout
                )
                
                if result.returncode == 0:
                    logger.info(f"PPX解析成功，输出目录: {output_dir}")
                    return self._process_output(output_dir, str(pdf_path))
                else:
                    error_msg = result.stderr or "未知错误"
                    logger.warning(f"PPX解析失败 (尝试 {attempt + 1}/{self.max_retries}): {error_msg}")
                    
                    if attempt < self.max_retries - 1:
                        continue
                    
                    return ParseResult(
                        source_file=str(pdf_path),
                        success=False,
                        error_message=f"PPX解析失败: {error_msg}"
                    )
                    
            except subprocess.TimeoutExpired:
                error_msg = f"解析超时（>{self.timeout}秒）"
                logger.warning(error_msg)
                if attempt < self.max_retries - 1:
                    continue
                return ParseResult(
                    source_file=str(pdf_path),
                    success=False,
                    error_message=error_msg
                )
            except Exception as e:
                return ParseResult(
                    source_file=str(pdf_path),
                    success=False,
                    error_message=f"解析异常: {str(e)}"
                )
        
        return ParseResult(
            source_file=str(pdf_path),
            success=False,
            error_message="达到最大重试次数"
        )
    
    def _process_output(self, output_dir: str, source_file: str) -> ParseResult:
        """处理PPX输出目录"""
        output_path = Path(output_dir)
        images = []
        markdown = ""
        json_data = {}
        metadata = {}
        
        # PPX通常输出的结构
        # 1. 查找Markdown文件
        md_files = list(output_path.glob("*.md")) + list(output_path.glob("*.markdown"))
        
        # 也可能在子目录
        md_files.extend(list(output_path.glob("**/*.md")))
        
        # 去重
        md_files = list(set(md_files))
        
        if md_files:
            # 合并所有Markdown文件
            for mf in sorted(md_files):
                with open(mf, "r", encoding="utf-8") as f:
                    content = f.read()
                    # 跳过空文件
                    if content.strip():
                        markdown += f"\n\n<!-- File: {mf.name} -->\n\n{content}"
            
            markdown = markdown.strip()
        
        # 2. 查找图片
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.gif"]:
            images.extend([str(p) for p in output_path.rglob(ext)])
        
        # 3. 查找JSON（如果有）
        json_files = list(output_path.glob("*.json"))
        if json_files:
            try:
                with open(json_files[0], "r", encoding="utf-8") as f:
                    json_data = json.load(f)
            except Exception as e:
                logger.warning(f"解析JSON失败: {e}")
        
        # 4. 收集输出文件列表
        metadata["files"] = [str(p) for p in output_path.rglob("*") if p.is_file()]
        metadata["output_dir"] = str(output_path)
        
        # 5. 尝试获取页数
        try:
            import PyPDF2
            with open(source_file, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                metadata["page_count"] = len(reader.pages)
        except Exception:
            pass
        
        return ParseResult(
            markdown=markdown,
            json_data=json_data,
            images=images,
            metadata=metadata,
            raw_output_dir=str(output_path),
            source_file=source_file,
            success=True
        )


# 便捷函数
def parse_pdf_local(pdf_path: str, **kwargs) -> ParseResult:
    """
    便捷函数：使用本地PPX解析PDF
    
    Args:
        pdf_path: PDF文件路径
        **kwargs: 传递给PPXParser的参数
        
    Returns:
        ParseResult: 解析结果
    """
    parser = PPXParser(**kwargs)
    return parser.parse(pdf_path)


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 2:
        print("用法: python ppx_parser.py <pdf_path>")
        print("注意: 需要先安装 memect-ppx (pip install memect-ppx)")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    result = parse_pdf_local(pdf_path)
    
    print(f"\n解析结果:")
    print(f"  成功: {result.success}")
    print(f"  Markdown长度: {len(result.markdown)} 字符")
    print(f"  图片数量: {len(result.images)}")
    print(f"  输出目录: {result.raw_output_dir}")
    
    if result.error_message:
        print(f"  错误: {result.error_message}")
