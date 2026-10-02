"""persona_runtime.overlay — 2d→Layer 1 演化应用（v2 M4，ADR-3 / §13.5）

v1 缺口：2d 记录「我变了」，但 Layer 1 永远不会被真的改——人格会记
日记、不长个子。本模块给出应用机制：

  - persona.overlay.yaml：**机写覆盖层**，与 persona.yaml（人写创作态）分离；
    manifest Layer 0 哈希不覆盖 overlay（改表达不影响「同一个人格」校验）
  - 只允许承载 Layer 1：触及 Layer 0 字段 → A11 加载时拒绝（PROTECTED 校验）
  - 两种形态：
      layer1_overrides  结构化字段覆盖（深合并进 Layer 1 渲染）
      adjustments       2d 触发的文字演化指令（渲染为 prompt 调整段）
  - 启动时 A11 加载，build_system_prompt 合成生效（persona.yaml 本体不动）

与 2d 的关系：2d 账本记「我变了 X 因为 Y」（可审计），overlay 记
「具体改成什么」（可回滚，reversible 对接）——写入同源（D6 成功后挂钩）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

OVERLAY_VERSION = 1

# PROTECTED 校验：这些顶层键出现在 overlay → 拒绝加载（宁可错杀）
FORBIDDEN_KEYS = {"layer0", "identity", "value_kernel", "scenarios", "identity_anchors"}


def overlay_path(config) -> Path:
    return Path(config.data_dir) / "persona.overlay.yaml"


def empty_overlay() -> dict[str, Any]:
    return {"overlay_version": OVERLAY_VERSION, "layer1_overrides": {}, "adjustments": []}


# ---------------------------------------------------------------------------
# A11 load_persona_overlay(config)
# ---------------------------------------------------------------------------
def A11_load_persona_overlay(config) -> dict[str, Any]:
    """A11 — 加载演化覆盖层（可选：文件缺失 → 空 overlay，行为与 v1 一致）。

    PROTECTED 校验：任何层0 键 → ValueError 拒绝。
    """
    path = overlay_path(config)
    if not path.exists():
        return empty_overlay()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("A11 overlay yaml must be a mapping — refused")
    for key in data:
        if str(key).lower() in FORBIDDEN_KEYS:
            raise ValueError(
                f"A11 overlay touches PROTECTED Layer 0 key '{key}' — refused "
                f"(Layer 0 变更必须走模块版本升级)"
            )
    data.setdefault("overlay_version", OVERLAY_VERSION)
    data.setdefault("layer1_overrides", {})
    data.setdefault("adjustments", [])
    return data


# ---------------------------------------------------------------------------
# 2d → overlay 写入（D6 成功后由 harness 挂钩调用）
# ---------------------------------------------------------------------------
def append_2d_adjustment(
    config,
    change: str,
    reason: str,
    timestamp: str,
    ledger_id: int,
    reversible: bool = True,
) -> dict[str, Any]:
    """把一条 affected_layer='Layer 1' 的 2d 自评落到 overlay 调整列表。

    机写 persona.overlay.yaml；读侧 A11 每次加载都重新校验 PROTECTED。
    """
    path = overlay_path(config)
    overlay = A11_load_persona_overlay(config)
    overlay.setdefault("adjustments", []).append(
        {
            "change": change,
            "reason": reason,
            "timestamp": timestamp,
            "ledger_id": ledger_id,
            "reversible": bool(reversible),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(overlay, f, allow_unicode=True, sort_keys=False)
    return {"overlay": str(path), "adjustments": len(overlay["adjustments"])}


def render_prompt_section(overlay: dict[str, Any]) -> str:
    """把 overlay 渲染为 system_prompt 的演化调整段（无内容 → 空串）。"""
    adjustments = overlay.get("adjustments") or []
    overrides = overlay.get("layer1_overrides") or {}
    if not adjustments and not overrides:
        return ""
    lines = ["【演化调整（来自自我更新账本，属于你 Layer 1 的现行表达）】"]
    for ov_key, ov_val in overrides.items():
        lines.append(f"- [字段覆盖] {ov_key}：{ov_val}")
    for adj in adjustments:
        lines.append(f"- {adj.get('change', '')}（因：{adj.get('reason', '')}，{adj.get('timestamp', '')}）")
    lines.append("")
    return "\n".join(lines)
