#!/usr/bin/env python3
"""M2 预处理管线计划与 VBS 验收脚本生成。

命令名以 scFLOWpre 真实录制的 ``tests/box_vbs*.vbs``（v1/v3/v4）为准：

- ``LOCKED_COMMANDS``：已在录制中出现并锁定的命令（含行号证据）；
- ``UNLOCKED_COMMANDS``：录制中未出现、仍待验证的占位命令；
- Wrapping 高层命令（Begin/Execute Wrapping）在 v1-v4 录制中均未出现，
  由 NativeBridge 走 SCTprime 原生入口，不作为 VBS 默认管线。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pph_parser import PphArchive

# 实测锁定命令（来源 tests/box_vbs*.vbs，括号内为行号）
LOCKED_COMMANDS: dict[str, str] = {
    "open_cad_file": 'Doc_.OpenCadFile "{path}"',                    # :14 (v1)
    "open_project": 'Doc_.OpenProject "{path}", False',              # :4352 (v4)
    "begin_solid_edit": "MeshingGroup_.BeginSolidEdit",              # :14 (v4)
    "parts_control": (                                               # :16-18 (v1)
        'Conditions_.SetPartsControl "Wrapping", False'),
    "build_analysis_model": "MeshingGroup_.BuildAnalysisModel",      # :210 (v3)
    "generate_octree": "MeshingGroup_.CreateOctree",                 # :3110 (v1)
    "set_mode_octree": "Doc_.SetModeOctree",                         # :3112 (v1)
    "generate_mesh": (                                               # :5276,5283 (v1)
        "MeshingGroup_.CreateMeshMonitor\nDoc_.WaitForWorker"),
    "set_mode_mesh": "Doc_.SetModeMesh",                             # :5285 (v1)
    "save_project": 'Doc_.SaveProject "{path}"',                     # :7209 (v1)
}

# 录制中未出现、仍为待验证的占位命令（实机录制后移入 LOCKED_COMMANDS）。
# BeginWrapping / ExecuteWrapping 在 v1-v4 录制中均未出现，VBS 层不暴露，
# 由 NativeBridge 走 SCTprime 原生入口（CreateWrapOctreeByDefaultParam /
# ExecuteWrapping），不再作为 VBS 默认管线步骤。
UNLOCKED_COMMANDS: dict[str, str] = {
    "quit": "App_.Quit",
}

DEFAULT_COMMANDS: dict[str, str] = {
    **UNLOCKED_COMMANDS,
    **LOCKED_COMMANDS,
}

# 默认执行步骤（来自 box_vbs*.vbs 的实际流程；打开命令按文件类型自动选择）
DEFAULT_STEPS = [
    "begin_solid_edit",
    "parts_control",
    "build_analysis_model",
    "generate_octree",
    "set_mode_octree",
    "generate_mesh",
    "set_mode_mesh",
    "save_project",
]

# GUI Execute 面板复选框 -> PipelinePlan 步骤（顺序固定为 BAM → Octree → Mesh）
EXECUTE_STEP_MAP: dict[str, list[str]] = {
    "bam": ["build_analysis_model"],
    "oct": ["generate_octree", "set_mode_octree"],
    "mesh": ["generate_mesh", "set_mode_mesh"],
}
DEFAULT_EXECUTE_ORDER = ["bam", "oct", "mesh"]


def steps_from_execute_plan(plan: dict) -> list[str]:
    """把 Execute 面板勾选结果映射为管线步骤列表。"""
    steps: list[str] = []
    for key in DEFAULT_EXECUTE_ORDER:
        if plan.get(key):
            steps.extend(EXECUTE_STEP_MAP[key])
    return steps


ROLE_MAP: dict[str, tuple[str, ...]] = {
    "mdl": ("surface_part_mdl", "surface_ridge_mdl"),
    "oct": ("octree",),
    "gph": ("volume_mesh_gph",),
}

CAD_EXTENSIONS = {".x_t", ".x_b", ".step", ".stp", ".iges", ".igs", ".stl"}


def _looks_like_cad(path: str) -> bool:
    return Path(path).suffix.lower() in CAD_EXTENSIONS


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

    def open_command(self) -> str:
        cmds = self.resolve_commands()
        key = "open_cad_file" if _looks_like_cad(self.project_path) \
            else "open_project"
        return cmds[key].format(path=self.project_path)

    def to_vbs_actions(self) -> list[str]:
        cmds = self.resolve_commands()
        actions = [self.open_command()]
        for step in self.steps:
            if step not in cmds:
                raise ValueError(f"unknown pipeline step: {step}")
            template = cmds[step]
            if "{path}" in template:
                template = template.format(path=self.project_path)
            for line in template.splitlines():
                line = line.strip()
                if not line:
                    continue
                # 生成可在 scFLOWpre 宿主中直接运行的 VBS：
                # MeshingGroup_* 调用前先取 meshing group 对象。
                if line.startswith("MeshingGroup_."):
                    actions.append(
                        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)")
                actions.append(line)
        if self.include_quit:
            actions.append(cmds["quit"])
        return actions

    def write_vbs(self, path: str | Path) -> Path:
        from automation.vbs_bridge import write_vbs_file

        return write_vbs_file(self.to_vbs_actions(), path,
                              title="scFLOWpre M2 pipeline plan (locked)")

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
    ap.add_argument("project", help="PPH 或 CAD 路径")
    ap.add_argument("--steps", nargs="*", default=list(DEFAULT_STEPS),
                    help="管线步骤（默认：录制锁定的 box 流程）")
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
