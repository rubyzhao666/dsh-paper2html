"""
Doc2X API解析器
封装pdfdeal SDK调用或手动requests调用
"""

import os
import time
import zipfile
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

from .models import ParseResult


class Doc2XParser:
    """
    Doc2X API解析器
    
    支持两种调用方式：
    1. pdfdeal SDK（优先）：使用 pdfdeal 库封装调用
    2. 手动requests：直接调用Doc2X REST API
    
    API Key通过环境变量 DOC2X_APIKEY 获取
    """
    
    BASE_URL = "https://v2.doc2x.noedgeai.com"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "v3-2026",  # v2 或 v3-2026
        max_retries: int = 3,
        retry_delay: float = 1.0,
        use_sdk: bool = True,
    ):
        """
        初始化解析器
        
        Args:
            api_key: Doc2X API密钥，默认从环境变量 DOC2X_APIKEY 读取
            model: 解析模型，"v2" 或 "v3-2026"
            max_retries: 最大重试次数
            retry_delay: 初始重试延迟（秒），会指数退避
            use_sdk: 是否优先使用pdfdeal SDK
        """
        self.api_key = api_key or os.environ.get("DOC2X_APIKEY", "")
        if not self.api_key:
            logger.warning("DOC2X_APIKEY 环境变量未设置，请从 https://pdf2x.cn/api/apikey 获取")
        
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.use_sdk = use_sdk
        self._sdk_client = None
    
    def _get_sdk_client(self):
        """懒加载pdfdeal SDK客户端"""
        if self._sdk_client is None:
            try:
                from pdfdeal import Doc2X
                self._sdk_client = Doc2X(apikey=self.api_key, debug=False)
                logger.info("已初始化 pdfdeal SDK 客户端")
            except ImportError:
                raise ImportError(
                    "pdfdeal 未安装。请运行: pip install pdfdeal\n"
                    "或从 https://pdf2x.cn/api/apikey 获取API密钥后使用手动调用模式"
                )
        return self._sdk_client
    
    def parse(self, pdf_path: str, output_dir: Optional[str] = None) -> ParseResult:
        """
        解析PDF文件
        
        Args:
            pdf_path: PDF文件路径
            output_dir: 输出目录，默认在PDF同目录下创建 output_paper2html
        
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
            output_dir = pdf_path.parent / "output_paper2html"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 优先尝试SDK模式
        if self.use_sdk and self.api_key:
            return self._parse_with_sdk(str(pdf_path), str(output_dir))
        else:
            return self._parse_with_requests(str(pdf_path), str(output_dir))
    
    def _parse_with_sdk(self, pdf_path: str, output_dir: str) -> ParseResult:
        """使用pdfdeal SDK解析"""
        logger.info(f"使用pdfdeal SDK解析: {pdf_path}")
        
        for attempt in range(self.max_retries):
            try:
                client = self._get_sdk_client()
                
                # 调用SDK的pdf2file方法
                # 注意：pdfdeal SDK的pdf2file不支持model参数
                # 如需指定模型(v2/v3)，需使用手动requests调用模式
                success, failed, flag = client.pdf2file(
                    pdf_file=pdf_path,
                    output_path=output_dir,
                    output_format="md_dollar",  # Markdown with $...$ formulas
                )
                
                # success是成功文件列表，failed是失败信息
                # 空列表也算失败
                if success and len(success) > 0:
                    logger.info(f"解析成功，输出目录: {output_dir}")
                    return self._process_output(output_dir, pdf_path)
                else:
                    # 构造错误信息
                    error_parts = []
                    if failed:
                        error_parts.append(str(failed))
                    if not success:
                        error_parts.append("SDK返回空结果（可能额度不足或解析失败）")
                    error_msg = "; ".join(error_parts) if error_parts else "SDK解析返回未知错误"
                    logger.warning(error_msg)
                    # 额度不足类错误不需要重试
                    if "quota" in error_msg.lower() or "额度" in error_msg:
                        return ParseResult(
                            source_file=pdf_path,
                            success=False,
                            error_message=error_msg
                        )
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))
                        continue
                    return ParseResult(
                        source_file=pdf_path,
                        success=False,
                        error_message=error_msg
                    )
                    
            except ImportError as e:
                logger.warning(f"pdfdeal SDK不可用: {e}，切换到手动API调用模式")
                self.use_sdk = False
                return self._parse_with_requests(pdf_path, output_dir)
            except Exception as e:
                logger.error(f"SDK解析异常 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                return ParseResult(
                    source_file=pdf_path,
                    success=False,
                    error_message=f"SDK解析失败: {str(e)}"
                )
        
        return ParseResult(
            source_file=pdf_path,
            success=False,
            error_message="达到最大重试次数"
        )
    
    def _parse_with_requests(self, pdf_path: str, output_dir: str) -> ParseResult:
        """使用手动requests调用Doc2X API"""
        import requests
        
        logger.info(f"使用手动API调用解析: {pdf_path}")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        
        for attempt in range(self.max_retries):
            try:
                # Step 1: 获取上传URL
                with open(pdf_path, "rb") as f:
                    file_size = len(f.read())
                
                preupload_url = f"{self.BASE_URL}/api/v2/parse/preupload"
                resp = requests.post(
                    preupload_url,
                    headers=headers,
                    json={"name": Path(pdf_path).name},
                    timeout=30
                )
                
                if resp.status_code != 200:
                    return ParseResult(
                        source_file=pdf_path,
                        success=False,
                        error_message=f"预上传失败: HTTP {resp.status_code} - {resp.text}"
                    )
                
                upload_data = resp.json()
                upload_url = upload_data.get("url")
                uid = upload_data.get("uid")
                
                if not upload_url or not uid:
                    return ParseResult(
                        source_file=pdf_path,
                        success=False,
                        error_message=f"获取上传URL失败: {upload_data}"
                    )
                
                # Step 2: 上传PDF文件
                with open(pdf_path, "rb") as f:
                    upload_resp = requests.put(
                        upload_url,
                        data=f,
                        headers={"Content-Type": "application/pdf"},
                        timeout=120
                    )
                
                if upload_resp.status_code not in (200, 201):
                    return ParseResult(
                        source_file=pdf_path,
                        success=False,
                        error_message=f"文件上传失败: HTTP {upload_resp.status_code}"
                    )
                
                # Step 3: 轮询解析状态
                status_url = f"{self.BASE_URL}/api/v2/parse/status"
                max_wait = 300  # 最多等待5分钟
                start_time = time.time()
                poll_interval = 2
                
                while time.time() - start_time < max_wait:
                    status_resp = requests.get(
                        status_url,
                        headers=headers,
                        params={"uid": uid},
                        timeout=30
                    )
                    
                    if status_resp.status_code == 200:
                        status_data = status_resp.json()
                        status = status_data.get("status", "")
                        
                        if status == "success" or status == "done":
                            break
                        elif status == "error":
                            return ParseResult(
                                source_file=pdf_path,
                                success=False,
                                error_message=f"解析状态错误: {status_data.get('error', 'Unknown')}"
                            )
                    
                    time.sleep(poll_interval)
                    poll_interval = min(poll_interval * 1.5, 10)  # 指数退避，最大10秒
                
                # Step 4: 提交格式转换
                convert_url = f"{self.BASE_URL}/api/v2/convert/parse"
                convert_resp = requests.post(
                    convert_url,
                    headers=headers,
                    json={
                        "uid": uid,
                        "to": "md",
                        "formula_mode": "dollar"  # $...$ 格式
                    },
                    timeout=30
                )
                
                if convert_resp.status_code != 200:
                    return ParseResult(
                        source_file=pdf_path,
                        success=False,
                        error_message=f"提交转换失败: HTTP {convert_resp.status_code} - {convert_resp.text}"
                    )
                
                convert_data = convert_resp.json()
                convert_uid = convert_data.get("uid")
                
                # Step 5: 获取转换结果
                time.sleep(3)  # 等待转换完成
                
                result_url = f"{self.BASE_URL}/api/v2/convert/parse/result"
                for _ in range(30):  # 最多等待60秒
                    result_resp = requests.get(
                        result_url,
                        headers=headers,
                        params={"uid": convert_uid},
                        timeout=30
                    )
                    
                    if result_resp.status_code == 200:
                        result_data = result_resp.json()
                        download_url = result_data.get("url")
                        
                        if download_url:
                            break
                    
                    time.sleep(2)
                
                if not download_url:
                    return ParseResult(
                        source_file=pdf_path,
                        success=False,
                        error_message="获取下载链接超时"
                    )
                
                # Step 6: 下载并解压结果
                zip_path = Path(output_dir) / "result.zip"
                download_resp = requests.get(download_url, timeout=120)
                
                with open(zip_path, "wb") as f:
                    f.write(download_resp.content)
                
                # 解压
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(output_dir)
                
                # 删除zip
                zip_path.unlink()
                
                logger.info(f"手动API解析成功，输出目录: {output_dir}")
                return self._process_output(output_dir, pdf_path)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"API请求异常 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                return ParseResult(
                    source_file=pdf_path,
                    success=False,
                    error_message=f"API请求失败: {str(e)}"
                )
            except Exception as e:
                logger.error(f"解析异常 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                return ParseResult(
                    source_file=pdf_path,
                    success=False,
                    error_message=f"解析异常: {str(e)}"
                )
        
        return ParseResult(
            source_file=pdf_path,
            success=False,
            error_message="达到最大重试次数"
        )
    
    def _process_output(self, output_dir: str, source_file: str) -> ParseResult:
        """处理解析输出目录，提取Markdown、图片等"""
        output_path = Path(output_dir)
        images = []
        markdown = ""
        json_data = {}
        metadata = {}
        
        # 先检查是否有未解压的zip文件（SDK模式下载的格式）
        zip_files = list(output_path.glob("*.zip"))
        for zf in zip_files:
            try:
                logger.info(f"解压SDK输出: {zf}")
                with zipfile.ZipFile(zf, "r") as z:
                    z.extractall(output_path)
                # 解压后删除zip
                zf.unlink()
                logger.info(f"解压完成，已删除zip: {zf}")
            except Exception as e:
                logger.warning(f"解压失败: {zf} - {e}")
        
        # 查找Markdown文件
        md_files = list(output_path.glob("*.md")) + list(output_path.glob("*.markdown"))
        # 也搜索子目录
        if not md_files:
            md_files = list(output_path.rglob("*.md")) + list(output_path.rglob("*.markdown"))
        if md_files:
            # 优先选择主文件（可能命名为原文件名或output）
            main_md = None
            for mf in md_files:
                if mf.stem == output_path.name or mf.stem == "output":
                    main_md = mf
                    break
            
            if main_md is None:
                main_md = md_files[0]
            
            with open(main_md, "r", encoding="utf-8") as f:
                markdown = f.read()
        
        # 查找JSON文件
        json_files = list(output_path.glob("*.json"))
        if json_files:
            try:
                with open(json_files[0], "r", encoding="utf-8") as f:
                    json_data = json.loads(f.read())
                
                # 尝试提取元数据
                if isinstance(json_data, dict):
                    metadata = {
                        "title": json_data.get("title", ""),
                        "authors": json_data.get("authors", []),
                        "abstract": json_data.get("abstract", ""),
                        "sections": list(json_data.get("sections", {}).keys()),
                    }
            except Exception as e:
                logger.warning(f"解析JSON元数据失败: {e}")
        
        # 查找图片（递归搜索所有子目录）
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", "*.webp"]:
            images.extend([str(p) for p in output_path.rglob(ext)])
        
        # 获取页数信息（如果可能）
        try:
            import PyPDF2
            with open(source_file, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                metadata["page_count"] = len(reader.pages)
        except Exception:
            pass
        
        metadata["output_dir"] = str(output_path)
        metadata["files"] = [str(p) for p in output_path.rglob("*") if p.is_file()]
        
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
def parse_pdf(pdf_path: str, api_key: Optional[str] = None, **kwargs) -> ParseResult:
    """
    便捷函数：解析PDF文件
    
    Args:
        pdf_path: PDF文件路径
        api_key: 可选的API密钥，默认从环境变量读取
        **kwargs: 传递给Doc2XParser的其他参数
    
    Returns:
        ParseResult: 解析结果
    """
    parser = Doc2XParser(api_key=api_key, **kwargs)
    return parser.parse(pdf_path)


if __name__ == "__main__":
    # 测试代码
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    if len(sys.argv) < 2:
        print("用法: python doc2x_parser.py <pdf_path> [api_key]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    api_key = sys.argv[2] if len(sys.argv) > 2 else None
    
    result = parse_pdf(pdf_path, api_key=api_key)
    
    print(f"\n解析结果:")
    print(f"  成功: {result.success}")
    print(f"  Markdown长度: {len(result.markdown)} 字符")
    print(f"  图片数量: {len(result.images)}")
    print(f"  输出目录: {result.raw_output_dir}")
    
    if result.error_message:
        print(f"  错误: {result.error_message}")
