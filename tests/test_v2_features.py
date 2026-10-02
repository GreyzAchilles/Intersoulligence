"""tests/test_v2_features.py — v2 M2-M4 新能力单元测试

D1/D2 写侧校验、Scribe 规则提取、F3 三路落点、EmbeddingProvider /
find_similar、C1 双路召回 + C5 语义联动、upsert_from_cluster、
Librarian 规则聚类、overlay（A11 / 2d 挂钩 / prompt 渲染）。
"""

from __future__ import annotations

import pytest

from persona_runtime import librarian, memory_recall, memory_write, overlay as overlay_mod, persistence, scribe
from persona_runtime.storage import HashingEmbeddingProvider, SQLiteStorage


# ---------------------------------------------------------------------------
# D1 / D2（M2 写侧接口层）
# ---------------------------------------------------------------------------
def test_D1_append_and_recall_roundtrip(backend):
    out = memory_write.D1_append_2a_entry(
        backend,
        {"content": "用户喜欢直接读论文", "type": "preference", "entities": ["论文"]},
    )
    assert "appended" in out
    records = backend.interactions.find_by_entities(["论文"], None)
    assert records[0]["content"] == "用户喜欢直接读论文"
    assert records[0]["source_conversation"] is None


def test_D1_rejects_overlong_content(backend):
    with pytest.raises(ValueError):
        memory_write.D1_append_2a_entry(
            backend, {"content": "长" * 81, "type": "observation"}
        )


def test_D1_rejects_unknown_type(backend):
    with pytest.raises(ValueError):
        memory_write.D1_append_2a_entry(backend, {"content": "x", "type": "diary"})


def test_D2_batch_atomic(backend):
    entries = [
        {"content": f"事实{i}", "type": "event"} for i in range(3)
    ]
    out = memory_write.D2_append_2a_batch(backend, entries)
    assert out["appended"]["count"] == 3
    # 坏条目 → 整批回滚
    with pytest.raises(ValueError):
        memory_write.D2_append_2a_batch(
            backend, [{"content": "好的", "type": "event"}, {"content": "", "type": "event"}]
        )


# ---------------------------------------------------------------------------
# Scribe（M2 规则提取）
# ---------------------------------------------------------------------------
def test_scribe_extracts_preference_and_fact():
    entries = scribe.extract_entries(
        "我喜欢直接读论文，我是工科生，昨天去了自贡", ""
    )
    types = {e["type"] for e in entries}
    assert "preference" in types and "observation" in types
    assert all(len(e["content"]) <= 80 for e in entries)


def test_scribe_max_per_turn_and_dedup():
    entries = scribe.extract_entries("我喜欢A。我喜欢A。我喜欢B。我喜欢C。我喜欢D。", "")
    assert len(entries) <= scribe.MAX_PER_TURN
    assert len({e["content"] for e in entries}) == len(entries)


def test_scribe_extract_fn_overrides_rules():
    custom = [{"content": "LLM 提取", "type": "reflection"}]
    out = scribe.extract_entries("我喜欢规则匹配的内容", "", extract_fn=lambda u, a: custom)
    assert out == custom


def test_scribe_turn_writes_via_D2(backend):
    out = scribe.scribe_turn(backend, "我喜欢收集手办", "好的", session_id="sess_1")
    assert out["scribe"]["extracted"] == 1
    traj = backend.interactions.find_by_conversation("sess_1")
    assert traj and traj[0]["type"] == "preference"


def test_scribe_turn_empty_no_write(backend):
    out = scribe.scribe_turn(backend, "嗯", "好")
    assert out["scribe"]["extracted"] == 0


# ---------------------------------------------------------------------------
# F3 会话总结（M2：三路落点 + 2b/2d 边界）
# ---------------------------------------------------------------------------
def test_F3_full_persistence(tmp_config, backend):
    scribe.scribe_turn(backend, "我喜欢直接读论文", "好", session_id="s1")
    scribe.scribe_turn(backend, "我在准备考试", "加油", session_id="s1")
    out = persistence.F3_persist_session_summary("s1", backend, tmp_config)
    assert out["persisted"] is True
    # ① episode 落 2a
    assert out["episode_id"] > 0
    traj = backend.interactions.find_by_conversation("s1")
    assert traj[-1]["type"] == "episode"
    # ② 2b current_status 更新
    assert out["entity_updates"] == {}
    # ③ markdown 投影
    assert out["markdown_path"] and "sessions" in out["markdown_path"]


