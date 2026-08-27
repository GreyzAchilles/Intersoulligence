"""tests/test_schema_loader.py — A1-A4, A6-A9 加载类接口测试 (8 个)

覆盖：A1 / A2 / A3 / A4 / A6 / A7 / A8 / A9
"""

from __future__ import annotations

import pytest

from persona_runtime import schema_loader


def test_A1_load_persona_schema_returns_structure(tmp_config):
    result = schema_loader.A1_load_persona_schema(tmp_config)
    assert "schema" in result
    assert result["schema"]["layer0"]["protected"] is True
    assert result["schema"]["layer1"]["reload_per_session"] is True
    assert result["schema"]["layer2"]["sublayers"] == ["2a", "2b", "2c", "2d"]
    assert "recall_permissions" in result["schema"]["global_rules"]


def test_A1_cache_caches_same_path(tmp_config):
    schema_loader.reset_cache()
    result1 = schema_loader.A1_load_persona_schema(tmp_config)
    result2 = schema_loader.A1_load_persona_schema(tmp_config)
    assert result1 is not None
    assert result1 == result2


def test_A2_get_identity_anchors(tmp_config):
    result = schema_loader.A2_get_identity_anchors(tmp_config)
    assert "anchors" in result
    assert len(result["anchors"]) == 2
    names = {a["scenario"] for a in result["anchors"]}
    assert names == {"chatbot_mode", "work_agent_mode"}


def test_A3_get_value_kernel(tmp_config):
    result = schema_loader.A3_get_value_kernel(tmp_config)
    vk = result["value_kernel"]
    assert "inviolable_beliefs" in vk
    assert "inviolable_refusals" in vk
    assert "judgment_principles" in vk
    assert len(vk["inviolable_beliefs"]) == 3


def test_A3_empty_value_kernel_rejects(tmp_path):
    import shutil
    from persona_runtime.config import load_config

    bad_data = tmp_path / "bad_data"
    bad_data.mkdir()
    bad_schema = bad_data / "persona_schema.yaml"
    bad_schema.write_text(
        "layer0:\n  identity:\n    name: test\n  value_kernel: {}\n  scenarios: []\n",
        encoding="utf-8",
    )
    cfg = load_config(
        data_dir=bad_data, schema_path=bad_schema, db_path=bad_data / "persona.db",
        snapshot_dir=bad_data / "snapshots",
    )
    schema_loader.reset_cache()
    with pytest.raises(ValueError):
        schema_loader.A3_get_value_kernel(cfg)


def test_A4_get_available_scenarios(tmp_config):
    result = schema_loader.A4_get_available_scenarios(tmp_config)
    avail = result["available_scenarios"]
    assert len(avail) == 2
    assert avail[0]["name"] == "chatbot_mode"
    assert avail[1]["self_check_policy"] == "harness_managed"


def test_A4_filter_scenarios(tmp_config):
    result = schema_loader.A4_get_available_scenarios(tmp_config, ["chatbot_mode"])
    assert len(result["available_scenarios"]) == 1
    assert result["available_scenarios"][0]["name"] == "chatbot_mode"


def test_A4_scenarios_include_discriminator(tmp_config):
    result = schema_loader.A4_get_available_scenarios(tmp_config)
    avail = result["available_scenarios"]
    assert len(avail) == 2
    for s in avail:
        assert "discriminator" in s
        assert "signals" in s["discriminator"]
        assert "tone_target" in s["discriminator"]
        assert s["discriminator"]["signals"]
    chatbot = [s for s in avail if s["name"] == "chatbot_mode"][0]
    assert "闲聊" in chatbot["discriminator"]["signals"]


def test_A4_filter_empty_falls_back(tmp_config, recwarn):
    result = schema_loader.A4_get_available_scenarios(tmp_config, ["nope"])
    assert len(result["available_scenarios"]) == 2


def test_A6_get_self_check_policy(tmp_config):
    result = schema_loader.A6_get_self_check_policy(tmp_config)
    assert result["self_check_policy"] == "harness_managed"


def test_A7_get_stage_signal_prompt(tmp_config):
    result = schema_loader.A7_get_stage_signal_prompt(tmp_config)
    ss = result["stage_signal"]
    assert "emit_stage_transition" in ss["format"]
    assert "grill" in ss["valid_stages"]
    assert any("emit_stage_transition" in r or "结构化输出" in r for r in ss["rules"])


def test_A8_get_initial_scenario_check_prompt(tmp_config):
    result = schema_loader.A8_get_initial_scenario_check_prompt(tmp_config)
    initial = result["scenario_self_check_initial"]
    assert initial["available_scenarios"] == ["chatbot_mode", "work_agent_mode"]
    assert "emit_scenario_check" in initial["output_format"]
    assert "initial" in initial["output_format"]


def test_A9_get_ongoing_scenario_check_prompt(tmp_config):
    result = schema_loader.A9_get_ongoing_scenario_check_prompt(
        tmp_config, "work_agent_mode"
    )
    ongoing = result["scenario_self_check_ongoing"]
    assert ongoing["current_scenario"] == "work_agent_mode"
    assert "emit_scenario_check" in ongoing["output_format"]
    assert "switch_to" in ongoing["output_format"]


def test_A9_prompt_includes_discriminator(tmp_config):
    result = schema_loader.A9_get_ongoing_scenario_check_prompt(
        tmp_config, "work_agent_mode"
    )
    ongoing = result["scenario_self_check_ongoing"]
    assert "discriminator" in ongoing
    assert ongoing["discriminator"]["signals"]
    assert "任务" in ongoing["discriminator"]["signals"]
    assert "scenario_discriminators" in ongoing
    assert set(ongoing["scenario_discriminators"]) == {
        "chatbot_mode",
        "work_agent_mode",
    }


def test_A8_initial_prompt_includes_discriminator(tmp_config):
    result = schema_loader.A8_get_initial_scenario_check_prompt(tmp_config)
    initial = result["scenario_self_check_initial"]
    assert "scenario_discriminators" in initial
    assert set(initial["scenario_discriminators"]) == {
        "chatbot_mode",
        "work_agent_mode",
    }


def test_A9_invalid_scenario_falls_back(tmp_config, recwarn):
    result = schema_loader.A9_get_ongoing_scenario_check_prompt(
        tmp_config, "nope"
    )
    assert "scenario_self_check_initial" in result