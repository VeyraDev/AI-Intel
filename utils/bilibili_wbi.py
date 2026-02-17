"""
B站 WBI 签名工具：获取 img_key/sub_key，生成 mixin_key，计算 w_rid/w_ts。
"""
import hashlib
import time
import urllib.parse
from functools import reduce
import logging

logger = logging.getLogger("ai_intel")

# WBI mixin 密钥混淆表（64位）
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def get_wbi_keys() -> tuple[str, str] | None:
    """从 nav 接口获取 img_key 和 sub_key。"""
    try:
        import requests
    except ImportError:
        logger.warning("requests 模块未安装，无法获取 WBI keys")
        return None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com",
        }
        resp = requests.get("https://api.bilibili.com/x/web-interface/nav", headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # 即使 code != 0（如 -101 未登录），只要 data.wbi_img 存在就可以提取 keys
        wbi_img = (data.get("data") or {}).get("wbi_img") or {}
        img_url = wbi_img.get("img_url") or ""
        sub_url = wbi_img.get("sub_url") or ""
        if not img_url or not sub_url:
            logger.warning("nav 接口未返回 wbi_img 数据 (code=%s): img_url=%s, sub_url=%s", 
                          data.get("code"), img_url[:30] if img_url else "None", sub_url[:30] if sub_url else "None")
            return None
        img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
        sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
        if not img_key or not sub_key:
            logger.warning("无法从 URL 提取 keys: img_url=%s, sub_url=%s", img_url, sub_url)
            return None
        logger.debug("成功获取 WBI keys: img_key=%s, sub_key=%s", img_key[:10] + "...", sub_key[:10] + "...")
        return img_key, sub_key
    except Exception as e:
        logger.warning("获取 WBI keys 失败: %s", e)
        return None


def get_mixin_key(img_key: str, sub_key: str) -> str:
    """生成 mixin_key：拼接后按 MIXIN_KEY_ENC_TAB 重排，取前 32 位。"""
    s = img_key + sub_key
    # 按 MIXIN_KEY_ENC_TAB 的索引顺序从 s 中取字符
    result = "".join(s[i] if i < len(s) else "" for i in MIXIN_KEY_ENC_TAB)
    return result[:32]


def enc_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    """对参数签名：添加 wts，排序，过滤特殊字符，计算 w_rid。"""
    mixin_key = get_mixin_key(img_key, sub_key)
    params = dict(params)
    wts = int(time.time())
    params["wts"] = wts
    # 按键名排序
    params = dict(sorted(params.items()))
    # 过滤特殊字符
    params = {
        k: "".join(filter(lambda c: c not in "!'()*", str(v)))
        for k, v in params.items()
    }
    # URL 编码
    query = urllib.parse.urlencode(params)
    # 计算 MD5
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = w_rid
    return params
