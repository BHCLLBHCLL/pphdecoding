#!/usr/bin/env python3
"""R30-4 回归：条件收割 merge 必须幂等（累加语义会凭空涨数）。

R30 实测：连跑三次 `python tools/_p12c_cond_harvest.py merge`，
`schemas/merged.json` 的 `CondSource` 计数 **79 → 80 → 81 → 82**。
根因：`extend_merged_schema` 是**累加**语义（`target["count"] += ...`），
而旧实现的载荷是「所有不在基线 pph 里的类型」——于是每次运行都把已入库的
类型再喂一遍（哨兵条件 `alias_evidence` 永不为空：`CondFan/CondFix/Spray`）。

后果不只是噪声：`p12h_registry_report.json`（冻结快照）与 `merged.json`
就此脱钩 —— HEAD 上两者本就差 1（8/59/79 vs 9/60/80），干净检出时
`test_p12h_reconcile` 的 round-trip 断言必红，而当时的工作树因为
「多跑了一次 merge」恰好对上，掩盖了这条红灯。
"""

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestMergeIdempotent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rc = _load("harvest_r304", ROOT / "tools" / "_p12c_cond_harvest.py")

    def _merge_twice(self, td):
        tmp = Path(td) / "merged.json"
        shutil.copyfile(self.rc.MERGED, tmp)
        self.rc.REPORT = Path(td) / "report.json"
        first = self.rc.merge(merged_path=tmp)
        blob = tmp.read_bytes()
        second = self.rc.merge(merged_path=tmp)
        return tmp, blob, first, second

    def test_double_merge_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as td:
            _tmp, blob, _first, second = self._merge_twice(td)
            self.assertEqual(second["to_add"], [])
            self.assertEqual(
                (Path(td) / "merged.json").read_bytes(), blob,
                "第二次 merge 不得改动 merged.json（累加语义只允许写新类型）")

    def test_harvest_types_already_landed(self):
        """当前收割产物里的类型应已全部入库；否则数据待刷新（to_add 非空）。"""
        with tempfile.TemporaryDirectory() as td:
            _tmp, _blob, first, _second = self._merge_twice(td)
            self.assertEqual(first["to_add"], [])

    def test_merge_does_not_touch_repo_files(self):
        before = self.rc.MERGED.read_bytes()
        with tempfile.TemporaryDirectory() as td:
            self._merge_twice(td)
        self.assertEqual(self.rc.MERGED.read_bytes(), before,
                         "merge(merged_path=...) 不得写仓库里的 merged.json")


if __name__ == "__main__":
    unittest.main()
