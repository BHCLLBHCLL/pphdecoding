#!/usr/bin/env python3
"""R40 证据回归：MDL 流程（R40-1）/ 契约门进回归入口（R40-2）/ 守卫盘点（R40-3）。

* **R40-1**：闭空间"造不出来"的原因必须**确切到机制** —— `mg.GetMDL()` 底层返回 None
  （拿到的是包着空对象的 ComObject；只看报错文本 'NoneType' object has no attribute …
  会误以为是成员名写错）。
* **R40-2**：`run_all_tests.py` 跑测试前先跑契约门，失败计入结论。
* **R40-3**：四条写路径的守卫覆盖逐条可查；直写 xenv 的工具必须逐个声明。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GUARD = ROOT / "tools" / "guard_coverage.py"
RUNNER = ROOT / "run_all_tests.py"
EVIDENCE = ROOT / "_p12u_gate" / "r40" / "name_verdicts.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestMdlFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EVIDENCE.is_file():
            raise unittest.SkipTest("r40 evidence missing")
        cls.data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_closed_volume_reason_is_mechanistic(self):
        reason = (self.data.get("chain_errors") or {}).get("ClosedVolume", "")
        self.assertTrue(reason, "必须留下原因")
        self.assertIn("GetMDL", reason)
        self.assertTrue("None" in reason or "空对象" in reason, reason)

    def test_mdl_mode_recorded(self):
        self.assertTrue(self.data.get("with_mdl"), "证据应记下本轮走了 MDL 流程")

    def test_no_false_neither_from_probe(self):
        for v in self.data["verdicts"]:
            if v["verdict"] == "neither":
                self.assertNotIn("AttributeError", str(v["heading_state"]))


class TestRunnerGate(unittest.TestCase):
    def test_runner_runs_contract_gate_first(self):
        src = RUNNER.read_text(encoding="utf-8")
        self.assertIn("api_contract_check.py", src)
        self.assertIn("contract_gate()", src)

    def test_gate_failure_affects_exit_code(self):
        src = RUNNER.read_text(encoding="utf-8")
        self.assertIn("gate_rc != 0", src)


class TestGuardCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load("guard_r40", GUARD)

    def test_all_three_paths_guarded(self):
        data = self.g.report()
        for path in data["paths"]:
            self.assertTrue(path["ok"], path["entry"])

    def test_direct_writers_declared(self):
        data = self.g.report()
        self.assertEqual(data["undeclared_direct"], [])
        self.assertIn("xenv_host_write_check.py", data["direct_writers"])

    def test_ast_detection_ignores_docstrings(self):
        """文本匹配会把文档里提到的 set_xenv_value( 也算上（第一版自证）。"""
        data = self.g.report()
        self.assertNotIn("guard_coverage.py", data["direct_writers"])


if __name__ == "__main__":
    unittest.main()
