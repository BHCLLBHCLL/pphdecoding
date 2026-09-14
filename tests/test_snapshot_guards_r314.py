#!/usr/bin/env python3
"""R31-4 回归：快照 / 收录一致性护栏（R30-4、R30-5 的通用化）。

R30 撞见的两类事故，本文件各钉一条**可复算**护栏：

* **快照脱钩**（R30-4）：`p12h_registry_report.json` 的实样计数来自当时**未提交**的
  `merged.json`（9/60/80），而已提交的数据是 8/59/79 —— 干净检出必红，
  当时只是因为工作树多跑了一次 merge 恰好对上；
* **收录静默丢件**（R30-5）：里程碑工具的体积上限把 2.14 MB 的权威目录
  `git reset` 出暂存区，提交「成功」但目录没进仓库。
"""

import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GM = ROOT / "tools" / "git_milestone.py"
REPORT = ROOT / "p12h_registry_report.json"
COND_TYPES = ROOT / "schemas" / "cond_types.json"
MERGED = ROOT / "schemas" / "merged.json"
EVID = re.compile(r"官方案例库实样 (\d+) 例")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestMilestoneNeverSkipsTracked(unittest.TestCase):
    """R30-5 护栏：被跟踪的文件不得出现在「跳过」清单里。"""

    @classmethod
    def setUpClass(cls):
        cls.gm = _load("gm_r314", GM)
        out = subprocess.run(["git", "ls-files"], cwd=str(ROOT), text=True,
                             encoding="utf-8", errors="replace",
                             capture_output=True, check=True)
        cls.tracked = set(out.stdout.split())

    def test_no_tracked_file_is_skipped(self):
        _take, skipped, _deleted = self.gm.candidates()
        names = {s.split(" (")[0] for s in skipped}
        self.assertEqual(names & self.tracked, set(),
                         "已跟踪文件被静默跳过 → 改了也进不了仓库")

    def test_schema_files_survive_the_size_filter(self):
        for rel in ("schemas/vb_api_catalog.json", "schemas/cond_types.json"):
            p = ROOT / rel
            if p.is_file():
                self.assertLessEqual(p.stat().st_size, self.gm._size_limit(rel))
                self.assertEqual(self.gm.bad_staged([rel]), [])


class TestSnapshotAgreement(unittest.TestCase):
    """R30-4 护栏：冻结快照 / 账本 / 语料三者的计数必须一致。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.ct = json.loads(COND_TYPES.read_text(encoding="utf-8"))
        cls.merged = json.loads(MERGED.read_text(encoding="utf-8"))

    def test_cond_types_dispositions_match_report(self):
        want = dict(self.report["dispositions"])
        want.update(self.report["family_annotations"])
        self.assertEqual(self.ct.get("dispositions"), want)

    def test_evidence_counts_match_merged_json(self):
        types = (self.merged.get("conditions") or {}).get("types") or {}
        checked = 0
        for name, disp in self.report["dispositions"].items():
            m = EVID.search(disp.get("evidence") or "")
            if not m or name not in types:
                continue
            checked += 1
            self.assertEqual(int(m.group(1)), types[name].get("count"),
                             name + ": 快照计数 ≠ merged.json")
        self.assertGreaterEqual(checked, 80, "受检类型过少，护栏形同虚设")


if __name__ == "__main__":
    unittest.main()
