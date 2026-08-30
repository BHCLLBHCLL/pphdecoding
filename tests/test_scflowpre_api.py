"""P9 typed COM 桥回归（scflowpre_api + vb_api_catalog）。

三层验证，全部不依赖宿主在位（宿主实机验收见 vbs_acceptance）：

1. **catalog 完整性**：199 类 / 4455 成员、关键类方法数、
   Doc.OpenProject 参数表与 FixDefault Note；
2. **typed 对账**：包装类每个公开方法名必须存在于手册目录对应类
   （防手写漂移——桥与目录唯一真相源）；
3. **无宿主降级**：Session 未连接时的行为、api_available /
   host_status 在无 win32com / 无宿主环境下不崩。
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

from automation import scflowpre_api as api


class _MissingModule:
    """占位缺失模块（monkeypatch.setitem(sys.modules, ...) 用）。"""

    def __init__(self, name):
        self.__name__ = name

    def __getattr__(self, item):
        raise ImportError(f"No module named {self.__name__}")

CATALOG_PATH = Path(__file__).resolve().parent.parent / "schemas" / "vb_api_catalog.json"
CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
CLASSES = CATALOG["classes"]


# ---------------------------------------------------------------------------
# 1. catalog 完整性
# ---------------------------------------------------------------------------

class TestVbApiCatalog:
    def test_totals(self):
        members = sum(len(c["methods"]) + len(c.get("properties", {}))
                      for c in CLASSES.values())
        assert len(CLASSES) == 199
        assert members == 4455

    def test_key_class_counts(self):
        assert len(CLASSES["Doc"]["methods"]) == 424
        assert len(CLASSES["Conditions"]["methods"]) == 606
        assert len(CLASSES["MeshingGroup"]["methods"]) == 173
        assert len(CLASSES["Octree"]["methods"]) == 28
        assert len(CLASSES["OctParam"]["methods"]) == 18
        assert len(CLASSES["WrappingGroup"]["methods"]) == 30
        assert len(CLASSES["Utility"]["methods"]) == 16
        assert len(CLASSES["Condition"]["methods"]) == 8
        # P12-A typed expansion
        assert len(CLASSES["SNode"]["methods"]) == 145
        assert len(CLASSES["FaceRegion"]["methods"]) == 70
        assert len(CLASSES["FluidRegion"]["methods"]) == 66
        assert len(CLASSES["NumericalRegion"]["methods"]) == 20
        assert len(CLASSES["SubmeshSurfaceRegion"]["methods"]) == 19
        assert len(CLASSES["AdaptiveParam"]["methods"]) == 4
        assert len(CLASSES["MeshingGroupSetting"]["methods"]) == 104
        assert len(CLASSES["Region"]["methods"]) == 6

    def test_open_project_full_entry(self):
        m = CLASSES["Doc"]["methods"]["OpenProject"]
        assert m["signature"] == "retval=doc.OpenProject(path)"
        assert m["arguments"][0]["name"] == "path"
        assert "True" in m["return"]["description"]
        # 手册 Note：打开工程后建议 FixDefault（session.open_project 内置）
        assert "FixDefault" in m["note"]

    def test_worker_state_semantics(self):
        ret = CLASSES["Doc"]["methods"]["GetWorkerState"]["return"]
        assert "0" in ret["description"] and "1" in ret["description"]

    def test_condition_subclass_inheritance(self):
        cond_classes = [n for n in CLASSES if n.startswith("Cond")]
        assert len(cond_classes) == 138
        # 纯标记类（无自有方法）标注 inherits Condition
        alecancel = CLASSES["CondALECancel"]
        assert not alecancel["methods"]
        assert alecancel.get("inherits") == "Condition"
        assert "QueryConditionByName" in alecancel.get("instance", "")

    def test_kicker_classes(self):
        assert "GetApplicationLaunchSetting" in CLASSES["Kicker.Application"]["methods"]
        assert "ValidLicenseExists" in CLASSES["Kicker.LicenseStatus"]["methods"]

    def test_progid_source(self):
        assert CATALOG["progid"] == api.PROGID

    def test_solver_entry(self):
        # P12-B basis: ExecuteSolver on the Doc authority surface
        m = CLASSES["Doc"]["methods"]["ExecuteSolver"]
        assert m["arguments"][0]["name"] == "sphPath"
        assert "QuitAndExecuteSolver" in CLASSES["Doc"]["methods"]


# ---------------------------------------------------------------------------
# 2. typed 包装对账（唯一真相源 = catalog）
# ---------------------------------------------------------------------------

# P12-A: invert the api registry (name -> class) to class -> name
WRAPPERS = {cls: name for name, cls in api.TYPED_CLASSES.items()}


# 桥自有泛型方法（非手册成员，ComObject 逃生口之外的便捷封装）
_LOCAL_METHODS = {"create_cond", "query_cond", "check"}

# catalog 键本身即拼写错误（录制原文如此）；包装以真实 COM 方法名为准，
# 对账时把真实名映射回 catalog 的错拼键。
_CATALOG_TYPO_ALIASES = {
    "CreateDiscontinuousMeshingGroupWithoutMovingPart":
        "CreateDiscontinuousMeshingGroupWitouthMovingPart",
}


class TestTypedWrappersAgainstCatalog:
    def _wrapper_methods(self, cls):
        base = {n for n in dir(api.ComObject) if not n.startswith("__")}
        names = set()
        for n, _ in inspect.getmembers(cls, inspect.isfunction):
            if not n.startswith("_") and n not in base:
                names.add(n)
        for n, v in inspect.getmembers(cls, lambda o: isinstance(o, property)):
            if not n.startswith("_") and n not in base:
                names.add(n)
        return names

    def test_all_methods_exist_in_catalog(self):
        problems = []
        for cls, class_name in WRAPPERS.items():
            catalog_names = set(CLASSES[class_name]["methods"]) | {
                # 属性键名带类型后缀，如 "Visible(BOOL)"
                p.split("(", 1)[0]
                for p in CLASSES[class_name].get("properties", {})}
            for name in self._wrapper_methods(cls):
                if name in _LOCAL_METHODS:
                    continue
                check = _CATALOG_TYPO_ALIASES.get(name, name)
                if check not in catalog_names:
                    problems.append(f"{class_name}.{name}")
        assert not problems, f"typed drift vs catalog: {problems}"

    def test_wrappers_nonempty(self):
        for cls, name in WRAPPERS.items():
            assert self._wrapper_methods(cls), f"{name} wrapper empty"

    def test_generic_escape_hatches(self):
        # ComObject.call 是泛型逃生口：手册任一成员可达
        fake = _FakeDispatch({"SaveCmbFile": True,
                              "GetPPHVersionString": "2025.2"})
        doc = api.ScFlowpreDoc(fake)
        assert doc.call("SaveCmbFile", "x.cmb", 0) is True
        # 未 typed 的成员同样直调
        assert doc.call("GetPPHVersionString") == "2025.2"

    def test_registry_names_exist_in_catalog(self):
        missing = [n for n in api.TYPED_CLASSES if n not in CLASSES]
        assert not missing, f"registry names not in catalog: {missing}"

    def test_doc_region_factory_typed(self):
        # P12-A: Doc.CreateFaceRegion returns typed wrapper (P12-D route)
        fake = _FakeDispatch({"CreateFaceRegion": _FakeDispatch()})
        doc = api.ScFlowpreDoc(fake)
        region = doc.CreateFaceRegion("wall")
        assert isinstance(region, api.ScFlowpreFaceRegion)
        assert fake.calls == [("CreateFaceRegion", "wall")]

    def test_snode_faceting_roundtrip(self):
        fake = _FakeDispatch({"GetFacetingParameter": (1.0, 2.0),
                              "SetFacetingParameter": True})
        node = api.ScFlowpreSNode(fake)
        assert node.GetFacetingParameter() == (1.0, 2.0)
        assert node.SetFacetingParameter((3.0,)) is True


class _FakeDispatch:
    """win32com dispatch 替身：记录 _FlagAsMethod，按名派发。

    仅 results 中登记的成员可调用；其余属性读取抛 AttributeError
    （对齐真实 dispatch 的行为，让 ComObject.prop 走 default 分支）。
    """

    def __init__(self, results: dict | None = None):
        self.flagged: list[str] = []
        self.results = results or {}
        self.calls: list[tuple] = []

    def _FlagAsMethod(self, *names):
        self.flagged.extend(names)

    def __getattr__(self, name):
        if name.startswith("_") or name not in self.results:
            raise AttributeError(name)

        def _method(*args):
            self.calls.append((name,) + args)
            return self.results[name]

        return _method


# ---------------------------------------------------------------------------
# 3. catalog coverage reconciliation (P12-A domain 7 acceptance)
# ---------------------------------------------------------------------------

class TestCatalogCoverage:
    def test_coverage_complete_no_fourth_bucket(self):
        """199 classes each land in one of three buckets."""
        coverage = api.catalog_coverage(CATALOG)
        assert set(coverage) == set(CLASSES)
        assert set(coverage.values()) == {
            "typed", "condition-subclass", "generic-call"}

    def test_typed_bucket(self):
        coverage = api.catalog_coverage(CATALOG)
        typed = {n for n, c in coverage.items() if c == "typed"}
        assert typed == set(api.TYPED_CLASSES)
        for name in ("SNode", "FaceRegion", "FluidRegion", "NumericalRegion",
                     "SubmeshSurfaceRegion", "AdaptiveParam",
                     "MeshingGroupSetting"):
            assert name in typed, f"{name} not typed"

    def test_condition_subclass_bucket(self):
        coverage = api.catalog_coverage(CATALOG)
        conds = {n for n, c in coverage.items()
                 if c == "condition-subclass"}
        expected = {n for n in CLASSES if n.startswith("Cond")} - {
            "Condition", "Conditions"}
        assert conds == expected
        # 136 marker subclasses (+ Condition/Conditions typed as bases)
        assert len(conds) == 136
        assert api.TYPED_CLASSES["Condition"] is api.ScFlowpreCondition

    def test_generic_bucket_is_call_reachable(self):
        """generic bucket: ComObject.call reaches any manual member."""
        coverage = api.catalog_coverage(CATALOG)
        generic = {n for n, c in coverage.items() if c == "generic-call"}
        for class_name, member in (("Env", "GetMeshingGroupSetting"),
                                   ("ProjectSetting", "GetCADImportType"),
                                   ("MDLWizard", "CreateMDL"),
                                   ("ClosedVolume", "GetAttribute")):
            assert class_name in generic
            assert member in CLASSES[class_name]["methods"]
        fake = _FakeDispatch({member: "ok"})
        obj = api.ComObject(fake)
        assert obj.call(member) == "ok"

    def test_coverage_counts(self):
        coverage = api.catalog_coverage(CATALOG)
        counts = {}
        for c in coverage.values():
            counts[c] = counts.get(c, 0) + 1
        assert counts["typed"] == len(api.TYPED_CLASSES)
        assert counts["condition-subclass"] == 136
        assert counts["generic-call"] == (
            199 - len(api.TYPED_CLASSES) - 136)


# ---------------------------------------------------------------------------
# 4. 无宿主降级
# ---------------------------------------------------------------------------

class TestSessionWithoutHost:
    def test_not_connected_state(self):
        s = api.ScFlowpreSession()
        assert not s.is_connected
        assert s.worker_state() == (None, None)
        assert not s.save_project("x.pph")
        assert api.last_error == "no document"

    def test_execute_vbs_requires_connection(self, monkeypatch):
        # 仅替换 "win32com.client" 条目不够：本会话早前真实导入过
        # win32com.client 时（如宿主在位、vbs_acceptance 先跑），
        # connect() 里 `import win32com.client` 绑定的顶层名 win32com
        # 仍指向真实包，`win32com.client.Dispatch` 照样可达——宿主在位
        # 会真连、不在位甚至会拉起 GUI。顶层条目一并替换才彻底隔离。
        monkeypatch.setattr(api, "host_process_running", lambda: False)
        monkeypatch.setitem(sys.modules, "win32com",
                            _MissingModule("win32com"))
        monkeypatch.setitem(sys.modules, "win32com.client",
                            _MissingModule("win32com.client"))
        s = api.ScFlowpreSession()
        # connect 在无 win32com / 无注册时失败但不崩
        ok = s.execute_vbs("MsgBox 1")
        assert ok is False

    def test_comobject_flag_as_method(self):
        fake = _FakeDispatch({"SetModeOctree": None})
        obj = api.ComObject(fake)
        obj.call("SetModeOctree")
        assert "SetModeOctree" in fake.flagged
        assert fake.calls == [("SetModeOctree",)]

    def test_prop_passthrough(self):
        fake = _FakeDispatch()
        fake.Visible = True  # type: ignore[attr-defined]
        obj = api.ComObject(fake)
        assert obj.prop("Visible") is True
        assert obj.prop("Missing", "dflt") == "dflt"

    def test_host_status_shape(self, monkeypatch):
        # 单元回归绝不真连 COM（Dispatch 可能拉起宿主 GUI——那是
        # vbs_acceptance 实机验收的职责）：模拟无宿主机。
        monkeypatch.setattr(api, "api_available", lambda: False)
        monkeypatch.setattr(api, "host_process_running", lambda: False)
        # 同 test_execute_vbs_requires_connection：顶层 win32com 条目
        # 一并替换，防止单测真连 COM / 拉起宿主。
        monkeypatch.setitem(sys.modules, "win32com",
                            _MissingModule("win32com"))
        monkeypatch.setitem(sys.modules, "win32com.client",
                            _MissingModule("win32com.client"))
        info = api.host_status()
        assert info["progid"] == api.PROGID
        assert info["registered"] is False
        assert info["process_running"] is False
        assert info["connected"] is False
        assert "error" in info
