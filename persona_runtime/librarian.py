"""persona_runtime.librarian — 2c 聚类 deep cycle（v2 M4，Librarian 组件）

冷却期（cooling）2a 行 → 模式候选聚类 → PatternRepo.upsert_from_cluster：
命中既有 pattern → confidence 只增 + evidence_count 累计（UNIQUE 去重）；
未命中 → 新建（confidence 初始 0.3）。

实现定位（如实声明）：
  - 架构 §13.5 说「聚类由 LLM 完成」；M4 交付为**规则聚类起步**——
    默认用 HashingEmbeddingProvider 余弦相似度做贪心凝聚聚类，
    零 LLM 依赖、可单测
  - LLM 聚类挂点：`cluster_cooling_patterns(..., cluster_fn=...)`，
    接入人格 LLM 后由调用方注入
"""

from __future__ import annotations

from typing import Any, Callable

from .storage import HashingEmbeddingProvider, StorageBackend, utc_now_iso

INITIAL_CONFIDENCE = 0.3
DEFAULT_MIN_SIMILARITY = 0.6
DEFAULT_CLUSTER_FN = None  # 占位：类型注解见 cluster_cooling_patterns


def _default_cluster_fn(
    rows: list[dict[str, Any]],
    provider: Any,
    min_similarity: float,
) -> list[dict[str, Any]]:
    """贪心凝聚聚类：与簇心余弦 ≥ min_similarity 即入簇，否则新建簇。"""
    clusters: list[dict[str, Any]] = []
    vectors: list[list[float]] = []
    for row in rows:
        vec = provider.embed([row["content"]])[0]
        best: dict[str, Any] | None = None
        best_sim = 0.0
        for cluster, centroid in zip(clusters, vectors):
            sim = _cosine(vec, centroid)
            if sim >= min_similarity and sim > best_sim:
                best, best_sim = cluster, sim
        if best is None:
            clusters.append({"members": [row], "centroid": list(vec)})
            vectors.append(list(vec))
        else:
            best["members"].append(row)
            # 簇心 = 成员向量的均值（增量更新）
            n = len(best["members"])
            for i in range(len(centroid)):
                centroid[i] += (vec[i] - centroid[i]) / n
    return clusters


def _cosine(a: list[float], b: list[float]) -> float:
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (norm_a * norm_b)


def cluster_cooling_patterns(
    backend: StorageBackend,
    now: str | None = None,
    provider: Any | None = None,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    cluster_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """对 cooling 期 2a 行做模式聚类并落 2c。

    候选优先级：type=preference 的行；无则退回全部 cooling 行。
    cluster_fn 签名：rows -> [{pattern: str, confidence: float, evidence_ids: list[int]}]。
    """
    ts = now or utc_now_iso()
    candidates = [
        r for r in backend.interactions.scan_decay_candidates()
        if r["status"] == "cooling" and r.get("content")
    ]
    if not candidates:
        return {"clusters": 0, "upserted": []}
    preference_rows = [r for r in candidates if r.get("type") == "preference"]
    rows = preference_rows or candidates

    if cluster_fn is not None:
        clusters = cluster_fn(rows)
    else:
        provider = provider or HashingEmbeddingProvider()
        clusters = _default_cluster_fn(rows, provider, min_similarity)

    upserted = []
    for cluster in clusters:
        if cluster_fn is not None:
            pattern = str(cluster["pattern"])[:80]
            confidence = float(cluster.get("confidence", INITIAL_CONFIDENCE))
            evidence = len(cluster.get("evidence_ids", [])) or 1
        else:
            members = cluster["members"]
            pattern = max((m["content"] for m in members), key=len)[:80]
            confidence = min(INITIAL_CONFIDENCE + 0.1 * (len(members) - 1), 1.0)
            evidence = len(members)
        result = backend.patterns.upsert_from_cluster(
            pattern, confidence, evidence, ts
        )
        upserted.append(result)
    return {"clusters": len(upserted), "upserted": upserted}
