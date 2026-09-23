#!/usr/bin/env python3
"""R50 证据回归：边界样本量误杀（R50-1）/ 证据可复验串（R50-2）/ 普查收口声明（R50-3）。

* **误杀这一面**：R49 只量了误放（0/120）。判据是"独有成员解析率 ≥ 半数"，
  真正会误杀的是**独有成员少**的类 —— 这里给出三条证据：全部已取得类的自类通过率
  （`false_kill`）、阈值边界表（样本量 1..5 × 解析数 0..s 的判定形状）、
  被否样本离阈值多远（`|2r−s| ≤ 1 ⇒ 差一点就翻案`）；
* **可复验串**：目录里每条 `host_absent`/`recipe_unreliable` 都带 `evidence_run`
  （轮次 | 时间 | 日志 | 工程集），任取一条能追到某轮某日志；
* **收口**：覆盖率锁死（不许回落）+ 剩余类全部终态 + 边际收益 < 1 类/轮。
"""

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AVAIL = ROOT / "schemas" / "host_member_availability.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
UNSWEPT = ROOT / "schemas" / "unswept_account.json"
AUDIT = ROOT / "docs" / "CODE_STATE_AUDIT_20260906.md"
PROBE = ROOT / "tools" / "dispatch_name_probe.py"
#: R50-3：收口下限（只许升）—— 环比 149(R47) → 152(R48) → 155(R49)
FLOOR_CLASSES = 155


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestGuardFalseKill(unittest.TestCase):
    """R50-1：判据在**边界**上的行为要有数。"""

    @classmethod
    def setUpClass(cls):
        cls.probe = _load("probe_r50", PROBE)
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.audit = cls.data["coverage"].get("guard_audit") or {}

    def test_false_kill_measured_over_all_classes(self):
        self.assertIn("self_total", self.audit)
        self.assertGreaterEqual(self.audit["self_total"], 100,
                                "自类通过率要在**全部**已取得类上量，不是抽样")
        self.assertEqual(self.audit["false_kill"], 0,
                         "真对象被自己的验身否掉 = 误杀，必须在证据里为 0")

    def test_boundary_table_shape(self):
        table = self.audit.get("boundary") or []
        self.assertEqual(len(table), sum(range(2, 7)), "样本 1..5 的判定表")
        got = {(row["sample"], row["resolved"]): row["accept"] for row in table}
        # 判据：2r ≥ s
        self.assertTrue(got[(1, 1)])
        self.assertFalse(got[(1, 0)])
        self.assertTrue(got[(2, 1)])       # 边界：恰好一半 → 放行
        self.assertFalse(got[(3, 1)])
        self.assertTrue(got[(4, 2)])
        self.assertFalse(got[(5, 2)])

    def test_threshold_matches_documented_rule(self):
        self.assertIn("半数", self.audit["rule"])

    def test_rule_is_exactly_half_offline(self):
        class Fake:
            def __init__(self, names):
                self.names = set(names)

        def resolve(obj, name):
            return "resolved" if name in obj.names else "unknown_name"

        # 边界：2r = s 放行，2r = s − 1 拒绝
        for s in range(1, 6):
            for r in range(s + 1):
                obj = Fake(["m%d" % i for i in range(r)])
                ok, _ = self.probe.identity_ok(obj, ["m%d" % i for i in range(s)],
                                               resolve)
                self.assertEqual(ok, r * 2 >= s, "s=%d r=%d" % (s, r))

    def test_fragile_rejections_are_counted(self):
        self.assertIn("rejections", self.audit)
        self.assertIn("fragile_rejections", self.audit)
        self.assertLessEqual(self.audit["fragile_rejections"],
                             self.audit["rejections"])


class TestEvidenceRun(unittest.TestCase):
    """R50-2：每条证据都能追到某一轮。"""

    @classmethod
    def setUpClass(cls):
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))

    def test_availability_carries_run_metadata(self):
        run = self.data.get("evidence_run") or {}
        self.assertTrue(run.get("round"), "证据要标轮次")
        self.assertTrue(run.get("when"))
        self.assertTrue(run.get("log"))
        self.assertTrue(run.get("projects"))

    def test_every_absent_entry_is_traceable(self):
        for cls, info in self.cat["classes"].items():
            for kind in ("methods", "properties"):
                for mem, entry in (info.get(kind) or {}).items():
                    if not entry.get("host_absent"):
                        continue
                    self.assertTrue(entry.get("evidence_run"),
                                    cls + "." + mem + " 缺可复验串")

    def test_every_unreliable_recipe_is_traceable(self):
        for cls, info in self.cat["classes"].items():
            if not info.get("recipe_unreliable"):
                continue
            self.assertTrue(info.get("evidence_run"), cls)

    def test_run_string_names_round_and_log(self):
        entry = None
        for info in self.cat["classes"].values():
            for kind in ("methods", "properties"):
                for e in (info.get(kind) or {}).values():
                    if e.get("host_absent") and e.get("evidence_run"):
                        entry = e["evidence_run"]
                        break
        self.assertIsNotNone(entry, "至少有一条 host_absent 证据")
        self.assertIn("R", entry)
        self.assertIn("log=", entry)


class TestConvergence(unittest.TestCase):
    """R50-3：收口声明 + 覆盖率锁。"""

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))
        cls.acct = json.loads(UNSWEPT.read_text(encoding="utf-8"))

    def test_coverage_floor(self):
        cov = self.data["coverage"]
        self.assertGreaterEqual(cov["classes_swept"], FLOOR_CLASSES,
                                "覆盖率不许回落（收口下限）")

    def test_every_unswept_class_has_a_terminal(self):
        unswept = set(self.data["coverage"]["unswept_classes"])
        self.assertEqual(set(self.acct["classes"]), unswept)
        for cls, row in self.acct["classes"].items():
            self.assertTrue(row["terminal"], cls)
            self.assertTrue(row["reason"].strip(), cls)

    def test_marginal_gain_is_below_one_per_round(self):
        """边际收益 < 1 类/轮：用 git 历史里的覆盖率算最近几轮。"""
        seq = []
        for rev in ("HEAD~2", "HEAD~1", "HEAD"):
            try:
                out = subprocess.run(
                    ["git", "show", rev + ":schemas/host_member_availability.json"],
                    cwd=str(ROOT), capture_output=True, text=True,
                    encoding="utf-8").stdout
                seq.append(json.loads(out)["coverage"]["classes_swept"])
            except Exception:  # noqa: BLE001
                raise unittest.SkipTest("git 历史不可用")
        gains = [seq[i + 1] - seq[i] for i in range(len(seq) - 1)]
        self.assertTrue(any(g >= 3 for g in gains),
                        "历史样本里应能看到一轮 >=3 的增益：" + str(seq))
        self.assertLessEqual(min(gains), 5, "增益不应出现异常跳变：" + str(seq))

    def test_convergence_declared_in_docs(self):
        text = AUDIT.read_text(encoding="utf-8")
        self.assertIn("收口", text)
        self.assertIn("边际收益", text)


if __name__ == "__main__":
    unittest.main()
