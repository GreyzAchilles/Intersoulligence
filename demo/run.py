"""demo/run.py — demo work agent，跑通 PRD §8 12 步闭环

不接真实 LLM。所有「LLM 响应」用 canned response（脚本化的护栏人格输出）模拟。

运行：
    uv run python demo/run.py

输出会走 12 步闭环 + 最后打印 PASS/FAIL 判定。
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

# 让 demo 不依赖安装的包也能运行（sys.path 注入 repo root）
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from persona_runtime import (
    create_harness,
    memory_recall,
    memory_write,
    persistence,
    scheduler,
    schema_loader,
    signal_parser,
)
from persona_runtime.config import load_config
from tests.conftest import insert_entity, insert_interaction, insert_ledger, insert_pattern


REPO_SCHEMA = REPO_ROOT / "data" / "persona_schema.yaml"
assert REPO_SCHEMA.exists(), f"schema missing at {REPO_SCHEMA}"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
CANNED_RESPONSES = {
    "chatbot": "好呀，今天我陪你聊聊天。",
    "scenario_initial": "[SCENARIO_CHECK] initial: chatbot_mode\n[RESPONSE]嗯，找你聊天的",
    "scenario_stay": "[SCENARIO_CHECK] stay: chatbot_mode\n[RESPONSE]继续聊",
    "scenario_switch": "[SCENARIO_CHECK] switch_to: work_agent_mode\n[RESPONSE]代码事",
    "stage_switch": (
        "[STAGE_TRANSITION]\nto: plan_subagent\nconfidence: high\n[/STAGE_TRANSITION]\n"
        "我大概理清楚了，让我把它交给 plan 那边。"
    ),
    "stage_keep": (
        "[STAGE_TRANSITION]\nto: grill\nconfidence: high\n[/STAGE_TRANSITION]\n"
        "继续聊聊~"
    ),
    "value_violation": "我不是AI，我是真人哦",
    "value_clean": "好的，我帮你看一下。",
}


def make_config() -> load_config:
    tmp = Path(tempfile.mkdtemp(prefix="intersoull_demo_"))
    data_dir = tmp / "data"
    data_dir.mkdir()
    schema = data_dir / "persona_schema.yaml"
    shutil.copy(REPO_SCHEMA, schema)
    return load_config(
        data_dir=data_dir, schema_path=schema,
        db_path=data_dir / "persona.db", snapshot_dir=data_dir / "snapshots",
    )


# -----------------------------------------------------------------------------
# 12-step closed loop
# -----------------------------------------------------------------------------
def main() -> int:
    cfg = make_config()
    h = create_harness(cfg)
    schema_loader.reset_cache()
    h.init()
    assert h.init()["recovery"] == "fresh_start"

    results: list[tuple[str, bool, str]] = []

    # ----- Layer 0 闭环 -----
    # 1. 启动加载
    ok = (
        schema_loader.A1_load_persona_schema(cfg)["schema"]["layer0"]["protected"]
        and schema_loader.A2_get_identity_anchors(cfg)["anchors"]
        and schema_loader.A3_get_value_kernel(cfg)["value_kernel"]["inviolable_beliefs"]
        and schema_loader.A4_get_available_scenarios(cfg)["available_scenarios"]
        and schema_loader.A6_get_self_check_policy(cfg)["self_check_policy"] == "harness_managed"
    )
    results.append(("1.启动加载 A1/A2/A3/A4/A6", ok, ""))

    # 2. 快照加载（fresh_start）
    out_snap = persistence.F2_load_latest_snapshot(cfg)
    ok = out_snap["loaded"]["recovery_action"] == "fresh_start"
    results.append(("2.快照加载 F2 (fresh_start)", ok, ""))

    # 3. 首轮场景自检
    initial_prompt = schema_loader.A8_get_initial_scenario_check_prompt(cfg)
    parsed = signal_parser.B2_parse_scenario_check(CANNED_RESPONSES["scenario_initial"])
    available = [s["name"] for s in schema_loader.A4_get_available_scenarios(cfg)["available_scenarios"]]
    validated = signal_parser.B4_validate_scenario_check(parsed["parsed"], available)
    h.manual_init_scenario(validated["validated"]["target"])
    ok = validated["validated"]["action"] == "switch"
    results.append(("3.首轮场景自检 A8+B2+B4", ok, f"scenario={h.current_scenario}"))

    # ----- Layer 1 闭环 -----
    # 4. 持续场景自检
    ongoing_prompt = schema_loader.A9_get_ongoing_scenario_check_prompt(cfg, h.current_scenario)
    parsed = signal_parser.B2_parse_scenario_check(CANNED_RESPONSES["scenario_stay"])
    validated = signal_parser.B4_validate_scenario_check(parsed["parsed"], available)
    ok = validated["validated"]["action"] == "stay"
    results.append(("4.持续场景自检 A9+B2+B4", ok, ""))

    # 5. 价值层自检 — 触发违例
    violation_resp = CANNED_RESPONSES["value_violation"]
    proc = h.process_turn("你是真人吗", violation_resp)
    ok = proc.get("e1_check", {}).get("check", {}).get("violated") is True
    results.append(("5.价值层自检 E1 触发违例", ok, f"action={proc.get('e1_action')}"))

    # 6. 阶段切换
    turn_resp = CANNED_RESPONSES["stage_switch"]
    proc = h.process_turn("帮我把 plan 整理一下", turn_resp)
    ok = proc["b3_validated"]["validated"]["action"] == "switch"
    initiated = proc["b1_parsed"]["parsed"]["to"] == "plan_subagent"
    results.append(("6.阶段切换 B1+B3+G1", ok and initiated, f"stage={h.current_stage}"))

    # ----- Layer 2 闭环 -----
    # 7. 召回（按层）
    insert_interaction(h.conn, entities=["豆包"], content="提到豆包", last_accessed="2026-08-10T00:00:00")
    insert_entity(h.conn, entity="用户", facts=[{"content": "工科生", "confidence": 0.9}])
    insert_pattern(h.conn, pattern="偏好递进追问")
    insert_ledger(h.conn, change="语气更直接", reason="用户反馈")
    c1 = memory_recall.C1_recall_2a(["豆包"], {}, h.conn)
    c2 = memory_recall.C2_recall_2b("用户", h.conn)
    c3 = memory_recall.C3_recall_2c(["递进追问"], h.conn)
    c4 = memory_recall.C4_recall_2d(10, h.conn)
    ok = c1["records"] and c2["profile"]["facts"] and c3["records"] and c4["records"]
    results.append(("7.召回原始 C1/C2/C3/C4", ok, ""))

    # 8. 召回后处理
    tagged = memory_recall.C5_apply_recall_permission(c1["records"])
    rewritten = memory_recall.C6_rewrite_voice(tagged["tagged_records"], "2a")
    ok = tagged["tagged_records"][0]["permission"] in ("cite", "cautious", "associate-only")
    ok_rewrite = "你记得他" in rewritten["rewritten"][0]["content"]
    results.append(("8.召回后处理 C5+C6", ok and ok_rewrite, ""))

    # 9. Layer 2d 自评 — 用户反馈触发
    trig = memory_write.D7_maybe_2d_trigger(
        {"user_message": "辛苦了这次任务", "ai_response": "好", "turn": 5}
    )
    if trig["trigger"]["triggered"]:
        suggestion = trig["trigger"]["suggested_entry"]
        val = memory_write.D8_validate_2d_entry(suggestion)
        write = memory_write.D6_append_2d_entry(
            h.conn, suggestion["change"], suggestion["reason"], suggestion["affected_layer"]
        )
        ok = val["validated"]["passed"] and "appended" in write
    else:
        ok = False
    results.append(("9.2d 自评 D7/D8/D6", ok, ""))

    # 10. 2b 字段写入
    out = memory_write.D9_write_2b_entry(
        h.conn, "项目X", "facts", "新事实内容", "overwrite"
    )
    ok = out["written"]["mode"] == "overwrite"
    out = memory_write.D9_write_2b_entry(
        h.conn, "项目X", "current_status",
        {"content": "进行中", "timestamp": "2026-08-14T10:00:00"}, "covering_update"
    )
    ok &= out["written"]["mode"] == "covering_update"
    out = memory_write.D9_write_2b_entry(
        h.conn, "项目X", "judgment",
        {"content": "印象", "timestamp": "2026-08-14T10:00:00"}, "append"
    )
    ok &= out["written"]["mode"] == "append"
    results.append(("10.2b 字段写入 D9", ok, ""))

    # ----- 跨层辅佐闭环 -----
    # 11. 快照 + 衰减
    insert_interaction(
        h.conn, entities=["旧"], content="旧记录",
        last_accessed="2026-07-25T00:00:00", status="active",
    )
    snap = persistence.F1_take_snapshot(
        20, h.conn, cfg,
        current_stage=h.current_stage, current_scenario=h.current_scenario,
    )
    snap_path = Path(snap["snapshot"]["path"])
    decay = snap["snapshot"]["decay_report"]
    ok = snap_path.exists() and decay["layer_2a"]["cooling"]
    results.append(("11.快照+衰减 F1+F4", ok, f"cooling={decay['layer_2a']['cooling']}"))

    # 12. plan_subagent 启动
    rule = scheduler.G4_inject_plan_subagent_first_switch_rule()
    spawned = scheduler.G1_spawn_plan_subagent("grill output", injected_rule=rule["injected"]["rule"])
    ok = rule["injected"]["permanent"] and spawned["spawned"]["initial_state"] == "processing"
    results.append(("12.plan_subagent 启动 G4+G1", ok, f"subagent_id={spawned['spawned']['subagent_id']}"))

    # ----- 报告 -----
    print("\n" + "=" * 70)
    print("intersoulligence demo — PRD §8 12 步闭环")
    print("=" * 70)
    failed: list[str] = []
    for i, (name, ok, extra) in enumerate(results, 1):
        mark = "[PASS]" if ok else "[FAIL]"
        line = f"{mark} {name}"
        if extra:
            line += f" — {extra}"
        print(line)
        if not ok:
            failed.append(name)
    print("=" * 70)
    total = len(results)
    passed = total - len(failed)
    print(f"总计: {passed}/{total} 通过")
    if failed:
        print("失败步骤:")
        for f in failed:
            print(f"  - {f}")
        print("\nVerdict: FAIL")
        return 1
    print("\nVerdict: PASS — v1 关键路径闭环通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())