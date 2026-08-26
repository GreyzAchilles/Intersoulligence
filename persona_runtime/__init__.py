"""persona_runtime — 人机关系人格模块运行时

实现 25 个 v1 接口契约。

按模块组织：
- config         配置加载
- db             SQLite 连接 + schema 初始化
- schema_loader   A1-A4, A6-A9 加载类接口
- signal_parser  B1-B4 解析类接口
- memory_recall  C1-C6 召回类接口
- memory_write   D6-D9 写入类接口
- self_check     E1 自检类接口
- persistence    F1, F2, F4 持久化类接口
- scheduler      G1, G4 调度类接口
- harness        C5+C6 强制约束点 + 主循环协调器

来源：PRD.md / 接口-v1-按工程分类.md / 接口-v2-按Layer分类.md
"""

from .config import Config, load_config
from .db import connect, get_connection, init_schema
from .harness import Harness, create_harness
from . import (
    memory_recall,
    memory_write,
    persistence,
    scheduler,
    schema_loader,
    self_check,
    signal_parser,
)

__version__ = "0.1.0"

__all__ = [
    "Config",
    "load_config",
    "connect",
    "get_connection",
    "init_schema",
    "Harness",
    "create_harness",
    "schema_loader",
    "signal_parser",
    "memory_recall",
    "memory_write",
    "self_check",
    "persistence",
    "scheduler",
]