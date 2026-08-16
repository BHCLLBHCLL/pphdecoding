#!/usr/bin/env python3
"""M2 预处理管线计划与 VBS 验收脚本生成。

命令名以 scFLOWpre 真实录制的 ``tests/box_vbs*.vbs``（v1/v3/v4）与
``box_scflow_mdl.vbs``（2026-08-14，含完整 BAM 向导流程）为准：

- ``LOCKED_COMMANDS``：已在录制中出现并锁定的命令（含行号证据）；
- ``UNLOCKED_COMMANDS``：录制中未出现、仍待验证的占位命令；
- Wrapping 高层命令（Begin/Execute Wrapping）在 v1-v4 录制中均未出现，
  由 NativeBridge 走 SCTprime 原生入口，不作为 VBS 默认管线。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pph_parser import PphArchive

# ── Wrapping（从 x_t 曲面）录制锁定参数 ──────────────────────────────────
# 来源：box_scflow_wrapping.vbs（2026/08/14）：
# Doc_.BeginWrapping → Doc_.CreateWrappingGroup → WrappingGroup_.GetOctParam
# → WrappingParam_.SetMethod/SetOutsideType/SetOutsideRegions/SetInsideGroups
# → WrappingGroup_.CreateOctree → ExecuteWrapping ×4 → Octree_.UpdateGroups →
# ExecuteWrapping ×2 → Doc_.EndWrapping。
WRAP_OCT_PARAM_PAIRS: list[tuple[str, str]] = [
    ("BALANCING", "3"),
    ("BASELEV.MAX", "6"),
    ("BASELEV.MIN", "-1"),
    ("BASELEV.ROOTFAC", "1.3999999999999999"),
    ("BASEMODE", "2"),
    ("BASENAME", ""),
    ("BASENELEM", "0"),
    ("BASEPOS", "1"),
    ("BASEPOS.X", "0"),
    ("BASEPOS.Y", "0"),
    ("BASEPOS.Z", "0"),
    ("BASESIZE.MAX", "0.001"),
    ("BASESIZE.MIN", "0.00050000000000000001"),
    ("BASESIZEFORAUTOGEN", "0"),
    ("BOUNDARYRANGE", "0"),
    ("CHECKONLYFLUID", "0"),
    ("CSPCGROUPINGTYPE", "0"),
    ("IGNOREDRATIO", "0.0001"),
    ("INITIALIZED", "0"),
    ("NUMERICALREGION.N", "0"),
    ("OCTNAME", ""),
    ("PATCHEFFECTMODE", "0"),
    ("PROXIMITYITEM.N", "0"),
    ("REFMODEL.N", "0"),
    ("REFSECTITEM.N", "0"),
    ("REGNMODE", "0"),
    ("REGNNAME", ""),
    ("SECTAVOIDORDERDEPENDENCY", "1"),
    ("SECTGRP2", "0"),
    ("SECTITEM.N", "1"),
    ("SECTITEM[0].NAME", "Part"),
    ("SECTITEM[0].NEIGHBOR", "0"),
    ("SECTITEM[0].SIZE", "0.00050000000000000001"),
    ("SECTTYPE", "1"),
    ("TARGETNUMBER", "100000"),
]

WRAP_PARAM_PAIRS: list[tuple[str, str]] = [
    ("AVOIDEDGECONTACT", "0"),
    ("AVOIDMULTINODE", "0"),
    ("CORRECTGROUPTYPE", "2"),
    ("EXPANDNARRAWSPACE", "3"),
    ("EXPANDRT", "0.10000000000000001"),
    ("EXPANDTHIN", "1"),
    ("EXTRACTEDGEAFTERTARGET", "2"),
    ("FILLHOLE", "0"),
    ("FITTOEDGE", "4"),
    ("IMPROVERELATION", "3"),
    ("LOGNAME", ""),
    ("MARKEDFACE", "0"),
    ("MARKEDGELIST", "0"),
    ("MDLMODE", "0"),
    ("MDLNAME", ""),
    ("NEARTPATCHTYPE", "2"),
    ("NEWCOORDTYPE", "2"),
    ("NOCONNECT.N", "0"),
    ("NOCONNECTTYPE", "1"),
    ("NOTEXPANDREGN.N", "0"),
    ("NUMOFOCTTOIGNORE", "0"),
    ("OCTMODE", "0"),
    ("OCTNAME", ""),
    ("PROJECTANDMOVEINNORMTYPE", "2"),
    ("PROTECTNDTP", "2"),
    ("RECOVERYTYPE", "0"),
    ("REFINEDOCTNAME", ""),
    ("REGISTFRGN", "0"),
    ("REMOVEISECT", "1"),
    ("REMOVENARRAWTHIN", "0"),
    ("REPORTEDGELIST", "0"),
    ("SMOOTHTYPE", "2"),
    ("SMTUNFITBDRY", "3"),
    ("SMTUNFITEDGE", "30"),
    ("SWAPEDGE", "3"),
    ("TARGETGRP.N", "1"),
    ("TARGETGRP[0]", "2"),
    ("TARGETOCTDIV", "1"),
    ("UPDATENEARESTFACETYPE", "3"),
    ("USERAWEDGELIST", "0"),
    ("WRAPPEDMDLNAME", ""),
    ("WTOECANCELRANGE", "3"),
    ("WTOETYPE", "1"),
]


def _array_assign_actions(pairs: list[tuple[str, str]],
                          var: str = "ArrayParam1_",
                          declare: bool = True) -> list[str]:
    """键值对 → ``Dim/Redim ArrayParam1_(n)`` + 逐项字符串赋值。

    ``declare=False`` 用于同一脚本内多次拼接数组参数段：VBScript 不允许
    重复 ``Dim`` 同名变量（编译期 "Name redefined"，整段脚本不执行），
    后续段只 ``Redim``。
    """
    n = len(pairs) * 2 - 1
    actions = ([f"Dim {var}()"] if declare else []) + [f"Redim {var}({n})"]
    for i, (key, val) in enumerate(pairs):
        esc = str(val).replace('"', '""')
        actions.append(f'{var}({i * 2}) = "{key}"')
        actions.append(f'{var}({i * 2 + 1}) = "{esc}"')
    return actions


def _wrapping_param_actions(marked_face: int = 0,
                           declare: bool = True) -> list[str]:
    """WrappingParam：Method/OutsideType/OutsideRegions/InsideGroups/SetParams。"""
    pairs = [list(p) for p in WRAP_PARAM_PAIRS]
    for p in pairs:
        if p[0] == "MARKEDFACE":
            p[1] = str(int(marked_face))
    actions = [
        'Param1_ = "outside"',
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set WrappingParam_ = WrappingGroup_.GetWrappingParam",
        "WrappingParam_.SetMethod Param1_",
        'Param1_ = "all"',
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set WrappingParam_ = WrappingGroup_.GetWrappingParam",
        "WrappingParam_.SetOutsideType Param1_",
        "Redim ArrayParam1_(-1)",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set WrappingParam_ = WrappingGroup_.GetWrappingParam",
        "WrappingParam_.SetOutsideRegions ArrayParam1_",
        "Redim ArrayParam1_(-1)",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set WrappingParam_ = WrappingGroup_.GetWrappingParam",
        "WrappingParam_.SetInsideGroups ArrayParam1_",
        *_array_assign_actions(pairs, declare=declare),
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set WrappingParam_ = WrappingGroup_.GetWrappingParam",
        "WrappingParam_.SetParams ArrayParam1_",
    ]
    return actions


def _wrapping_oct_param_actions(declare: bool = True) -> list[str]:
    """WrappingGroup 八叉树参数（录制顺序：SetOctType→Initialize→SetParams）。"""
    actions = [
        "Param1_ = 3",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set OctParam_ = WrappingGroup_.GetOctParam",
        "OctParam_.SetOctType Param1_",
        "Param1_ = 1",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set OctParam_ = WrappingGroup_.GetOctParam",
        "OctParam_.SetOctType Param1_",
        'Param1_ = "@TemporaryOct"',
        "Doc_.DeleteTemporaryDrawingObject Param1_",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set OctParam_ = WrappingGroup_.GetOctParam",
        "OctParam_.Initialize",
        "Param1_ = 3",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set OctParam_ = WrappingGroup_.GetOctParam",
        "OctParam_.SetOctType Param1_",
        "Param1_ = 10000",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set OctParam_ = WrappingGroup_.GetOctParam",
        "OctParam_.SetMeshNum Param1_",
        "Param1_ = 0",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set OctParam_ = WrappingGroup_.GetOctParam",
        "OctParam_.SetMinSize Param1_",
        *_array_assign_actions(WRAP_OCT_PARAM_PAIRS, declare=declare),
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set OctParam_ = WrappingGroup_.GetOctParam",
        "OctParam_.SetParams ArrayParam1_",
        "Param1_ = -1",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set OctParam_ = WrappingGroup_.GetOctParam",
        "OctParam_.SetGlobalAngularPrecisionMinOctLimitSize Param1_",
        "Redim ArrayParam1_(-1)",
        "Redim ArrayParam2_(-1)",
        "Redim ArrayParam3_(-1)",
        "Redim ArrayParam4_(-1)",
        "OctParam_.SetAngularPrecision ArrayParam1_, ArrayParam2_, "
        "ArrayParam3_, ArrayParam4_",
        'Param1_ = "default"',
        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)",
        "MeshingGroup_.SetOctCreateTypeWithSolidBaseOct Param1_",
    ]
    return actions


def _wrapping_body_actions() -> list[str]:
    """Execute 管线用 wrapping 主体（不含 App/Doc/Open 头，含 EndWrapping）。"""
    actions = [
        'Conditions_.SetPartsControl "Wrapping", True',
        "Doc_.BeginWrapping",
        "Doc_.CreateWrappingGroup",
        "Param1_ = False",
        'Set FaceRegion_ = Doc_.QueryFaceRegionByName("@PartSurface_Part")',
        "FaceRegion_.SetIsContactAngleSet Param1_",
        *_wrapping_oct_param_actions(declare=True),
        *_wrapping_param_actions(0, declare=False),
        'Param1_ = "Rearrange on the tree window"',
        "Doc_.BeginTransaction Param1_",
        'Param1_ = "Part"',
        'Param2_ = ""',
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set SNode_ = WrappingGroup_.GetRootSNode",
        "SNode_.MoveToChild Param1_, Param2_",
        "Doc_.EndTransaction",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "WrappingGroup_.CreateOctree",
        "Doc_.SetModeOctree",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(0)",
        "WrappingGroup_.ExecuteWrapping",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "WrappingGroup_.ExecuteWrapping",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(0)",
        "WrappingGroup_.ExecuteWrapping",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "WrappingGroup_.ExecuteWrapping",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set Octree_ = WrappingGroup_.GetOctree",
        "Octree_.UpdateGroups",
        *_wrapping_param_actions(1, declare=False),
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "Set Octree_ = WrappingGroup_.GetOctree",
        "Octree_.UpdateGroups",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(0)",
        "WrappingGroup_.ExecuteWrapping",
        "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
        "WrappingGroup_.ExecuteWrapping",
        "Doc_.EndWrapping",
    ]
    return actions


WRAPPING_BODY_ACTIONS: list[str] = _wrapping_body_actions()

# ── BAM（Analysis Model Wizard）录制锁定流程 ─────────────────────────────
# 来源：box_scflow_mdl.vbs（2026/08/14）：BeginMDLWizard → GetMDLWizard →
# CreateBoundary → CreateMultiEntityInfo ×6 → CreateMDL → FindAFFaceMatching
# → SetFaceMatched → FindTinyFace ×2 → SetTinyFacesRemoved → RepairMDL →
# CheckMDLErrors → EndMDLWizard；参数取值与录制一致（框体 6 个多实体域）。
BAM_WIZARD_ACTIONS: list[str] = [
    "MeshingGroup_.BeginMDLWizard",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.RemoveMDLFacetPreview",
    "Doc_.SetModePart",
    "Param1_ = True",
    "Set Proj_ = Doc_.GetProjectSetting",
    "Proj_.SetRidgeProjectSolids Param1_",
    "Param1_ = True",
    "Set Proj_ = Doc_.GetProjectSetting",
    "Proj_.SetRidgeProjectSheets Param1_",
    "Param1_ = True",
    "Set Proj_ = Doc_.GetProjectSetting",
    "Proj_.SetUseAFFacetter Param1_",
    "Param1_ = 0",
    "Set Proj_ = Doc_.GetProjectSetting",
    "Proj_.SetFacetAccuracySpecificationType Param1_",
    "Param1_ = True",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetUseOctLengthParam Param1_",
    "Param1_ = 5",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetOctLengthParamType Param1_",
    "Param1_ = 5",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetOctLengthParamItr Param1_",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CreateBoundary",
    "Param1_ = True",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CreateMultiEntityInfo Param1_",
    "Param1_ = False",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CreateMultiEntityInfo Param1_",
    "Param1_ = True",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CreateMultiEntityInfo Param1_",
    "Param1_ = False",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CreateMultiEntityInfo Param1_",
    "Param1_ = True",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CreateMultiEntityInfo Param1_",
    "Param1_ = False",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CreateMultiEntityInfo Param1_",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.SetBoundaryConfigured",
    "Param1_ = False",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetFacetUseAbsoluteValue Param1_",
    "Param1_ = 0.05",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetAFFaceterLengthFactor Param1_",
    "Param1_ = 10",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetAFFaceterMinimumAngle Param1_",
    "Param1_ = 5",
    "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    "MeshingGroupSetting_.SetFacetSimpleMaxWidth Param1_",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.RemoveMDLFacetPreview",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.SetSpatialSeparationSettingsConfigured",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.RemoveMDLFacetPreview",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.ReconfigureSpatialSeparationSettings",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.SetAutoRemoveTinyFaceConfigured",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CreateMDL",
    "Param1_ = 0.05",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.FindAFFaceMatching Param1_",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.SetFaceMatched",
    "Param1_ = 1e-05",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.FindTinyFace Param1_",
    "Doc_.ClearPreview",
    "Param1_ = 1e-05",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.FindTinyFace Param1_",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.SetTinyFacesRemoved",
    'Param1_ = "TINYFACEARROW"',
    "Doc_.DeleteTemporaryDrawingObject Param1_",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.RepairMDL",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.CheckMDLErrors",
    "Doc_.ClearPreview",
    "Set MDLWizard_ = MeshingGroup_.GetMDLWizard",
    "MDLWizard_.RemoveMDLFacetPreview",
    'Param1_ = "TINYFACEARROW"',
    "Doc_.DeleteTemporaryDrawingObject Param1_",
    "MeshingGroup_.EndMDLWizard",
]

# 实测锁定命令（来源 tests/box_vbs*.vbs，括号内为行号）
LOCKED_COMMANDS: dict[str, str] = {
    "open_cad_file": 'Doc_.OpenCadFile "{path}"',                    # :14 (v1)
    "open_project": 'Doc_.OpenProject "{path}", False',              # :4352 (v4)
    "begin_solid_edit": "MeshingGroup_.BeginSolidEdit",              # :14 (v4)
    "parts_control": (                                               # :16-18 (v1)
        'Conditions_.SetPartsControl "Discontinuous", False\n'
        'Conditions_.SetPartsControl "Overset", False\n'
        'Conditions_.SetPartsControl "Wrapping", False'),
    # BAM 走 Analysis Model Wizard（box_scflow_mdl.vbs :350-527）
    "build_analysis_model": "\n".join(BAM_WIZARD_ACTIONS),
    "generate_octree": "MeshingGroup_.CreateOctree",                 # :3110 (v1)
    "set_mode_octree": "Doc_.SetModeOctree",                         # :3112 (v1)
    "generate_mesh": (                                               # :5276,5283 (v1)
        "MeshingGroup_.CreateMeshMonitor\nDoc_.WaitForWorker"),
    "set_mode_mesh": "Doc_.SetModeMesh",                             # :5285 (v1)
    # Wrapping 从 x_t 曲面录制锁定（box_scflow_wrapping.vbs）
    "begin_wrapping": "\n".join(WRAPPING_BODY_ACTIONS),
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
    "wrapping": ["begin_wrapping"],
    "bam": ["build_analysis_model"],
    "oct": ["generate_octree", "set_mode_octree"],
    "mesh": ["generate_mesh", "set_mode_mesh"],
}
DEFAULT_EXECUTE_ORDER = ["wrapping", "bam", "oct", "mesh"]


def steps_from_execute_plan(plan: dict) -> list[str]:
    """把 Execute 面板勾选结果映射为管线步骤列表。"""
    steps: list[str] = []
    for key in DEFAULT_EXECUTE_ORDER:
        if plan.get(key):
            steps.extend(EXECUTE_STEP_MAP[key])
    return steps


# Octree/Faceter xenv 键 -> scFLOWpre VBS setter（参数值来自 GUI 面板）。
# 键与 box_vbs_v3/v4 录制命令一一对应。
OCTREE_SETTING_MAP: list[tuple[tuple[str, str], str]] = [
    (("OCT_MESH", "FACET_LENGTH_FACTOR"),
     "MeshingGroupSetting_.SetSolidFacetLengthFactor"),
    (("OCT_MESH", "FACET_ANGLE"),
     "MeshingGroupSetting_.SetSolidFacetAngle"),
    (("OCT_MESH", "FACET_MAX_WIDTH_FACTOR"),
     "MeshingGroupSetting_.SetSolidFacetMaxWidthFactor"),
    (("OCT_MESH", "FACET_SPECIFY_EACH_REGION"),
     "MeshingGroupSetting_.SetSolidFacetSpecifyEachRegionFlag"),
    (("OCT_MESH", "COMPLETE_PARALLEL"),
     "MeshingGroupSetting_.SetCompleteParallelFlag"),
    (("OCT_MESH", "VOXEL_OCT_REFINE_TYPE"),
     "MeshingGroupSetting_.SetVoxelOctRefineType"),
    (("FACET", "USE_FACETTER"),
     "MeshingGroupSetting_.SetUseAFFacetter"),
    (("FACET", "SOLID_BASE_LENGTH_FACTOR"),
     "MeshingGroupSetting_.SetAFFaceterLengthFactor"),
    (("FACET", "SOLID_BASE_MINIMUM_ANGLE"),
     "MeshingGroupSetting_.SetAFFaceterMinimumAngle"),
    (("FACET", "SOLID_BASE_TINY_FACE_WIDTH_RATIO"),
     "MeshingGroupSetting_.SetAFFaceterTinyFaceWidthRatio"),
    (("FACET", "SOLID_BASE_LENGTH_FACTOR_FOR_OCTREE"),
     "MeshingGroupSetting_.SetAFFaceterLengthFactorForOctree"),
    (("FACET", "SOLID_BASE_MINIMUM_ANGLE_FOR_OCTREE"),
     "MeshingGroupSetting_.SetAFFaceterMinimumAngleForOctree"),
    (("FACET", "MDL_METHOD"),
     "MeshingGroupSetting_.SetMDLMethod"),
    (("FACET", "USE_INTERSECTION_DETECTION_DEPTH_AS_CLOSED_VOLUME_DETECTION_DEPTH"),
     "MeshingGroupSetting_.SetUseIntersectionDetectionDepthAsClosedVolumeDetectionDepth"),
    (("FACET", "INTERSECTION_DETECTION_DEPTH"),
     "MeshingGroupSetting_.SetIntersectionDetectionDepth"),
    (("FACET", "FACET_ACCURACY_SPECIFY_TYPE"),
     "MeshingGroupSetting_.SetFacetAccuracySpecificationType"),
    (("FACET", "OCT_LENGTH_PARAM_FLAG"),
     "MeshingGroupSetting_.SetUseOctLengthParam"),
    (("FACET", "OCT_LENGTH_PARAM_TYPE"),
     "MeshingGroupSetting_.SetOctLengthParamType"),
    (("FACET", "OCT_LENGTH_PARAM_ITR"),
     "MeshingGroupSetting_.SetOctLengthParamItr"),
]

# xenv 数值/代号 -> VBS 字符串枚举（录制中仅见过 3 -> "octree"）
OCTREE_ENUM_MAP: dict[tuple[str, str], dict[str, str]] = {
    ("OCT_MESH", "VOXEL_OCT_REFINE_TYPE"): {"3": "octree"},
}


def _xenv_get(xenv, section: str, key: str, default=None):
    if xenv is None:
        return default
    getter = getattr(xenv, "get", None)
    if getter is not None:
        try:
            return getter(section, key, default)
        except TypeError:
            pass
    sec = xenv.get(section) if isinstance(xenv, dict) else None
    if isinstance(sec, dict):
        return sec.get(key, default)
    return default


def _vbs_value(value) -> str:
    text = str(value).strip()
    if text.lower() == "true":
        return "True"
    if text.lower() == "false":
        return "False"
    return text


def _vbs_enum(section: str, key: str, value) -> str:
    text = str(value).strip()
    mapping = OCTREE_ENUM_MAP.get((section, key), {})
    return mapping.get(text, text)


def octree_settings_actions(xenv) -> list[str]:
    """把 GUI 的 Octree/Faceter xenv 参数转成宿主 VBS setter 序列。"""
    pairs: list[tuple[str, str]] = []
    for (section, key), setter in OCTREE_SETTING_MAP:
        value = _xenv_get(xenv, section, key)
        if value is None or str(value).strip() == "":
            continue
        pairs.append((setter, _vbs_enum(section, key, _vbs_value(value))))
    if not pairs:
        return []
    actions = [
        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set MeshingGroupSetting_ = MeshingGroup_.GetMeshingGroupSetting",
    ]
    actions.extend(f"{setter} {value}" for setter, value in pairs)
    return actions


def _oct_sect_name(ui_name: str) -> str:
    """GUI 区域名 → OctParam SECTITEM 名。

    录制：``Part surface (@Part)`` → ``@PartSurface_Part``；
    多零件：``Part surface (@case1)`` → ``@PartSurface_case1``。
    """
    name = (ui_name or "").strip()
    if name.startswith("@PartSurface_"):
        return name
    if name.startswith("Part surface ("):
        inner = name[len("Part surface ("):].rstrip(")")
        if inner.startswith("@"):
            inner = inner[1:]
        return f"@PartSurface_{inner}" if inner else "@PartSurface_Part"
    return name


def _fmt_oct_num(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{f:.17g}"


def build_oct_param_pairs(octree_sess: Optional[dict]) -> list[tuple[str, str]]:
    """由 GUI session[octree_param] 构造 OctParam_.SetParams 键值对。

    键名/默认布局对齐 ``tests/box_vbs_v4.vbs`` 中 ``GetOctParam`` / ``SetParams``
    录制（含 ``SECTITEM[*].SIZE`` 区域尺寸）。
    """
    sess = dict(octree_sess or {})
    detail = dict(sess.get("detail") or {})
    # 兼容旧扁平字段
    for k in (
        "input_by", "min_oct_size", "max_oct_size", "restrict_max",
        "root_ratio", "max_level", "min_level", "restrict_min_level",
        "specify_center", "center_x", "center_y", "center_z",
        "region_size", "region_angle", "region_proximity",
        "region_size_eval", "refine_range", "limit_refine",
    ):
        if k not in detail and k in sess:
            detail[k] = sess[k]

    mode = sess.get("mode", "octant")
    # 录制中 BASEMODE=2 对应按长度的 Octant parameter
    basemode = {"target": "0", "min": "1", "octant": "2"}.get(mode, "2")
    min_oct = float(detail.get("min_oct_size", sess.get("min_size", 0.001))
                    or 0.001)
    if mode == "min" and "min_size" in sess:
        min_oct = float(sess["min_size"])
    max_oct = float(detail.get("max_oct_size", min_oct) or min_oct)
    if not detail.get("restrict_max", False):
        max_oct = min_oct
    root_fac = float(detail.get("root_ratio", 1.4) or 1.4)
    max_lev = int(detail.get("max_level", 6) or 6)
    if detail.get("restrict_min_level"):
        min_lev = int(detail.get("min_level", 0) or 0)
    else:
        min_lev = -1
    cx = float(detail.get("center_x", 0.005) or 0.005)
    cy = float(detail.get("center_y", 0.005) or 0.005)
    cz = float(detail.get("center_z", 0.005) or 0.005)
    basepos = "1" if detail.get("specify_center", True) else "0"
    balancing = int(detail.get("refine_range", 3) or 3)
    if detail.get("limit_refine") is False:
        balancing = 0
    boundary = "1" if detail.get("region_size_eval") else "0"
    target = int(sess.get("target", 100000) or 100000)

    pairs: list[tuple[str, str]] = [
        ("BALANCING", str(balancing)),
        ("BASELEV.MAX", str(max_lev)),
        ("BASELEV.MIN", str(min_lev)),
        ("BASELEV.ROOTFAC", _fmt_oct_num(root_fac)),
        ("BASEMODE", basemode),
        ("BASENAME", ""),
        ("BASENELEM", "0"),
        ("BASEPOS", basepos),
        ("BASEPOS.X", _fmt_oct_num(cx)),
        ("BASEPOS.Y", _fmt_oct_num(cy)),
        ("BASEPOS.Z", _fmt_oct_num(cz)),
        ("BASESIZE.MAX", _fmt_oct_num(max_oct)),
        ("BASESIZE.MIN", _fmt_oct_num(min_oct)),
        ("BASESIZEFORAUTOGEN", "0"),
        ("BOUNDARYRANGE", boundary),
        ("CHECKONLYFLUID", "0"),
        ("CSPCGROUPINGTYPE", "0"),
        ("IGNOREDRATIO", "0.0001"),
        ("INITIALIZED", "0"),
        ("NUMERICALREGION.N", "0"),
        ("OCTNAME", ""),
        ("PATCHEFFECTMODE", "0"),
    ]

    # Proximity → PROXIMITYITEM（仅非空项）
    prox_items: list[tuple[str, dict]] = []
    for name, rec in (detail.get("region_proximity") or {}).items():
        if not isinstance(rec, dict):
            continue
        gap = float(rec.get("gap", 0) or 0)
        count = int(rec.get("count", 0) or 0)
        mins = float(rec.get("min_size", 0) or 0)
        if gap <= 0 and count <= 0 and mins <= 0:
            continue
        prox_items.append((name, rec))
    pairs.append(("PROXIMITYITEM.N", str(len(prox_items))))
    for i, (name, rec) in enumerate(prox_items):
        pairs.append((f"PROXIMITYITEM[{i}].NAME", _oct_sect_name(name)))
        pairs.append((f"PROXIMITYITEM[{i}].GAP",
                      _fmt_oct_num(rec.get("gap", 0))))
        pairs.append((f"PROXIMITYITEM[{i}].COUNT",
                      str(int(rec.get("count", 1) or 1))))
        pairs.append((f"PROXIMITYITEM[{i}].MINSIZE",
                      _fmt_oct_num(rec.get("min_size", 0))))

    pairs.extend([
        ("REFMODEL.N", "0"),
        ("REFSECTITEM.N", "0"),
        ("REGNMODE", "0"),
        ("REGNNAME", ""),
        ("SECTAVOIDORDERDEPENDENCY", "1"),
        ("SECTGRP2", "0"),
    ])

    # Size Settings to Region → SECTITEM（录制核心）
    sects: list[tuple[str, dict]] = []
    for name, rec in (detail.get("region_size") or {}).items():
        if not isinstance(rec, dict):
            continue
        try:
            size = float(rec.get("size", 0) or 0)
        except (TypeError, ValueError):
            continue
        if size <= 0:
            continue
        sects.append((name, rec))
    pairs.append(("SECTITEM.N", str(len(sects))))
    for i, (name, rec) in enumerate(sects):
        pairs.append((f"SECTITEM[{i}].NAME", _oct_sect_name(name)))
        pairs.append((f"SECTITEM[{i}].NEIGHBOR",
                      _fmt_oct_num(rec.get("range", 0) or 0)))
        pairs.append((f"SECTITEM[{i}].SIZE",
                      _fmt_oct_num(rec.get("size", 0))))
    pairs.extend([
        ("SECTTYPE", "1"),
        ("TARGETNUMBER", str(target)),
    ])
    return pairs


def oct_param_actions(octree_sess: Optional[dict] = None) -> list[str]:
    """生成 ``GetOctParam`` / ``SetOctType`` / ``SetMinSize`` / ``SetParams`` VBS。

    录制（``tests/box_vbs_v2.vbs``）在 ``SetParams`` 之前必须：

    1. ``DeleteOctree``（否则宿主常复用旧八叉树，边长不变）；
    2. ``Initialize`` → ``SetOctType``（1=target / 2=min / 3=octant）；
    3. ``SetMeshNum`` / ``SetMinSize``（``SetParams``  alone 不会改全局最小尺寸）。

    COM 实测：仅 ``SetParams`` 时边界边长仍约 0.00022；补齐上述调用后
    ``SetMinSize 0.001`` → 边长约 0.001、单元数约 1000。
    """
    sess = dict(octree_sess or {})
    detail = dict(sess.get("detail") or {})
    for k in (
        "min_oct_size", "max_oct_size", "restrict_max",
    ):
        if k not in detail and k in sess:
            detail[k] = sess[k]
    mode = sess.get("mode", "octant")
    oct_type = {"target": 1, "min": 2, "octant": 3}.get(mode, 3)
    target = int(sess.get("target", 100000) or 100000)
    min_oct = float(detail.get("min_oct_size", sess.get("min_size", 0.001))
                    or 0.001)
    if mode == "min" and "min_size" in sess:
        min_oct = float(sess["min_size"])

    pairs = build_oct_param_pairs(octree_sess)
    n = len(pairs) * 2 - 1
    actions = [
        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)",
        "MeshingGroup_.DeleteOctree",
        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set OctParam_ = MeshingGroup_.GetOctParam(False)",
        "OctParam_.Initialize",
        f"OctParam_.SetOctType {oct_type}",
        f"OctParam_.SetMeshNum {target}",
        f"OctParam_.SetMinSize {_fmt_oct_num(min_oct)}",
        f"Redim ArrayParam1_({n})",
    ]
    idx = 0
    for key, val in pairs:
        actions.append(f'ArrayParam1_({idx}) = "{key}"')
        idx += 1
        # 录制把数值也写成字符串；与 history.vbs 一致更稳妥
        esc = str(val).replace('"', '""')
        actions.append(f'ArrayParam1_({idx}) = "{esc}"')
        idx += 1
    actions.append(
        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)")
    actions.append(
        "Set OctParam_ = MeshingGroup_.GetOctParam(False)")
    actions.append("OctParam_.SetParams ArrayParam1_")
    # CreateOctree 前：与录制一致的创建类型 + 空角度精度
    actions.extend([
        "Param1_ = -1",
        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)",
        "Set OctParam_ = MeshingGroup_.GetOctParam(False)",
        "OctParam_.SetGlobalAngularPrecisionMinOctLimitSize Param1_",
        "Redim ArrayParam1_(-1)",
        "Redim ArrayParam2_(-1)",
        "Redim ArrayParam3_(-1)",
        "Redim ArrayParam4_(-1)",
        "OctParam_.SetAngularPrecision ArrayParam1_, ArrayParam2_, "
        "ArrayParam3_, ArrayParam4_",
        'Param1_ = "default"',
        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)",
        "MeshingGroup_.SetOctCreateTypeWithSolidBaseOct Param1_",
    ])
    return actions


def _looks_numeric(text: str) -> bool:
    try:
        float(text)
        return True
    except (TypeError, ValueError):
        return False


def oct_param_sect_summary(octree_sess: Optional[dict] = None) -> list[str]:
    """可读摘要：将写入 SECTITEM 的区域尺寸与全局最小尺寸。"""
    sess = dict(octree_sess or {})
    detail = dict(sess.get("detail") or {})
    min_oct = detail.get("min_oct_size", sess.get("min_size"))
    out = []
    if min_oct is not None:
        out.append(f"min_oct={min_oct}")
    for key, val in build_oct_param_pairs(octree_sess):
        if key.endswith("].NAME") and key.startswith("SECTITEM"):
            out.append(val)
        elif key.endswith("].SIZE") and key.startswith("SECTITEM") and out:
            out[-1] = f"{out[-1]} size={val}"
    return out


def parts_control_actions(pc_sess: Optional[dict] = None) -> list[str]:
    """GUI ``session['parts_control']`` → ``Conditions_.SetPartsControl``。

    录制证据：``Conditions_.SetPartsControl "Wrapping", False``（box_vbs:16-18）。
    Discontinuous / Overset 与对话框三项勾选一一对应。

    P4-3 COM 实测锁定（box_com_diag4.log）：Discontinuous / Overset 的
    True/False 四种调用在宿主内全部 err=0。

    宿主脚本里 ``Conditions_`` 不是隐式全局对象，须先
    ``Set Conditions_ = Doc_.GetConditions``（COM 实测 err=424 否则）。
    """
    pc = dict(pc_sess or {})
    pairs = (
        ("Discontinuous", bool(pc.get("discontinuous"))),
        ("Overset", bool(pc.get("overset"))),
        ("Wrapping", bool(pc.get("wrapping"))),
    )
    return [
        "Set Conditions_ = Doc_.GetConditions",
        *[
            f'Conditions_.SetPartsControl "{name}", '
            f'{"True" if flag else "False"}'
            for name, flag in pairs
        ],
    ]


# Wrapping / Disc / Overset 导航项 → VBS 草稿
# （Wrapping 序列 v1–v4 录制锁定；Disc/Overset P4-3 COM 实测锁定，
#   见 box_com_diag4.log：SetPartsControl 四种调用全部 err=0）
_WRAP_OP_COMMENTS: dict[str, str] = {
    "begin_wrap": "Begin Wrapping — NativeBridge/SCTprime CreateWrap…",
    "cancel_wrap": "Cancel Wrapping",
    "exec_wrap": "Execute Wrapping — NativeBridge ExecuteWrapping",
    "retry_wrap": "Retry Wrapping",
    "wrap_octree": "Wrapping Octree Parameter — SetWrapOctParam (录制锁定)",
    "wrap_param": "Wrapping Parameter — SetWrapParam (录制锁定)",
    "specify_disc": 'Conditions_.SetPartsControl "Discontinuous", True',
    "overset_mesh": 'Conditions_.SetPartsControl "Overset", True',
}


def wrapping_actions(op: str, project_path: str | Path) -> list[str]:
    """生成 Wrapping/Disc/Overset 宿主脚本（wrapping 序列已录制锁定）。"""
    path = Path(project_path).as_posix()
    actions = [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        f'Doc_.OpenProject "{path}", False',
        "Set Conditions_ = Doc_.GetConditions",
    ]
    if op == "specify_disc":
        actions.append(
            'Conditions_.SetPartsControl "Discontinuous", True')
    elif op == "overset_mesh":
        actions.append('Conditions_.SetPartsControl "Overset", True')
    elif op == "begin_wrap":
        actions.append('Conditions_.SetPartsControl "Wrapping", True')
        actions.extend(_wrapping_body_actions())
    elif op in ("exec_wrap", "retry_wrap"):
        actions.append('Conditions_.SetPartsControl "Wrapping", True')
        actions.extend([
            "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(0)",
            "WrappingGroup_.ExecuteWrapping",
            "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
            "WrappingGroup_.ExecuteWrapping",
            "Set WrappingGroup_ = Doc_.QueryWrappingGroupByIndex(1)",
            "Set Octree_ = WrappingGroup_.GetOctree",
            "Octree_.UpdateGroups",
        ])
    elif op == "cancel_wrap":
        actions.append('Conditions_.SetPartsControl "Wrapping", True')
        actions.append("Doc_.CancelWrapping")
    elif op == "wrap_octree":
        actions.append('Conditions_.SetPartsControl "Wrapping", True')
        actions.append("Doc_.BeginWrapping")
        actions.append("Doc_.CreateWrappingGroup")
        actions.extend(_wrapping_oct_param_actions())
    elif op == "wrap_param":
        actions.append('Conditions_.SetPartsControl "Wrapping", True')
        actions.append("Doc_.BeginWrapping")
        actions.append("Doc_.CreateWrappingGroup")
        actions.extend(_wrapping_param_actions(0))
    else:
        raise ValueError(
            f"unknown wrapping op {op!r}; valid: "
            + ", ".join(sorted(_WRAP_OP_COMMENTS)))
    actions.append(f'Doc_.SaveProject "{path}"')
    return actions


def create_parts_actions(draft: dict, project_path: str | Path) -> list[str]:
    """Create Parts → BeginSolidEdit + 原生几何标记（实体 VBS API 未录制）。

    实体操作（Cuboid/Cylinder/Sphere/Rectangle）由 ``geometry_ops`` 原生
    Parasolid 直调（``execute_create_parts``）执行，不在 VBS 录制锁定范围；
    本函数只保留已锁定的 BeginSolidEdit 上下文，不伪造实体 VBS 调用。
    """
    path = Path(project_path).as_posix()
    shape = draft.get("shape", "?")
    name = draft.get("name", "Part")
    return [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        f'Doc_.OpenProject "{path}", False',
        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)",
        "MeshingGroup_.BeginSolidEdit",
        f"' Create {shape} name={name} → 实体操作走原生 geometry_ops"
        "（实体 VBS API 未录制）"[:180],
        f'Doc_.SaveProject "{path}"',
    ]


def modify_parts_actions(draft: dict, project_path: str | Path) -> list[str]:
    """Modify Parts → BeginSolidEdit + 原生几何标记（实体 VBS API 未录制）。

    布尔/变换/删面等操作由 ``geometry_ops.execute_modify_parts`` 原生执行，
    不在 VBS 录制锁定范围；本函数只保留 BeginSolidEdit 上下文。
    """
    path = Path(project_path).as_posix()
    op = draft.get("op_label") or draft.get("op") or "?"
    return [
        "Set App_ = GetApplication()",
        'If App_ Is Nothing Then Set App_ = '
        'CreateObject("scFLOWpre_Bx64net.Application.2025")',
        "Set Doc_ = App_.GetDocument",
        f'Doc_.OpenProject "{path}", False',
        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)",
        "MeshingGroup_.BeginSolidEdit",
        f"' Modify op={op} → 原生 geometry_ops（实体 VBS API 未录制）"[:180],
        f'Doc_.SaveProject "{path}"',
    ]


def write_nav_vbs(op: str, project_path: str | Path,
                  output: str | Path,
                  draft: Optional[dict] = None) -> Path:
    """写出导航/几何相关 VBS 草稿，返回路径。"""
    from automation.vbs_bridge import write_vbs_file
    if op in ("create_parts",):
        actions = create_parts_actions(draft or {}, project_path)
    elif op in ("modify_parts",):
        actions = modify_parts_actions(draft or {}, project_path)
    else:
        actions = wrapping_actions(op, project_path)
    return write_vbs_file(actions, output, title=f"pph_gui {op}")


def build_execute_vbs(project_path: str | Path, plan: dict,
                      output: str | Path,
                      marker: Optional[str | Path] = None,
                      step_marker: Optional[str | Path] = None,
                      include_save: bool = True,
                      xenv=None,
                      octree_sess: Optional[dict] = None,
                      parts_control_sess: Optional[dict] = None) -> Path:
    """生成可在 scFLOWpre 宿主中执行的 BAM→Octree→Mesh VBS。

    PPH 项目默认在末尾追加 ``Doc_.SaveProject``；传入 ``marker`` 时在脚本
    末尾写一个完成标记文件，供 GUI 轮询后自动 Reload。
    ``step_marker``：可选进度标记文件，脚本在 BAM/Octree/Mesh 完成后各写
    一行，供 GUI 显示“当前步骤”。

    ``octree_sess``：GUI ``session['octree_param']``，含 Detail 的
    ``region_size`` / ``min_oct_size`` 等；会生成 ``SetOctType`` /
    ``SetMinSize`` / ``OctParam_.SetParams``（缺前两者时宿主会复用旧
    八叉树尺寸，改 SECTITEM 也不生效）。

    ``parts_control_sess``：GUI ``session['parts_control']``，在打开项目后
    写入 ``SetPartsControl``（与 Parts Control 对话框勾选一致）。
    """
    steps = steps_from_execute_plan(plan)
    if include_save and Path(project_path).suffix.lower() == ".pph":
        steps.append("save_project")
    actions = PipelinePlan(project_path=str(project_path),
                           steps=steps).to_vbs_actions()
    # 打开项目后立刻同步 Parts Control（Execute 步骤本身不含 parts_control）
    if parts_control_sess is not None:
        insert_at = 0
        for i, line in enumerate(actions):
            if line.startswith("Doc_.Open"):
                insert_at = i + 1
                break
        actions[insert_at:insert_at] = parts_control_actions(parts_control_sess)
    if "generate_octree" in steps:
        idx = actions.index("MeshingGroup_.CreateOctree")
        insert_at = idx
        if idx > 0 and actions[idx - 1].startswith("Set MeshingGroup_ ="):
            insert_at = idx - 1
        chunk: list[str] = []
        settings = octree_settings_actions(xenv)
        if settings:
            chunk.extend(settings)
        # OctParam 必须在 CreateOctree 之前（录制顺序）
        chunk.extend(oct_param_actions(octree_sess))
        actions[insert_at:idx] = chunk
    elif octree_sess and "build_analysis_model" in steps:
        # 仅 BAM：OctParam 参数在 EndMDLWizard 之后设置（录制顺序）
        idx = actions.index("MeshingGroup_.EndMDLWizard") + 1
        actions[idx:idx] = oct_param_actions(octree_sess)
    if step_marker is not None:
        for anchor, step in (
            ("Doc_.EndWrapping", "wrap"),
            ("MeshingGroup_.EndMDLWizard", "bam"),
            ("MeshingGroup_.CreateOctree", "octree"),
            ("Doc_.WaitForWorker", "mesh"),
        ):
            if anchor in actions:
                at = actions.index(anchor) + 1
                actions[at:at] = _step_progress_actions(step_marker, step)
    if marker is not None:
        actions.append('Set fso_ = CreateObject("Scripting.FileSystemObject")')
        actions.append(f'Set tf_ = fso_.CreateTextFile("{marker}", True)')
        actions.append("tf_.Close")
    from automation.vbs_bridge import write_vbs_file
    return write_vbs_file(actions, output,
                          title="pph_gui scFLOWpre API execute")


def _step_progress_actions(step_marker: str | Path, step: str) -> list[str]:
    """追加一行步骤进度到 sidecar 文件（VBS FileSystemObject 追加模式）。"""
    return [
        'Set fso_ = CreateObject("Scripting.FileSystemObject")',
        f'Set tf_ = fso_.OpenTextFile("{step_marker}", 8, True)',
        f'tf_.WriteLine "{step}"',
        "tf_.Close",
    ]


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
        actions = [
            "Set App_ = GetApplication()",
            'If App_ Is Nothing Then Set App_ = '
            'CreateObject("scFLOWpre_Bx64net.Application.2025")',
            "Set Doc_ = App_.GetDocument",
            self.open_command(),
        ]
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
                # MeshingGroup_* / Conditions_* 调用前先取对象。
                if line.startswith("MeshingGroup_."):
                    actions.append(
                        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)")
                elif line.startswith("MeshingGroupSetting_."):
                    actions.append(
                        "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)")
                    actions.append(
                        "Set MeshingGroupSetting_ = "
                        "MeshingGroup_.GetMeshingGroupSetting")
                elif line.startswith("Conditions_."):
                    getter = "Set Conditions_ = Doc_.GetConditions"
                    if getter not in actions[-5:]:
                        actions.append(getter)
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
