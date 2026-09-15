"""LLM 接入层——「柔性任务交给模型」。

设计要点：
    **LLM 是可插拔的，而不是必需的。**
    所有 checker 都有「规则实现」作为基线，LLM 只用于增强语义推理。
    因此：

        mode="rule"    -> 完全不调用 LLM，离线可跑，测试与评估用这个
        mode="hybrid"  -> 规则 + LLM 增强（需要 provider）
        mode="llm"     -> 仅 LLM

    这样任何人都能 `pip install -e . && pytest` 跑通，
    不需要任何 API key —— 工程上"开箱可验证"比"功能更强"更重要。

支持的接入方式：任何 **OpenAI 兼容** 接口，包括
    百炼 DashScope / DeepSeek / 本地 Ollama / vLLM。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Protocol


class LLMError(RuntimeError):
    """LLM 调用失败。"""


class LLMProvider(Protocol):
    """最小 LLM 接口。"""

    def complete(self, prompt: str, *, system: str = "") -> str:
        """返回模型输出的纯文本。"""
        ...


def extract_json(text: str) -> Any:
    """从模型输出里稳健地取出 JSON。

    模型常把 JSON 包在 ```json 代码块里，或前后带解释文字，
    这里做一次容错解析，避免因格式问题整体失败。
    """
    text = text.strip()

    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 退一步：截取第一个 { 或 [ 到最后一个 } 或 ]
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue

    raise LLMError(f"无法从模型输出中解析 JSON：{text[:200]}")


class ScriptedLLM:
    """按顺序返回预设回答的假模型。

    用于在**不联网、不需要 key** 的前提下测试 LLM 分支的逻辑。
    """

    def __init__(self, responses: List[str]):
        self._responses = list(responses)
        self.calls: List[str] = []

    def complete(self, prompt: str, *, system: str = "") -> str:
        self.calls.append(prompt)
        if not self._responses:
            raise LLMError("ScriptedLLM 的预设回答已用尽")
        return self._responses.pop(0)


class OpenAICompatLLM:
    """OpenAI 兼容接口的轻量客户端。

    只用 `requests`，不引入官方 SDK —— 减少依赖，也便于接任意兼容服务。

    Example:
        llm = OpenAICompatLLM(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=os.environ["DASHSCOPE_API_KEY"],
            model="qwen-plus",
        )
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "qwen-plus",
        timeout: int = 60,
        temperature: float = 0.0,
    ):
        if not base_url:
            raise LLMError("base_url 不能为空")
        if not api_key:
            raise LLMError("api_key 不能为空")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    def complete(self, prompt: str, *, system: str = "") -> str:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "使用真实 LLM 需要安装 requests：pip install 'trustguard[llm]'"
            ) from exc

        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                },
                timeout=self.timeout,
            )
        except Exception as exc:
            raise LLMError(f"请求 LLM 失败：{exc}") from exc

        if resp.status_code != 200:
            raise LLMError(f"LLM 返回 {resp.status_code}：{resp.text[:200]}")

        try:
            payload = resp.json()
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"无法解析 LLM 响应：{resp.text[:200]}") from exc


def provider_from_env() -> Optional[LLMProvider]:
    """按环境变量构造 provider；未配置则返回 None。

    支持的环境变量（任一组合）：
        TRUSTGUARD_LLM_BASE_URL   例如 https://dashscope.aliyuncs.com/compatible-mode/v1
        TRUSTGUARD_LLM_API_KEY    对应的 key
        TRUSTGUARD_LLM_MODEL      默认 qwen-plus
    """
    base_url = os.environ.get("TRUSTGUARD_LLM_BASE_URL", "").strip()
    api_key = os.environ.get("TRUSTGUARD_LLM_API_KEY", "").strip()
    if not base_url or not api_key:
        return None

    return OpenAICompatLLM(
        base_url=base_url,
        api_key=api_key,
        model=os.environ.get("TRUSTGUARD_LLM_MODEL", "qwen-plus"),
    )
