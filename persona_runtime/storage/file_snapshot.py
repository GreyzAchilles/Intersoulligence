"""persona_runtime.storage.file_snapshot — 快照存储的 JSON 文件实现

F1/F2 的文件逻辑自 persistence.py 转正为 SnapshotStore 端口实现。
快照层天然后端无关（JSON 文件），与 Layer 2 的数据库选型解耦。
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any


class FileSnapshotStore:
    def __init__(self, snapshot_dir: Path) -> None:
        self._dir = Path(snapshot_dir)

    def save(self, snapshot: dict[str, Any]) -> str:
        """落盘快照，返回路径。路径冲突自动备份上一份；IO 失败警告后返回预期路径。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{snapshot['id']}.json"
        if path.exists():
            backup = self._dir / f"{snapshot['id']}.bak.json"
            try:
                path.rename(backup)
            except OSError as e:
                warnings.warn(f"F1 backup failed: {e}")
        try:
            path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as e:
            warnings.warn(f"F1 snapshot write failed: {e} — keep in-memory")
        return str(path)

    def load_latest(self) -> dict[str, Any] | None:
        """最近一份可用快照；无 → None；损坏文件警告后回退上一份。"""
        if not self._dir.exists():
            return None
        snapshots = sorted(
            [p for p in self._dir.glob("snap_*.json")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not snapshots:
            return None
        for path in snapshots:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as e:
                warnings.warn(f"F2 snapshot {path.name} corrupted: {e} — try previous")
                continue
        return None
