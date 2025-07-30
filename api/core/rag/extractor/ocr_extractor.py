import datetime
import io
import logging
import mimetypes
import os
import re
import uuid
from typing import Any, Optional, cast

import pdfplumber
from openai import OpenAI
from PIL import Image

from configs import dify_config
from core.rag.extractor.blob.blob import Blob
from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document
from extensions.ext_database import db
from extensions.ext_storage import storage
from libs.http_client import HttpClient
from models import UploadFile
from models.enums import CreatedByRole

logger = logging.getLogger(__name__)


def _remove_html_label(content):
    """
    去掉字符串中HTML标签及其内容

    Args:
        content: 包含HTML标签的字符串

    Returns:
        str: 去除HTML标签后的字符串
    """
    if not content:
        return content

    # 使用正则表达式去除HTML标签及其内容
    # 匹配 <标签名...>内容</标签名> 的模式
    cleaned_content = re.sub(r"<[^>]+>.*?</[^>]+>", "", content, flags=re.DOTALL)

    # 去除单独的开始或结束标签（如果有的话）
    cleaned_content = re.sub(r"<[^>]+>", "", cleaned_content)

    return cleaned_content


def html_2_markdown_table(html_table):
    rows = re.findall(r"<tr>(.*?)</tr>", html_table, re.DOTALL)
    markdown_rows = []

    for row in rows:
        cells = re.findall(r"<th|td>(.*?)</\1>", row, re.DOTALL)
        cell_contents = [cell[1].strip() for cell in cells]
        markdown_row = "| " + " | ".join(cell_contents) + " | "
        markdown_rows.append(markdown_row)

    if markdown_rows:
        header_separator = "| " + " | ".join(["---"] * len(cells)) + " |"
        markdown_rows.insert(1, header_separator)
    return "\n".join(markdown_rows)


def process_markdown_file(content):
    html_tables = re.findall(r"<table.*?>(.*?)</table>", content, re.DOTALL)

    for html_table in html_tables:
        markdown_table = html_2_markdown_table(html_table)
        content = re.sub(r"<table.*?>.*?</table>", markdown_table, content, flags=re.DOTALL)
    return content


def _find_table_title(
    page: Any, table_bbox: tuple[float, float, float, float], max_distance: int = 50
) -> tuple[str | None, tuple[float, float, float, float]]:
    """
    在表格上方查找可能的标题

    Args:
        page: pdfplumber页面对象
        table_bbox: 表格边界框 (x0, top, x1, bottom)
        max_distance: 标题与表格的最大距离(像素)

    Returns:
        tuple: (标题文本, 扩展后的边界框) 或 (None, 原边界框)
    """
    x0, top, x1, bottom = table_bbox

    # 在表格上方查找文本
    title_area = (x0 - 20, max(0, top - max_distance), x1 + 20, top)

    try:
        # 获取该区域内的文本
        title_texts: list[dict[str, Any]] = []
        words = page.within_bbox(title_area).extract_words()

        for text_obj in words:
            # 处理不同的词典结构
            if "bbox" in text_obj:
                text_bbox = text_obj["bbox"]
            elif "x0" in text_obj:
                # 有些版本使用 x0, top, x1, bottom 字段
                text_bbox = (text_obj["x0"], text_obj["top"], text_obj["x1"], text_obj["bottom"])
            else:
                # 跳过无法获取边界框的文本
                continue

            text_x0, text_top, text_x1, text_bottom = text_bbox

            # 检查文本是否在表格水平范围内或附近
            if text_x0 < x1 + 15 and text_x1 > x0 - 15:  # 水平重叠或接近
                title_texts.append(
                    {
                        "text": text_obj["text"],
                        "bbox": text_bbox,
                        "distance": top - text_bottom,  # 与表格的距离
                    }
                )

        if not title_texts:
            return None, table_bbox

        # 按距离排序，选择最近的文本作为标题
        title_texts.sort(key=lambda x: x["distance"])

        # 组合可能的标题文本（距离相近的文本）
        title_parts: list[dict[str, Any]] = []
        min_distance = title_texts[0]["distance"]

        for text_info in title_texts:
            if text_info["distance"] <= min_distance + 15:  # 容忍小的距离差异
                title_parts.append(text_info)

        if title_parts:
            # 按水平位置排序
            title_parts.sort(key=lambda x: x["bbox"][0])
            title_text = " ".join([part["text"] for part in title_parts])

            # 计算包含标题的扩展边界框
            title_top = min([part["bbox"][1] for part in title_parts])
            extended_bbox = (x0, title_top - 5, x1, bottom)  # 上方留5像素边距

            return title_text, extended_bbox

    except Exception as e:
        # 如果标题检测失败，返回原始边界框
        print(f"标题检测失败: {e}")
        return None, table_bbox

    return None, table_bbox


