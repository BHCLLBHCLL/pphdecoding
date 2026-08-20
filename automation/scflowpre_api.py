#!/usr/bin/env python3
"""scFLOWpre 官方 typed COM 桥（P9 路线：替代 VBS 字符串拼接）。

参考：``Manuals/scFLOW/HTML/VB_Interface_eng``（机读目录
``schemas/vb_api_catalog.json``：199 类 / 4455 成员，含签名/参数表/
Note）。ProgID：``scFLOWpre_Bx64net.Application.2025``。

与 cabdecoding ``cab_stpre_api.py`` 同模式，适配 scFLOWpre 事实：

* :class:`ComObject.call` 做 ``_FlagAsMethod`` 派发——手册任一成员可达，
  无需预写包装（官方手册 "VB interface usage in Python" 认证的模式；
  Application/Doc 的无参方法不 flag 会 DISP_E_MEMBERNOTFOUND）；
* typed 包装类覆盖高频成员：Application/Doc/Conditions/Condition/
  MeshingGroup/Octree/OctParam/WrappingGroup/Utility；
* :class:`ScFlowpreSession` 附着优先：宿主机上 Kicker 常驻实例
  （headless）几乎总在运行，``GetActiveObject``（ROT）附着它驱动，
  ``_owned=False`` 守卫——附着实例永不 ``Quit``；无运行实例时
  ``Dispatch`` 自启（``_owned=True``，close 时 Quit）；
* 就绪握手（P9-3）：``Doc.GetWorkerState``（0=无 worker 即空闲，
  1=worker 存在即忙）+ ``GetWorkerStateString`` 轮询，取代
  pywinauto 猜窗口；
* ``Application.ExecuteVBS``/``ExecuteVBSWithFile`` 仍可用
  （``execute_vbs``），作为 typed 直调之外的兼容通道。

线程亲和：COM 对象创建线程必须与调用线程一致；Session 首次调用时
``CoInitialize``，全部方法在同一线程使用（或用 ``run_com_thread``）。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

PROGID = "scFLOWpre_Bx64net.Application.2025"

last_error: Optional[str] = None
# GetWorkerState 返回值（手册）：0 无 worker（空闲） / 1 worker 存在（忙）
WORKER_IDLE = 0
WORKER_BUSY = 1


def set_error(msg: Optional[str]) -> None:
    global last_error
    last_error = msg


def api_available() -> bool:
    """True when the scFLOWpre COM ProgID is registered on this machine."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, PROGID):
            return True
    except Exception:
        return False


def host_process_running() -> bool:
    """True when a scFLOWpre process is already running.

    本机常态：Kicker 双实例常驻（headless）。单实例 COM 服务器上
    ``Dispatch`` 会返回该运行实例——因此探测到进程时一律走 attach
    路径（永不 Quit 用户/常驻实例）。
    """
    import subprocess
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq scFLOWpre_Bx64net.exe",
             "/NH"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout or ""
    except Exception:
        return False
    return "scflowpre_bx64net.exe" in out.lower()


def _ensure_com() -> None:
    """幂等初始化当前线程的 COM（STA）。"""
    import pythoncom
    pythoncom.CoInitialize()


def _invoke(obj, name: str, *args):
    """调用 COM 成员——先 ``_FlagAsMethod`` 再 invoke。

    scFLOWpre 的无参/纯 VARIANT 成员（OpenProject/GetConditions/
    SetModeOctree…）不 flag 会被晚绑定当属性读，触发
    ``Property ... can not be set`` / DISP_E_MEMBERNOTFOUND。
    """
    try:
        obj._FlagAsMethod(name)
    except AttributeError:
        pass  # already flagged or non-dynamic dispatch
    return getattr(obj, name)(*args)


# ============================================================================
# ComObject 基类：泛型逃生口 + typed 子类
# ============================================================================


class ComObject:
    """泛型晚绑定 COM 包装（cabdecoding ComObject 模式）。

    :meth:`call` 经 ``_FlagAsMethod`` 调任意手册成员；属性走
    :meth:`prop` / :meth:`set_prop`；:attr:`raw` 暴露底层 dispatch。
    """

    def __init__(self, obj):
        self._obj = obj

    @property
    def raw(self):
        return self._obj

    def call(self, name: str, *args):
        """按方法调用（``_FlagAsMethod`` 先行）。"""
        return _invoke(self._obj, name, *args)

    def prop(self, name: str, default=None):
        """读 COM 属性（失败返回 default）。"""
        try:
            return getattr(self._obj, name)
        except Exception:
            return default

    def set_prop(self, name: str, value) -> None:
        setattr(self._obj, name, value)

    def __repr__(self):
        return f"<{type(self).__name__} {self._obj!r}>"


