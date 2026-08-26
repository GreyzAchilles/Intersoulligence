"""persona_runtime.config — 配置加载

加载人格模块运行所需路径配置：
- 数据目录 / schema 路径 / SQLite db 路径 / 快照目录

来源：PRD §11 序号 8
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    """默认数据目录：<package>/../data。"""
    return Path(__file__).resolve().parent.parent / "data"


@dataclass
class Config:
    """人格模块运行配置。

    所有路径默认相对于工程 data/ 目录，但允许通过环境变量或
    构造参数覆盖（便于测试用临时目录）。
    """

    data_dir: Path = field(default_factory=_default_data_dir)
    schema_path: Path = field(init=False)
    db_path: Path = field(init=False)
    snapshot_dir: Path = field(init=False)

    # harness 行为参数
    snapshot_interval: int = 20
    decay_interval: int = 20
    short_window_size: int = 10
    long_window_size: int = 100

    # 2d 触发节流
    trigger_dedup_turns: int = 5
    trigger_max_per_window: int = 1

    # 2d 衰减 TTL（天）
    ledger_ttl_days: int = 180

    # 2a 三阶段衰减阈值（天）
    cooling_days: int = 14
    vector_delete_days: int = 30
    content_wipe_days: int = 90

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.schema_path = self.data_dir / "persona_schema.yaml"
        self.db_path = self.data_dir / "persona.db"
        self.snapshot_dir = self.data_dir / "snapshots"
        self.schema_path = Path(
            os.environ.get("PERSONA_SCHEMA_PATH", str(self.schema_path))
        )
        self.db_path = Path(os.environ.get("PERSONA_DB_PATH", str(self.db_path)))
        self.snapshot_dir = Path(
            os.environ.get("PERSONA_SNAPSHOT_DIR", str(self.snapshot_dir))
        )


def load_config(
    data_dir: Path | str | None = None,
    schema_path: Path | str | None = None,
    db_path: Path | str | None = None,
    snapshot_dir: Path | str | None = None,
) -> Config:
    """构造 Config，允许显式覆盖路径。

    测试用例通过显式传参将所有路径指向 tmp_path。
    """
    cfg = Config(data_dir=Path(data_dir) if data_dir else _default_data_dir())
    if schema_path:
        cfg.schema_path = Path(schema_path)
    if db_path:
        cfg.db_path = Path(db_path)
    if snapshot_dir:
        cfg.snapshot_dir = Path(snapshot_dir)
    return cfg