def _expand_table_bbox_with_title(
    page: Any, table: Any, padding: int = 25
) -> tuple[str | None, tuple[float, float, float, float]]:
    """
    扩展表格边界框以包含标题

    Args:
        page: pdfplumber页面对象
        table: 表格对象
        padding: 边距像素

    Returns:
        tuple: (标题文本, 扩展后的边界框)
    """
    original_bbox = table.bbox
    title_text, extended_bbox = _find_table_title(page, original_bbox)

    # 添加左右边距
    x0, top, x1, bottom = extended_bbox
    final_bbox = (
        max(0, x0 - padding),
        max(0, top - padding),
        min(page.width, x1 + padding),
        min(page.height, bottom + padding),
    )

    return title_text, final_bbox


def _are_tables_connected(prev_table: Any, curr_table: Any, prev_page: Any, threshold: float = 0.1) -> bool:
    """
    判断两个表格是否是同一个表格被分页分割

    Args:
        prev_table: 前一页的表格对象
        curr_table: 当前页的表格对象
        prev_page: 前一页对象
        threshold: 水平位置差异阈值(相对于页面宽度)

    Returns:
        bool: 是否为连续表格
    """
    # 获取表格边界框
    prev_bbox = prev_table.bbox
    curr_bbox = curr_table.bbox

    # 检查水平对齐 - 左边界差异小于阈值
    page_width = prev_page.width
    left_diff = abs(prev_bbox[0] - curr_bbox[0]) / page_width

    if left_diff > threshold:
        return False

    # 检查表格宽度相似性
    prev_width = prev_bbox[2] - prev_bbox[0]
    curr_width = curr_bbox[2] - curr_bbox[0]
    width_diff = abs(prev_width - curr_width) / max(prev_width, curr_width)

    if width_diff > threshold:
        return False

    # 检查列结构相似性
    prev_cells = prev_table.cells
    curr_cells = curr_table.cells

    if not prev_cells or not curr_cells:
        return False

    # 比较列数
    prev_cols = {cell[0] for cell in prev_cells}  # x坐标去重得到列数
    curr_cols = {cell[0] for cell in curr_cells}

    if abs(len(prev_cols) - len(curr_cols)) > 1:  # 允许1列的差异
        return False

    return True


def _merge_table_images(img1: Any, img2: Any, overlap_height: int = 0) -> Image.Image:
    """
    合并两个表格图片

    Args:
        img1: PIL Image对象 或 pdfplumber的PageImage对象
        img2: pdfplumber的PageImage对象
        overlap_height: 重叠部分高度(像素)

    Returns:
        PIL.Image: 合并后的图片
    """
    # 转换为PIL Image对象
    if hasattr(img1, "original"):
        pil_img1 = img1.original
    else:
        pil_img1 = img1

    if hasattr(img2, "original"):
        pil_img2 = img2.original
    else:
        pil_img2 = img2

    # 确保两个图片宽度一致
    width = max(pil_img1.width, pil_img2.width)

    if pil_img1.width != width:
        pil_img1 = pil_img1.resize((width, pil_img1.height))
    if pil_img2.width != width:
        pil_img2 = pil_img2.resize((width, pil_img2.height))

    # 创建合并后的图片
    total_height = pil_img1.height + pil_img2.height - overlap_height
    merged_img = Image.new("RGB", (width, total_height), "white")

    # 粘贴图片
    merged_img.paste(pil_img1, (0, 0))
    merged_img.paste(pil_img2, (0, pil_img1.height - overlap_height))

    return merged_img


