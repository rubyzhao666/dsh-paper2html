"""
PDF2X API解析器
将PDF转换为Markdown，用于paper2html的解析层
API文档: https://pdf2x.cn/docs
"""

import os
import time
import requests
import tempfile
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from .models import ParseResult


class PDF2XParser:
    """
    PDF2X API解析器
    
    使用PDF2X平台的API将PDF转换为Markdown格式
    接口: 提交文件 → 获取task_id → 轮询结果 → 下载文件
    
    API Key通过环境变量 PDF2X_APIKEY 或 DOC2X_APIKEY 获取
    """
    
    BASE_URL = "https://pdf2x.cn"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        max_retries: int = 360,
        poll_interval: float = 10.0,
        timeout: int = 3600,
    ):
        """
        初始化解析器
        
        Args:
            api_key: PDF2X API密钥，默认从环境变量 PDF2X_APIKEY 或 DOC2X_APIKEY 读取
            max_retries: 最大轮询次数
            poll_interval: 轮询间隔（秒）
            timeout: 总超时（秒）
        """
        self.api_key = api_key or os.environ.get("PDF2X_APIKEY", "") or os.environ.get("DOC2X_APIKEY", "")
        if not self.api_key:
            logger.warning("PDF2X_APIKEY 或 DOC2X_APIKEY 环境变量未设置")
        self.max_retries = max_retries
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
    
    def parse(self, pdf_path: str, output_dir: Optional[str] = None) -> ParseResult:
        """
        使用PDF2X API解析PDF文件为Markdown
        
        Args:
            pdf_path: PDF文件路径
            output_dir: 输出目录（可选）
            
        Returns:
            ParseResult: 解析结果，markdown字段包含转换后的Markdown内容
        """
        pdf_path = Path(pdf_path).resolve()
        
        if not pdf_path.exists():
            return ParseResult(
                source_file=str(pdf_path),
                success=False,
                error_message=f"PDF文件不存在: {pdf_path}"
            )
        
        if not self.api_key:
            return ParseResult(
                source_file=str(pdf_path),
                success=False,
                error_message="PDF2X API Key未设置"
            )
        
        logger.info(f"使用PDF2X API解析: {pdf_path}")
        
        try:
            # Step 1: 提交解析任务
            task_id = self._submit_task(pdf_path)
            if not task_id:
                return ParseResult(
                    source_file=str(pdf_path),
                    success=False,
                    error_message="提交PDF2X解析任务失败"
                )
            
            logger.info(f"PDF2X任务已提交: {task_id}")
            
            # Step 2: 轮询结果
            result = self._poll_result(task_id)
            if not result or result.get("status") != "done":
                error_msg = result.get("error", "轮询超时或解析失败") if result else "轮询超时"
                return ParseResult(
                    source_file=str(pdf_path),
                    success=False,
                    error_message=f"PDF2X解析失败: {error_msg}"
                )
            
            logger.info(f"PDF2X解析完成，耗时: {result.get('duration', 0):.1f}秒")
            
            # Step 3: 下载Markdown内容
            markdown_content = self._download_markdown(result, task_id, pdf_path, output_dir)
            
            if not markdown_content:
                return ParseResult(
                    source_file=str(pdf_path),
                    success=False,
                    error_message="下载Markdown内容失败"
                )
            
            # Step 4: 下载图片（如果有）
            images = self._download_images(result, output_dir)
            
            # 构建结果
            metadata = {
                "source": "pdf2x_api",
                "task_id": task_id,
                "duration": result.get("duration", 0),
            }
            
            if output_dir:
                metadata["output_dir"] = str(output_dir)
            
            return ParseResult(
                markdown=markdown_content,
                json_data={},
                images=images,
                metadata=metadata,
                raw_output_dir=output_dir or str(pdf_path.parent),
                source_file=str(pdf_path),
                success=True
            )
            
        except Exception as e:
            logger.error(f"PDF2X解析异常: {e}")
            return ParseResult(
                source_file=str(pdf_path),
                success=False,
                error_message=f"PDF2X解析异常: {str(e)}"
            )
    
    def _submit_task(self, pdf_path: Path) -> Optional[str]:
        """提交PDF2Markdown解析任务"""
        url = f"{self.BASE_URL}/api/parse/pdf2markdown"
        
        try:
            with open(pdf_path, "rb") as f:
                response = requests.post(
                    url,
                    headers=self.headers,
                    files={"file": (pdf_path.name, f, "application/pdf")},
                    timeout=120
                )
            
            if response.status_code == 401:
                logger.error("PDF2X认证失败，请检查API Key")
                return None
            
            if response.status_code != 200:
                logger.error(f"PDF2X提交任务失败: HTTP {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            task_id = data.get("task_id")
            
            if not task_id:
                logger.error(f"PDF2X未返回task_id: {data}")
                return None
            
            return task_id
            
        except requests.exceptions.Timeout:
            logger.error("PDF2X提交任务超时")
            return None
        except Exception as e:
            logger.error(f"PDF2X提交任务异常: {e}")
            return None
    
    def _poll_result(self, task_id: str) -> Optional[dict]:
        """轮询任务结果"""
        url = f"{self.BASE_URL}/api/parse/result/{task_id}"
        
        elapsed = 0
        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, headers=self.headers, timeout=60)
                
                if response.status_code != 200:
                    logger.warning(f"PDF2X轮询失败: HTTP {response.status_code}")
                    time.sleep(self.poll_interval)
                    elapsed += self.poll_interval
                    continue
                
                data = response.json()
                status = data.get("status", "")
                
                if status == "done":
                    return data
                elif status == "failed":
                    logger.error(f"PDF2X解析失败: {data.get('error', '未知错误')}")
                    return data
                elif status == "processing":
                    if attempt % 5 == 0:
                        logger.info(f"PDF2X处理中... ({elapsed:.0f}秒)")
                    time.sleep(self.poll_interval)
                    elapsed += self.poll_interval
                else:
                    logger.warning(f"PDF2X未知状态: {status}")
                    time.sleep(self.poll_interval)
                    elapsed += self.poll_interval
                
                if elapsed > self.timeout:
                    logger.error(f"PDF2X轮询超时 ({self.timeout}秒)")
                    return None
                    
            except Exception as e:
                logger.warning(f"PDF2X轮询异常: {e}")
                time.sleep(self.poll_interval)
                elapsed += self.poll_interval
        
        return None
    
    def _download_markdown(self, result: dict, task_id: str, pdf_path: Path, output_dir: Optional[str] = None) -> Optional[str]:
        """下载Markdown内容"""
        download_url = result.get("download_url")
        
        if not download_url:
            logger.error("PDF2X结果中没有download_url")
            return None
        
        try:
            response = requests.get(download_url, timeout=120)
            if response.status_code != 200:
                logger.error(f"PDF2X下载Markdown失败: HTTP {response.status_code}")
                return None
            
            content = response.text
            
            # 保存到文件
            if output_dir:
                out_path = Path(output_dir)
            else:
                out_path = pdf_path.parent / f"{pdf_path.stem}_pdf2x"
            out_path.mkdir(parents=True, exist_ok=True)
            
            md_file = out_path / f"{pdf_path.stem}.md"
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(content)
            
            logger.info(f"Markdown已保存: {md_file} ({len(content)} 字符)")
            return content
            
        except Exception as e:
            logger.error(f"PDF2X下载Markdown异常: {e}")
            return None
    
    def _download_images(self, result: dict, output_dir: Optional[str] = None) -> list:
        """下载图片资源"""
        images_info = result.get("images", {})
        if not images_info:
            return []
        
        if output_dir:
            img_dir = Path(output_dir) / "images"
        else:
            img_dir = Path(tempfile.mkdtemp()) / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        
        downloaded = []
        for rel_path, url in images_info.items():
            try:
                response = requests.get(url, timeout=60)
                if response.status_code == 200:
                    img_path = img_dir / Path(rel_path).name
                    img_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(img_path, "wb") as f:
                        f.write(response.content)
                    downloaded.append(str(img_path))
            except Exception as e:
                logger.warning(f"下载图片失败 {rel_path}: {e}")
        
        logger.info(f"已下载 {len(downloaded)}/{len(images_info)} 张图片")
        return downloaded


def parse_pdf(pdf_path: str, api_key: Optional[str] = None, **kwargs) -> ParseResult:
    """
    便捷函数：使用PDF2X API解析PDF
    
    Args:
        pdf_path: PDF文件路径
        api_key: 可选的API密钥，默认从环境变量读取
        
    Returns:
        ParseResult: 解析结果
    """
    parser = PDF2XParser(api_key=api_key, **kwargs)
    return parser.parse(pdf_path)
