"""scFLOWpre 宿主编辑操作 VBS 生成（P2：Ridge / Octant 编辑）。

依据 ``VB_Interface_eng`` 手册：

- ``VMDL`` 类：``RecalcRidge`` / ``RecalcRidgeFromProjectSetting`` /
  ``SetSelectedEdgeToRidge`` / ``SetSelectedEdgeToNonRidge`` /
  ``GetEdge`` / ``SetSelectAllEdges``；
- ``Octree`` 类：``Refine`` / ``Merge`` / ``RefineByLevel`` /
  ``RefineByNumber`` / ``RefineFromCurvature`` /
  ``ShowOctBySelectedFace`` / ``ShowOctBySelectedEdge``；
- ``Doc`` 类：``SetModeOctree`` / ``SaveProject``。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Sequence

from automation.vbs_bridge import write_vbs_file


def _header(project_path: str | Path) -> list[str]:
    path = Path(project_path).as_posix()
    return [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        f'Doc_.OpenProject "{path}", False',
        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)",
    ]


def _marker_actions(marker: Optional[str | Path]) -> list[str]:
    if marker is None:
        return []
    return [
        'Set fso_ = CreateObject("Scripting.FileSystemObject")',
        f'Set tf_ = fso_.CreateTextFile("{Path(marker)}", True)',
        "tf_.Close",
    ]


def ridge_actions(project_path: str | Path, op: str,
                  *, angle: Optional[float] = None,
                  edge_numbers: Sequence[int] = (),
                  select_all_edges: bool = True) -> list[str]:
    """Ridge 编辑 VBS（``op`` ∈ set / unset / recalc）。"""
    if op not in ("set", "unset", "recalc"):
        raise ValueError(f"unknown ridge op: {op}")
    actions = _header(project_path)
    actions.append("Set VMDL_ = MeshingGroup_.GetVMDL")
    if op == "recalc":
        if angle is not None:
            actions.append(f"VMDL_.RecalcRidge {angle:g}")
        else:
            actions.append("VMDL_.RecalcRidgeFromProjectSetting")
    else:
        # 手册中无按坐标选边的 VBS API（IVEdge 仅有 GetEdgeNum/SetSelect），
        # 因此默认“全选边”；若已锁定 VMDL 边号，则逐条 GetEdge+SetSelect。
        actions.append("' Edge selection")
        actions.append("VMDL_.SetSelectAllEdges(False)")
        nums = [int(n) for n in edge_numbers if n is not None]
        if nums:
            for n in nums:
                actions.append(f"Set VEdge_ = VMDL_.GetEdge({n})")
                actions.append("VEdge_.SetSelect(True, False)")
        elif select_all_edges:
            actions.append(
                "' 无按坐标选边 API（IVEdge 无几何端点），默认选择全部边")
            actions.append("VMDL_.SetSelectAllEdges(True)")
        actions.append("VMDL_.SetSelectedEdgeToRidge"
                       if op == "set"
                       else "VMDL_.SetSelectedEdgeToNonRidge")
    actions.append(f'Doc_.SaveProject "{Path(project_path).as_posix()}"')
    return actions


def octant_actions(project_path: str | Path, op: str,
                   *, level: Optional[int] = None,
                   range_: Optional[int] = None,
                   num: Optional[int] = None,
                   rmin: Optional[Sequence[float]] = None,
                   rmax: Optional[Sequence[float]] = None,
                   lowerlimit: Optional[float] = None) -> list[str]:
    """Octant 编辑 VBS（``op`` 见 :func:`octant_op_label`）。"""
    label = octant_op_label(op)
    if label is None:
        raise ValueError(f"unsupported octant op: {op}")
    actions = _header(project_path)
    actions.append("Doc_.SetModeOctree")
    actions.append("Set Octree_ = MeshingGroup_.GetOctree")
    if op == "refine":
        actions.append("Octree_.Refine")
    elif op == "merge":
        actions.append("Octree_.Merge")
    elif op == "refine_rec":
        if level is None or range_ is None:
            raise ValueError("refine_rec requires level and range")
        actions.append(f"Octree_.RefineByLevel {int(level)}, {int(range_)}")
    elif op == "refine_num":
        if level is None or num is None:
            raise ValueError("refine_num requires level and num")
        actions.append(f"Octree_.RefineByNumber {int(level)}, {int(num)}")
    elif op == "refine_curv":
        if lowerlimit is None:
            raise ValueError("refine_curv requires lowerlimit")
        if rmin is None or rmax is None or len(rmin) != len(rmax):
            raise ValueError(
                "refine_curv requires rmin/rmax arrays of equal length")
        actions.append("Dim rmin_()")
        actions.append("rmin_ = Array("
                       + ", ".join(f"{v:g}" for v in rmin) + ")")
        actions.append("Dim rmax_()")
        actions.append("rmax_ = Array("
                       + ", ".join(f"{v:g}" for v in rmax) + ")")
        actions.append(
            f"Octree_.RefineFromCurvature rmin_, rmax_, {lowerlimit:g}")
    elif op == "show_by_face":
        actions.append("Octree_.ShowOctBySelectedFace")
    elif op == "show_by_edge":
        actions.append("Octree_.ShowOctBySelectedEdge")
    elif op == "show_all":
        actions.append("Octree_.ShowAll")
    actions.append(f'Doc_.SaveProject "{Path(project_path).as_posix()}"')
    return actions


def octant_op_label(op: str) -> Optional[str]:
    """宿主可执行的 Octant 操作 → 手册方法说明；不支持时返回 None。"""
    return {
        "refine": "Refine",
        "merge": "Merge",
        "refine_rec": "RefineByLevel",
        "refine_num": "RefineByNumber",
        "refine_curv": "RefineFromCurvature",
        "show_by_face": "ShowOctBySelectedFace",
        "show_by_edge": "ShowOctBySelectedEdge",
        "show_all": "ShowAll",
    }.get(op)


def write_host_edit_vbs(project_path: str | Path,
                        actions: Iterable[str],
                        output: str | Path,
                        *,
                        marker: Optional[str | Path] = None,
                        title: str = "pph_gui host edit") -> Path:
    """写宿主 VBS（UTF-16LE），末尾按需追加完成标记。"""
    lines = list(actions)
    lines.extend(_marker_actions(marker))
    return write_vbs_file(lines, output, title=title)


def write_ridge_vbs(project_path: str | Path, op: str,
                    output: str | Path,
                    *, angle: Optional[float] = None,
                    edge_numbers: Sequence[int] = (),
                    select_all_edges: bool = True,
                    marker: Optional[str | Path] = None) -> Path:
    return write_host_edit_vbs(
        project_path,
        ridge_actions(project_path, op, angle=angle,
                      edge_numbers=edge_numbers,
                      select_all_edges=select_all_edges),
        output, marker=marker, title=f"pph_gui ridge {op}")


def write_octant_vbs(project_path: str | Path, op: str,
                     output: str | Path,
                     *, level: Optional[int] = None,
                     range_: Optional[int] = None,
                     num: Optional[int] = None,
                     rmin: Optional[Sequence[float]] = None,
                     rmax: Optional[Sequence[float]] = None,
                     lowerlimit: Optional[float] = None,
                     marker: Optional[str | Path] = None) -> Path:
    return write_host_edit_vbs(
        project_path,
        octant_actions(project_path, op, level=level, range_=range_,
                       num=num, rmin=rmin, rmax=rmax,
                       lowerlimit=lowerlimit),
        output, marker=marker, title=f"pph_gui octant {op}")
