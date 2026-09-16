#!/usr/bin/env python3
"""R42 证据回归：成员可用性入册（R42-1）/ 仓内引用自检（R42-2）/ NYI 终态口径（R42-3）。

* **普查**：用 `GetIDsOfNames` 对已取到实例的类逐个解析手册成员（只解析、不调用）→
  实测 **12 个成员宿主未实现**（`DISP_E_UNKNOWNNAME`），其中
  `CondBoundaryFlowIO.GetMassVolumePressureInflowDirectionType` 的名字里还带一个
  **零宽空格**（手册数据卫生问题：这个名字永远调不通）。
* **入册**：目录条目带 `host_absent`，物化包装**跳过**它们（不再造出注定失败的方法）。
* **自检**：仓内不得引用"无歧义未实现"的成员（同名成员在别的类实现了就不算，避免假阳性）。
* **终态**：9 条 NYI 全部有 `terminal`（3 宿主无接口 / 6 需要 GUI 流程），不留"待办"。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import scflowpre_api as api  # noqa: E402

AVAIL = ROOT / "schemas" / "host_member_availability.json"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
ACCOUNT = ROOT / "schemas" / "dispatch_account.json"
GATE = ROOT / "tools" / "api_contract_check.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestAvailabilitySweep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not AVAIL.is_file():
            raise unittest.SkipTest("availability evidence missing")
        cls.data = json.loads(AVAIL.read_text(encoding="utf-8"))

    def test_sweep_found_unimplemented_members(self):
        classes = self.data["classes"]
        self.assertGreaterEqual(len(classes), 7)
        total = sum(v["total"] for v in classes.values())
        # 注意：证据里 `unknown` 是**名单**（不是计数），便于直接看是哪些成员
        unknown = [m for v in classes.values() for m in v["unknown"]]
        self.assertGreater(total, 800, "普查应覆盖大量成员")
        # R44 扩面后从 12 涨到 16（新增 CondInitial/CondPorousMedia/CondSource 的成员）
        # —— 断言改成单调下界，避免每轮扩面都要改数字
        self.assertGreaterEqual(len(unknown), 12, "本轮实测 ≥12 个成员未实现")
        self.assertIn("GetMassVolumePressureInflowDirectionType\u200b", unknown)

    def test_members_are_fully_classified(self):
        """状态三态：resolved / unknown_name（宿主未实现）/ error:*（探针侧）。

        `error:*` 是**探针侧**问题（对象形态、空对象等），**不得**算作
        "宿主未实现" —— 入册只认 `unknown_name`。
        """
        seen = err = 0
        for cls, members in self.data["availability"].items():
            for mem, state in members.items():
                self.assertTrue(state == "resolved"
                                or state == "unknown_name"
                                or state.startswith("error:"),
                                cls + "." + mem + " -> " + state)
                if state == "unknown_name":
                    seen += 1
                elif state.startswith("error:"):
                    err += 1
        self.assertGreaterEqual(seen, 12)   # R44 扩面后 16
        # 目录里入册的必须正好等于 unknown_name 的条数（error 一条都不许混进去）
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        marked = sum(1 for info in cat["classes"].values()
                     for kind in ("methods", "properties")
                     for e in (info.get(kind) or {}).values()
                     if e.get("host_absent"))
        self.assertEqual(marked, seen)

    def test_zero_width_space_member_is_recorded(self):
        """手册成员名里带零宽空格（数据卫生问题）——必须如实记下来。"""
        names = [m for members in self.data["availability"].values()
                 for m in members]
        zwsp = [n for n in names if "\u200b" in n]
        self.assertTrue(zwsp, "应记录带零宽空格的成员名")
        self.assertTrue(any("MassVolumePressureInflowDirectionType" in n
                            for n in zwsp))


class TestCatalogHostAbsent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def _absent(self):
        return [(c, m) for c, info in self.cat["classes"].items()
                for kind in ("methods", "properties")
                for m, e in (info.get(kind) or {}).items()
                if e.get("host_absent")]

    def test_members_marked_with_evidence(self):
        absent = self._absent()
        self.assertGreaterEqual(len(absent), 12, "R42 起入册，R44 扩面后更多")
        for cls, mem in absent:
            entry = (self.cat["classes"][cls]["methods"].get(mem)
                     or self.cat["classes"][cls].get("properties", {}).get(mem))
            self.assertIn("UNKNOWNNAME", entry.get("host_absent_evidence", ""))

    def test_known_cases(self):
        pairs = {("Doc", "GetAllMapCondNames"),
                 ("MeshingGroupSetting", "GetInternalUnit"),
                 ("SpecialRegion", "ImportCSV")}
        self.assertTrue(pairs.issubset(set(self._absent())))

    def test_materialisation_skips_host_absent(self):
        api.materialize_catalog_wrappers()
        self.assertFalse(hasattr(api.ScFlowpreMeshingGroupSetting,
                                 "GetInternalUnit"),
                         "宿主未实现的成员不得被物化成包装")

    def test_other_classes_keep_their_own_member(self):
        """同名成员可能只在**部分类**未实现（`ImportCSV` → SpecialRegion +
        CondPorousMedia…），别的类（FaceRegion/NumericalRegion）的实现必须保留。

        R45 把这条从"当前事实集合相等"改成**单调下界**：扩面每多普查一个类，
        未实现该成员的类就可能多一个（实测从 2 个涨到 6 个），但已确认的两个
        必须一直在，且**解析得到**的类不许被标。
        """
        absent = {c for c, m in self._absent() if m == "ImportCSV"}
        self.assertTrue({"SpecialRegion", "CondPorousMedia"}.issubset(absent),
                        absent)
        for cls in ("FaceRegion", "NumericalRegion"):
            entry = (self.cat["classes"].get(cls) or {}).get("methods", {}).get(
                "ImportCSV")
            if entry is not None:
                self.assertFalse(entry.get("host_absent"), cls + ".ImportCSV")


class TestRepoReferenceCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gate = _load("gate_r42", GATE)

    def test_no_repo_reference_to_unambiguous_absent(self):
        res = self.gate.check_host_absent()
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["reference_count"], 0)
        self.assertGreaterEqual(res["absent_members"], 8)


class TestNyiTerminal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load("acct_r42", ROOT / "tools" / "dispatch_account.py")

    def test_every_nyi_has_a_terminal_kind(self):
        data = self.mod.account()
        nyi = [r for r in data["rows"] if r["state"] == "nyi"]
        # R45：口径改为**只减不增**（9 = R42 收口基线）。扩面会把 NYI 里那些
        # "取不到对象"的对裁定掉 —— 实测 9 → 6（自动配方取到了对象），
        # 但绝不允许凭空多出无法裁定的条目。
        self.assertLessEqual(len(nyi), 9)
        kinds = {}
        for row in nyi:
            self.assertIn("terminal", row, row["heading"])
            kinds[row["terminal"]] = kinds.get(row["terminal"], 0) + 1
        self.assertLessEqual(kinds.get("host-interface-absent", 0), 3)
        self.assertLessEqual(kinds.get("needs-gui-flow", 0), 6)
        # 总数 = 有终态的（不许有既无终态又算不出的条目）
        self.assertEqual(len(nyi), sum(kinds.values()))

    def test_committed_account_matches(self):
        saved = json.loads(ACCOUNT.read_text(encoding="utf-8"))
        live = self.mod.account()
        self.assertEqual(saved["counts"]["nyi"], live["counts"]["nyi"])


if __name__ == "__main__":
    unittest.main()
