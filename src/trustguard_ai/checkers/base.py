"""检查器基类。

所有 checker 遵循同一套约定：

    1. **规则优先**：能用确定性规则判定的，绝不丢给 LLM；
    2. **LLM 只做增强**：没有 provider 时必须仍能工作（降级而非失败）；
    3. **每条问题都带证据**：evidence 字段必须是原文片段。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from ..llm import LLMProvider
from ..models import CheckName, CheckResult, Source


class BaseChecker(ABC):
    """检查器基类。"""

    name: CheckName

    def __init__(self, llm: Optional[LLMProvider] = None):
        self.llm = llm

    @property
    def llm_enabled(self) -> bool:
        return self.llm is not None

    @abstractmethod
    def check(self, claim: str, sources: Sequence[Source]) -> CheckResult:
        """执行检查并返回结果。"""
        raise NotImplementedError

    # -- 供子类使用的辅助方法 -------------------------------------------

    def _result(self, result: CheckResult) -> CheckResult:
        if not self.llm_enabled:
            result.note = "未接入 LLM，使用规则实现（mode=rule）"
        return result
