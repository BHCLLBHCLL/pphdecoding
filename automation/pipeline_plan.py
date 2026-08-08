#!/usr/bin/env python3
"""M2 预处理管线计划与 VBS 验收脚本生成。

把“Prepare Parts → Wrapping → Build Analysis Model → Octree → Mesh →
Save”的步骤序列化为 scFLOWpre VBScript 动作；命令名以 scFLOWpre
history.vbs 录制的实际名称为准，本模块提供默认映射并允许覆盖。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pph_parser import PphArchive

DEFAULT_STEPS = [
    "prepare_parts",
    "begin_wrapping",
    "execute_wrapping",
    "build_analysis_model",
    "generate_octree",
    "generate_mesh",
]

# 默认命令映射（待用真实 history.vbs 录制校准后锁定）
DEFAULT_COMMANDS: dict[str, str] = {
    "open_project": 'scFLOWpre.OpenProject "{path}"',
    "prepare_parts": "scFLOWpre.ReturnToPrepareParts",
    "begin_wrapping": "scFLOWpre.BeginWrapping",
    "execute_wrapping": "scFLOWpre.ExecuteWrapping",
    "build_analysis_model": "scFLOWpre.BuildAnalysisModel",
    "generate_octree": "scFLOWpre.GenerateOctree",
    "generate_mesh": "scFLOWpre.GenerateMesh",
    "save": 'scFLOWpre.SaveProject "{path}"',
    "quit": "scFLOWpre.Quit",
}

ROLE_MAP: dict[str, tuple[str, ...]] = {
    "mdl": ("surface_part_mdl", "surface_ridge_mdl"),
    "oct": ("octree",),
    "gph": ("volume_mesh_gph",),
}


@dataclass
class PipelinePlan:
    """一个预处理管线计划。"""

    project_path: str
    steps: list[str] = field(default_factory=lambda: list(DEFAULT_STEPS))
    commands: dict[str, str] = field(default_factory=dict)
    include_quit: bool = False

    def resolve_commands(self) -> dict[str, str]:
        merged = dict(DEFAULT_COMMANDS)
        merged.update(self.commands)
        return merged

    def to_vbs_actions(self) -> list[str]:
        cmds = self.resolve_commands()
        actions = [cmds["open_project"].format(path=self.project_path)]
        for step in self.steps:
            if step not in cmds:
                raise ValueError(f"unknown pipeline step: {step}")
            actions.append(cmds[step])
        if self.include_quit:
            actions.append(cmds["quit"])
        return actions

    def write_vbs(self, path: str | Path) -> Path:
        from automation.vbs_bridge import write_vbs_file

        return write_vbs_file(self.to_vbs_actions(), path,
                              title="scFLOWpre M2 pipeline plan")

    def verify_outputs(self, pph_path: Optional[str | Path] = None,
                       roles: tuple[str, ...] = ("mdl", "oct", "gph")) -> dict:
        """校验执行结果：PPH 中是否出现 MDL/OCT/GPH 成员。"""
        target = pph_path or self.project_path
        arch = PphArchive.open(str(target))
        counts: dict[str, int] = {}
        for role in roles:
            counts[role] = sum(len(arch.by_role(r)) for r in ROLE_MAP[role])
        return {"pph": str(target), "member_count": len(arch.members),
                "role_counts": counts}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="生成 scFLOWpre M2 预处理管线 VBS 计划")
    ap.add_argument("project", help="PPH 项目路径")
    ap.add_argument("--steps", nargs="*", default=list(DEFAULT_STEPS),
                    help="管线步骤（默认全流程）")
    ap.add_argument("--output", required=True, help="输出 .vbs 路径")
    ap.add_argument("--verify", action="store_true",
                    help="校验项目是否已有 MDL/OCT/GPH 成员")
    ap.add_argument("--quit", action="store_true", help="脚本末尾退出 scFLOWpre")
    args = ap.parse_args(argv)

    plan = PipelinePlan(project_path=args.project, steps=args.steps,
                        include_quit=args.quit)
    plan.write_vbs(args.output)
    print(f"plan -> {args.output}")
    if args.verify:
        result = plan.verify_outputs()
        print(f"verify: {result['role_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
