#!/usr/bin/env python3
"""加载 ``schemas/conditions.yaml``，供 Condition Wizard 合并 BC 过滤器。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
DEFAULT_YAML = ROOT / "schemas" / "conditions.yaml"


def load_conditions_yaml(path: Optional[Path] = None) -> dict:
    """返回解析后的 YAML dict；失败时返回空 dict。"""
    p = Path(path) if path else DEFAULT_YAML
    if not p.is_file():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        return _parse_bc_filters_fallback(p)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _parse_bc_filters_fallback(path: Path) -> dict:
    """无 PyYAML 时的极简解析：只提取 ``bc_filters`` 下的列表。"""
    text = path.read_text(encoding="utf-8")
    out: dict[str, list[str]] = {}
    cur: Optional[str] = None
    in_filters = False
    for line in text.splitlines():
        if line.startswith("bc_filters:"):
            in_filters = True
            continue
        if not in_filters:
            continue
        if line and not line.startswith(" ") and not line.startswith("\t"):
            if line.strip() and not line.strip().startswith("#"):
                break
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.endswith(":") and not s.startswith("-"):
            cur = s[:-1].strip()
            out[cur] = []
            continue
        if s.startswith("- ") and cur:
            out[cur].append(s[2:].strip())
    return {"bc_filters": out} if out else {}


def load_bc_filters(path: Optional[Path] = None) -> dict[str, frozenset[str]]:
    """``{wizard_leaf: frozenset(Cond*)}``。"""
    data = load_conditions_yaml(path)
    raw = data.get("bc_filters") or {}
    result: dict[str, frozenset[str]] = {}
    for key, types in raw.items():
        if isinstance(types, (list, tuple)):
            result[str(key)] = frozenset(str(t) for t in types)
    return result