class ScFlowpreApplication(ComObject):
    """Application 类（手册 21 方法 + Visible/ErrorCode 属性）。"""

    def GetDocument(self) -> "ScFlowpreDoc":
        return ScFlowpreDoc(self.call("GetDocument"))

    def ExecuteVBS(self, code: str) -> bool:
        return bool(self.call("ExecuteVBS", code))

    def ExecuteVBSWithFile(self, path: str | Path) -> bool:
        return bool(self.call("ExecuteVBSWithFile", str(Path(path).resolve())))

    def GetProcessID(self) -> Any:
        return self.call("GetProcessID")

    def GetFileVersion(self) -> Any:
        return self.call("GetFileVersion")

    def IsViewerMode(self) -> bool:
        return bool(self.call("IsViewerMode"))

    def BeginViewerMode(self) -> Any:
        return self.call("BeginViewerMode")

    def UpdateAll(self) -> None:
        self.call("UpdateAll")

    def Quit(self) -> None:
        self.call("Quit")

    @property
    def Visible(self):
        return self.prop("Visible")

    @Visible.setter
    def Visible(self, value) -> None:
        self.set_prop("Visible", value)


class ScFlowpreDoc(ComObject):
    """Doc 类高频成员（手册 424 方法，其余经 :meth:`call` 直达）。

    手册 Note：OpenProject 后建议 ``FixDefault``（修复历史 bug 造成的
    错误默认值）——:class:`ScFlowpreSession.open_project` 已内置。
    """

    # --- 工程 ---
    def OpenProject(self, path: str | Path) -> bool:
        return bool(self.call("OpenProject", str(Path(path).resolve())))

    def SaveProject(self, path: str | Path) -> bool:
        return bool(self.call("SaveProject", str(Path(path).resolve())))

    def CreateProject(self, name: str) -> None:
        self.call("CreateProject", name)

    def FixDefault(self) -> Any:
        return self.call("FixDefault")

    def GetProjectName(self) -> Any:
        return self.call("GetProjectName")

    def SetProjectName(self, name: str) -> Any:
        return self.call("SetProjectName", name)

    # --- 子对象 ---
    def GetConditions(self) -> "ScFlowpreConditions":
        return ScFlowpreConditions(self.call("GetConditions"))

    def GetUtility(self) -> "ScFlowpreUtility":
        return ScFlowpreUtility(self.call("GetUtility"))

    def GetProjectSetting(self) -> ComObject:
        return ComObject(self.call("GetProjectSetting"))

    def GetEnv(self) -> ComObject:
        return ComObject(self.call("GetEnv"))

    # --- 模式 ---
    def SetModeOctree(self) -> bool:
        return bool(self.call("SetModeOctree"))

    def SetModeMesh(self) -> bool:
        return bool(self.call("SetModeMesh"))

    def SetModePart(self) -> bool:
        return bool(self.call("SetModePart"))

    def SetModeWrap(self) -> bool:
        return bool(self.call("SetModeWrap"))

    def IsModeOctree(self) -> bool:
        return bool(self.call("IsModeOctree"))

    # --- 就绪握手（P9-3） ---
    def GetWorkerState(self) -> Any:
        """0 = 无 worker（空闲） / 1 = worker 存在（忙）。"""
        return self.call("GetWorkerState")

    def GetWorkerStateString(self) -> Any:
        return self.call("GetWorkerStateString")

    def InterruptWorker(self) -> Any:
        return self.call("InterruptWorker")

    def IsLicenseLost(self) -> bool:
        return bool(self.call("IsLicenseLost"))

    def RetryLostLicense(self) -> Any:
        return self.call("RetryLostLicense")

    # --- 网格组 ---
    def GetMeshingGroups(self) -> Any:
        return self.call("GetMeshingGroups")

    def GetActiveMeshingGroup(self) -> "ScFlowpreMeshingGroup":
        return ScFlowpreMeshingGroup(self.call("GetActiveMeshingGroup"))

    def SetActiveMeshingGroup(self, index: int, type_=0) -> bool:
        return bool(self.call("SetActiveMeshingGroup", index, type_))

    def CreateMeshingGroup(self) -> "ScFlowpreMeshingGroup":
        return ScFlowpreMeshingGroup(self.call("CreateMeshingGroup"))

    def QueryMeshingGroupByIndex(self, index: int) -> "ScFlowpreMeshingGroup":
        return ScFlowpreMeshingGroup(self.call("QueryMeshingGroupByIndex",
                                               index))

    def QueryWrappingGroupByIndex(self, index: int) -> "ScFlowpreWrappingGroup":
        return ScFlowpreWrappingGroup(
            self.call("QueryWrappingGroupByIndex", index))

    def QueryFaceRegionByName(self, name: str) -> ComObject:
        return ComObject(self.call("QueryFaceRegionByName", name))

    # --- 区域 ---
    def GetFaceRegions(self) -> Any:
        return self.call("GetFaceRegions")

    def GetFluidRegions(self) -> Any:
        return self.call("GetFluidRegions")

    def GetVolumeRegions(self) -> Any:
        return self.call("GetVolumeRegions")

    def IsNameUsed(self, name: str) -> bool:
        return bool(self.call("IsNameUsed", name))

    def GetUnusedName(self, name: str) -> Any:
        return self.call("GetUnusedName", name)

    # --- 事务 / Wrapping ---
    def BeginTransaction(self, name: str) -> None:
        self.call("BeginTransaction", name)

    def EndTransaction(self) -> bool:
        return bool(self.call("EndTransaction"))

    def BeginWrapping(self) -> bool:
        return bool(self.call("BeginWrapping"))

    def EndWrapping(self) -> Any:
        return self.call("EndWrapping")

    def CreateWrappingGroup(self) -> "ScFlowpreWrappingGroup":
        return ScFlowpreWrappingGroup(self.call("CreateWrappingGroup"))

    # --- CAD / 求解 / 导出 ---
    def OpenCadFile(self, path: str | Path) -> ComObject:
        """导入 CAD（返回 SNode）。"""
        return ComObject(self.call("OpenCadFile", str(Path(path).resolve())))

    def ImportCADAsFacet(self, path: str | Path, meshgroup) -> bool:
        return bool(self.call("ImportCADAsFacet",
                              str(Path(path).resolve()), meshgroup))

    def ImportXML(self, path: str | Path) -> ComObject:
        return ComObject(self.call("ImportXML", str(Path(path).resolve())))

    def ExportXML(self, path: str | Path) -> bool:
        return bool(self.call("ExportXML", str(Path(path).resolve())))

    def BuildAnalysisModel(self) -> bool:
        return bool(self.call("BuildAnalysisModel"))

    def ExecuteSolver(self, sph_path: str | Path) -> bool:
        return bool(self.call("ExecuteSolver", str(Path(sph_path).resolve())))

    def SaveCmbFile(self, path: str | Path, type_=0) -> bool:
        return bool(self.call("SaveCmbFile", str(Path(path).resolve()), type_))

    def SavePolyFile(self, path: str | Path) -> bool:
        return bool(self.call("SavePolyFile", str(Path(path).resolve())))

    def SaveXTFile(self, path: str | Path) -> bool:
        return bool(self.call("SaveXTFile", str(Path(path).resolve())))


