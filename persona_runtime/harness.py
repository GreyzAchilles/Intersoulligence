"""persona_runtime.harness — C5+C6 强制约束点 + 主循环协调器

整合所有 runtime 子模块，实现：
- PRD §6.2「每轮响应闭环」
- PRD §6.3「阶段切换闭环」
- harness §6 "人格模块自包含原则"

来源：PRD §11 序号 17
       harness 定稿 §3 会话机制 / §5 边界识别
"""

from __future__ import annotations

import sqlite3
import warnings
from datetime import datetime, timezone
from typing import Any

from . import (
    memory_recall,
    memory_write,
    persistence,
    scheduler,
    schema_loader,
    self_check,
    signal_parser,
)
from .config import Config

UTC_FMT = "%Y-%m-%dT%H:%M:%S"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(UTC_FMT)


class Harness:
    """persona_runtime 主协调器。

    持有：
      - config
      - db connection
      - 运行时状态：turn / current_stage / current_scenario / dedup_state / check_freq
    """

    def __init__(self, config: Config, conn: sqlite3.Connection | None = None) -> None:
        self.config = config
        self.conn = conn or self._init_conn()
        self.turn = 0
        self.current_stage = "grill"
        self.current_scenario = ""
        self.subagent_first_switched = False
        self.dedup_state: dict[str, Any] = {
            "keyword_counts": {},
            "last_trigger_map": {},
            "last_self_eval_turn": -999,
        }
        self.long_window_violation_rate = 0.0
        self.short_window: list[bool] = []
        self.check_freq = self_check.CheckFrequencyManager()
        self.last_snapshot_turn = 0

    def _init_conn(self) -> sqlite3.Connection:
        from .db import get_connection

        return get_connection(self.config)

    # ----------------------------------------------------------------
    # 启动加载
    # ----------------------------------------------------------------
    def init(self) -> dict[str, Any]:
        """启动加载 — A1-A4/A6-A9 全部加载 + F2 快照恢复。"""
        # 加载 schema（A1）
        schema_loader.reset_cache()
        schema_loader.A1_load_persona_schema(self.config)
        loaded = {
            "A1": True,
            "A2": bool(schema_loader.A2_get_identity_anchors(self.config)["anchors"]),
            "A3": True,
            "A4": bool(schema_loader.A4_get_available_scenarios(self.config)["available_scenarios"]),
            "A6": True,
        }
        # F2 加载最近快照
        snap = persistence.F2_load_latest_snapshot(self.config)
        recovery = snap["loaded"]["recovery_action"]
        if snap["loaded"]["snapshot"]:
            s = snap["loaded"]["snapshot"]
            self.current_stage = s.get("current_stage", "grill")
            self.current_scenario = s.get("current_scenario", "")
            rate = s.get("short_window_violation_rate", 0.0)
            self.long_window_violation_rate = rate
            self.check_freq.set_long_window_rate(rate)
        return {"init": loaded, "recovery": recovery}

    # ----------------------------------------------------------------
    # 每轮响应闭环（PRD §6.2）
    # ----------------------------------------------------------------
    def process_turn(
        self,
        user_message: str,
        ai_response: str,
        recent_turns: list[str] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """每轮响应主闭环。

        turn 计数在末尾自增——首回合 process_turn 时 self.turn == 0，
        默认抽检模式 0 % 3 == 0 触发 E1 自检，符合「会话初始化即默认抽检」。

        协议信号来源（问题 2 结构化输出）：
          - tool_calls：LLM 通过 persona_runtime_op emit_* 发的结构化标记，优先于文本
          - ai_response：响应文本里的协议标记（兼容回退）
        """
        result: dict[str, Any] = {"turn": self.turn}

        # 1) A9 注入持续场景自检 prompt（不输给 LLM，仅记录）
        if self.current_scenario:
            result["ongoing_scenario_prompt"] = schema_loader.A9_get_ongoing_scenario_check_prompt(
                self.config, self.current_scenario
            )

        # 2) E1 价值层自检（按自检频率）
        if self.check_freq.should_check(self.turn):
            check = self_check.E1_value_self_check(
                ai_response, self.current_scenario or "chatbot_mode", self.config
            )
            violated = check["check"]["violated"]
            result["e1_check"] = check
            self.short_window.append(violated)
            if len(self.short_window) > 10:
                self.short_window = self.short_window[-10:]
            self.check_freq.record_violation(violated)
            if violated:
                memory_write.update_keyword_counts(user_message, self.dedup_state)
                result["e1_action"] = "regenerate"
        memory_write.update_keyword_counts(user_message, self.dedup_state)

        # 3) B1/B2 信号解析：tool call 优先，文本回退
        emit = self._extract_emit_signals(tool_calls)
        trans: dict[str, Any] | None = None
        scen: dict[str, Any] | None = None
        if emit["stage_transition"] is not None:
            trans = signal_parser.B1_parse_stage_transition(emit["stage_transition"])
        elif ai_response:
            trans = signal_parser.B1_parse_stage_transition(ai_response)
        if emit["scenario_check"] is not None:
            scen = signal_parser.B2_parse_scenario_check(emit["scenario_check"])
        elif ai_response:
            scen = signal_parser.B2_parse_scenario_check(ai_response)
        if emit["stage_transition"] is not None or emit["scenario_check"] is not None:
            result["signal_source"] = "tool_call"
        elif trans or scen:
            result["signal_source"] = "text"
        else:
            result["signal_source"] = "none"
        result["b1_parsed"] = trans
        result["b2_parsed"] = scen

        if trans:
            b3 = signal_parser.B3_validate_stage_transition(
                trans["parsed"],
                {"long_window_violation_rate": self.long_window_violation_rate},
            )
            result["b3_validated"] = b3
            if b3["validated"]["action"] == "switch":
                self._handle_stage_switch(trans["parsed"]["to"])
        if scen:
            available = schema_loader.A4_get_available_scenarios(self.config)[
                "available_scenarios"
            ]
            avail_names = [s["name"] for s in available]
            b4 = signal_parser.B4_validate_scenario_check(scen["parsed"], avail_names)
            result["b4_validated"] = b4
            # 仅当校验通过（switch）才写入场景；B4 对合法 initial 已返回 switch，
            # 无效/空 target 时 action=stay → 保持当前场景，避免写入白名单外值
            if b4["validated"]["action"] == "switch":
                self.current_scenario = b4["validated"]["target"]

        # 4) D7 触发 2d 自评
        trig = memory_write.D7_maybe_2d_trigger(
            {
                "user_message": user_message,
                "ai_response": ai_response,
                "value_violation_detected": result.get("e1_check", {}).get("check", {}).get("violated", False),
                "recent_5_turns": recent_turns or [],
                "turn": self.turn,
            },
            self.dedup_state,
        )
        result["d7_trigger"] = trig
        if trig["trigger"]["triggered"]:
            suggestion = trig["trigger"]["suggested_entry"]
            validation = memory_write.D8_validate_2d_entry(suggestion)
            result["d8_validated"] = validation
            if validation["validated"]["passed"]:
                write = memory_write.D6_append_2d_entry(
                    self.conn,
                    suggestion["change"],
                    suggestion["reason"],
                    suggestion["affected_layer"],
                )
                result["d6_appended"] = write
                self.dedup_state["last_self_eval_turn"] = self.turn
            self.dedup_state["last_trigger_map"][trig["trigger"]["reason"]] = self.turn

        # 5) 每 20 轮：F1 快照 + F4 衰减
        if self.turn - self.last_snapshot_turn >= self.config.snapshot_interval:
            snap = persistence.F1_take_snapshot(
                self.turn,
                self.conn,
                self.config,
                current_stage=self.current_stage,
                current_scenario=self.current_scenario,
                short_window_violation_rate=(
                    sum(1 for v in self.short_window if v) / max(1, len(self.short_window))
                ),
                trigger_decay=True,
            )
            result["f1_snapshot"] = snap
            self.last_snapshot_turn = self.turn

        self.turn += 1
        return result

    # ----------------------------------------------------------------
    # 召回注入（Layer 2 闭环，由 harness 编排）
    # ----------------------------------------------------------------
    def inject_recall(
        self,
        entities: list[str],
        time_range: dict[str, str] | None = None,
        entity: str | None = None,
        patterns: list[str] | None = None,
    ) -> dict[str, Any]:
        """C1-C6 召回 + 后处理流水线 → 返回可注入 prompt 的已标记已改写记录。"""
        result: dict[str, Any] = {}
        # 2a 召回 + C5/C6 后处理
        if entities:
            r2a = memory_recall.C1_recall_2a(
                entities, time_range or {}, self.conn
            )
            tagged = memory_recall.C5_apply_recall_permission(r2a["records"])
            rewritten = memory_recall.C6_rewrite_voice(tagged["tagged_records"], "2a")
            result["layer_2a_tagged"] = tagged["tagged_records"]
            result["layer_2a_rewritten"] = rewritten["rewritten"]
        # 2b 召回
        if entity:
            r2b = memory_recall.C2_recall_2b(entity, self.conn)
            result["layer_2b_profile"] = r2b["profile"]
            facts = r2b["profile"]["facts"]
            tagged = memory_recall.C5_apply_recall_permission(facts)
            rewritten = memory_recall.C6_rewrite_voice(tagged["tagged_records"], "2b")
            result["layer_2b_rewritten"] = rewritten["rewritten"]
        # 2c 召回
        if patterns is not None:
            r2c = memory_recall.C3_recall_2c(patterns, self.conn)
            tagged = memory_recall.C5_apply_recall_permission(r2c["records"])
            rewritten = memory_recall.C6_rewrite_voice(
                tagged["tagged_records"], "2c"
            )
            result["layer_2c_tagged"] = tagged["tagged_records"]
            result["layer_2c_rewritten"] = rewritten["rewritten"]
        return result

    # ----------------------------------------------------------------
    # stage 切换
    # ----------------------------------------------------------------
    def _handle_stage_switch(self, to: str) -> None:
        """切换阶段：to=grill 维持，to=plan_subagent 启动 subagent。"""
        if to == "grill":
            self.current_stage = "grill"
            return
        if to == "plan_subagent":
            roam = scheduler.G1_spawn_plan_subagent("")
            if not self.subagent_first_switched:
                scheduler.G4_inject_plan_subagent_first_switch_rule()
                self.subagent_first_switched = True
            self.current_stage = "plan_consulted"

    def _extract_emit_signals(
        self, tool_calls: list[dict[str, Any]] | None
    ) -> dict[str, dict[str, Any] | None]:
        """从 tool_calls 提取 emit_* 结构化信号参数（问题 2）。

        支持两种 tool call 形态：
          - {"operation": "emit_stage_transition", "params": {...}}
          - MCP 风格 {"name": "persona_runtime_op",
                       "params"/"arguments": {"operation": ..., "params": {...}}}
        """
        stage: dict[str, Any] | None = None
        scen: dict[str, Any] | None = None
        if not tool_calls:
            return {"stage_transition": stage, "scenario_check": scen}
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            op = tc.get("operation")
            payload = tc.get("params")
            if op is None:
                inner = tc.get("params") or tc.get("arguments") or {}
                if isinstance(inner, dict):
                    op = inner.get("operation")
                    payload = inner.get("params")
            if not isinstance(payload, dict):
                continue
            if op == "emit_stage_transition":
                stage = payload
            elif op == "emit_scenario_check":
                scen = payload
        return {"stage_transition": stage, "scenario_check": scen}

    # ----------------------------------------------------------------
    # 工具：直接测试用接口
    # ----------------------------------------------------------------
    def manual_init_scenario(self, scenario: str) -> dict[str, Any]:
        """在缺乏 LLM 时手动设场景（demo / 测试用）。"""
        available = schema_loader.A4_get_available_scenarios(self.config)[
            "available_scenarios"
        ]
        avail_names = [s["name"] for s in available]
        if scenario not in avail_names:
            warnings.warn(f"scenario {scenario} not in whitelist")
            return {"scenario": "", "error": "not in whitelist"}
        self.current_scenario = scenario
        return {"scenario": scenario}

    # ----------------------------------------------------------------
    # prompt 强制组装器（问题 1）：从 yaml 拼完整 system_prompt
    # ----------------------------------------------------------------
    def build_system_prompt(self, config: Config | None = None) -> str:
        """把人格声明组装成 LLM 看到的完整 system_prompt。

        组装 Layer 0（核心身份 / 价值内核 / 场景变体含判定特征）
        + Layer 1（表达规范）+ MCP 工具说明 + 结构化信号约束。
        LLM 永远看到「被封装好的人格」，不再依赖软提示。

        必填字段缺失 → ValueError（yaml 字段校验）。
        """
        cfg = config or self.config
        doc = schema_loader.get_raw_schema(cfg)

        layer0 = doc.get("layer0", {})
        identity = layer0.get("identity", {})
        if not identity or not identity.get("name"):
            raise ValueError("build_system_prompt: layer0.identity.name missing")
        vk = layer0.get("value_kernel", {})
        if not vk or not vk.get("inviolable_beliefs"):
            raise ValueError(
                "build_system_prompt: layer0.value_kernel empty — refuse to load persona module"
            )
        scenarios = schema_loader.A4_get_available_scenarios(cfg)[
            "available_scenarios"
        ]
        if not scenarios:
            raise ValueError("build_system_prompt: layer0.scenarios empty")
        layer1 = doc.get("layer1", {})
        if not layer1.get("voice"):
            raise ValueError("build_system_prompt: layer1.voice missing")

        lines: list[str] = []

        lines.append(f"你是 {identity.get('name', '')}，这是你的人格模块声明。")
        lines.append("以下内容由人格模块强制注入，运行期不可改写，请严格遵守。")
        lines.append("")

        # Layer 0.1 核心身份
        lines.append("【核心身份】")
        if identity.get("self_description"):
            lines.append(f"- 自我描述：{identity['self_description']}")
        if identity.get("origin"):
            lines.append(f"- 来历：{identity['origin']}")
        for t in identity.get("core_traits", []):
            lines.append(f"- 特质：{t}")
        lines.append("")

        # Layer 0.2 价值内核
        lines.append("【价值内核（不可改写）】")
        for b in vk.get("inviolable_beliefs", []):
            lines.append(f"- 信念：{b}")
        for r in vk.get("inviolable_refusals", []):
            lines.append(f"- 拒绝：{r}")
        for j in vk.get("judgment_principles", []):
            lines.append(f"- 判断原则：{j}")
        lines.append("")

        # Layer 0.3 场景价值变体 + 判定特征
        lines.append("【场景价值变体（含判定特征）】")
        for s in scenarios:
            name = s["name"]
            discr = s.get("discriminator", {})
            signals = "、".join(discr.get("signals", [])) or "（未声明）"
            tone = discr.get("tone_target", "") or s.get("voice_tone", "")
            lines.append(f"- {name}：判定信号 [{signals}]；目标语气 {tone}")
            priority = s.get("priority_subset", [])
            if priority:
                lines.append(f"  优先级：{'、'.join(priority)}")
        lines.append("")

        # Layer 1 表达规范
        lines.append("【表达规范】")
        voice = layer1.get("voice", {})
        for key, val in voice.items():
            lines.append(f"- {key}：{val}")
        catchphrases = layer1.get("catchphrases", [])
        if catchphrases:
            lines.append(f"- 口头禅：{'；'.join(catchphrases)}")
        addressing = layer1.get("addressing", {})
        if addressing.get("default"):
            lines.append(f"- 默认称呼：{addressing['default']}")
        if addressing.get("forbidden_terms"):
            lines.append(f"- 禁用称呼：{'、'.join(addressing['forbidden_terms'])}")
        aside = layer1.get("aside", {})
        if aside:
            lines.append(
                f"- 蛐蛐（~> 前缀单独成行）：格式「~> 内容」，每轮最多 {aside.get('max_per_turn', 2)} 条"
            )
        lines.append("")

        # 工具说明 + 结构化信号约束
        lines.append("【工具与行为约束】")
        lines.append(
            "- persona_layer0_get / persona_layer1_get：获取 Layer 0/1 声明与场景自检 prompt"
        )
        lines.append(
            "- persona_layer2_query：召回 / 写入 Layer 2 记忆（2a/2b/2c/2d）"
        )
        lines.append(
            "- persona_runtime_op：运行时操作（解析 / 自检 / 快照 / 衰减 / 调度）"
        )
        lines.append(
            "- persona_get_system_prompt：获取本份完整人格声明（本提示即其组装结果）"
        )
        lines.append(
            "- 阶段切换 / 场景自检必须通过 persona_runtime_op 的 "
            "emit_stage_transition(to, confidence) / emit_scenario_check(mode, target) "
            "结构化输出发送，不要写进响应文本。"
        )
        lines.append(
            "- 响应文本必须是干净的对话内容；文本中不要出现 [STAGE_TRANSITION] / "
            "[SCENARIO_CHECK] / [RESPONSE] 等协议标记字面量。"
        )
        lines.append("")

        return "\n".join(lines)


def create_harness(config: Config) -> Harness:
    """便捷入口。"""
    return Harness(config)