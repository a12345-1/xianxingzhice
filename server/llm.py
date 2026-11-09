# -*- coding: utf-8 -*-
"""模型调用：OpenAI 兼容接口 + JSON 容错 + 失败即降级。"""
import json
import re

try:
    import httpx
except ImportError:          # 没装 httpx 时仍可跑本地规则
    httpx = None

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, TIMEOUT, use_mock


def available() -> bool:
    return (not use_mock()) and bool(LLM_API_KEY) and httpx is not None


def extract_json(text: str):
    if not isinstance(text, str):
        return None
    s = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def complete_json(system: str, user: str, model: str = None):
    """调模型并解析 JSON；任何异常都返回 None，由调用方走本地规则。"""
    if not available():
        return None
    payload = {
        "model": model or LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
    }
    try:
        r = httpx.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None
    return extract_json(content)