class ScFlowpreConditions(ComObject):
    """Conditions 聚合类（手册 607 方法：Create* 85 / Set* 166 / Query* 18）。

    typed 只覆盖高频；其余经 :meth:`call` 直达，或用
    :meth:`create_cond` / :meth:`query_cond` 泛型。
    """

    def QueryConditionByName(self, name: str) -> "ScFlowpreCondition":
        return ScFlowpreCondition(self.call("QueryConditionByName", name))

    def create_cond(self, cond_type: str, *args) -> "ScFlowpreCondition":
        """泛型 ``CreateCond<type>``（85 个子类的逃生口）。

        ``create_cond("Fan")`` → ``conditions.CreateCondFan()``。
        """
        return ScFlowpreCondition(self.call("CreateCond" + cond_type, *args))

    def query_cond(self, method: str, *args) -> "ScFlowpreCondition":
        """泛型 ``QueryCond<Method>``（QueryCondDTSR 等带参查询）。"""
        return ScFlowpreCondition(self.call("QueryCond" + method, *args))

    def DeleteCondition(self, name: str) -> bool:
        return bool(self.call("DeleteCondition", name))

    def GetAnalysisType(self, type_) -> Any:
        return self.call("GetAnalysisType", type_)

    def SetAnalysisType(self, type_, flag) -> Any:
        return self.call("SetAnalysisType", type_, flag)

    def GetPartsControl(self, type_) -> Any:
        return self.call("GetPartsControl", type_)

    def GetUnusedName(self, name: str) -> Any:
        return self.call("GetUnusedName", name)

    def IsNameUsed(self, name: str) -> bool:
        return bool(self.call("IsNameUsed", name))


