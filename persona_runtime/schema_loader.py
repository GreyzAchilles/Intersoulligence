"""persona_runtime.schema_loader — A1-A4, A6-A9 加载类接口

从 data/persona_schema.yaml 读取 Layer 0/1 声明，返回结构化数据。
所有加载在 work agent 启动时一次性完成。

来源：PRD §11 序号 10
       接口契约 v1 §A（8 个加载接口）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import Config

_LOADED_SCHEMA: dict[str, Any] | None = None
_SCHEMA_PATH: Path | None = None


def _load_raw(schema_path: Path) -> dict[str, Any]:
    """读取 YAML 并返回原始字典。schema 损坏 → ValueError 拒绝加载。"""
    global _LOADED_SCHEMA, _SCHEMA_PATH
    if _LOADED_SCHEMA is not None and _SCHEMA_PATH == schema_path:
        return _LOADED_SCHEMA
    if not schema_path.exists():
        raise FileNotFoundError(f"persona schema not found: {schema_path}")
    try:
        with schema_path.open("r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"schema corrupted: {e}") from e
    if not isinstance(doc, dict):
        raise ValueError("schema must be a mapping at top level")
    _LOADED_SCHEMA = doc
    _SCHEMA_PATH = schema_path
    return doc


def _get_schema(config: Config) -> dict[str, Any]:
    return _load_raw(config.schema_path)


def get_raw_schema(config: Config) -> dict[str, Any]:
    """返回已缓存的完整 persona schema 原始文档。

    build_system_prompt 组装 Layer 0 身份 / Layer 1 表达时使用
    （现有 A 接口只返回摘要，不暴露原始 doc）。
    """
    return _get_schema(config)


def reset_cache() -> None:
    """重置加载缓存（测试用）。"""
    global _LOADED_SCHEMA, _SCHEMA_PATH
    _LOADED_SCHEMA = None
    _SCHEMA_PATH = None


# ---------------------------------------------------------------------------
# A1 load_persona_schema()
# ---------------------------------------------------------------------------
def A1_load_persona_schema(config: Config) -> dict[str, Any]:
    """A1 — 返回完整 schema 结构（含 protected 标记 + global_rules）。

    输出见 接口-v1-按工程分类.md A1。
    """
    doc = _get_schema(config)
    layer0 = doc.get("layer0", {})
    layer1 = doc.get("layer1", {})
    return {
        "schema": {
            "layer0": {
                "fields": list(layer0.get("identity", {}).keys()),
                "subsections": ["identity", "value_kernel", "scenarios"],
                "protected": True,
            },
            "layer1": {
                "fields": list(layer1.keys()),
                "protected": False,
                "reload_per_session": True,
            },
            "layer2": {
                "sublayers": ["2a", "2b", "2c", "2d"],
            },
            "global_rules": [
                "recall_permissions",
                "voice_rewrite",
                "stability_constraints",
            ],
        }
    }


# ---------------------------------------------------------------------------
# A2 get_identity_anchors()
# ---------------------------------------------------------------------------
def A2_get_identity_anchors(config: Config) -> dict[str, Any]:
    """A2 — 返回场景 → identity_anchor 映射。返回空列表 → 警告（不报错）。"""
    doc = _get_schema(config)
    scenarios = doc.get("layer0", {}).get("scenarios", [])
    anchors = [
        {"scenario": s["name"], "anchor": s.get("identity_anchor", "")}
        for s in scenarios
        if s.get("identity_anchor")
    ]
    return {"anchors": anchors}


# ---------------------------------------------------------------------------
# A3 get_value_kernel()
# ---------------------------------------------------------------------------
def A3_get_value_kernel(config: Config) -> dict[str, Any]:
    """A3 — 返回价值内核。空 → 拒绝加载人格模块。"""
    doc = _get_schema(config)
    vk = doc.get("layer0", {}).get("value_kernel", {})
    if not vk or not vk.get("inviolable_beliefs"):
        raise ValueError("value_kernel empty — refuse to load persona module")
    return {"value_kernel": vk}


# ---------------------------------------------------------------------------
# A4 get_available_scenarios(filter=None)
# ---------------------------------------------------------------------------
def A4_get_available_scenarios(
    config: Config, filter_scenarios: list[str] | None = None
) -> dict[str, Any]:
    """A4 — 返回可用场景白名单。filter 过滤后空 → 警告，保留默认全集。"""
    doc = _get_schema(config)
    scenarios = doc.get("layer0", {}).get("scenarios", [])
    available = []
    for s in scenarios:
        item = {
            "name": s["name"],
            "inherits_from_value_kernel": s.get("inherits_from_value_kernel", []),
            "priority_subset": s.get("priority_subset", []),
            "identity_anchor": s.get("identity_anchor", ""),
            "voice_tone": s.get("voice_tone", ""),
            "self_check_policy": s.get("self_check_policy", "harness_managed"),
            "discriminator": s.get("discriminator", {}),
        }
        available.append(item)
    if filter_scenarios:
        filtered = [s for s in available if s["name"] in filter_scenarios]
        if filtered:
            available = filtered
        else:
            import warnings

            warnings.warn("A4 filter empty — keep full set")
    return {"available_scenarios": available}


# ---------------------------------------------------------------------------
# A6 get_self_check_policy()
# ---------------------------------------------------------------------------
def A6_get_self_check_policy(config: Config) -> dict[str, Any]:
    """A6 — 返回自检机制归属。未声明 → 默认 harness_managed。"""
    doc = _get_schema(config)
    layer0 = doc.get("layer0", {})
    policy = layer0.get("self_check_policy")
    if not policy:
        for s in layer0.get("scenarios", []):
            if s.get("self_check_policy"):
                policy = s["self_check_policy"]
                break
    if not policy:
        policy = "harness_managed"
    return {"self_check_policy": policy}


# ---------------------------------------------------------------------------
# A7 get_stage_signal_prompt()
# ---------------------------------------------------------------------------
def A7_get_stage_signal_prompt(config: Config) -> dict[str, Any]:
    """A7 — 返回阶段切换信号 prompt 模板。未声明 → 警告（返回空）。"""
    doc = _get_schema(config)
    stage_signal = doc.get("stage_signal")
    if not stage_signal:
        import warnings

        warnings.warn("A7 stage_signal missing")
        return {"stage_signal": {}}
    return {"stage_signal": stage_signal}


# ---------------------------------------------------------------------------
# A8 get_initial_scenario_check_prompt()
# ---------------------------------------------------------------------------
def A8_get_initial_scenario_check_prompt(config: Config) -> dict[str, Any]:
    """A8 — 返回首轮场景自检 prompt。available_scenarios 由 A4 注入。"""
    doc = _get_schema(config)
    ssc = doc.get("scenario_self_check", {})
    initial = dict(ssc.get("initial", {}))
    if not initial:
        import warnings

        warnings.warn("A8 initial scenario check missing")
    scenarios = A4_get_available_scenarios(config)["available_scenarios"]
    initial["available_scenarios"] = [s["name"] for s in scenarios]
    initial["scenario_discriminators"] = {
        s["name"]: s.get("discriminator", {}) for s in scenarios
    }
    return {"scenario_self_check_initial": initial}


# ---------------------------------------------------------------------------
# A9 get_ongoing_scenario_check_prompt(current_scenario)
# ---------------------------------------------------------------------------
def A9_get_ongoing_scenario_check_prompt(
    config: Config, current_scenario: str
) -> dict[str, Any]:
    """A9 — 返回持续场景自检 prompt。current_scenario 失效 → 回退首轮。"""
    doc = _get_schema(config)
    ssc = doc.get("scenario_self_check", {})
    ongoing = dict(ssc.get("ongoing", {}))
    scenarios = A4_get_available_scenarios(config)["available_scenarios"]
    scenario_names = [s["name"] for s in scenarios]
    if current_scenario not in scenario_names:
        import warnings

        warnings.warn("A9 current_scenario invalid — fallback to initial")
        return A8_get_initial_scenario_check_prompt(config)
    ongoing["current_scenario"] = current_scenario
    ongoing["available_scenarios"] = scenario_names
    ongoing["scenario_discriminators"] = {
        s["name"]: s.get("discriminator", {}) for s in scenarios
    }
    ongoing["discriminator"] = ongoing["scenario_discriminators"].get(
        current_scenario, {}
    )
    return {"scenario_self_check_ongoing": ongoing}