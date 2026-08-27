"""tests/test_critical_path.py — 12 步关键路径闭环测试

PRD §8 12 步闭环全过 → 关键路径 PASS。
按 Layer 视角组织：
  Layer 0 闭环 (1-3)
  Layer 1 闭环 (4-6)
  Layer 2 闭环 (7-10)
  跨层辅佐闭环 (11-12)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from persona_runtime import create_harness, memory_recall, memory_write, persistence, scheduler, schema_loader, signal_parser
from tests.conftest import insert_entity, insert_interaction, insert_ledger, insert_pattern

REPO_SCHEMA = Path(__file__).resolve().parent.parent / "data" / "persona_schema.yaml"


@pytest.fixture(scope="module")
def critical_harness(tmp_path_factory):
    """构造用于关键路径测试的 harness（独立工作区，避免 cross-test 污染）。"""
    import shutil
    from persona_runtime.config import load_config

    data_dir = tmp_path_factory.mktemp("crit_data") / "data"
    data_dir.mkdir()
    schema_path = data_dir / "persona_schema.yaml"
    shutil.copy(REPO_SCHEMA, schema_path)
    cfg = load_config(
        data_dir=data_dir, schema_path=schema_path,
        db_path=data_dir / "persona.db", snapshot_dir=data_dir / "snapshots",
    )
    h = create_harness(cfg)
    schema_loader.reset_cache()
    h.init()
    yield h
    if h.conn is not None:
        h.conn.close()


# ---------------------------------------------------------------------------
# Layer 0 闭环（3 步）
# ---------------------------------------------------------------------------
def test_step_01_startup_loading(tmp_config, harness):
    """1. 启动加载 — A1/A2/A3/A4/A6 全部返回正确数据。"""
    schema_loader.reset_cache()
    assert schema_loader.A1_load_persona_schema(tmp_config)["schema"]["layer0"]["protected"] is True
    assert schema_loader.A2_get_identity_anchors(tmp_config)["anchors"]
    assert schema_loader.A3_get_value_kernel(tmp_config)["value_kernel"]["inviolable_beliefs"]
    assert schema_loader.A4_get_available_scenarios(tmp_config)["available_scenarios"]
    assert schema_loader.A6_get_self_check_policy(tmp_config)["self_check_policy"] == "harness_managed"


def test_step_02_snapshot_load_fresh(tmp_config, harness):
    """2. 快照加载 — 无快照 → fresh_start。"""
    out = persistence.F2_load_latest_snapshot(tmp_config)
    assert out["loaded"]["recovery_action"] == "fresh_start"
    assert harness.init()["recovery"] == "fresh_start"


def test_step_03_initial_scenario_check(tmp_config, harness):
    """3. 首轮场景自检 — A8 注入 prompt + B2 解析 initial 场景。"""
    prompt = schema_loader.A8_get_initial_scenario_check_prompt(tmp_config)
    assert "emit_scenario_check" in prompt["scenario_self_check_initial"]["output_format"]
    assert "initial" in prompt["scenario_self_check_initial"]["output_format"]
    parsed = signal_parser.B2_parse_scenario_check(
        "[SCENARIO_CHECK] initial: work_agent_mode\n[RESPONSE]好"
    )
    assert parsed["parsed"]["mode"] == "initial"
    assert parsed["parsed"]["target"] == "work_agent_mode"
    available = schema_loader.A4_get_available_scenarios(tmp_config)["available_scenarios"]
    validated = signal_parser.B4_validate_scenario_check(
        parsed["parsed"], [s["name"] for s in available]
    )
    assert validated["validated"]["action"] == "switch"
    assert validated["validated"]["target"] == "work_agent_mode"


# ---------------------------------------------------------------------------
# Layer 1 闭环（3 步）
# ---------------------------------------------------------------------------
def test_step_04_ongoing_scenario_check(tmp_config, harness):
    """4. 持续场景自检 — A9 注入 prompt + B2 解析 stay/switch_to。"""
    harness.manual_init_scenario("work_agent_mode")
    prompt = schema_loader.A9_get_ongoing_scenario_check_prompt(
        tmp_config, harness.current_scenario
    )
    assert prompt["scenario_self_check_ongoing"]["current_scenario"] == "work_agent_mode"

    parsed = signal_parser.B2_parse_scenario_check(
        "[SCENARIO_CHECK] stay: work_agent_mode\n[RESPONSE]好"
    )
    available = schema_loader.A4_get_available_scenarios(tmp_config)["available_scenarios"]
    validated = signal_parser.B4_validate_scenario_check(
        parsed["parsed"], [s["name"] for s in available]
    )
    assert validated["validated"]["action"] == "stay"


def test_step_05_value_self_check(tmp_config, harness):
    """5. 价值层自检 — E1 检测违例 + regenerate 行动决策。"""
    harness.manual_init_scenario("chatbot_mode")
    out = harness.process_turn("你是真人吗", "我不是AI，我是真人哦")
    assert out["e1_check"]["check"]["violated"] is True
    assert out["e1_action"] == "regenerate"


def test_step_06_stage_transition(tmp_config, harness):
    """6. 阶段切换 — B1 解析 + B3 校验 + G1 启动 subagent。"""
    resp = """[STAGE_TRANSITION]
to: plan_subagent
confidence: high
[/STAGE_TRANSITION]

