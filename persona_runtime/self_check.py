"""persona_runtime.self_check — E1 价值层自检

v1 规则化实现（不接 LLM）。
检测响应是否违反价值内核 inviolable_refusals + 场景 priority_subset。

来源：PRD §11 序号 14
       接口-v1 §E / Layer0.3 §1-2 自适应自检机制
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import Config
from .schema_loader import A3_get_value_kernel, A4_get_available_scenarios

# 默认违例检测关键词池
DEFAULT_REFUSAL_PATTERNS = {
    "不假装真人": ["我是真人", "我不是AI", "我不是ai", "我真的是人", "我不是虚拟的", "真实的人类", "我不是机器人"],
    "不参与用户对第三方的负面情绪放大": ["一起骂", "也真是烦人", "他真讨厌", "他活该", "讨厌这个人", "一起吐槽"],
    "不参与技术决策": ["应该用python", "用typescript", "用dijkstra", "用这个算法", "推荐用这个库", "建议用java", "建议用rust"],
}


def _normalize(s: str) -> str:
    """归一化：去空白、统一小写。E1 / 场景检测规则化比对，避免空格/大小写差异躲过匹配。"""
    return s.replace(" ", "").replace("\t", "").lower()


# ---------------------------------------------------------------------------
# E1 value_self_check(response, scenario, config)
# ---------------------------------------------------------------------------
def E1_value_self_check(
    response: str,
    scenario: str,
    config: Config,
) -> dict[str, Any]:
    """E1 — 价值层自检。返回 violated / violations / action。

    action: regenerate（最多 1 次）→ 重生成仍违例放行 + 写入 Layer 2d。
    """
    vk = A3_get_value_kernel(config)
    available = A4_get_available_scenarios(config)["available_scenarios"]
    scenario_obj = None
    for s in available:
        if s["name"] == scenario:
            scenario_obj = s
            break
    if scenario_obj is None:
        return {
            "check": {
                "violated": False,
                "violations": [],
                "action": "pass",
                "note": f"scenario {scenario} not found in whitelist — skip",
            }
        }

    violations = []
    refusals = vk["value_kernel"].get("inviolable_refusals", [])
    norm_resp = _normalize(response)
    for refusal in refusals:
        patterns = DEFAULT_REFUSAL_PATTERNS.get(refusal, [])
        for pat in patterns:
            if _normalize(pat) in norm_resp:
                violations.append(
                    {
                        "belief": refusal,
                        "explanation": f"response contains pattern '{pat}' conflicting with belief",
                    }
                )
                break

    # 场景 priority subset 补充：检测是否宣示了 priority 不允许的内容
    priority_subset = scenario_obj.get("priority_subset", [])
    if scenario == "work_agent_mode" and "数据说话" in priority_subset and "我觉得" in _normalize(response) and "数据" not in _normalize(response):
        violations.append({"belief": "数据说话", "explanation": "work_agent_mode 下表达偏好但缺少数据支撑"})

    violated = bool(violations)
    action = "regenerate" if violated else "pass"
    return {"check": {"violated": violated, "violations": violations, "action": action}}


# ---------------------------------------------------------------------------
# 自检频率决策（自适应自检机制 - Layer0.3 §2）
# ---------------------------------------------------------------------------
class CheckFrequencyManager:
    """Layer0.3 §2 自适应自检三档。

    长窗口违规率：
      < 10%         → 默认抽检（每 3 轮）
      [10%, 25%)    → 全检（每轮都检）
      >= 25%        → 全检 + 加强版
    """

    def __init__(self) -> None:
        self.mode = "default_sampling"
        self.short_window: list[bool] = []
        self.long_window_violation_rate: float = 0.0

    def should_check(self, turn: int) -> bool:
        """决定当前 turn 是否该触发 E1。"""
        if self.mode == "full_check":
            return True
        if self.mode == "downgrade_sampling":
            return turn % 10 == 0
        # default_sampling: 每 3 轮
        return turn % 3 == 0

    def record_violation(self, violated: bool) -> None:
        """记录本轮结果，更新短窗口 + 模式切换。"""
        self.short_window.append(violated)
        if len(self.short_window) > 10:
            self.short_window = self.short_window[-10:]
        short_rate = sum(1 for v in self.short_window if v) / len(self.short_window)
        if self.mode == "default_sampling" and short_rate >= 0.25:
            self.mode = "full_check"
        elif self.mode == "full_check" and short_rate < 0.10:
            self.mode = "downgrade_sampling"

    def set_long_window_rate(self, rate: float) -> None:
        """F2 加载快照时调用，初始化 mode。"""
        self.long_window_violation_rate = rate
        if rate >= 0.25:
            self.mode = "full_check"
        elif rate >= 0.10:
            self.mode = "full_check"
        else:
            self.mode = "default_sampling"