class ScFlowpreCondition(ComObject):
    """Condition 基类（手册 8 方法；138 个 Cond* 子类全部继承）。"""

    def GetName(self) -> Any:
        return self.call("GetName")

    def SetName(self, name: str) -> bool:
        return bool(self.call("SetName", name))

    def GetConditionType(self) -> Any:
        return self.call("GetConditionType")

    def GetRegions(self) -> Any:
        return self.call("GetRegions")

    def ApplyToRegion(self, name: str) -> bool:
        return bool(self.call("ApplyToRegion", name))

    def RemoveFromRegion(self, name: str) -> bool:
        return bool(self.call("RemoveFromRegion", name))

    def RemoveFromAllRegions(self) -> bool:
        return bool(self.call("RemoveFromAllRegions"))

    def DoesConflictWithAnalysisType(self) -> bool:
        return bool(self.call("DoesConflictWithAnalysisType"))


class ScFlowpreMeshingGroup(ComObject):
    """MeshingGroup 类高频成员（手册 173 方法）。"""

    def CreateOctree(self) -> bool:
        return bool(self.call("CreateOctree"))

    def CreateOctreeForSolidBase(self) -> bool:
        return bool(self.call("CreateOctreeForSolidBase"))

    def DeleteOctree(self) -> bool:
        return bool(self.call("DeleteOctree"))

    def DoesMeshingOctreeExist(self) -> bool:
        return bool(self.call("DoesMeshingOctreeExist"))

    def CreateMesh(self) -> bool:
        return bool(self.call("CreateMesh"))

    def DeleteMesh(self) -> Any:
        return self.call("DeleteMesh")

    def DoesMeshExist(self) -> bool:
        return bool(self.call("DoesMeshExist"))

    def BuildAnalysisModel(self) -> bool:
        return bool(self.call("BuildAnalysisModel"))

    def DoesMeshErrorExist(self) -> bool:
        return bool(self.call("DoesMeshErrorExist"))


class ScFlowpreOctree(ComObject):
    """Octree 类（手册 28 方法全量）。"""

    def Refine(self) -> Any:
        return self.call("Refine")

    def RefineByLevel(self, level, range_) -> Any:
        return self.call("RefineByLevel", level, range_)

    def RefineByNumber(self, level, num) -> Any:
        return self.call("RefineByNumber", level, num)

    def RefineFromCurvature(self, rangeminarray, rangemaxarray,
                            lowerlimit) -> bool:
        return bool(self.call("RefineFromCurvature", rangeminarray,
                              rangemaxarray, lowerlimit))

    def Merge(self) -> Any:
        return self.call("Merge")

    def Save(self, path: str | Path) -> bool:
        return bool(self.call("Save", str(Path(path).resolve())))

    def GetOctantCountByGroup(self, group) -> Any:
        return self.call("GetOctantCountByGroup", group)

    def GetRootOctantSize(self) -> Any:
        return self.call("GetRootOctantSize")

    def GetOctLevelSize(self) -> Any:
        return self.call("GetOctLevelSize")

    def GetOctInfo(self, info) -> Any:
        return self.call("GetOctInfo", info)

    def GetCurvatureHistgram(self, rangeminarray, rangemaxarray,
                             areaarray) -> Any:
        return self.call("GetCurvatureHistgram", rangeminarray,
                         rangemaxarray, areaarray)

    def CreateCurvatureArray(self) -> Any:
        return self.call("CreateCurvatureArray")

    def IsEdited(self) -> bool:
        return bool(self.call("IsEdited"))

    def IsForMeshingWithSolidBaseSurfMesher(self) -> bool:
        return bool(self.call("IsForMeshingWithSolidBaseSurfMesher"))

    def UpdateGroups(self) -> bool:
        return bool(self.call("UpdateGroups"))

    def GetMeshingGroup(self) -> ScFlowpreMeshingGroup:
        return ScFlowpreMeshingGroup(self.call("GetMeshingGroup"))

    def GetWrappingGroup(self) -> "ScFlowpreWrappingGroup":
        return ScFlowpreWrappingGroup(self.call("GetWrappingGroup"))

    def GetVisible(self) -> bool:
        return bool(self.call("GetVisible"))

    def SetVisible(self, b_visible: bool) -> Any:
        return self.call("SetVisible", b_visible)

    def ShowAll(self) -> Any:
        return self.call("ShowAll")

    def ShowNearbyOctant(self, b_node_connect) -> Any:
        return self.call("ShowNearbyOctant", b_node_connect)

    def ShowNearbyOctantByDirection(self, b_direction) -> Any:
        return self.call("ShowNearbyOctantByDirection", b_direction)

    def ShowOctantByGroup(self, groups) -> Any:
        return self.call("ShowOctantByGroup", groups)

    def ShowOctByLevels(self, b_all_target, levels) -> Any:
        return self.call("ShowOctByLevels", b_all_target, levels)

    def ShowOctBySelectedEdge(self) -> Any:
        return self.call("ShowOctBySelectedEdge")

    def ShowOctBySelectedFace(self) -> Any:
        return self.call("ShowOctBySelectedFace")