def _append_table_label(table_file_path: str, table_desc: str) -> str:
    """
    在表格描述的markdown列表项行尾添加图片链接

    Args:
        table_file_path: 表格文件路径
        table_desc: markdown格式的表格描述

    Returns:
        str: 处理后的表格描述
    """
    if not table_desc or not table_file_path:
        return table_desc

    lines = table_desc.split("\n")
    processed_lines = []

    for line in lines:
        # 检查是否是以 > 开头的markdown列表项
        stripped_line = line.strip()
        if stripped_line.startswith("> "):
            # 在行尾将表格图片用markdown格式追加到内容中
            processed_line = line + f"![](http://dify.cffex.net/dify-images/{table_file_path})"
            processed_lines.append(processed_line)
        else:
            processed_lines.append(line)

    return "\n".join(processed_lines)


class OcrExtractor(BaseExtractor):
    """OCR extractor for extracting text from images and PDFs."""

    def __init__(
        self,
        file_path: str,
        file_cache_key: str | None = None,
        upload_file_key: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ):
        """Initialize with file path."""
        self._file_path = file_path
        self._file_cache_key = file_cache_key
        self._tenant_id = tenant_id or ""
        self._user_id = user_id or ""
        self._upload_file_key = upload_file_key or ""
        # construct a ocr model client by http client
        self._ocr_client = HttpClient(
            base_url=dify_config.LAB_SERVICE_BASE_URL or "",
            timeout=dify_config.LAB_OCR_MODEL_CONN_TIMEOUT or 600,
        )
        # llm_client invoke llm to summarize MarkdownTable
        self._llm_client = OpenAI(
            base_url=dify_config.LAB_OCR_DEFAULT_LLM_BASE_URL, api_key=dify_config.LAB_SERVICE_DEFAULT_TOKEN
        )

    def extract(self) -> list[Document]:
        # 1. check whether file have loaded
        if self._file_cache_key:
            try:
                text = cast(bytes, storage.load(self._file_cache_key, stream=False)).decode("utf-8")
                return [Document(page_content=text)]
            except FileNotFoundError:
                pass

        # 2. load file
        if not os.path.exists(self._file_path):
            raise FileNotFoundError(f"File not found: {self._file_path}")

        uploaded_files: list[UploadFile] = []  # 跟踪所有上传的文件记录
        try:
            # 3. extract table and pic (pdf or word) and use storage.save to persistence and get pic persistence path
            with Blob.from_path(self._file_path).as_bytes_io() as bytes_io:
                raw_bytes = bytes_io.read()
            logger.info(f"加载pdf文件: {self._file_path} 成功")

            table_image_paths, tables_image_bytes = self._extract_tables_with_merge(raw_bytes, uploaded_files)
            logger.info(f"抽取pdf文件: {self._file_path}中的表格内容成功，共抽取表格图片: {len(table_image_paths)}个")

            # 4. fetch ocr model to parse table and file content
            logger.info(f"通过OCR解析文件: {self._file_path}内容")
            file_md_content = _remove_html_label(self._call_ocr_service(mime_type="application/pdf"))
            logger.info(f"通过OCR解析文件: {self._file_path}内容流程完成")

            ocr_table_results = []
            for index, table_bytes in enumerate(tables_image_bytes):
                ocr_table_results.append(
                    process_markdown_file(self._call_ocr_service(file_content=table_bytes, mime_type="image/png"))
                )
                logger.info(f"通过OCR解析: {self._file_path}文件中的第{index}表格图片流程完成")

            # 5. extract Markdown table and ask llm to demonstrate
            # (This step would involve LLM processing, which might be implemented later)
            llm_table_descriptions = []
            for table_path_index, ocr_table in enumerate(ocr_table_results):
                llm_table_descriptions.append(
                    _append_table_label(
                        table_image_paths[table_path_index], _remove_html_label(self._invoke_llm(content=ocr_table))
                    )
                )

            # 将表格描述追加到文件内容中
            if llm_table_descriptions:
                # 添加表格详细内容标题
                file_md_content += "\n\n## 文件表格详细内容\n\n"
                # 将所有表格描述追加到文件内容中
                file_md_content += "\n\n".join(llm_table_descriptions)

            # save plaintext file for caching
            if self._file_cache_key:
                storage.save(self._file_cache_key, file_md_content.encode("utf-8"))

            logger.info(f"文件：{self._file_path}解析已完成, 内容为：{file_md_content}\n\n")

            return [Document(page_content=file_md_content)]

        except Exception as e:
            # 异常时清理所有上传的图片和数据库记录
            self._cleanup_uploaded_files(uploaded_files=uploaded_files)
            raise RuntimeError(f"OCR extraction failed: {str(e)}")

    def _call_ocr_service(self, file_content: Optional[bytes] = None, mime_type: str = "application/pdf") -> str:
        """Call the OCR service to parse the file content."""
        try:
            # 如果没有提供文件内容，从文件路径读取
            if file_content is None:
                if not hasattr(self, "_file_path") or not self._file_path:
                    raise ValueError("Neither file_content nor _file_path is available")

                with open(self._file_path, "rb") as f:
                    file_content = f.read()

            # 准备OCR服务请求
            suffix = "png" if mime_type == "image/png" else "pdf"
            files = {"files": (f"document.{suffix}", file_content, mime_type)}

            data = {
                "is_json_md_dump": "false",
                "return_middle_json": "false",
                "return_model_output": "false",
                "return_md": "true",
                "return_images": "false",
                "end_page_id": "99999",
                "parse_method": "auto",
                "start_page_id": "0",
                "lang_list": "ch",
                "output_dir": "./output",
                "server_url": "string",
                "return_content_list": "false",
                "backend": "vlm-transformers",
                "table_enable": "true",
                "formula_enable": "true",
            }

            # 设置请求头
            headers = {}
            if dify_config.LAB_OCR_SERVICE_ACTION:
                headers["X-TC-Action"] = dify_config.LAB_OCR_SERVICE_ACTION
            if dify_config.LAB_OCR_MODEL_NAME:
                headers["X-TC-Service"] = dify_config.LAB_OCR_MODEL_NAME
            if dify_config.LAB_OCR_MODEL_VERSION:
                headers["X-TC-Version"] = dify_config.LAB_OCR_MODEL_VERSION

            # 确保URL不为None
            url = dify_config.LAB_SERVICE_BASE_URL
            if not url:
                raise ValueError("LAB_SERVICE_BASE_URL is not configured")

            # 使用上下文管理器确保连接被正确关闭
            import requests

            with requests.post(
                url=url,
                data=data,
                files=files,
                headers=headers,
                timeout=dify_config.LAB_OCR_MODEL_CONN_TIMEOUT or 600,
            ) as response:
                # 确保请求成功
                response.raise_for_status()

                # 解析响应
                response_data = response.json()

                if response_data and response_data.get("results"):
                    # 解析OCR返回的数据结构
                    results = response_data.get("results", {})
                    md_contents = []

                    # 遍历results中的所有页面，提取md_content
                    for _, page_data in results.items():
                        if isinstance(page_data, dict) and "md_content" in page_data:
                            md_content = page_data["md_content"]
                            if md_content:
                                md_contents.append(md_content)

                    # 将所有页面的md_content合并
                    if md_contents:
                        return "\n\n".join(md_contents)
                    else:
                        logger.warning("OCR模型响应中未找到md_content")
                        return ""

                return ""

        except Exception as e:
            raise RuntimeError(f"OCR service call failed: {str(e)}")

    def _save_image_to_storage(
        self, image_data: bytes, image_ext: str = "png", uploaded_files: Optional[list[UploadFile]] = None
    ) -> str:
        """Save image to storage and return the file key."""
        try:
            file_uuid = str(uuid.uuid4())
            file_key = f"image_files/{self._tenant_id}/{file_uuid}.{image_ext}"
            mime_type, _ = mimetypes.guess_type(file_key)

            # Save to storage
            storage.save(file_key, image_data)

            # Save file record to database
            upload_file = None
            if self._tenant_id and self._user_id:
                upload_file = UploadFile(
                    tenant_id=self._tenant_id,
                    storage_type=dify_config.STORAGE_TYPE,
                    key=file_key,
                    name=file_key,
                    size=len(image_data),
                    extension=image_ext,
                    mime_type=mime_type or "",
                    created_by=self._user_id,
                    created_by_role=CreatedByRole.ACCOUNT,
                    created_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
                    used=True,
                    used_by=self._user_id,
                    used_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
                )

                db.session.add(upload_file)
                db.session.commit()

            # 跟踪上传的文件记录
            if uploaded_files is not None and upload_file:
                uploaded_files.append(upload_file)

            return f"/{self._tenant_id}/{file_uuid}.{image_ext}"

        except Exception as e:
            raise RuntimeError(f"Failed to save image to storage: {str(e)}")

    def _cleanup_uploaded_files(self, uploaded_files: list[UploadFile]) -> None:
        """清理上传的文件和数据库记录"""

        # 策略：先确保数据库操作成功，再删除文件
        # 这样可以避免文件已删除但数据库记录仍存在的不一致状态

        try:
            # 第一步：删除数据库记录
            logger.info("开始删除数据库记录...")
            for upload_file in uploaded_files:
                db.session.delete(upload_file)
                logger.debug(f"标记删除数据库记录: {upload_file.key}")

            # 提交数据库更改
            db.session.commit()
            logger.info(f"成功删除 {len(uploaded_files)} 条数据库记录")

        except Exception as e:
            logger.exception("删除数据库记录失败")
            try:
                db.session.rollback()
                logger.info("数据库事务已回滚")
            except Exception as rollback_error:
                logger.exception("数据库回滚失败")

            # 数据库操作失败时，不执行文件删除
            raise RuntimeError(f"数据库清理失败，已回滚事务: {str(e)}")

        # 第二步：数据库操作成功后，删除存储中的文件
        try:
            logger.info("开始删除存储文件...")
            for upload_file in uploaded_files:
                try:
                    if upload_file and upload_file.key:
                        # 从路径中提取文件key
                        storage.delete(upload_file.key)
                        logger.info(f"已删除图片文件: {upload_file.key}")
                except Exception as e:
                    logger.warning(f"删除图片文件失败: {upload_file.key}: {str(e)}")

        except Exception as e:
            logger.exception("删除存储文件时发生错误")

        logger.info("文件清理操作完成")

    def _invoke_llm(self, content: str) -> str:
        """
        使用LLM分析和描述文档内容，特别是表格数据，以便于RAG检索

        Args:
            content: OCR提取的原始内容

        Returns:
            str: LLM处理后的结构化描述内容
        """
        messages = [
            {
                "role": "system",
                "content": dify_config.LAB_MARKDOWN_TABLE_SYSTEM_PROMPT,
            },
            {"role": "user", "content": f"请分析以下文档内容，特别关注其中的表格数据：\n\n{content}"},
        ]

        try:
            model_name = dify_config.LAB_OCR_DEFAULT_LLM_MODEL
            if not model_name:
                logger.warning("LLM模型名称未配置，使用原始内容")
                return content

            llm_response = self._llm_client.chat.completions.create(
                model=model_name,
                messages=messages,  # type: ignore
                temperature=0.1,  # 降低温度以获得更一致的结果
                max_tokens=2000,  # 增加token限制以获得更详细的描述
            )

            if llm_response and llm_response.choices and len(llm_response.choices) > 0:
                choice = llm_response.choices[0]
                if choice.message and choice.message.content:
                    processed_content = choice.message.content

                    # 如果LLM处理成功，返回处理后的内容
                    if processed_content and len(processed_content.strip()) > 0:
                        return processed_content
                    else:
                        logger.warning("LLM返回空内容，使用原始内容")
                        return content
                else:
                    logger.warning("LLM响应消息为空，使用原始内容")
                    return content
            else:
                logger.warning("LLM响应为空，使用原始内容")
                return content

        except Exception:
            logger.exception("调用LLM描述文档内容失败")
            # 如果LLM调用失败，返回原始内容而不是空字符串
            return content

    def _extract_tables_with_merge(
        self, file_bytes: bytes, uploaded_files: Optional[list[UploadFile]] = None
    ) -> tuple[list[str], list[bytes]]:
        """
        提取PDF中的表格，自动合并跨页分割的表格（支持多页连续表格，包含标题）

        Args:
            file_bytes: PDF文件的字节数据
            uploaded_files: 用于跟踪上传的文件记录

        Returns:
            list[str]: 保存的表格图片的存储路径列表
        """
        continuous_table: dict[str, Any] | None = None  # 当前连续表格的信息
        table_counter = 1
        saved_image_paths: list[str] = []
        saved_image_bytes: list[bytes] = []

        # 使用 io.BytesIO 将 bytes 转换为文件对象
        pdf_file = io.BytesIO(file_bytes)

        with pdfplumber.open(pdf_file) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                tables = page.find_tables()

                for table_idx, table in enumerate(tables):
                    # 查找标题并扩展边界框
                    title_text, extended_bbox = _expand_table_bbox_with_title(page, table)

                    current_table_info = {
                        "page_num": page_num,
                        "table_idx": table_idx,
                        "table": table,
                        "page": page,
                        "bbox": extended_bbox,  # 使用扩展后的边界框
                        "original_bbox": table.bbox,  # 保留原始边界框用于表格结构比较
                        "title": title_text,
                    }

                    # 检查是否需要与当前连续表格合并
                    should_merge = False
                    if continuous_table and page_num == continuous_table["end_page"] + 1:
                        # 只检查相邻页面的第一个表格
                        if table_idx == 0:
                            # 与连续表格的最后一部分比较（使用原始边界框比较结构）
                            last_part = continuous_table["parts"][-1]
                            should_merge = _are_tables_connected(last_part["table"], table, last_part["page"])

                    if should_merge:
                        # 添加到连续表格中
                        if continuous_table and "parts" in continuous_table:
                            continuous_table["parts"].append(current_table_info)
                            continuous_table["end_page"] = page_num
                        title_info = f" (标题: {title_text})" if title_text else ""
                        logger.info(f"检测到连续表格，添加第{page_num}页表格{table_idx + 1}{title_info}")

                    else:
                        # 如果有连续表格但不需要合并，保存它
                        if continuous_table:
                            image_path, image_bytes = self._save_continuous_table(continuous_table, uploaded_files)
                            if image_path and image_bytes is not None:
                                saved_image_paths.append(image_path)
                                saved_image_bytes.append(image_bytes)
                            table_counter += 1

                        # 开始新的连续表格
                        continuous_table = {"parts": [current_table_info], "start_page": page_num, "end_page": page_num}

            # 处理最后一个连续表格
            if continuous_table:
                image_path, image_bytes = self._save_continuous_table(continuous_table, uploaded_files)
                if image_path and image_bytes is not None:
                    saved_image_paths.append(image_path)
                    saved_image_bytes.append(image_bytes)

        return saved_image_paths, saved_image_bytes

    def _save_continuous_table(
        self, continuous_table: dict[str, Any], uploaded_files: Optional[list[UploadFile]] = None
    ) -> tuple[Optional[str], Optional[bytes]]:
        """
        保存连续表格（可能包含多个部分），包含标题信息

        Args:
            continuous_table: 连续表格信息
            uploaded_files: 用于跟踪上传的文件记录

        Returns:
            Optional[str]: 保存的图片存储路径，如果保存失败则返回None
        """
        parts = continuous_table["parts"]

        # 收集所有标题信息
        titles = [part["title"] for part in parts if part["title"]]
        title_info = f" ({titles[0]})" if titles else ""

        try:
            if len(parts) == 1:
                # 单个表格，直接保存
                part = parts[0]
                img = part["page"].crop(part["bbox"]).to_image(resolution=300)

                # 将PIL图片转换为bytes
                img_bytes_io = io.BytesIO()
                if img and hasattr(img, "save"):
                    img.save(img_bytes_io, format="PNG")
                    img_bytes = img_bytes_io.getvalue()

                    # 使用 _save_image_to_storage 保存
                    image_path = self._save_image_to_storage(img_bytes, "png", uploaded_files)
                    logger.info(f"单独表格保存: {image_path}{title_info}")
                    return image_path, img_bytes

            else:
                # 多个部分，需要合并
                logger.info(f"合并连续表格{title_info} (共{len(parts)} 部分): ")
                for i, part in enumerate(parts):
                    part_title = f" - {part['title']}" if part["title"] else ""
                    logger.info(f" - 第{part['page_num']}页表格{part['table_idx'] + 1}{part_title}")

                # 逐步合并所有部分
                merged_img: Image.Image | None = None
                for i, part in enumerate(parts):
                    part_img = part["page"].crop(part["bbox"]).to_image(resolution=300)

                    if merged_img is None:
                        if hasattr(part_img, "original"):
                            merged_img = part_img.original.copy()
                        else:
                            merged_img = part_img.copy()
                    else:
                        merged_img = _merge_table_images(merged_img, part_img)

                if merged_img:
                    # 将合并后的图片转换为bytes
                    img_bytes_io = io.BytesIO()
                    merged_img.save(img_bytes_io, format="PNG")
                    img_bytes = img_bytes_io.getvalue()

                    # 使用 _save_image_to_storage 保存
                    image_path = self._save_image_to_storage(img_bytes, "png", uploaded_files)
                    logger.info(f"连续表格保存: {image_path}")
                    return image_path, img_bytes

        except Exception:
            logger.exception("保存表格图片失败")
            return None, None

        return None, None
