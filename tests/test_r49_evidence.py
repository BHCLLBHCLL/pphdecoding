#!/usr/bin/env python3
"""R49 证据回归：先全选再取几何（R49-1）/ 验身闸门误放率（R49-2）/ 取法不可照抄上产品面（R49-3）。

* **全选**：`GetSelected<X>` 系列只在**有选中**时给对象 —— 取实例前把 Doc 上的
  `SetSelectAll*` 逐个打上，`ISFace`/`IVFace`/`ISEdge`/`IVEdge`/`ISVertex`
  这类"取法都在、就是返回空"的类才有机会；
* **误放率**：判据（独有成员解析率 ≥ 半数）此前只有"拦住了什么"的记录，没有
  "会不会放错"的数 —— `audit_identity_guard()` 在真对象上做跨类对照；
* **产品面**：`scflowpre_api.unreliable_recipes()` + 面板「Host 边界…」增列。
"""

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

AVAIL = ROOT / "schemas" / "host_member_availability.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
PROBE = ROOT / "tools" / "dispatch_name_probe.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestSelectionPriming(unittest.TestCase):
    """R49-1：全选是"取几何类"的前置步骤。"""

    @classmethod
    def setUpClass(cls):
        cls.probe = _load("probe_r49", PROBE)
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))

    def test_primes_every_setselectall(self):
        calls = []

        class Fake:
            def _FlagAsMethod(self, *_a):
                pass

        def fake_call(self, name, *args):
            calls.append((name, args))
            return True

        from automation.scflowpre_api import ComObject
        orig = ComObject.call
        ComObject.call = fake_call
        try:
            done, errs = self.probe.prime_selection({"Doc": Fake()}, self.cat)
        finally:
            ComObject.call = orig
        self.assertTrue(done)
        self.assertEqual(errs, {})
        self.assertTrue(all(n.startswith("SetSelectAll") for n in done))
        self.assertTrue(all(args and args[0] is True for _, args in calls),
                        "布尔参数必须给 True（选上）")

    def test_priming_recorded_in_evidence(self):
        primed = self.data["coverage"].get("selection_primed") or []
        self.assertTrue(primed)
        self.assertTrue(all(n.startswith("SetSelectAll") for n in primed))
        self.assertIn("SetSelectAllSFace", primed)
        self.assertIn("SetSelectAllSEdge", primed)
        self.assertIn("SetSelectAllVEdge", primed)
        # 打不上的要留原因（不许静默）
        errs = self.data["coverage"].get("selection_prime_errors") or {}
        for name, err in errs.items():
            self.assertNotIn(name, primed, name)
            self.assertTrue(str(err).strip(), name)

    def test_geometry_classes_got_a_terminal(self):
        # 全选之后仍取不到的几何类，必须有终态（不许无声无息）
        acct = json.loads((ROOT / "schemas" / "unswept_account.json")
                          .read_text(encoding="utf-8"))
        no_member = set(self.data["coverage"].get("no_member_classes") or [])
        for cls in ("ISFace", "IVFace", "ISEdge", "IVEdge", "ISVertex"):
            if cls in self.data["classes"] or cls in no_member:
                continue      # 普查到了，或取到了对象但手册页无成员
            self.assertIn(cls, acct["classes"], cls)


class TestGuardAudit(unittest.TestCase):
    """R49-2：误放率要有数。"""

    @classmethod
    def setUpClass(cls):
        cls.probe = _load("probe_r49b", PROBE)
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.audit = cls.data["coverage"].get("guard_audit") or {}

    def test_audit_recorded(self):
        self.assertTrue(self.audit, "本轮必须落盘误放率")
        for key in ("classes_sampled", "self_pass", "cross_trials",
                    "false_accept", "false_accept_rate", "rule"):
            self.assertIn(key, self.audit)

    def test_false_accept_rate_is_low(self):
        rate = self.audit.get("false_accept_rate")
        self.assertIsNotNone(rate)
        self.assertLess(rate, 0.10,
                        "误放率过高说明判据太松：拿别家对象也会被认作此类")

    def test_self_pass_is_total(self):
        # 真对象必须过自己的验身（不过就是误杀）
        self.assertEqual(self.audit["self_pass"],
                         self.audit["classes_sampled"])

    def test_rule_is_the_documented_one(self):
        self.assertIn("半数", self.audit["rule"])

    def test_offline_rule_behaviour(self):
        class Fake:
            def __init__(self, names):
                self.names = set(names)

        def resolve(obj, name):
            return "resolved" if name in obj.names else "unknown_name"

        ok, _ = self.probe.identity_ok(Fake(["a", "b", "c"]), ["a", "b", "c"],
                                       resolve)
        self.assertTrue(ok)
        ok2, _ = self.probe.identity_ok(Fake(["a"]), ["a", "b", "c"], resolve)
        self.assertFalse(ok2)

    def test_audit_zero_sample_returns_empty(self):
        self.assertEqual(self.probe.audit_identity_guard(
            self.cat, {}, {}, 0), {})


class TestRecipeSurface(unittest.TestCase):
    """R49-3：取法不可照抄要能一处查到。"""

    @classmethod
    def setUpClass(cls):
        from automation import scflowpre_api as api
        cls.api = api
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_api_matches_catalog(self):
        got = self.api.unreliable_recipes()
        want = {c: i.get("recipe_unreliable_evidence") or []
                for c, i in self.cat["classes"].items()
                if i.get("recipe_unreliable")}
        self.assertEqual(got, want)
        self.assertTrue(got, "本轮应有被验身否掉的取法")

    def test_panel_shows_them(self):
        import nav_panels
        data = nav_panels.host_boundary_data()
        self.assertEqual(data["recipes"], self.api.unreliable_recipes())
        text = nav_panels.render_host_boundary(data)
        self.assertIn("取法不可照抄", text)
        for cls in data["recipes"]:
            self.assertIn(cls, text)


if __name__ == "__main__":
    unittest.main()