class ScFlowpreOctParam(ComObject):
    """OctParam 类（手册 18 方法全量）。"""

    def Initialize(self) -> Any:
        return self.call("Initialize")

    def GetOctType(self) -> Any:
        return self.call("GetOctType")

    def SetOctType(self, type_) -> Any:
        return self.call("SetOctType", type_)

    def GetMeshNum(self) -> Any:
        return self.call("GetMeshNum")

    def SetMeshNum(self, num) -> Any:
        return self.call("SetMeshNum", num)

    def GetMinSize(self) -> Any:
        return self.call("GetMinSize")

    def GetParams(self) -> Any:
        return self.call("GetParams")

    def GetPureParams(self) -> Any:
        return self.call("GetPureParams")

    def SetParams(self, param) -> Any:
        return self.call("SetParams", param)

    def SetBoundingBox(self, bbox) -> Any:
        return self.call("SetBoundingBox", bbox)

    def GetGlobalAngularPrecisionMinOctLimitSize(self) -> Any:
        return self.call("GetGlobalAngularPrecisionMinOctLimitSize")

    def SetGlobalAngularPrecisionMinOctLimitSize(self, limit_size) -> Any:
        return self.call("SetGlobalAngularPrecisionMinOctLimitSize",
                         limit_size)

    def GetAngularPrecision(self, regionarray, anglearray, neighborarray,
                            limitarray) -> Any:
        return self.call("GetAngularPrecision", regionarray, anglearray,
                         neighborarray, limitarray)

    def SetAngularPrecision(self, newregionarray, newanglearray,
                            newneighborarray, newlimitarray) -> Any:
        return self.call("SetAngularPrecision", newregionarray,
                         newanglearray, newneighborarray, newlimitarray)

    def IsForEnv(self) -> bool:
        return bool(self.call("IsForEnv"))

    def GetWrappingGroup(self) -> "ScFlowpreWrappingGroup":
        return ScFlowpreWrappingGroup(self.call("GetWrappingGroup"))


class ScFlowpreWrappingGroup(ComObject):
    """WrappingGroup 类（手册 30 方法全量）。"""

    def CreateOctree(self) -> "ScFlowpreOctree":
        return ScFlowpreOctree(self.call("CreateOctree"))

    def GetOctree(self) -> ScFlowpreOctree:
        return ScFlowpreOctree(self.call("GetOctree"))

    def DeleteOctree(self) -> Any:
        return self.call("DeleteOctree")

    def ImportOctree(self, path: str | Path) -> ScFlowpreOctree:
        return ScFlowpreOctree(self.call("ImportOctree",
                                         str(Path(path).resolve())))

    def GetOctParam(self) -> ScFlowpreOctParam:
        return ScFlowpreOctParam(self.call("GetOctParam"))

    def GetWrappingParam(self) -> ComObject:
        return ComObject(self.call("GetWrappingParam"))

    def ExecuteWrapping(self) -> bool:
        return bool(self.call("ExecuteWrapping"))

    def IsWrapped(self) -> bool:
        return bool(self.call("IsWrapped"))

    def GetWrappingMode(self) -> Any:
        return self.call("GetWrappingMode")

    def SetWrappingMode(self, flag) -> bool:
        return bool(self.call("SetWrappingMode", flag))

    def GetRootSNode(self) -> ComObject:
        return ComObject(self.call("GetRootSNode"))

    def GetSelectedMDLFaceCount(self) -> Any:
        return self.call("GetSelectedMDLFaceCount")

    def GetSelectedMDLFaces(self) -> Any:
        return self.call("GetSelectedMDLFaces")

    def SelectMDLFace(self, n_face, b_select, b_spread) -> bool:
        return bool(self.call("SelectMDLFace", n_face, b_select, b_spread))

    def SelectAllMDLFace(self, b_select) -> Any:
        return self.call("SelectAllMDLFace", b_select)

    def SelectMDLEdge(self, n_face, n_edge, b_select, b_spread) -> bool:
        return bool(self.call("SelectMDLEdge", n_face, n_edge, b_select,
                              b_spread))

    def SelectAllMDLEdge(self, b_select) -> Any:
        return self.call("SelectAllMDLEdge", b_select)

    def SelectAllMDLRidge(self) -> Any:
        return self.call("SelectAllMDLRidge")

    def IsMDLFaceSelected(self, n_face) -> bool:
        return bool(self.call("IsMDLFaceSelected", n_face))

    def IsMDLEdgeSelected(self, n_face, n_edge) -> bool:
        return bool(self.call("IsMDLEdgeSelected", n_face, n_edge))

    def HideSelectedMDLFaces(self) -> Any:
        return self.call("HideSelectedMDLFaces")

    def ShowAllMDL(self) -> Any:
        return self.call("ShowAllMDL")

    def ShowOnlySelectedMDLFaces(self) -> Any:
        return self.call("ShowOnlySelectedMDLFaces")

    def SaveMDL(self, path: str | Path) -> bool:
        return bool(self.call("SaveMDL", str(Path(path).resolve())))

    def SaveXTFile(self, path: str | Path) -> bool:
        return bool(self.call("SaveXTFile", str(Path(path).resolve())))

    def GetIndex(self) -> Any:
        return self.call("GetIndex")

    def GetVisible(self) -> bool:
        return bool(self.call("GetVisible"))

    def SetVisible(self, flag) -> bool:
        return bool(self.call("SetVisible", flag))

    def IsExpanded(self) -> bool:
        return bool(self.call("IsExpanded"))

    def SetExpand(self, b_expand) -> Any:
        return self.call("SetExpand", b_expand)


