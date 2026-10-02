"""tests/test_memory_lifecycle.py — M5 canned 记忆增长闭环（v2 验收线 ②）

验证人格模块「能长期活着」：对话 → 2a 写入（Scribe/D1/D2）→ 召回
（精确 + 语义双路）→ F3 会话总结（2a episode + 2b + markdown 投影）
→ F4 衰减 → 2c 聚类（Librarian）→ 2d 自评 → Layer 1 overlay 演化
→ system_prompt 合成变化。全程 canned、零 LLM。
"""

from __future__ import annotations

from pathlib import Path

from persona_runtime import (
    librarian,
    memory_recall,
    memory_write,
    overlay as overlay_mod,
    persistence,
    scribe,
)
from persona_runtime.storage import SQLiteStorage


def test_memory_growth_lifecycle(tmp_config):
    backend = SQLiteStorage.from_config(tmp_config)
    try:
        # ---- 第一阶段：多轮对话，Scribe 每轮写入 2a ----
        dialogue = [
            ("你好呀", "老板好"),
            ("我喜欢直接读论文，别老给我摘要", "收到"),
            ("我在准备考研，最近在刷题", "加油"),
            ("昨天去了自贡找我朋友", "玩得开心"),
            ("我喜欢把复杂问题拆解", "这个习惯不错"),
        ]
        known = ["自贡", "考研", "论文"]
        for user, ai in dialogue:
            scribe.scribe_turn(backend, user, ai, session_id="life_s1", known_entities=known)
        before = len(backend.interactions.find_by_conversation("life_s1"))
        assert before >= 3, f"Scribe 应至少写入 3 条，实际 {before}"

        # ---- 第二阶段：召回——精确 + 语义双路 ----
        records = memory_recall.C1_recall_2a(["自贡"], {}, backend)
        assert records["records"]
        # 语义路：注入 provider 的 backend 上按内容相似命中
        provider = backend.embedding_provider
        assert provider is not None
        vec = provider.embed(["读论文原文"])[0]
        semantic = backend.interactions.find_similar(vec, top_k=3)
        assert semantic and "论文" in semantic[0]["content"]
        # C5/C6 后处理链路
        tagged = memory_recall.C5_apply_recall_permission(records["records"])
        rewritten = memory_recall.C6_rewrite_voice(tagged["tagged_records"], "2a")
        assert rewritten["rewritten"]

        # ---- 第三阶段：F3 会话总结三路落点 ----
        out = persistence.F3_persist_session_summary("life_s1", backend, tmp_config)
        assert out["persisted"] is True
        traj = backend.interactions.find_by_conversation("life_s1")
        assert traj[-1]["type"] == "episode"
        assert Path(out["markdown_path"]).exists()
        assert "会话总结" in Path(out["markdown_path"]).read_text(encoding="utf-8")

        # ---- 第四阶段：F4 衰减——把若干行推入冷却期再触发 ----
        import sqlite3

        backend.conn.execute(
            "UPDATE interaction_memory SET last_accessed = ?, status = 'cooling' "
            "WHERE type = 'preference'",
            ("2026-07-01T00:00:00",),
        )
        backend.conn.commit()
        now = "2026-10-02T00:00:00"
        report = persistence.F4_apply_decay(now, backend, tmp_config)
        # 30 天阈值：cooling 行 vector_indexed=1 → 进入 vector_deleted 名单
        assert report["layer_2a"]["vector_deleted"]

        # ---- 第五阶段：2c 聚类（Librarian）——preference 凝聚成模式 ----
        cluster = librarian.cluster_cooling_patterns(backend, now=now)
        assert cluster["clusters"] >= 1
        patterns = backend.patterns.query(None)
        assert patterns
        top = patterns[0]
        assert top["confidence"] >= 0.3
        # 重复聚类 → confidence 只增 / evidence 累计
        again = librarian.cluster_cooling_patterns(backend, now=now)
        top_after = backend.patterns.query(None)[0]
        assert top_after["evidence_count"] >= top["evidence_count"]

        # ---- 第六阶段：2d 自评 → overlay 演化 → prompt 合成 ----
        write = memory_write.D6_append_2d_entry(
            backend, "语气更克制", "用户反馈我话太多", "Layer 1"
        )
        assert "appended" in write
        overlay_mod.append_2d_adjustment(
            tmp_config,
            "语气更克制",
            "用户反馈我话太多",
            write["appended"]["timestamp"],
            write["appended"]["id"],
        )
        overlay = overlay_mod.A11_load_persona_overlay(tmp_config)
        section = overlay_mod.render_prompt_section(overlay)
        assert "语气更克制" in section

        # ---- 第七阶段：账本可召回（C4）----
        ledger = memory_recall.C4_recall_2d(5, backend)
        assert any("语气更克制" == r["change"] for r in ledger["records"])
    finally:
        backend.close()


def test_lifecycle_via_harness_process_turn(tmp_config):
    """process_turn 主闭环内 Scribe 自动写入（无需手动调用）。"""
    from persona_runtime import create_harness

    h = create_harness(tmp_config)
    try:
        h.init()
        h.session_id = "harness_s1"
        h.process_turn("我喜欢直接读论文", "好的老板")
        traj = h.backend.interactions.find_by_conversation("harness_s1")
        assert traj and traj[0]["type"] == "preference"
        assert traj[0]["source_conversation"] == "harness_s1"
    finally:
        h.backend.close()
