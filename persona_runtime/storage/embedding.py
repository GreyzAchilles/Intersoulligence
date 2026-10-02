"""persona_runtime.storage.embedding — EmbeddingProvider 默认实现（v2 M3）

HashingEmbeddingProvider：字符 bigram 哈希到固定维度的本地确定性向量，
L2 归一化后可直接做余弦相似度。

定位（如实声明）：
  - 这是零依赖、离线、确定性的「弱语义」实现——相近文本共享 bigram →
    相似度升高，足以验证双路召回 / C5 联动链路与做规则聚类
  - 不是神经语义模型。接入本地小模型（1B-7B 量化方向）或 API provider
    时只需实现 base.EmbeddingProvider 并注入 SQLiteStorage(embedding_provider=...)
"""

from __future__ import annotations

import hashlib
import math
from typing import Sequence


def _tokenize(text: str) -> list[str]:
    text = "".join(text.split())  # 去空白，保留中英文混合的 bigram 连续性
    if len(text) < 2:
        return [text] if text else []
    return [text[i : i + 2] for i in range(len(text) - 1)]


class HashingEmbeddingProvider:
    """字符 bigram 哈希嵌入（默认 dim=256）。

    dim=64 实测会出现共享 bigram 被其他 token 碰撞对消的退化情形
    （相似文本余弦归零），256 维下此类对消基本消失。
    """

    def __init__(self, dim: int = 256) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for token in _tokenize(str(text)):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "little") % self._dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            return vec
        return [x / norm for x in vec]
