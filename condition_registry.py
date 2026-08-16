#!/usr/bin/env python3
"""条件 Schema 注册表。

汇总多个 PPH 项目中的 ``Cond*`` 条件类型、字段、区域引用，为通用条件
编辑器提供类型信息与校验入口。数据来源是 :mod:`schema_extract`。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pphxml
from pph_parser import PphArchive
from schema_extract import (condition_fields, extract_archive_schema,
                            merge_schemas)

# 枚举判定：字符串样本须为 token 形态（无空格），避免把自由文本当枚举
_TOKEN_RE = re.compile(r"^[A-Za-z_][\w.:/\-+]*$")
_ENUM_MAX_VALUES = 8


@dataclass
class ConditionField:
    name: str
    kind: str
    indexed: bool = False
    children: int = 0
    samples: list[str] = field(default_factory=list)
    count: int = 0  # 在该类型全部实例中出现的次数（0=旧数据未知）

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "indexed": self.indexed,
            "children": self.children,
            "samples": list(self.samples),
            "count": self.count,
        }

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "ConditionField":
        return cls(
            name=name,
            kind=data.get("kind", "string"),
            indexed=bool(data.get("indexed")),
            children=int(data.get("children", 0)),
            samples=list(data.get("samples", [])),
            count=int(data.get("count", 0)),
        )

    @property
    def enum_values(self) -> list[str]:
        """样本集形态良好时视为枚举候选（供下拉框），否则空表。

        规则：非空、去重后 ≤8 个、int/bool 全收、string 须全部为
        token 形态；float/empty/composite 不做枚举。
        """
        vals: list[str] = []
        for s in self.samples:
            if s and s not in vals:
                vals.append(s)
        if not vals or len(vals) > _ENUM_MAX_VALUES:
            return []
        if self.kind in ("float", "empty", "composite"):
            return []
        if self.kind == "string":
            if self.name in ("name", "type"):
                return []
            if not all(_TOKEN_RE.match(v) for v in vals):
                return []
        return vals


@dataclass
class ConditionType:
    name: str
    count: int = 0
    regions: list[str] = field(default_factory=list)
    fields: dict[str, ConditionField] = field(default_factory=dict)
    # 目录元数据（cond_types.json，二进制扫描 + HTML 帮助交叉核对）
    category: str = ""
    display: str = ""
    help_file: str = ""
    lineage: str = ""      # sample（pph 样本）/ gui / cmd
    sample_count: int = 0

    def field_meta(self, skip: tuple[str, ...] = ("type", "name")) -> list[dict]:
        """按首次出现顺序返回字段元数据（通用表单生成输入）。

        每项 ``{"name", "kind", "indexed", "children", "required",
        "enum": [...], "default"}``；``required=None`` 表示出现计数
        未知（旧 schema JSON），按可选渲染。
        """
        out: list[dict] = []
        for fname, f in self.fields.items():
            if fname in skip or fname == "regions" or fname.startswith(
                    "regions."):
                continue
            required = (True if f.count and self.count
                        and f.count >= self.count else
                        (False if f.count else None))
            out.append({
                "name": fname,
                "kind": f.kind,
                "indexed": f.indexed,
                "children": f.children,
                "required": required,
                "enum": f.enum_values,
                "default": (f.samples[0] if f.samples else ""),
            })
        return out

    def to_dict(self) -> dict:
        d = {
            "count": self.count,
            "regions": list(self.regions),
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
        }
        for k in ("category", "display", "help_file", "lineage"):
            v = getattr(self, k)
            if v:
                d[k] = v
        if self.sample_count:
            d["sample"] = self.sample_count
        return d

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "ConditionType":
        return cls(
            name=name,
            count=int(data.get("count", 0)),
            regions=list(data.get("regions", [])),
            fields={k: ConditionField.from_dict(k, v)
                    for k, v in data.get("fields", {}).items()},
            category=str(data.get("category", "")),
            display=str(data.get("display", "")),
            help_file=str(data.get("help", data.get("help_file", ""))),
            lineage=str(data.get("lineage", "")),
            sample_count=int(data.get("sample", 0)),
        )


class ConditionRegistry:
    """条件类型注册表（内存 + JSON 持久化）。"""

    def __init__(self, projects: Optional[list[str]] = None):
        self.projects: list[str] = projects or []
        self.types: dict[str, ConditionType] = {}
        self.aliases: dict[str, str] = {}  # 旧式类型名 → Cond* 规范名

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
                f.count += int(fdesc.get("count", 0))
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
        """校验单个 ``<condition>`` 元素：未知字段 / 类型不匹配 / 缺失必填。"""
        tname = cond.findtext("type", "")
        known = self.types.get(tname)
        issues: list[str] = []
        if known is None:
            issues.append(f"unknown condition type: {tname}")
            return {"type": tname, "issues": issues}
        present = condition_fields(cond)
        for fname, fdesc in present.items():
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
        # 缺失必填（仅当字段出现计数已知时判定）
        for fname, kf in known.fields.items():
            if fname in ("type", "name", "regions") or fname.startswith(
                    "regions."):
                continue
            if fname in present or not kf.count:
                continue
            if kf.count >= known.count:
                issues.append(f"missing required field: {fname}")
        return {"type": tname, "issues": issues}

    def resolve_alias(self, name: str) -> str:
        r"""旧式类型名 → 规范 ``Cond*`` 名（无别名定义时原样返回）。"""
        return self.aliases.get(name, name)

    def by_category(self, cats: list[str]) -> list[str]:
        """按目录 category 过滤类型名（含样本背书类型）。"""
        want = set(cats)
        return sorted(n for n, t in self.types.items()
                      if t.category in want)

    def merge_catalog(self, path: str | Path) -> int:
        """合并 ``cond_types.json`` 目录（P4-1）。

        样本已背书的类型回填 display/category/help 等元数据；
        其余二进制扫描类型以空字段形态入库（通用表单仅 name+regions，
        字段 schema 待更多样本补全）。返回新增类型数。
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.aliases.update(data.get("aliases", {}))
        added = 0
        for name, meta in data.get("types", {}).items():
            t = self.types.get(name)
            if t is None:
                t = self.types[name] = ConditionType(name=name)
                added += 1
            if not t.category:
                t.category = meta.get("category", "")
            if not t.display:
                t.display = meta.get("display", "")
            if not t.help_file:
                t.help_file = meta.get("help", "")
            if not t.lineage:
                t.lineage = "gui" if "GUI" in meta.get(
                    "evidence", []) else meta.get("lineage", "cmd")
            if meta.get("sample") and not t.sample_count:
                t.sample_count = int(meta["sample"])
        return added


def registry_from_archives(archives: list[PphArchive]) -> ConditionRegistry:
    """批量构建：合并 schema 后再转注册表。"""
    schemas = [(extract_archive_schema(a),
                a.by_role("project_xml")[0].name if a.by_role("project_xml")
                else "") for a in archives]
    return ConditionRegistry.from_schemas(schemas)
