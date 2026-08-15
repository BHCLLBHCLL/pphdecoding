#!/usr/bin/env python3
"""ifld：官方 scPOST iFLD 样例（Samples_POST/iFLD）回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import ifld  # noqa: E402

BASE = Path("C:/Program Files/Cradle/CradleCFD2025.2/"
            "Programs_x64/Samples_POST/iFLD")


class TestMinimumHexa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (BASE / "minimumHexa.iFLD").exists():
            raise unittest.SkipTest("Samples_POST/iFLD not installed")

    def test_container_header(self):
        f = ifld.IfldFile.load(str(BASE / "minimumHexa.iFLD"))
        self.assertEqual(f.words["toc_size"], 1024)
        self.assertEqual(f.words["n_entries"], 11)
        self.assertEqual(f.words["version"], 0x01321AF1)
        names = [r.name for r in f.records]
        self.assertEqual(names[0], "FILEINFO")
        self.assertEqual(names[-1], "VAR_OS_PRES")

    def test_fileinfo_is_header_copy(self):
        f = ifld.IfldFile.load(str(BASE / "minimumHexa.iFLD"))
        p = f.payload("FILEINFO")
        self.assertEqual(p, bytes(f.data[0:20]))

    def test_var_arrays_zero(self):
        f = ifld.IfldFile.load(str(BASE / "minimumHexa.iFLD"))
        a = f.var_array("VAR_MS_PRES")
        self.assertEqual(a.size, 6)
        self.assertEqual(float(a.sum()), 0.0)

    def test_bad_magic_rejected(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as t:
            t.write(b"\x00" * 64)
            path = t.name
        try:
            with self.assertRaises(ValueError):
                ifld.IfldFile.load(path)
        finally:
            Path(path).unlink()


class TestExample1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (BASE / "scSTREAM_example1_100.iFLD").exists():
            raise unittest.SkipTest("Samples_POST/iFLD not installed")

    def setUp(self):
        self.f = ifld.IfldFile.load(
            str(BASE / "scSTREAM_example1_100.iFLD"))

    def test_toc(self):
        self.assertEqual(self.f.words["n_entries"], 29)
        names = [r.name for r in self.f.records]
        self.assertIn("SURFBLOCK1", names)
        self.assertIn("ELEMBLOCK1", names)
        self.assertIn("VAR_MS_PRES", names)
        self.assertIn("VAR_OV_HVEC", names)
        # 记录偏移/大小互不重叠且不越界
        n = len(self.f.data)
        for r in self.f.records:
            self.assertGreaterEqual(r.offset, 0)
            self.assertLessEqual(r.offset + r.size, n)

    def test_var_shapes(self):
        self.assertEqual(self.f.var_array("VAR_MS_PRES").size, 70)
        self.assertEqual(self.f.var_array("VAR_OS_PRES").size, 21145)
        self.assertEqual(self.f.var_array("VAR_MV_VECT").size, 280)
        self.assertEqual(self.f.var_array("VAR_OV_VECT").size, 63435)
        # OV = OS x 3 分量
        self.assertEqual(self.f.var_array("VAR_OV_VECT").size,
                         3 * self.f.var_array("VAR_OS_PRES").size)

    def test_temp_sane(self):
        s = self.f.var_stats("VAR_OS_TEMP")
        self.assertGreater(s["count"], 0)
        self.assertLess(s["min"], s["max"])
        self.assertLess(s["max"], 200.0)  # 摄氏度量级

    def test_nodata_sentinel(self):
        # SURT 未启用：MS 整段为 0x60AD78EC 哨兵
        s = self.f.var_stats("VAR_MS_SURT")
        self.assertEqual(s["nodata"], s["count"])
        a = self.f.var_array("VAR_MS_SURT")
        self.assertTrue((a.view(np.uint32) == ifld.NODATA_U32).all())

    def test_embedded_toc_prefix(self):
        emb = [r.name for r in self.f.embedded_toc()]
        toc = [r.name for r in self.f.records]
        self.assertEqual(emb[:10], toc[:10])  # 接缝前一致


if __name__ == "__main__":
    unittest.main()