def test_F3_updates_2b_when_entities_known(tmp_config, backend):
    backend.entities.ensure("自贡", "2026-08-01T00:00:00")
    memory_write.D1_append_2a_entry(
        backend, {"content": "昨天去了自贡", "type": "event", "entities": ["自贡"],
                  "source_conversation": "s2"}
    )
    out = persistence.F3_persist_session_summary("s2", backend, tmp_config)
    assert "自贡" in out["entity_updates"]
    profile = backend.entities.get("自贡")
    assert profile["current_status"] and "s2" in profile["current_status"][0]["content"]


def test_F3_empty_session_noop(tmp_config, backend):
    out = persistence.F3_persist_session_summary("不存在", backend, tmp_config)
    assert out["persisted"] is False


def test_F3_never_writes_2d(tmp_config, backend):
    scribe.scribe_turn(backend, "我喜欢直接读论文", "好", session_id="s3")
    persistence.F3_persist_session_summary("s3", backend, tmp_config)
    assert backend.ledger.recent(0) == []


# ---------------------------------------------------------------------------
# M3 语义召回
# ---------------------------------------------------------------------------
def test_hashing_embedding_deterministic_and_normalized():
    p = HashingEmbeddingProvider(dim=32)
    v1, v2 = p.embed(["我喜欢直接读论文", "我喜欢直接读论文"])
    assert v1 == v2
    assert abs(sum(x * x for x in v1) - 1.0) < 1e-9
    assert p.dimension == 32


def test_find_similar_returns_similar_first(tmp_config):
    provider = HashingEmbeddingProvider(dim=256)
    backend = SQLiteStorage.from_config(tmp_config, embedding_provider=provider)
    try:
        backend.interactions.append_entry(
            {"content": "用户喜欢直接读论文", "type": "preference", "timestamp": "2026-08-14T10:00:00"}
        )
        backend.interactions.append_entry(
            {"content": "今天天气不错", "type": "event", "timestamp": "2026-08-15T10:00:00"}
        )
        q = provider.embed(["用户喜欢读论文原文"])[0]
        records = backend.interactions.find_similar(q, top_k=2)
        assert records[0]["content"] == "用户喜欢直接读论文"
    finally:
        backend.close()


def test_find_similar_without_provider_raises(tmp_config):
    from persona_runtime.storage import StorageNotSupported

    no_vec = SQLiteStorage.from_config(tmp_config, embedding_provider=None)
    try:
        with pytest.raises(StorageNotSupported):
            no_vec.interactions.find_similar([0.1], top_k=1)
    finally:
        no_vec.close()


def test_C1_dual_path_merges_channels(tmp_config):
    provider = HashingEmbeddingProvider(dim=256)
    backend = SQLiteStorage.from_config(tmp_config, embedding_provider=provider)
    try:
        backend.interactions.append_entry(
            {"content": "用户喜欢直接读论文", "type": "preference",
             "entities": ["论文"], "timestamp": "2026-08-14T10:00:00"}
        )
        out = memory_recall.C1_recall_2a(
            ["论文"], {}, backend, semantic_query="用户喜欢读论文原文"
        )
        rec = out["records"][0]
        assert rec["recall_channels"] == ["entity", "semantic"]
    finally:
        backend.close()


def test_C5_semantic_only_is_capped_at_cautious():
    records = [{
        "content": "x", "entities": ["a"], "channel": "direct",
        "timestamp": "2026-10-01T00:00:00", "recall_channels": ["semantic"],
    }]
    tagged = memory_recall.C5_apply_recall_permission(records)
    assert tagged["tagged_records"][0]["permission"] == "cautious"


