"""mcp_server.tools.system_prompt — persona_get_system_prompt 工具

返回人格模块强制组装的完整 system_prompt（问题 1）。
work agent 启动时调用，不再在 opencode 配置里写死人格声明。

来源：Debug_v1_1 问题 1（harness 提升为 prompt 强制组装器）
"""

from __future__ import annotations

from typing import Any

from persona_runtime.config import Config
from persona_runtime.harness import create_harness


def persona_get_system_prompt(config: Config) -> dict[str, Any]:
    """persona_get_system_prompt — 返回完整人格 system_prompt。

    input:
      config: 人格模块配置
    output:
      data.system_prompt: Harness.build_system_prompt() 组装结果
    errors:
      yaml 必填字段缺失 / schema 不存在 → 拒绝
    """
    h = create_harness(config)
    try:
        sp = h.build_system_prompt(config)
        return {"data": {"system_prompt": sp}}
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}
    finally:
        if h.conn is not None:
            h.conn.close()