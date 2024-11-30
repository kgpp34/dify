# -*- coding: UTF-8 -*-
"""
@Project : api
@File    : http_proxy.py
@Author  : yanglh
@Data    : 2024/11/27 10:47
"""

import requests
from typing import Dict, Union, Optional


class HttpProxy:
    """
    A simple HTTP client for making GET, POST, PUT, PATCH, and DELETE requests.
    """

    def __init__(self, base_url: str, headers: Optional[Dict[str, str]] = None):
        """
        Initialize the HttpClient with a base URL and optional headers.

        :param base_url: The base URL for the API.
        :param headers: Optional headers to include in all requests.
        """
        self.base_url = base_url
        self.headers = headers or {}

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> \
            Union[Dict, str]:
        """
        Make an HTTP request to the specified endpoint.

        :param method: The HTTP method (GET, POST, PUT, PATCH, DELETE).
        :param endpoint: The API endpoint to request.
        :param data: Optional data to send in the request body (for POST, PUT, PATCH).
        :param params: Optional query parameters to include in the request.
        :return: The response data as a dictionary or string.
        """
        url = f"{self.base_url}{endpoint}"
        response = requests.request(method, url, json=data, params=params, headers=self.headers)

        # Raise an exception for HTTP errors
        response.raise_for_status()

        # Return the response data
        return response.json() if response.headers.get('Content-Type') == 'application/json' else response.text

    def get(self, endpoint: str, params: Optional[Dict] = None) -> Union[Dict, str]:
        """
        Send a GET request to the specified endpoint.

        :param endpoint: The API endpoint to request.
        :param params: Optional query parameters to include in the request.
        :return: The response data as a dictionary or string.
        """
        return self._make_request('GET', endpoint, params=params)

    def post(self, endpoint: str, data: Optional[Dict] = None) -> Union[Dict, str]:
        """
        Send a POST request to the specified endpoint.

        :param endpoint: The API endpoint to request.
        :param data: Optional data to send in the request body.
        :return: The response data as a dictionary or string.
        """
        return self._make_request('POST', endpoint, data=data)