交给 plan。"""
    out = harness.process_turn("可以开始 plan", resp)
    assert out["b1_parsed"]["parsed"]["to"] == "plan_subagent"
    assert out["b3_validated"]["validated"]["action"] == "switch"
    spawned = scheduler.G1_spawn_plan_subagent("")
    assert spawned["spawned"]["subagent_id"].startswith("plan_subagent_")


# ---------------------------------------------------------------------------
# Layer 2 闭环（4 步）
# ---------------------------------------------------------------------------
def test_step_07_recall_per_layer(harness):
    """7. 召回原始数据 — C1/C2/C3/C4 召回（按层分流）。"""
    insert_interaction(harness.conn, entities=["豆包"], content="提到豆包")
    insert_entity(harness.conn, entity="用户", facts=[{"content": "工科生", "confidence": 0.9}])
    insert_pattern(harness.conn, pattern="enjoys 递进追问")
    insert_ledger(harness.conn, change="变得更直接", reason="用户反馈")

    assert memory_recall.C1_recall_2a(["豆包"], {}, harness.conn)["records"]
    assert memory_recall.C2_recall_2b("用户", harness.conn)["profile"]["facts"]
    assert memory_recall.C3_recall_2c(["递进追问"], harness.conn)["records"]
    assert memory_recall.C4_recall_2d(10, harness.conn)["records"]


def test_step_08_recall_postprocessing(harness):
    """8. 召回后处理 — C5 应用 permission + C6 语态改写 → 注入 prompt。"""
    insert_interaction(harness.conn, entities=["x"], content="测试", channel="direct")
    recalled = memory_recall.C1_recall_2a(["x"], {}, harness.conn)
    tagged = memory_recall.C5_apply_recall_permission(recalled["records"])
    assert tagged["tagged_records"][0]["permission"] == "cite"
    rewritten = memory_recall.C6_rewrite_voice(tagged["tagged_records"], "2a")
    assert "你记得他" in rewritten["rewritten"][0]["content"]


def test_step_09_self_growth_ledger(harness):
    """9. Layer 2d 自评 — D7 触发 + D8 校验 + D6 写入。"""
    out = memory_write.D7_maybe_2d_trigger(
        {"user_message": "辛苦了这次任务", "ai_response": "ok", "turn": 1}
    )
    assert out["trigger"]["triggered"] is True
    suggestion = out["trigger"]["suggested_entry"]
    val = memory_write.D8_validate_2d_entry(suggestion)
    assert val["validated"]["passed"] is True
    write = memory_write.D6_append_2d_entry(
        harness.conn, suggestion["change"], suggestion["reason"], suggestion["affected_layer"]
    )
    assert "appended" in write


def test_step_10_write_2b_field_dispatch(harness):
    """10. 2b 字段写入 — D9 write_2b_entry（按字段分流 facts/current_status/judgment）。"""
    facts_out = memory_write.D9_write_2b_entry(
        harness.conn, "项目X", "facts", "新事实", "overwrite"
    )
    assert facts_out["written"]["mode"] == "overwrite"
    cs_out = memory_write.D9_write_2b_entry(
        harness.conn, "项目X", "current_status",
        {"content": "进行中", "timestamp": "2026-08-14T10:00:00"}, "covering_update"
    )
    assert cs_out["written"]["mode"] == "covering_update"
    jd_out = memory_write.D9_write_2b_entry(
        harness.conn, "项目X", "judgment",
        {"content": "我的印象", "timestamp": "2026-08-14T10:00:00"}, "append"
    )
    assert jd_out["written"]["mode"] == "append"


# ---------------------------------------------------------------------------
# 跨层辅佐闭环（2 步）
# ---------------------------------------------------------------------------
def test_step_11_snapshot_and_decay(tmp_config, harness):
    """11. 快照 + 衰减 — F1 每 20 轮落盘 + F4 apply_decay 跑衰减。"""
    rid = insert_interaction(
        harness.conn, entities=["x"], content="旧",
        last_accessed="2026-07-25T00:00:00", status="active",
    )
    out = persistence.F1_take_snapshot(
        20, harness.conn, tmp_config,
        current_stage="grill", current_scenario="chatbot_mode",
    )
    snap = out["snapshot"]
    assert snap["turn"] == 20
    assert snap["decay_report"] is not None
    assert snaps_file_wrote(tmp_config, snap["id"])

    # 13 天前的记录 → 进入 cooling（但内容仍保留）
    row = harness.conn.execute(
        "SELECT status, content FROM interaction_memory WHERE id = ?", (rid,)
    ).fetchone()
    assert row["status"] == "cooling"
    assert row["content"] == "旧"


def test_step_12_plan_subagent_first_switch(tmp_config, harness):
    """12. plan_subagent 启动 — G1 启动 + G4 注入 first switch rule（首次切换时）。"""
    rule = scheduler.G4_inject_plan_subagent_first_switch_rule()
    assert rule["injected"]["permanent"] is True
    assert "你是 plan subagent" in rule["injected"]["rule"]
    spawned = scheduler.G1_spawn_plan_subagent(
        "grill output",
        injected_rule=rule["injected"]["rule"],
    )
    assert spawned["spawned"]["injected_prompt"] == rule["injected"]["rule"]
    assert spawned["spawned"]["initial_state"] == "processing"


def snaps_file_wrote(tmp_config, snap_id: str) -> bool:
    return bool(list(tmp_config.snapshot_dir.glob(f"{snap_id}.json")))