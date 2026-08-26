"""tests/test_mcp_server.py — mcp_server 单元测试

覆盖 4 个 MCP 工具（persona_layer0_get / persona_layer1_get /
persona_layer2_query / persona_runtime_op）+ server 构建与入口。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from persona_runtime import schema_loader
from tests.conftest import insert_interaction, insert_ledger, insert_pattern


# ---------------------------------------------------------------------------
# tools.layer0 — persona_layer0_get
# ---------------------------------------------------------------------------
def test_layer0_valid_fields_return_data(tmp_config):
    from mcp_server.tools import persona_layer0_get

    for field in (
        "schema",
        "anchors",
        "value_kernel",
        "scenarios",
        "self_check_policy",
        "initial_scenario_check",
    ):
        result = persona_layer0_get(field, tmp_config)
        assert "data" in result, f"field={field} should return data"
    assert "layer0" in persona_layer0_get("schema", tmp_config)["data"]["schema"]


def test_layer0_invalid_field_rejected(tmp_config):
    from mcp_server.tools import persona_layer0_get

    result = persona_layer0_get("nope", tmp_config)
    assert "error" in result
    assert "schema" in result["valid"]


def test_layer0_uninitialized_schema_rejected(tmp_path):
    from persona_runtime.config import load_config
    from mcp_server.tools import persona_layer0_get

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    cfg = load_config(
        data_dir=empty_dir,
        schema_path=empty_dir / "missing.yaml",
        db_path=empty_dir / "persona.db",
        snapshot_dir=empty_dir / "snapshots",
    )
    schema_loader.reset_cache()
    result = persona_layer0_get("schema", cfg)
    assert "error" in result


# ---------------------------------------------------------------------------
# tools.layer1 — persona_layer1_get
# ---------------------------------------------------------------------------
def test_layer1_stage_signal_prompt(tmp_config):
    from mcp_server.tools import persona_layer1_get

    result = persona_layer1_get("stage_signal_prompt", tmp_config)
    assert "[STAGE_TRANSITION]" in result["data"]["stage_signal"]["format"]


def test_layer1_ongoing_requires_scenario(tmp_config):
    from mcp_server.tools import persona_layer1_get

    result = persona_layer1_get("ongoing_scenario_check", tmp_config)
    assert "error" in result
    assert "current_scenario" in result["error"]


def test_layer1_ongoing_with_scenario(tmp_config):
    from mcp_server.tools import persona_layer1_get

    result = persona_layer1_get(
        "ongoing_scenario_check", tmp_config, current_scenario="work_agent_mode"
    )
    assert result["data"]["scenario_self_check_ongoing"]["current_scenario"] == (
        "work_agent_mode"
    )


def test_layer1_invalid_field_rejected(tmp_config):
    from mcp_server.tools import persona_layer1_get

    result = persona_layer1_get("nope", tmp_config)
    assert "error" in result


# ---------------------------------------------------------------------------
# tools.layer2 — persona_layer2_query（7 个 operations）
# ---------------------------------------------------------------------------
def test_layer2_invalid_operation_rejected(conn):
    from mcp_server.tools import persona_layer2_query

    result = persona_layer2_query("nope", conn)
    assert "error" in result
    assert "recall_2a" in result["valid"]


def test_layer2_recall_2a_with_entities(conn):
    from mcp_server.tools import persona_layer2_query

    insert_interaction(conn, entities=["豆包"], content="用户聊到豆包")
    result = persona_layer2_query(
        "recall_2a", conn, {"entities": ["豆包"], "time_range": {}}
    )
    assert len(result["records"]) == 1
    assert "豆包" in result["records"][0]["entities"]


def test_layer2_recall_2b_missing_param_returns_error(conn):
    from mcp_server.tools import persona_layer2_query

    result = persona_layer2_query("recall_2b", conn, {})
    assert "KeyError" in result["error"]
    assert result["operation"] == "recall_2b"


def test_layer2_recall_2c_default_all(conn):
    from mcp_server.tools import persona_layer2_query

    insert_pattern(conn, pattern="偏好递进追问")
    result = persona_layer2_query("recall_2c", conn)
    assert len(result["records"]) == 1


def test_layer2_recall_2d_recent_n(conn):
    from mcp_server.tools import persona_layer2_query

    insert_ledger(conn, change="c1", timestamp="2026-08-13T10:00:00")
    insert_ledger(conn, change="c2", timestamp="2026-08-14T10:00:00")
    result = persona_layer2_query("recall_2d", conn, {"recent": 1})
    assert result["records"][0]["change"] == "c2"


def test_layer2_append_2d_writes_ledger(conn):
    from mcp_server.tools import persona_layer2_query

    result = persona_layer2_query(
        "append_2d",
        conn,
        {"change": "更克制", "reason": "用户反馈", "affected_layer": "Layer 1"},
    )
    assert "id" in result["appended"]


def test_layer2_append_2d_protected_layer_conflict(conn):
    from mcp_server.tools import persona_layer2_query

    result = persona_layer2_query(
        "append_2d",
        conn,
        {"change": "x", "reason": "y", "affected_layer": "Layer 0.2"},
    )
    assert result.get("refused") is True


def test_layer2_maybe_2d_trigger_user_feedback(conn):
    from mcp_server.tools import persona_layer2_query

    result = persona_layer2_query(
        "maybe_2d_trigger",
        conn,
        {"input": {"user_message": "辛苦了这次", "ai_response": "好的", "turn": 1}},
    )
    assert result["trigger"]["triggered"] is True
    assert result["trigger"]["reason"] == "user_feedback"


def test_layer2_write_2b_overwrite_facts(conn):
    from mcp_server.tools import persona_layer2_query

    result = persona_layer2_query(
        "write_2b",
        conn,
        {"entity": "新实体", "field": "facts", "value": "工科生", "mode": "overwrite"},
    )
    assert result["written"]["entity"] == "新实体"


def test_layer2_value_error_caught(conn):
    from mcp_server.tools import persona_layer2_query

    result = persona_layer2_query(
        "append_2d", conn, {"change": "", "reason": "y", "affected_layer": "Layer 1"}
    )
    assert "ValueError" in result["error"]


# ---------------------------------------------------------------------------
# tools.runtime — persona_runtime_op（13 个 operations）
# ---------------------------------------------------------------------------
B1_RESP = "[STAGE_TRANSITION]\nto: plan_subagent\nconfidence: high\n[/STAGE_TRANSITION]"
B2_RESP = "[SCENARIO_CHECK] stay: chatbot_mode\n[RESPONSE]好的"


def _op(operation, config, params=None, conn=None, available_scenarios=None):
    from mcp_server.tools import persona_runtime_op

    return persona_runtime_op(
        operation, config, params, conn=conn, available_scenarios=available_scenarios
    )


def test_runtime_invalid_operation_rejected(tmp_config):
    result = _op("nope", tmp_config)
    assert "error" in result
    assert "parse_stage_transition" in result["valid"]


def test_runtime_parse_stage_transition(tmp_config):
    result = _op("parse_stage_transition", tmp_config, {"response": B1_RESP})
    assert result == {"parsed": {"to": "plan_subagent", "confidence": "high"}}


def test_runtime_parse_stage_transition_no_marker(tmp_config):
    result = _op("parse_stage_transition", tmp_config, {"response": "plain"})
    assert result == {"parsed": None}


def test_runtime_parse_stage_transition_missing_param(tmp_config):
    result = _op("parse_stage_transition", tmp_config, {})
    assert "KeyError: 'response'" in result["error"]
    assert result["operation"] == "parse_stage_transition"


def test_runtime_parse_scenario_check(tmp_config):
    result = _op("parse_scenario_check", tmp_config, {"response": B2_RESP})
    assert result["parsed"]["action"] == "stay"


def test_runtime_validate_stage_transition_low_rate(tmp_config):
    result = _op(
        "validate_stage_transition",
        tmp_config,
        {
            "parsed": {"to": "plan_subagent", "confidence": "high"},
            "harness_state": {"long_window_violation_rate": 0.05},
        },
    )
    assert result["validated"]["action"] == "switch"


def test_runtime_validate_scenario_check_whitelist(tmp_config):
    result = _op(
        "validate_scenario_check",
        tmp_config,
        {
            "parsed": {
                "mode": "ongoing",
                "action": "switch_to",
                "target": "work_agent_mode",
            }
        },
        available_scenarios=["chatbot_mode", "work_agent_mode"],
    )
    assert result["validated"]["action"] == "switch"


def test_runtime_apply_recall_permission_cite(tmp_config):
    ts = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
    result = _op(
        "apply_recall_permission",
        tmp_config,
        {"records": [{"content": "x", "entities": ["a"], "channel": "direct", "timestamp": ts}]},
    )
    assert result["tagged_records"][0]["permission"] == "cite"


def test_runtime_rewrite_voice_2a(tmp_config):
    result = _op(
        "rewrite_voice",
        tmp_config,
        {
            "records": [{"content": "今天吃了牛肉面"}],
            "source_layer": "2a",
        },
    )
    assert "你记得他" in result["rewritten"][0]["content"]


def test_runtime_validate_2d_entry_passes(tmp_config):
    result = _op(
        "validate_2d_entry",
        tmp_config,
        {"entry": {"change": "更简洁", "reason": "用户反馈", "affected_layer": "Layer 1"}},
    )
    assert result["validated"]["passed"] is True


def test_runtime_value_self_check_clean(tmp_config):
    result = _op(
        "value_self_check",
        tmp_config,
        {"response": "好，我帮你看一下这个数据。", "scenario": "work_agent_mode"},
    )
    assert result["check"]["violated"] is False
    assert result["check"]["action"] == "pass"


def test_runtime_take_snapshot(tmp_config, conn):
    result = _op("take_snapshot", tmp_config, {"turn": 20}, conn=conn)
    assert result["snapshot"]["turn"] == 20


def test_runtime_load_latest_snapshot_fresh_start(tmp_config):
    result = _op("load_latest_snapshot", tmp_config)
    assert result["loaded"]["recovery_action"] == "fresh_start"


def test_runtime_apply_decay_empty_db(tmp_config, conn):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    result = _op("apply_decay", tmp_config, {"now": now}, conn=conn)
    assert result["layer_2a"]["cooling"] == []
    assert result["layer_2d"]["ttl_expired"] == []


def test_runtime_spawn_plan_subagent(tmp_config):
    result = _op("spawn_plan_subagent", tmp_config, {"grill_output": "grill output here"})
    spawned = result["spawned"]
    assert spawned["subagent_id"].startswith("plan_subagent_")


def test_runtime_inject_plan_subagent_rule(tmp_config):
    result = _op("inject_plan_subagent_rule", tmp_config)
    assert result["injected"]["permanent"] is True


# ---------------------------------------------------------------------------
# server — 构建 + 注册 + stdio 入口
# ---------------------------------------------------------------------------
@pytest.fixture
def srv(tmp_config, monkeypatch):
    """隔离的 mcp_server.server 模块：harness 用 tmp_config，不碰真实 data/。"""
    import mcp_server.server as srv_mod

    monkeypatch.setattr(srv_mod, "_STATE", {})
    monkeypatch.setattr(srv_mod, "load_config", lambda *a, **k: tmp_config)

    created = []
    real_create = srv_mod.create_harness

    def tracking_create(cfg):
        h = real_create(cfg)
        created.append(h)
        return h

    monkeypatch.setattr(srv_mod, "create_harness", tracking_create)
    yield srv_mod
    for h in created:
        if getattr(h, "conn", None) is not None:
            h.conn.close()
    schema_loader.reset_cache()


def test_server_build_registers_four_tools(srv):
    mcp = srv._build_server()
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {
        "persona_layer0_get_tool",
        "persona_layer1_get_tool",
        "persona_layer2_query_tool",
        "persona_runtime_op_tool",
    }


def test_server_missing_sdk_raises(srv, monkeypatch):
    monkeypatch.setattr(srv, "FastMCP", None)
    with pytest.raises(RuntimeError, match="mcp SDK not installed"):
        srv._build_server()


def test_server_call_layer0_tool_end_to_end(srv):
    mcp = srv._build_server()
    res = asyncio.run(mcp.call_tool("persona_layer0_get_tool", {"field": "schema"}))
    payload = json.loads(res.content[0].text)
    assert "layer0" in payload["data"]["schema"]
    assert res.is_error is False


def test_server_call_runtime_tool_end_to_end(srv):
    mcp = srv._build_server()
    res = asyncio.run(
        mcp.call_tool("persona_runtime_op_tool", {"operation": "load_latest_snapshot"})
    )
    payload = json.loads(res.content[0].text)
    assert payload["loaded"]["recovery_action"] == "fresh_start"


def test_server_harness_lazy_singleton(srv):
    state: dict = {}
    h1 = srv._ensure_harness(state)
    assert state["harness"] is h1
    h2 = srv._ensure_harness(state)
    assert h2 is h1


def test_server_main_runs_stdio(srv, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(srv.FastMCP, "run", lambda self, transport="stdio": calls.append(transport))
    srv.main()
    assert calls == ["stdio"]