class ScFlowpreUtility(ComObject):
    """Utility 类（手册 16 方法全量；doc.GetUtility 获取）。"""

    def ConvertValueWithUnit(self, value, from_unit, to_unit) -> Any:
        return self.call("ConvertValueWithUnit", value, from_unit, to_unit)

    def GetUnitCandidate(self) -> Any:
        return self.call("GetUnitCandidate")

    def GetSphUnit(self) -> Any:
        return self.call("GetSphUnit")

    def ScreenToWorldCoord(self, x, y) -> Any:
        return self.call("ScreenToWorldCoord", x, y)

    def WorldCoordToScreen(self, x, y, z) -> Any:
        return self.call("WorldCoordToScreen", x, y, z)

    def GetFaceDirectionByMaterial(self, faces, types) -> Any:
        return self.call("GetFaceDirectionByMaterial", faces, types)

    def GetMeshElemNumFromMergedElemNum(self, merged_num, meshing_unit,
                                        num) -> Any:
        return self.call("GetMeshElemNumFromMergedElemNum", merged_num,
                         meshing_unit, num)

    def ApplyLayerNumRatioToHYBRIDPARAM(self, hybrid_param, layer_num,
                                        ratio) -> Any:
        return self.call("ApplyLayerNumRatioToHYBRIDPARAM", hybrid_param,
                         layer_num, ratio)

    def GetLayerNumRatioFromHYBRIDPARAM(self, hybrid_param) -> Any:
        return self.call("GetLayerNumRatioFromHYBRIDPARAM", hybrid_param)

    def CalcSweepLayerThicknessByInnerRatio(self, num, ratio,
                                            total_thickness) -> Any:
        return self.call("CalcSweepLayerThicknessByInnerRatio", num, ratio,
                         total_thickness)

    def CalcSweepLayerThicknessByOuterRatio(self, num, ratio,
                                            total_thickness) -> Any:
        return self.call("CalcSweepLayerThicknessByOuterRatio", num, ratio,
                         total_thickness)

    def CalcNormalizedSweepLayerThicknessByEachThickness(self, layers,
                                                         total_thickness):
        return self.call("CalcNormalizedSweepLayerThicknessByEachThickness",
                         layers, total_thickness)

    def ConvertPlaneParamEquationtoNorm(self, param) -> Any:
        return self.call("ConvertPlaneParamEquationtoNorm", param)

    def ConvertPlaneParamNormtoEquation(self, param) -> Any:
        return self.call("ConvertPlaneParamNormtoEquation", param)

    def ConvertPlaneParamXYZtoEquation(self, param) -> Any:
        return self.call("ConvertPlaneParamXYZtoEquation", param)

    def ConvertPlaneParamXYZtoNorm(self, param) -> Any:
        return self.call("ConvertPlaneParamXYZtoNorm", param)


# ============================================================================
# Session：附着优先 + 就绪握手 + 管线便利
# ============================================================================


