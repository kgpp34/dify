import base64
import json


def get_dept_from_token(token: str):
    parts = token.strip().split('.')
    header_b64, payload_b64, signature_b64 = parts
    payload = decode_base64url(payload_b64)
    payload_dict = json.loads(payload)
    groups = payload_dict.get("user", {}).get("groups", [])
    dept = groups[0].get("name", [])
    return dept


def decode_base64url(data):
    """Base64Url 解码并返回原始字符串"""

    rem = len(data) % 4
    if rem:
        data += '=' * (4 - rem)
    try:
        decoded_bytes = base64.urlsafe_b64decode(data)
        return decoded_bytes.decode('utf-8')
    except Exception as e:
        return f"[解码错误] 无法解码: {str(e)}"