# ---------------------------------------------------------------------------
# M4 upsert_from_cluster + Librarian
# ---------------------------------------------------------------------------
def test_upsert_from_cluster_insert_then_merge(backend):
    first = backend.patterns.upsert_from_cluster("用户偏好递进追问", 0.3, 2, "2026-08-14T10:00:00")
    assert first["merged"] is False
    second = backend.patterns.upsert_from_cluster("用户偏好递进追问", 0.2, 3, "2026-08-15T10:00:00")
    assert second["merged"] is True
    assert second["confidence"] == 0.3  # 只增不减
    assert second["evidence_count"] == 5  # 累计


def test_librarian_clusters_cooling_preferences(backend):
    # 两句相近的偏好 + 一句无关 → 聚成 ≥1 簇，preference 优先
    backend.interactions.append_entry(
        {"content": "用户喜欢直接读论文", "type": "preference",
         "timestamp": "2026-08-01T10:00:00", "status": "cooling"}
    )
    backend.interactions.append_entry(
        {"content": "用户喜欢直接读论文原文", "type": "preference",
         "timestamp": "2026-08-02T10:00:00", "status": "cooling"}
    )
    out = librarian.cluster_cooling_patterns(backend)
    assert out["clusters"] >= 1
    assert backend.patterns.query(None)


def test_librarian_custom_cluster_fn():
    seen = {}

    def fake_cluster(rows):
        seen["rows"] = rows
        return [{"pattern": "固定模式", "confidence": 0.5, "evidence_ids": [1, 2]}]

    class FakeBackend:
        interactions = None
        patterns = None

    # 只验证 hook 被接管（不落库，FakeBackend 会炸——捕获后断言 hook 调用）
    class Interactions:
        @staticmethod
        def scan_decay_candidates():
            return [{"id": 1, "status": "cooling", "content": "x", "type": "preference",
                     "entities": [], "vector_indexed": 1, "last_accessed": "2026-08-01T00:00:00"}]

    class Patterns:
        @staticmethod
        def upsert_from_cluster(pattern, confidence, evidence_count, last_accessed):
            return {"id": 9, "pattern": pattern, "confidence": confidence,
                    "evidence_count": evidence_count, "merged": False}

    backend = FakeBackend()
    backend.interactions = Interactions()
    backend.patterns = Patterns()
    out = librarian.cluster_cooling_patterns(backend, cluster_fn=fake_cluster)
    assert seen["rows"] and out["upserted"][0]["pattern"] == "固定模式"


# ---------------------------------------------------------------------------
# M4 overlay
# ---------------------------------------------------------------------------
def test_A11_missing_overlay_returns_empty(tmp_config):
    assert overlay_mod.A11_load_persona_overlay(tmp_config) == overlay_mod.empty_overlay()


def test_A11_rejects_layer0_keys(tmp_config):
    import yaml

    path = overlay_mod.overlay_path(tmp_config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"layer0": {"name": "冒充"}}), encoding="utf-8")
    with pytest.raises(ValueError):
        overlay_mod.A11_load_persona_overlay(tmp_config)


def test_overlay_append_and_prompt_render(tmp_config):
    out = overlay_mod.append_2d_adjustment(
        tmp_config, "语气更克制", "用户反馈我话太多", "2026-10-01T00:00:00", ledger_id=1
    )
    assert out["adjustments"] == 1
    loaded = overlay_mod.A11_load_persona_overlay(tmp_config)
    section = overlay_mod.render_prompt_section(loaded)
    assert "语气更克制" in section
    assert "演化调整" in section


def test_overlay_render_empty_is_blank(tmp_config):
    assert overlay_mod.render_prompt_section(overlay_mod.empty_overlay()) == ""


def test_harness_process_turn_writes_overlay(tmp_config, harness):
    # "辛苦了" 触发 D7 user_feedback → suggested_entry affected_layer="Layer 1"
    proc = harness.process_turn("辛苦了这次任务", "好的老板")
    assert proc["d7_trigger"]["trigger"]["triggered"] is True
    assert "overlay_written" in proc
    overlay = overlay_mod.A11_load_persona_overlay(tmp_config)
    assert overlay["adjustments"]
    # prompt 合成生效
    sp = harness.build_system_prompt()
    assert "演化调整" in sp