class ScFlowpreSession:
    """可复用 scFLOWpre COM 会话（attach 优先，own 守卫）。

    本机常态：Kicker 常驻实例 headless 运行 → ``connect()`` 走
    ``GetActiveObject``（ROT）附着，``_owned=False``，close 不 Quit。
    无运行实例 → ``Dispatch`` 自启，``_owned=True``，close 时 Quit。
    """

    def __init__(self):
        self._app = None
        self._doc = None
        self._owned = False

    # --- 连接 ---
    def connect(self) -> bool:
        """附着运行实例（ROT），否则 Dispatch 自启。"""
        global last_error
        if self._app is not None:
            return True
        try:
            _ensure_com()
            import win32com.client
        except ImportError as exc:
            set_error(f"pywin32 unavailable: {exc!r}")
            return False
        app = None
        if host_process_running():
            try:
                app = win32com.client.GetActiveObject(PROGID)
                self._owned = False
            except Exception:
                app = None
        if app is None:
            try:
                app = win32com.client.Dispatch(PROGID)
                # Dispatch 对单实例服务器可能返回已运行实例：
                # 探测过进程则视为附着（保守，不 Quit）。
                self._owned = not host_process_running()
            except Exception as exc:
                set_error(f"COM connect failed: {exc!r}")
                return False
        try:
            self._app = ScFlowpreApplication(app)
            self._doc = self._app.GetDocument()
        except Exception as exc:
            set_error(f"GetDocument failed: {exc!r}")
            self._app = None
            return False
        set_error(None)
        return True

    @property
    def is_connected(self) -> bool:
        return self._app is not None

    @property
    def owned(self) -> bool:
        """True = 自启实例（close 会 Quit）；False = 附着（永不 Quit）。"""
        return self._owned

    @property
    def app(self) -> Optional[ScFlowpreApplication]:
        return self._app

    @property
    def doc(self) -> Optional[ScFlowpreDoc]:
        return self._doc

    # --- 就绪握手（P9-3） ---
    def worker_state(self) -> tuple[Any, Any]:
        """(state, state_string)：state 0=空闲 / 1=忙（手册语义）。"""
        if self._doc is None:
            return (None, None)
        try:
            state = self._doc.GetWorkerState()
        except Exception:
            state = None
        try:
            text = self._doc.GetWorkerStateString()
        except Exception:
            text = None
        return (state, text)

    def wait_ready(self, timeout: float = 60.0,
                   poll: float = 0.5) -> bool:
        """轮询 ``GetWorkerState == 0``（无 worker）直至就绪或超时。

        取代 pywinauto 猜窗口的官方就绪判定。
        """
        global last_error
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state, _ = self.worker_state()
            if state == WORKER_IDLE:
                set_error(None)
                return True
            time.sleep(poll)
        set_error(f"wait_ready timeout after {timeout}s "
                  f"(last state={self.worker_state()})")
        return False

    # --- 工程 ---
    def open_project(self, path: str | Path, *, fix_default: bool = True,
                     wait: float = 120.0) -> bool:
        """OpenProject（+ 手册 Note 建议的 FixDefault）+ 等待 worker 空闲。"""
        global last_error
        if not self.connect():
            return False
        try:
            ok = self._doc.OpenProject(path)
        except Exception as exc:
            set_error(f"OpenProject raised: {exc!r}")
            return False
        if not ok:
            set_error(f"OpenProject returned False: {path}")
            return False
        if fix_default:
            try:
                self._doc.FixDefault()
            except Exception:
                pass  # 部分工程无默认值可修
        if wait > 0:
            return self.wait_ready(wait)
        set_error(None)
        return True

    def save_project(self, path: str | Path) -> bool:
        if self._doc is None:
            set_error("no document")
            return False
        try:
            ok = self._doc.SaveProject(path)
        except Exception as exc:
            set_error(f"SaveProject raised: {exc!r}")
            return False
        if not ok:
            set_error(f"SaveProject returned False: {path}")
            return False
        set_error(None)
        return True

    # --- VBS 兼容通道 ---
    def execute_vbs(self, code: str) -> bool:
        """Application.ExecuteVBS（typed 直调之外的兼容通道）。"""
        if not self.connect():
            return False
        return self._app.ExecuteVBS(code)

    def execute_vbs_file(self, path: str | Path) -> bool:
        if not self.connect():
            return False
        return self._app.ExecuteVBSWithFile(path)

    # --- 收尾 ---
    def close(self) -> None:
        if self._app is not None and self._owned:
            try:
                self._app.Quit()
            except Exception:
                pass
        self._app = None
        self._doc = None
        self._owned = False


def host_status() -> dict:
    """诊断快照：ProgID 注册 / 进程 / 会话 / worker 状态。"""
    info = {
        "progid": PROGID,
        "registered": api_available(),
        "process_running": host_process_running(),
    }
    session = ScFlowpreSession()
    try:
        if session.connect():
            info["connected"] = True
            info["owned"] = session.owned
            try:
                info["file_version"] = session.app.GetFileVersion()
            except Exception:
                pass
            state, text = session.worker_state()
            info["worker_state"] = state
            info["worker_state_string"] = text
            info["ready"] = (state == WORKER_IDLE)
        else:
            info["connected"] = False
            info["error"] = last_error
    finally:
        session.close()
    return info


