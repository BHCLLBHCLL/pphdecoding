#!/usr/bin/env python3
"""scFLOWpre 官方 typed COM 桥（P9 路线：替代 VBS 字符串拼接）。

参考：``Manuals/scFLOW/HTML/VB_Interface_eng``（机读目录
``schemas/vb_api_catalog.json``：199 类 / 4455 成员，含签名/参数表/
Note）。ProgID：``scFLOWpre_Bx64net.Application.2025``。

与 cabdecoding ``cab_stpre_api.py`` 同模式，适配 scFLOWpre 事实：

* :class:`ComObject.call` 做 ``_FlagAsMethod`` 派发——手册任一成员可达，
  无需预写包装（官方手册 "VB interface usage in Python" 认证的模式；
  Application/Doc 的无参方法不 flag 会 DISP_E_MEMBERNOTFOUND）；
* typed 包装类覆盖高频成员（P12-A 起 17 类，经 ``TYPED_CLASSES``
  注册表对 catalog 199 类全量对账）：Application/Doc/Conditions/
  Condition/MeshingGroup/Octree/OctParam/WrappingGroup/Utility/Region/
  SNode/FaceRegion/FluidRegion/NumericalRegion/SubmeshSurfaceRegion/
  AdaptiveParam/MeshingGroupSetting；136 个 ``Cond*`` 标记子类经
  Condition 泛型出口，其余手册类经 ``ComObject.call`` 直达；
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

    def QueryFaceRegionByName(self, name: str) -> "ScFlowpreFaceRegion":
        return ScFlowpreFaceRegion(self.call("QueryFaceRegionByName", name))

    # --- 区域创建（P12-A typed 建面：Register Region 权威路线） ---
    def CreateFaceRegion(self, name: str) -> "ScFlowpreFaceRegion":
        return ScFlowpreFaceRegion(self.call("CreateFaceRegion", name))

    def CreateFluidRegion(self, name: str) -> "ScFlowpreFluidRegion":
        return ScFlowpreFluidRegion(self.call("CreateFluidRegion", name))

    def CreateNumericalRegion(self, name: str,
                              type_) -> "ScFlowpreNumericalRegion":
        return ScFlowpreNumericalRegion(
            self.call("CreateNumericalRegion", name, type_))

    def CreateSubmeshSurfaceRegion(
            self, name: str) -> "ScFlowpreSubmeshSurfaceRegion":
        return ScFlowpreSubmeshSurfaceRegion(
            self.call("CreateSubmeshSurfaceRegion", name))

    def CreateSubmeshMeshingGroup(self, name: str) -> ComObject:
        return ComObject(self.call("CreateSubmeshMeshingGroup", name))

    def CreateDiscontinuousMeshingGroupWithMovingPart(
            self, name: str) -> ComObject:
        return ComObject(
            self.call("CreateDiscontinuousMeshingGroupWithMovingPart", name))

    def CreateCoordinatesSpecifiedPart(self, name: str) -> ComObject:
        return ComObject(self.call("CreateCoordinatesSpecifiedPart", name))

    def CreateGroupPart(self, name: str) -> Any:
        return self.call("CreateGroupPart", name)

    # --- SNode（P12-D CreateMDL 注入路线） ---
    def QuerySNodeByName(self, name: str) -> "ScFlowpreSNode":
        return ScFlowpreSNode(self.call("QuerySNodeByName", name))

    def GetAdaptiveParam(self) -> "ScFlowpreAdaptiveParam":
        return ScFlowpreAdaptiveParam(self.call("GetAdaptiveParam"))

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
    def OpenCadFile(self, path: str | Path) -> "ScFlowpreSNode":
        """导入 CAD（XT/STEP 等，返回 SNode）。"""
        return ScFlowpreSNode(
            self.call("OpenCadFile", str(Path(path).resolve())))

    def ImportCADAsFacet(self, path: str | Path, meshgroup) -> bool:
        return bool(self.call("ImportCADAsFacet",
                              str(Path(path).resolve()), meshgroup))

    def ImportPatchAsCAD(self, path: str | Path) -> ComObject:
        """导入 patch 文件为 CAD（Define Facet Part 前置）。"""
        return ComObject(
            self.call("ImportPatchAsCAD", str(Path(path).resolve())))

    def ImportXML(self, path: str | Path) -> ComObject:
        return ComObject(self.call("ImportXML", str(Path(path).resolve())))

    def ExportXML(self, path: str | Path) -> bool:
        return bool(self.call("ExportXML", str(Path(path).resolve())))

    def BuildAnalysisModel(self) -> bool:
        return bool(self.call("BuildAnalysisModel"))

    def ExecuteSolver(self, sph_path: str | Path) -> bool:
        return bool(self.call("ExecuteSolver", str(Path(sph_path).resolve())))

    def QuitAndExecuteSolver(self, sph_path: str | Path) -> bool:
        """提交求解并退出前处理（P12-B 求解链路入口）。"""
        return bool(self.call("QuitAndExecuteSolver",
                              str(Path(sph_path).resolve())))

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

    def IsAnalysisModelBuilt(self) -> bool:
        return bool(self.call("IsAnalysisModelBuilt"))

    # --- 子对象（P12-A typed 建面） ---
    def GetOctree(self) -> "ScFlowpreOctree":
        return ScFlowpreOctree(self.call("GetOctree"))

    def GetOctParam(self) -> "ScFlowpreOctParam":
        return ScFlowpreOctParam(self.call("GetOctParam"))

    def GetMeshingGroupSetting(self) -> "ScFlowpreMeshingGroupSetting":
        return ScFlowpreMeshingGroupSetting(
            self.call("GetMeshingGroupSetting"))

    # --- MDL Wizard / VMDL（P12-E BAM e2e 面） ---
    def BeginMDLWizard(self) -> bool:
        return bool(self.call("BeginMDLWizard"))

    def EndMDLWizard(self) -> bool:
        return bool(self.call("EndMDLWizard"))

    def CancelMDLWizard(self) -> bool:
        return bool(self.call("CancelMDLWizard"))

    def GetMDLWizard(self) -> ComObject:
        return ComObject(self.call("GetMDLWizard"))

    def CreateVMDL(self) -> bool:
        return bool(self.call("CreateVMDL"))

    def GetVMDL(self) -> ComObject:
        return ComObject(self.call("GetVMDL"))

    def GetMDL(self) -> ComObject:
        return ComObject(self.call("GetMDL"))

    def DeleteMDL(self) -> bool:
        return bool(self.call("DeleteMDL"))

    def GetCreateVMDLError(self) -> Any:
        return self.call("GetCreateVMDLError")

    # --- 网格检查族（View/Select 菜单权威后端） ---
    def CheckIntersectionForMeshModel(self) -> Any:
        return self.call("CheckIntersectionForMeshModel")

    def check(self, name: str, *args) -> Any:
        """泛型 ``Check*``（12 项质量检查：AbnormalFaceDirection /
        AtomicElementVolume / BothSideSameElement / …）。"""
        return self.call("Check" + name, *args)


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




class ScFlowpreRegion(ComObject):
    """Region 基类（手册 6 方法全量；FaceRegion/FluidRegion 等的公共面）。"""

    def GetName(self) -> Any:
        return self.call("GetName")

    def SetName(self, name: str) -> Any:
        return self.call("SetName", name)

    def GetRegionType(self) -> Any:
        return self.call("GetRegionType")

    def GetConditions(self) -> Any:
        return self.call("GetConditions")

    def GetValue(self, name: str) -> Any:
        return self.call("GetValue", name)

    def CheckConditionExist(self, name: str) -> bool:
        return bool(self.call("CheckConditionExist", name))


class ScFlowpreSNode(ComObject):
    """SNode 类高频成员（手册 145 方法，其余经 :meth:`call` 直达）。

    P12-D CreateMDL 注入路线的核心对象（OpenCadFile / QuerySNodeByName /
    CreateGroupPart 产物）。
    """

    # --- 树结构 ---
    def GetParent(self) -> "ScFlowpreSNode":
        return ScFlowpreSNode(self.call("GetParent"))

    def GetChild(self, index) -> "ScFlowpreSNode":
        return ScFlowpreSNode(self.call("GetChild", index))

    def GetChildren(self) -> Any:
        return self.call("GetChildren")

    def GetNextSibling(self) -> "ScFlowpreSNode":
        return ScFlowpreSNode(self.call("GetNextSibling"))

    def CanHaveChild(self) -> bool:
        return bool(self.call("CanHaveChild"))

    # --- 身份 / 类型 ---
    def GetOriginalName(self) -> Any:
        return self.call("GetOriginalName")

    def IsGroupPart(self) -> bool:
        return bool(self.call("IsGroupPart"))

    def IsGroupPartComponent(self) -> bool:
        return bool(self.call("IsGroupPartComponent"))

    def IsAssembly(self) -> bool:
        return bool(self.call("IsAssembly"))

    def IsFluid(self) -> bool:
        return bool(self.call("IsFluid"))

    def IsObstacle(self) -> bool:
        return bool(self.call("IsObstacle"))

    def SetObstacle(self, flag) -> Any:
        return self.call("SetObstacle", flag)

    def IsSheet(self) -> bool:
        return bool(self.call("IsSheet"))

    def IsSheetTypePanel(self) -> bool:
        return bool(self.call("IsSheetTypePanel"))

    def GetGroupNumber(self) -> Any:
        return self.call("GetGroupNumber")

    def SetGroupNumber(self, number) -> Any:
        return self.call("SetGroupNumber", number)

    # --- 细化参数 ---
    def GetFacetingParameter(self) -> Any:
        return self.call("GetFacetingParameter")

    def SetFacetingParameter(self, param) -> Any:
        return self.call("SetFacetingParameter", param)

    def ClearFacetingParameter(self) -> Any:
        return self.call("ClearFacetingParameter")

    def IsFacetingParameterSet(self) -> bool:
        return bool(self.call("IsFacetingParameterSet"))

    def GetFacetingParameterType(self) -> Any:
        return self.call("GetFacetingParameterType")

    def SetFacetingParameterType(self, type_) -> Any:
        return self.call("SetFacetingParameterType", type_)

    def GetFacetingOptionParameter(self) -> Any:
        return self.call("GetFacetingOptionParameter")

    def SetFacetingOptionParameter(self, param) -> Any:
        return self.call("SetFacetingOptionParameter", param)

    # --- 几何量 ---
    def GetBoundingBox(self) -> Any:
        return self.call("GetBoundingBox")

    def GetCentroid(self) -> Any:
        return self.call("GetCentroid")

    def GetArea(self) -> Any:
        return self.call("GetArea")

    def GetVolume(self) -> Any:
        return self.call("GetVolume")

    def GetThickness(self) -> Any:
        return self.call("GetThickness")

    def SetThickness(self, thickness) -> Any:
        return self.call("SetThickness", thickness)

    def GetSphereCenterRadius(self) -> Any:
        return self.call("GetSphereCenterRadius")

    # --- 关联对象 ---
    def GetFluidRegion(self) -> "ScFlowpreFluidRegion":
        return ScFlowpreFluidRegion(self.call("GetFluidRegion"))

    def GetSurfaceRegion(self) -> ComObject:
        return ComObject(self.call("GetSurfaceRegion"))

    def GetWrappingGroup(self) -> "ScFlowpreWrappingGroup":
        return ScFlowpreWrappingGroup(self.call("GetWrappingGroup"))

    def GetMovingGroup(self) -> ComObject:
        return ComObject(self.call("GetMovingGroup"))

    def GetBelongingGroupPart(self) -> "ScFlowpreSNode":
        return ScFlowpreSNode(self.call("GetBelongingGroupPart"))

    def GetCoordinatesSpecifiedParts(self) -> Any:
        return self.call("GetCoordinatesSpecifiedParts")

    # --- 显示 / 选择 ---
    def GetVisible(self) -> bool:
        return bool(self.call("GetVisible"))

    def SetVisible(self, flag) -> Any:
        return self.call("SetVisible", flag)

    def GetSelect(self) -> bool:
        return bool(self.call("GetSelect"))

    def SetSelect(self, flag) -> Any:
        return self.call("SetSelect", flag)

    def IsExpanded(self) -> bool:
        return bool(self.call("IsExpanded"))

    def SetExpand(self, flag) -> Any:
        return self.call("SetExpand", flag)

    # --- IO / 属性 ---
    def SaveXTFile(self, path: str | Path) -> bool:
        return bool(self.call("SaveXTFile", str(Path(path).resolve())))

    def ImportCSV(self, path: str | Path) -> Any:
        return self.call("ImportCSV", str(Path(path).resolve()))

    def QueryPropValueObj(self, name: str) -> ComObject:
        return ComObject(self.call("QueryPropValueObj", name))

    def GetMaterial(self) -> Any:
        return self.call("GetMaterial")

    def SetMaterial(self, material) -> Any:
        return self.call("SetMaterial", material)


class ScFlowpreFaceRegion(ComObject):
    """FaceRegion 类高频成员（手册 70 方法；Register Region 权威路线核心）。"""

    # --- 注册（P12-D：Register Region 关门验收的官方路径） ---
    def RegisterSelectedMDLFace(self) -> bool:
        return bool(self.call("RegisterSelectedMDLFace"))

    def RegisterVFace(self, faces) -> bool:
        return bool(self.call("RegisterVFace", faces))

    def RegisterSFace(self, faces) -> bool:
        return bool(self.call("RegisterSFace", faces))

    def SetSelectMDLFaces(self, faces, flag) -> Any:
        return self.call("SetSelectMDLFaces", faces, flag)

    # --- 类型 / 编组 ---
    def GetFaceRegionType(self) -> Any:
        return self.call("GetFaceRegionType")

    def SetFaceRegionType(self, type_) -> Any:
        return self.call("SetFaceRegionType", type_)

    def GetGroupNumber(self) -> Any:
        return self.call("GetGroupNumber")

    def SetGroupNumber(self, number) -> Any:
        return self.call("SetGroupNumber", number)

    def IsDiscontinuous(self) -> bool:
        return bool(self.call("IsDiscontinuous"))

    # --- 面 / 部件 ---
    def GetMDLFaceCount(self) -> Any:
        return self.call("GetMDLFaceCount")

    def GetMDLFaces(self) -> Any:
        return self.call("GetMDLFaces")

    def GetVFaces(self) -> Any:
        return self.call("GetVFaces")

    def GetSFaces(self) -> Any:
        return self.call("GetSFaces")

    def GetPartSNode(self) -> "ScFlowpreSNode":
        return ScFlowpreSNode(self.call("GetPartSNode"))

    def GetPartVPart(self) -> ComObject:
        return ComObject(self.call("GetPartVPart"))

    def GetPartClosedVolume(self) -> ComObject:
        return ComObject(self.call("GetPartClosedVolume"))

    # --- 几何 / 显示 ---
    def GetBoundingBox(self) -> Any:
        return self.call("GetBoundingBox")

    def GetCentroid(self) -> Any:
        return self.call("GetCentroid")

    def GetColor(self) -> Any:
        return self.call("GetColor")

    def SetColor(self, color) -> Any:
        return self.call("SetColor", color)

    def RemoveColor(self) -> Any:
        return self.call("RemoveColor")

    def IsColorSet(self) -> bool:
        return bool(self.call("IsColorSet"))

    def GetContactAngle(self) -> Any:
        return self.call("GetContactAngle")

    def SetContactAngle(self, angle) -> Any:
        return self.call("SetContactAngle", angle)

    # --- Overset ---
    def GetOversetMeshingGroup(self) -> ComObject:
        return ComObject(self.call("GetOversetMeshingGroup"))

    def SetOversetMeshingGroup(self, group) -> Any:
        return self.call("SetOversetMeshingGroup", group)

    def QueryPropValueObj(self, name: str) -> ComObject:
        return ComObject(self.call("QueryPropValueObj", name))


class ScFlowpreFluidRegion(ComObject):
    """FluidRegion 类高频成员（手册 66 方法）。"""

    # --- 注册 ---
    def RegisterSPart(self, part) -> bool:
        return bool(self.call("RegisterSPart", part))

    def RegisterSPartWithVPart(self, spart, vpart) -> bool:
        return bool(self.call("RegisterSPartWithVPart", spart, vpart))

    def RegisterVPart(self, part) -> bool:
        return bool(self.call("RegisterVPart", part))

    def RegisterClosedVolume(self, volume) -> bool:
        return bool(self.call("RegisterClosedVolume", volume))

    def RegisterCoordinatesSpecifiedPart(self, part) -> bool:
        return bool(self.call("RegisterCoordinatesSpecifiedPart", part))

    def RegisterFaceRegionDerivedSheet(self, sheet) -> bool:
        return bool(self.call("RegisterFaceRegionDerivedSheet", sheet))

    def RemoveSPart(self, part) -> bool:
        return bool(self.call("RemoveSPart", part))

    def RemoveVParts(self, parts) -> bool:
        return bool(self.call("RemoveVParts", parts))

    def RemoveClosedVolume(self, volume) -> bool:
        return bool(self.call("RemoveClosedVolume", volume))

    # --- 查询 ---
    def GetClosedVolumes(self) -> Any:
        return self.call("GetClosedVolumes")

    def GetSParts(self) -> Any:
        return self.call("GetSParts")

    def GetVParts(self) -> Any:
        return self.call("GetVParts")

    def GetFaceRegionDerivedSheets(self) -> Any:
        return self.call("GetFaceRegionDerivedSheets")

    def GetCoordinatesSpecifiedParts(self) -> Any:
        return self.call("GetCoordinatesSpecifiedParts")

    def GetBoundingBox(self) -> Any:
        return self.call("GetBoundingBox")

    # --- 材料 / 参数 ---
    def GetMaterial(self) -> Any:
        return self.call("GetMaterial")

    def SetMaterial(self, material) -> Any:
        return self.call("SetMaterial", material)

    def GetParam(self) -> Any:
        return self.call("GetParam")

    def SetParam(self, param) -> Any:
        return self.call("SetParam", param)

    def GetValue(self, name: str) -> Any:
        return self.call("GetValue", name)

    def ImportCSV(self, path: str | Path) -> Any:
        return self.call("ImportCSV", str(Path(path).resolve()))

    def IsObstacle(self) -> bool:
        return bool(self.call("IsObstacle"))

    def SetObstacle(self, flag) -> Any:
        return self.call("SetObstacle", flag)

    def IsExpanded(self) -> bool:
        return bool(self.call("IsExpanded"))

    def SetExpand(self, flag) -> Any:
        return self.call("SetExpand", flag)


class ScFlowpreNumericalRegion(ComObject):
    """NumericalRegion 类（手册 20 方法全量）。"""

    def GetDefinitionType(self) -> Any:
        return self.call("GetDefinitionType")

    def GetDefinitionTypeDisplayStr(self) -> Any:
        return self.call("GetDefinitionTypeDisplayStr")

    def GetCombinationOption(self) -> Any:
        return self.call("GetCombinationOption")

    def SetCombinationOption(self, option) -> Any:
        return self.call("SetCombinationOption", option)

    def GetCombinationUnits(self) -> Any:
        return self.call("GetCombinationUnits")

    def SetCombinationUnits(self, units) -> Any:
        return self.call("SetCombinationUnits", units)

    def GetCuboid(self) -> Any:
        return self.call("GetCuboid")

    def SetCuboid(self, cuboid) -> Any:
        return self.call("SetCuboid", cuboid)

    def GetCylinder(self) -> Any:
        return self.call("GetCylinder")

    def SetCylinder(self, cylinder) -> Any:
        return self.call("SetCylinder", cylinder)

    def GetSphere(self) -> Any:
        return self.call("GetSphere")

    def SetSphere(self, sphere) -> Any:
        return self.call("SetSphere", sphere)

    def GetPlaneType(self) -> Any:
        return self.call("GetPlaneType")

    def SetPlaneType(self, type_) -> Any:
        return self.call("SetPlaneType", type_)

    def GetPlaneParam(self) -> Any:
        return self.call("GetPlaneParam")

    def SetPlaneParam(self, param) -> Any:
        return self.call("SetPlaneParam", param)

    def GetSide(self) -> Any:
        return self.call("GetSide")

    def SetSide(self, side) -> Any:
        return self.call("SetSide", side)

    def GetMovingOption(self) -> Any:
        return self.call("GetMovingOption")

    def SetMovingOption(self, option) -> Any:
        return self.call("SetMovingOption", option)


class ScFlowpreSubmeshSurfaceRegion(ComObject):
    """SubmeshSurfaceRegion 类（手册 19 方法全量）。"""

    def RegisterSelectedMDLFace(self) -> bool:
        return bool(self.call("RegisterSelectedMDLFace"))

    def RegisterVFace(self, faces) -> bool:
        return bool(self.call("RegisterVFace", faces))

    def RegisterSFace(self, faces) -> bool:
        return bool(self.call("RegisterSFace", faces))

    def SetSelectMDLFaces(self, faces, flag) -> Any:
        return self.call("SetSelectMDLFaces", faces, flag)

    def SetSelectMeshFaces(self, faces, flag) -> Any:
        return self.call("SetSelectMeshFaces", faces, flag)

    def SetSelectSFaces(self, faces, flag) -> Any:
        return self.call("SetSelectSFaces", faces, flag)

    def SetSelectVFaces(self, faces, flag) -> Any:
        return self.call("SetSelectVFaces", faces, flag)

    def GetMDLFaces(self) -> Any:
        return self.call("GetMDLFaces")

    def GetSFaces(self) -> Any:
        return self.call("GetSFaces")

    def GetVFaces(self) -> Any:
        return self.call("GetVFaces")

    def GetSubmeshMeshingGroup(self) -> ComObject:
        return ComObject(self.call("GetSubmeshMeshingGroup"))

    def IsLinkedWithMeshingGroup(self) -> bool:
        return bool(self.call("IsLinkedWithMeshingGroup"))

    def GetBoundingBox(self) -> Any:
        return self.call("GetBoundingBox")

    def GetFacetingParameter(self) -> Any:
        return self.call("GetFacetingParameter")

    def SetFacetingParameter(self, param) -> Any:
        return self.call("SetFacetingParameter", param)

    def GetFacetingParameterType(self) -> Any:
        return self.call("GetFacetingParameterType")

    def SetFacetingParameterType(self, type_) -> Any:
        return self.call("SetFacetingParameterType", type_)

    def ClearFacetingParameter(self) -> Any:
        return self.call("ClearFacetingParameter")

    def IsFacetingParameterSet(self) -> bool:
        return bool(self.call("IsFacetingParameterSet"))


class ScFlowpreAdaptiveParam(ComObject):
    """AdaptiveParam 类（手册 4 方法全量）。"""

    def Initialize(self) -> Any:
        return self.call("Initialize")

    def GetParam(self) -> Any:
        return self.call("GetParam")

    def SetParam(self, param) -> Any:
        return self.call("SetParam", param)

    def GetValue(self) -> Any:
        return self.call("GetValue")


class ScFlowpreMeshingGroupSetting(ComObject):
    """MeshingGroupSetting 类高频成员（手册 104 方法）。

    网格生成参数（mesher / faceter / 容差）的官方参数面。
    """

    # --- mesher 选择 ---
    def GetMesher(self) -> Any:
        return self.call("GetMesher")

    def ChangeMesher(self, mesher) -> Any:
        return self.call("ChangeMesher", mesher)

    def GetSurfMesher(self) -> Any:
        return self.call("GetSurfMesher")

    def ChangeSurfMesher(self, mesher) -> Any:
        return self.call("ChangeSurfMesher", mesher)

    def GetMDLMethod(self) -> Any:
        return self.call("GetMDLMethod")

    def SetMDLMethod(self, method) -> Any:
        return self.call("SetMDLMethod", method)

    # --- faceter 简易设置 ---
    def GetFacetAccuracySpecificationType(self) -> Any:
        return self.call("GetFacetAccuracySpecificationType")

    def SetFacetAccuracySpecificationType(self, type_) -> Any:
        return self.call("SetFacetAccuracySpecificationType", type_)

    def GetFacetUseSimpleSetting(self) -> Any:
        return self.call("GetFacetUseSimpleSetting")

    def SetFacetUseSimpleSetting(self, flag) -> Any:
        return self.call("SetFacetUseSimpleSetting", flag)

    def GetFacetSimpleChordTol(self) -> Any:
        return self.call("GetFacetSimpleChordTol")

    def SetFacetSimpleChordTol(self, tol) -> Any:
        return self.call("SetFacetSimpleChordTol", tol)

    def GetFacetSimpleMaxWidth(self) -> Any:
        return self.call("GetFacetSimpleMaxWidth")

    def SetFacetSimpleMaxWidth(self, width) -> Any:
        return self.call("SetFacetSimpleMaxWidth", width)

    def GetFacetSimpleMaxAngle(self) -> Any:
        return self.call("GetFacetSimpleMaxAngle")

    def SetFacetSimpleMaxAngle(self, angle) -> Any:
        return self.call("SetFacetSimpleMaxAngle", angle)

    # --- ridge / 容差 ---
    def GetRidgeAngle(self) -> Any:
        return self.call("GetRidgeAngle")

    def SetRidgeAngle(self, angle) -> Any:
        return self.call("SetRidgeAngle", angle)

    def GetContactTolerance(self) -> Any:
        return self.call("GetContactTolerance")

    def SetContactTolerance(self, tol) -> Any:
        return self.call("SetContactTolerance", tol)

    def GetSewingTolerance(self) -> Any:
        return self.call("GetSewingTolerance")

    def SetSewingTolerance(self, tol) -> Any:
        return self.call("SetSewingTolerance", tol)

    def GetOverlapTolerance(self) -> Any:
        return self.call("GetOverlapTolerance")

    def SetOverlapTolerance(self, tol) -> Any:
        return self.call("SetOverlapTolerance", tol)

    def GetInvalidTolerance(self) -> Any:
        return self.call("GetInvalidTolerance")

    def SetInvalidTolerance(self, tol) -> Any:
        return self.call("SetInvalidTolerance", tol)

    # --- 单位 / 归属 ---
    def GetInternalUnit(self) -> Any:
        return self.call("GetInternalUnit")

    def GetMeshingGroup(self) -> ScFlowpreMeshingGroup:
        return ScFlowpreMeshingGroup(self.call("GetMeshingGroup"))


# ============================================================================
# typed 类注册表（P12-A：catalog 199 类覆盖对账的单一映射）
# ============================================================================

#: 手册类名 → typed 包装类。新增包装必须在此登记——
#: ``tests/test_scflowpre_api.py`` 以此对 catalog 全类对账。
TYPED_CLASSES: dict[str, type] = {
    "Application": ScFlowpreApplication,
    "Doc": ScFlowpreDoc,
    "Conditions": ScFlowpreConditions,
    "Condition": ScFlowpreCondition,
    "MeshingGroup": ScFlowpreMeshingGroup,
    "Octree": ScFlowpreOctree,
    "OctParam": ScFlowpreOctParam,
    "WrappingGroup": ScFlowpreWrappingGroup,
    "Utility": ScFlowpreUtility,
    "Region": ScFlowpreRegion,
    "SNode": ScFlowpreSNode,
    "FaceRegion": ScFlowpreFaceRegion,
    "FluidRegion": ScFlowpreFluidRegion,
    "NumericalRegion": ScFlowpreNumericalRegion,
    "SubmeshSurfaceRegion": ScFlowpreSubmeshSurfaceRegion,
    "AdaptiveParam": ScFlowpreAdaptiveParam,
    "MeshingGroupSetting": ScFlowpreMeshingGroupSetting,
}

#: 条件标记类前缀：136 个 ``Cond*`` 标记子类无自有方法（catalog
#: ``inherits: Condition``；另有 Condition/Conditions 两个基类已 typed），
#: 全部经 :class:`ScFlowpreCondition` 包装 +
#: :meth:`ScFlowpreConditions.create_cond` 泛型出口覆盖。
COND_CLASS_PREFIX = "Cond"


def catalog_coverage(catalog: dict) -> dict[str, str]:
    """catalog 类名 → 覆盖方式（typed / condition-subclass / generic-call）。

    P12-A 域 7 验收口径：199 类每类可判——typed 包装，或 Cond* 子类
    （Condition 泛型），或 generic（``ComObject.call`` 逃生口，手册
    任一成员可达）。对账测试断言无第四类。
    """
    coverage: dict[str, str] = {}
    for name in catalog["classes"]:
        if name in TYPED_CLASSES:
            coverage[name] = "typed"
        elif name.startswith(COND_CLASS_PREFIX):
            coverage[name] = "condition-subclass"
        else:
            coverage[name] = "generic-call"
    return coverage


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
