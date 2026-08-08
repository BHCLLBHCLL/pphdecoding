#!/usr/bin/env python3
"""条件 Schema 注册表。

汇总多个 PPH 项目中的 ``Cond*`` 条件类型、字段、区域引用，为通用条件
编辑器提供类型信息与校验入口。数据来源是 :mod:`schema_extract`。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pphxml
from pph_parser import PphArchive
from schema_extract import (condition_fields, extract_archive_schema,
                            merge_schemas)


@dataclass
class ConditionField:
    name: str
    kind: str
    indexed: bool = False
    children: int = 0
    samples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "indexed": self.indexed,
            "children": self.children,
            "samples": list(self.samples),
        }

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "ConditionField":
        return cls(
            name=name,
            kind=data.get("kind", "string"),
            indexed=bool(data.get("indexed")),
            children=int(data.get("children", 0)),
            samples=list(data.get("samples", [])),
        )


@dataclass
class ConditionType:
    name: str
    count: int = 0
    regions: list[str] = field(default_factory=list)
    fields: dict[str, ConditionField] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "regions": list(self.regions),
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
        }

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "ConditionType":
        return cls(
            name=name,
            count=int(data.get("count", 0)),
            regions=list(data.get("regions", [])),
            fields={k: ConditionField.from_dict(k, v)
                    for k, v in data.get("fields", {}).items()},
        )


class ConditionRegistry:
    """条件类型注册表（内存 + JSON 持久化）。"""

    def __init__(self, projects: Optional[list[str]] = None):
        self.projects: list[str] = projects or []
        self.types: dict[str, ConditionType] = {}

    @classmethod
    def from_archive(cls, arch: PphArchive,
                     project_name: str = "") -> "ConditionRegistry":
        schema = extract_archive_schema(arch)
        if not project_name:
            project_name = schema.get("project", {}).get("name", "")
        return cls.from_schemas([(schema, project_name)])

    @classmethod
    def from_schemas(cls, schemas: list[tuple[dict, str]]) -> "ConditionRegistry":
        reg = cls()
        for schema, project in schemas:
            reg.add_schema(schema, project)
        return reg

    def add_schema(self, schema: dict, project: str = "") -> None:
        if project and project not in self.projects:
            self.projects.append(project)
        cond = schema.get("conditions", {})
        for tname, tentry in cond.get("types", {}).items():
            t = self.types.setdefault(tname, ConditionType(name=tname))
            t.count += int(tentry.get("count", 0))
            for r in tentry.get("regions", []):
                if r and r not in t.regions:
                    t.regions.append(r)
            for fname, fdesc in tentry.get("fields", {}).items():
                f = t.fields.setdefault(
                    fname,
                    ConditionField(
                        name=fname,
                        kind=fdesc.get("kind", "string"),
                        indexed=bool(fdesc.get("indexed")),
                        children=int(fdesc.get("children", 0)),
                    ),
                )
                for s in fdesc.get("samples", []):
                    if s and s not in f.samples:
                        f.samples.append(s)

    def type_names(self) -> list[str]:
        return sorted(self.types)

    def get(self, name: str) -> Optional[ConditionType]:
        return self.types.get(name)

    def summary(self) -> dict:
        return {
            "projects": list(self.projects),
            "condition_type_count": len(self.types),
            "condition_count": sum(t.count for t in self.types.values()),
            "types": {k: v.to_dict() for k, v in self.types.items()},
        }

    def to_dict(self) -> dict:
        return {
            "projects": list(self.projects),
            "types": {k: v.to_dict() for k, v in self.types.items()},
        }

    def save_json(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path

    @classmethod
    def load_json(cls, path: str | Path) -> "ConditionRegistry":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        reg = cls(projects=data.get("projects", []))
        for name, tdata in data.get("types", {}).items():
            reg.types[name] = ConditionType.from_dict(name, tdata)
        return reg

    def validate_condition(self, cond) -> dict:
        """校验单个 ``<condition>`` 元素：报告未知字段与类型不匹配。"""
        tname = cond.findtext("type", "")
        known = self.types.get(tname)
        issues: list[str] = []
        if known is None:
            issues.append(f"unknown condition type: {tname}")
            return {"type": tname, "issues": issues}
        for fname, fdesc in condition_fields(cond).items():
            if fname in ("type", "name", "regions"):
                continue
            kf = known.fields.get(fname)
            if kf is None:
                issues.append(f"unknown field: {fname}")
                continue
            if fdesc["children"] == 0 and kf.kind != "empty" \
                    and fdesc["kind"] != kf.kind:
                issues.append(
                    f"field type mismatch: {fname} "
                    f"expected={kf.kind} actual={fdesc['kind']}")
        return {"type": tname, "issues": issues}


def registry_from_archives(archives: list[PphArchive]) -> ConditionRegistry:
    """批量构建：合并 schema 后再转注册表。"""
    schemas = [(extract_archive_schema(a),
                a.by_role("project_xml")[0].name if a.by_role("project_xml")
                else "") for a in archives]
    return ConditionRegistry.from_schemas(schemas)