def run_pipeline(project_in: str | Path, project_out: str | Path, *,
                 build_analysis_model: bool = False,
                 wait: float = 180.0) -> dict:
    """typed 直调全管线：open → (调用方自行驱动) → save。

    最小闭环为 open_project（含 FixDefault + wait_ready）与
    save_project；中间步骤（octree/wrapping/conditions）由调用方经
    ``session.doc`` typed 直调或 :meth:`ScFlowpreSession.execute_vbs`
    混合驱动。返回诊断 dict。
    """
    session = ScFlowpreSession()
    result: dict = {"ok": False}
    try:
        if not session.connect():
            result["error"] = last_error
            return result
        result["owned"] = session.owned
        if not session.open_project(project_in, wait=wait):
            result["error"] = last_error
            return result
        if build_analysis_model:
            try:
                result["build_analysis_model"] = \
                    session.doc.BuildAnalysisModel()
            except Exception as exc:
                result["error"] = f"BuildAnalysisModel: {exc!r}"
                return result
            if not session.wait_ready(wait):
                result["error"] = last_error
                return result
        if not session.save_project(project_out):
            result["error"] = last_error
            return result
        result["ok"] = True
        result["out"] = str(Path(project_out).resolve())
        return result
    finally:
        session.close()


def _cli(argv: list[str] | None = None) -> int:
    """CLI::

        python -m automation.scflowpre_api status [--timeout 30]
        python -m automation.scflowpre_api open <pph> [--timeout 180]
        python -m automation.scflowpre_api vbs <file.vbs>
        python -m automation.scflowpre_api pipeline <in.pph> <out.pph>
    """
    import argparse
    import threading

    ap = argparse.ArgumentParser(prog="scflowpre_api",
                                 description="scFLOWpre typed COM bridge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_status = sub.add_parser("status", help="host diagnostics")
    p_status.add_argument("--timeout", type=float, default=30.0)
    p_open = sub.add_parser("open", help="open project (typed direct)")
    p_open.add_argument("pph")
    p_open.add_argument("--timeout", type=float, default=180.0)
    p_vbs = sub.add_parser("vbs", help="ExecuteVBSWithFile")
    p_vbs.add_argument("file")
    p_pipe = sub.add_parser("pipeline", help="open + save round-trip")
    p_pipe.add_argument("pph_in")
    p_pipe.add_argument("pph_out")
    p_pipe.add_argument("--build", action="store_true",
                        help="BuildAnalysisModel before save")
    p_pipe.add_argument("--timeout", type=float, default=180.0)
    args = ap.parse_args(argv)

    if args.cmd == "status":
        # COM 调用可能挂起（Dispatch 拉起宿主 / 许可等待）——线程 +
        # join 超时保护，绝不无限阻塞
        box: dict = {}
        t = threading.Thread(
            target=lambda: box.update(host_status()), daemon=True)
        t.start()
        t.join(args.timeout)
        if t.is_alive():
            print(f"timeout after {args.timeout}s (dispatch hung or host "
                  "busy); registered={{{api_available()}}} "
                  f"process={host_process_running()}")
            return 3
        info = box
        print("connected:", info.get("connected"))
        print("owned:", info.get("owned"))
        print("file_version:", info.get("file_version"))
        print("worker_state:", info.get("worker_state"),
              info.get("worker_state_string"))
        print("ready:", info.get("ready"))
        if not info.get("connected"):
            print("error:", info.get("error"))
            return 1
        return 0

    if args.cmd == "open":
        session = ScFlowpreSession()
        try:
            if not session.connect():
                print("connect failed:", last_error)
                return 1
            if not session.open_project(args.pph, wait=args.timeout):
                print("open failed:", last_error)
                return 1
            state, text = session.worker_state()
            print(f"opened {args.pph} worker_state={state} ({text})")
            return 0
        finally:
            session.close()

    if args.cmd == "vbs":
        session = ScFlowpreSession()
        try:
            if not session.connect():
                print("connect failed:", last_error)
                return 1
            ok = session.execute_vbs_file(args.file)
            print("ExecuteVBSWithFile:", ok)
            return 0 if ok else 1
        finally:
            session.close()

    if args.cmd == "pipeline":
        result = run_pipeline(args.pph_in, args.pph_out,
                              build_analysis_model=args.build,
                              wait=args.timeout)
        print("ok:", result.get("ok"))
        if not result.get("ok"):
            print("error:", result.get("error"))
            return 1
        print("out:", result.get("out"))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
