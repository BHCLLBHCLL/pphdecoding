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


# ---------------------------------------------------------------------------
# 2. typed 包装对账（唯一真相源 = catalog）
# ---------------------------------------------------------------------------

WRAPPERS = {
    api.ScFlowpreApplication: "Application",
    api.ScFlowpreDoc: "Doc",
    api.ScFlowpreConditions: "Conditions",
    api.ScFlowpreCondition: "Condition",
    api.ScFlowpreMeshingGroup: "MeshingGroup",
    api.ScFlowpreOctree: "Octree",
    api.ScFlowpreOctParam: "OctParam",
    api.ScFlowpreWrappingGroup: "WrappingGroup",
    api.ScFlowpreUtility: "Utility",
}


# 桥自有泛型方法（非手册成员，ComObject 逃生口之外的便捷封装）
_LOCAL_METHODS = {"create_cond", "query_cond"}


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
                if name not in catalog_names:
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
# 3. 无宿主降级
# ---------------------------------------------------------------------------

class TestSessionWithoutHost:
    def test_not_connected_state(self):
        s = api.ScFlowpreSession()
        assert not s.is_connected
        assert s.worker_state() == (None, None)
        assert not s.save_project("x.pph")
        assert api.last_error == "no document"

    def test_execute_vbs_requires_connection(self, monkeypatch):
        monkeypatch.setattr(api, "host_process_running", lambda: False)
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
        monkeypatch.setitem(sys.modules, "win32com.client",
                            _MissingModule("win32com.client"))
        info = api.host_status()
        assert info["progid"] == api.PROGID
        assert info["registered"] is False
        assert info["process_running"] is False
        assert info["connected"] is False
        assert "error" in info
