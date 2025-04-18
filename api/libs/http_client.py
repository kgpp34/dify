"""通用 HTTP 客户端模块。"""

import json
import logging
from typing import Any, Optional

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class HttpClient:
    """
    通用 HTTP 客户端，提供基础的 HTTP 请求功能。
    """

    def __init__(self, base_url: str = "", timeout: int = 30, headers: Optional[dict[str, str]] = None):
        """
        初始化 HTTP 客户端。

        Args:
            base_url: 基础 URL，所有请求都会基于此 URL
            timeout: 请求超时时间（秒）
            headers: 默认请求头
        """
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.timeout = timeout
        self.headers = headers or {}

    def get(
        self, endpoint: str, params: Optional[dict[str, Any]] = None, headers: Optional[dict[str, str]] = None
    ) -> dict[str, Any]:
        """
        发送 GET 请求。

        Args:
            endpoint: API 端点
            params: 查询参数
            headers: 请求头，会与默认请求头合并

        Returns:
            响应数据（JSON）

        Raises:
            RuntimeError: 当请求失败时
        """
        return self._request("GET", endpoint, params=params, headers=headers)

    def post(
        self,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """
        发送 POST 请求。

        Args:
            endpoint: API 端点
            data: 表单数据
            json_data: JSON 数据
            headers: 请求头，会与默认请求头合并

        Returns:
            响应数据（JSON）

        Raises:
            RuntimeError: 当请求失败时
        """
        return self._request("POST", endpoint, data=data, json=json_data, headers=headers)

    def put(
        self,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """
        发送 PUT 请求。

        Args:
            endpoint: API 端点
            data: 表单数据
            json_data: JSON 数据
            headers: 请求头，会与默认请求头合并

        Returns:
            响应数据（JSON）

        Raises:
            RuntimeError: 当请求失败时
        """
        return self._request("PUT", endpoint, data=data, json=json_data, headers=headers)

    def delete(
        self, endpoint: str, params: Optional[dict[str, Any]] = None, headers: Optional[dict[str, str]] = None
    ) -> dict[str, Any]:
        """
        发送 DELETE 请求。

        Args:
            endpoint: API 端点
            params: 查询参数
            headers: 请求头，会与默认请求头合并

        Returns:
            响应数据（JSON）

        Raises:
            RuntimeError: 当请求失败时
        """
        return self._request("DELETE", endpoint, params=params, headers=headers)

    def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """
        发送 HTTP 请求。

        Args:
            method: HTTP 方法
            endpoint: API 端点
            **kwargs: 其他请求参数

        Returns:
            响应数据（JSON）

        Raises:
            RuntimeError: 当请求失败时
        """
        url = f"{self.base_url}{endpoint}" if self.base_url else endpoint

        # 合并请求头
        headers = kwargs.pop("headers", {})
        if self.headers:
            merged_headers = self.headers.copy()
            merged_headers.update(headers)
            headers = merged_headers

        # 设置超时
        kwargs.setdefault("timeout", self.timeout)

        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()

            # Add explicit type annotation to fix the error
            result: dict[str, Any] = response.json()
            return result
        except RequestException as e:
            logging.exception("HTTP 请求失败")
            raise RuntimeError(f"HTTP 请求失败: {str(e)}")
        except json.JSONDecodeError as e:
            logging.exception("解析 JSON 响应失败")
            raise RuntimeError(f"解析 JSON 响应失败: {str(e)}")
        except Exception as e:
            logging.exception("发送 HTTP 请求时发生未知错误")
            raise RuntimeError(f"发送 HTTP 请求时发生未知错误: {str(e)}")
