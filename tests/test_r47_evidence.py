#!/usr/bin/env python3
"""R47 证据回归：带语料/词表再扩面（R47-1）/ Kicker 会话实测（R47-2）/ 未实现成员前置校验（R47-3）。

* **扩面**：取实例的两条新机制 —— ① 手册**词表**填实参（`CreateMultiYAxisTable(name,
  type)` 的 type 只认词表里的字符串，喂 0 必被拒）；② **真名字池**
  （已持有对象的 `GetName()` + 宿主 `GetAll*Names` + 配方里的 ``@名字``）
  喂给 `Query<X>ByName` 类取法；
* **Kicker**：宿主就是 Kicker 启动的 —— 附着 `Kicker_Bx64.Application.2025`
  取 `ApplicationLaunchSetting`/`LicenseStatus`，验身后入普查；
* **前置校验**：`automation/vbs_bridge.host_absent_methods()` 在**生成期**拦下
  "宿主未实现（无歧义）"的成员，不再等 COM 报错。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AVAIL = ROOT / "schemas" / "host_member_availability.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
PROBE = ROOT / "tools" / "dispatch_name_probe.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestSignatureArgs(unittest.TestCase):
    """R47-1a：实参要按手册给（词表 > 猜）。"""

    @classmethod
    def setUpClass(cls):
        cls.probe = _load("probe_r47", PROBE)
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def _entry(self, cls, member):
        return self.cat["classes"][cls]["methods"][member]

    def test_uses_manual_value_vocabulary(self):
        e = self._entry("Doc", "CreateMultiYAxisTable")
        args = self.probe.signature_args(e, "R47X")
        self.assertEqual(args[0], "R47X")            # name
        self.assertIn(args[1], {"freq_absorp_coeff_table"})

    def test_progid_still_substituted(self):
        e = self._entry("Kicker.Application", "GetApplicationLaunchSetting")
        self.assertEqual(self.probe.signature_args(e, "x"),
                         (self.probe.PROGID,))

    def test_unknown_argument_refuses(self):
        # 认不出的参数一律返回 None（回到阶梯，不猜取值）
        self.assertIsNone(self.probe.signature_args(
            {"arguments": [{"name": "[in](BSTR)somethingWeird"}]}, "x"))


class TestNamePool(unittest.TestCase):
    """R47-1b：Query<X>ByName 要用**真名字**。"""

    @classmethod
    def setUpClass(cls):
        cls.probe = _load("probe_r47b", PROBE)
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_pool_collects_getname_and_getters(self):
        calls = []

        class Fake:
            def __init__(self, name):
                self.name = name

        def call(obj, member):
            calls.append(member)
            if member == "GetName":
                return obj.name
            if member == "GetAllConditionNames":
                return ["c1", "c2"]
            raise RuntimeError("no member")

        pool = self.probe.harvest_names(
            self.cat, {"Doc": Fake("d"), "CondFan": Fake("fan1")}, call)
        self.assertIn("fan1", pool)
        self.assertIn("c1", pool)
        self.assertIn("c2", pool)
        self.assertNotIn("d", pool, "宿主对象自己的名字不进池")
        self.assertLessEqual(len(pool), 40)

    def test_pool_takes_at_names_from_recipes(self):
        pool = self.probe.harvest_names(self.cat, {}, lambda o, m: None)
        self.assertIn("@ALECancel", pool)


class TestKickerEvidence(unittest.TestCase):
    """R47-2：Kicker 三个类要么取到，要么留下失败证据。"""

    @classmethod
    def setUpClass(cls):
        if not AVAIL.is_file():
            raise unittest.SkipTest("availability evidence missing")
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.cov = cls.data["coverage"]

    def test_kicker_classes_have_a_terminal(self):
        swept = set(self.data["classes"])
        via = self.cov.get("obtained_via") or {}
        acct = json.loads((ROOT / "schemas" / "unswept_account.json")
                          .read_text(encoding="utf-8"))
        for cls in ("Kicker.Application", "Kicker.ApplicationLaunchSetting",
                    "Kicker.LicenseStatus"):
            if cls in swept:
                self.assertTrue(str(via.get(cls, "")).startswith("kicker:"),
                                cls + " 的取得路径必须写明是 Kicker 会话")
            else:
                self.assertIn(cls, acct["classes"],
                              cls + " 既没普查也没归因")
                self.assertIn(acct["classes"][cls]["terminal"],
                              ("foreign-app", "needs-corpus", "call-rejected"))
                # Kicker 会话实测过的，理由里要有宿主原话（不许笼统写"取不到"）
                self.assertTrue(acct["classes"][cls]["attempts"], cls)


class TestBridgePrecheck(unittest.TestCase):
    """R47-3：宿主未实现的成员要在**生成期**被点名。"""

    @classmethod
    def setUpClass(cls):
        from automation import vbs_bridge as bridge
        cls.bridge = bridge

    def test_absent_set_is_unambiguous(self):
        absent = self.bridge.host_absent_methods()
        self.assertIn("GetAllMapCondNames", absent)
        # 有歧义的同名成员（部分类实现了）不许进集合
        self.assertNotIn("ImportCSV", absent)

    def test_validate_actions_flags_absent(self):
        warns = self.bridge.validate_actions(["doc.GetAllMapCondNames 1"])
        self.assertTrue(any("宿主未实现" in w for w in warns), warns)
        # 正常成员不报
        ok = self.bridge.validate_actions(["doc.GetProjectSetting"])
        self.assertEqual([w for w in ok if "宿主未实现" in w], [])

    def test_build_vbs_strict_raises(self):
        from automation.scflowpre_api import ApiValueError
        with self.assertRaises(ApiValueError):
            self.bridge.build_vbs(["doc.GetAllMapCondNames 1"],
                                  strict_values=True)


if __name__ == "__main__":
    unittest.main()
