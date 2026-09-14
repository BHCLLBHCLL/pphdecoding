#!/usr/bin/env python3
"""R30-5 回归：里程碑工具的体量上限必须对权威文本资产放宽。

事故：`schemas/vb_api_catalog.json` 在 R30 已达 **2.14 MB**，而工具的上限是
1 MB —— 它被**静默跳过**（只在 `--dry-run` 的「跳过」清单里露面）。实测该文件
自 2026-08-20（`0cecf53`, P9）之后就没再进过仓库，目录更新一直躺在工作树里：
仓库里的 API 面比实际提取结果旧了一个版本。

口径：`schemas/*.json`（权威 schema）与 `docs/*.md`（文档）不属于「大运行产物」，
它们即使超过 1 MB 也必须能提交；其他路径维持 1 MB 上限。
"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GM = ROOT / "tools" / "git_milestone.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestSizeLimit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gm = _load("gm_r305", GM)

    def test_schema_and_docs_get_relaxed_limit(self):
        self.assertEqual(self.gm._size_limit("schemas/vb_api_catalog.json"),
                         self.gm.MAX_BYTES_BIG)
        self.assertEqual(self.gm._size_limit("docs/ROUNDS.md"),
                         self.gm.MAX_BYTES_BIG)

    def test_other_paths_keep_one_mb(self):
        self.assertEqual(self.gm._size_limit("_p12u_gate/r6_5_keys.json"),
                         self.gm.MAX_BYTES)
        self.assertEqual(self.gm._size_limit("p12c_registry_report.json"),
                         self.gm.MAX_BYTES)

    def test_relaxed_limit_is_above_one_mb(self):
        self.assertGreater(self.gm.MAX_BYTES_BIG, self.gm.MAX_BYTES)

    def test_catalog_fits_under_its_limit(self):
        """不变量：权威目录的**当前**体量必须在上限内（否则又会被静默跳过）。"""
        p = ROOT / "schemas" / "vb_api_catalog.json"
        if not p.is_file():
            self.skipTest("catalog not present")
        self.assertLessEqual(p.stat().st_size,
                             self.gm._size_limit("schemas/vb_api_catalog.json"))


if __name__ == "__main__":
    unittest.main()
