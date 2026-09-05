#!/usr/bin/env python3
"""P12-L Sprint I7 生成器/分类器离线单测（无宿主）。"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_SPEC = importlib.util.spec_from_file_location(
    "p12l_scan", str(ROOT / "tools" / "_p12l_i7_scan.py"))
scan = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(scan)

_SPEC2 = importlib.util.spec_from_file_location(
    "p12l_run", str(ROOT / "tools" / "_p12l_i7_run.py"))
run = importlib.util.module_from_spec(_SPEC2)
_SPEC2.loader.exec_module(run)


class TestClassifyMagic(unittest.TestCase):
    def _tmp(self, name: str, data: bytes) -> Path:
        p = Path(tempfile.gettempdir()) / name
        p.write_bytes(data)
        self.addCleanup(p.unlink, missing_ok=True)
        return p

    def test_ole2_catia_stream(self):
        # OLE2 头 + 头部含 CATIA 字样（CATPart 布局简化模型）
        data = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 0x1E
                + b"CATIAV5PART")
        r = scan.classify_magic(self._tmp("t_i7_a.CATPart", data))
        self.assertEqual(r["verdict"], "REAL")
        self.assertEqual(r["kind"], "catia_v5_ole2")

    def test_hdf5_exp_false_positive(self):
        r = scan.classify_magic(self._tmp(
            "t_i7_b.exp", b"\x89HDF\r\n\x1a\n" + b"\x00" * 32))
        self.assertEqual(r["verdict"], "FALSE-POSITIVE")
        self.assertEqual(r["kind"], "hdf5_exp")

    def test_linker_exp_false_positive(self):
        r = scan.classify_magic(self._tmp(
            "t_i7_c.exp", b"EXPORTS\nfoo\n"))
        self.assertEqual(r["verdict"], "FALSE-POSITIVE")
        self.assertEqual(r["kind"], "linker_export")

    def test_datakit_dtk_model_schema(self):
        # dtk.* 前缀 = Datakit schema（G3 命中的误报族，I7 钉死分类）
        r = scan.classify_magic(self._tmp(
            "dtk.model", b"\xc4\xe3\xd2\x40" + b"CATIA V4" * 4))
        self.assertEqual(r["verdict"], "FALSE-POSITIVE")
        self.assertEqual(r["kind"], "datakit_schema")

    def test_real_v5_cfV2_magic_detected(self):
        # 真 CATIA V5 魔数 V5_CFV2（starcat5 样本实测）→ REAL
        r = scan.classify_magic(self._tmp(
            "t_i7_e.CATPart", b"V5_CFV2" + b"\x00" * 32))
        self.assertEqual(r["verdict"], "REAL")
        self.assertEqual(r["kind"], "catia_v5_cfV2")


class TestFlowBuilders(unittest.TestCase):
    def test_catia_open_actions(self):
        acts = run.build_groups(
            "catia_open", Path("D:/x/c1.pph"), Path("D:/x/c1_out.pph"))
        joined = "\n".join(acts)
        self.assertIn("OpenCadFile", joined)
        self.assertIn("Set SN_ = Doc_.OpenCadFile(", joined)  # 括号 retval
        self.assertIn("QuerySNodeByName", joined)
        self.assertNotIn("IIf", joined)

    def test_catia_facet_actions(self):
        acts = run.build_groups(
            "catia_facet", Path("D:/x/c2.pph"), Path("D:/x/c2_out.pph"))
        joined = "\n".join(acts)
        self.assertIn("CreateMeshingGroup", joined)
        self.assertIn("ImportCADAsFacet", joined)
        self.assertIn("f_ret=", joined)

    def test_verify_log(self):
        text = ("start\ns001=0\ns002=0\nsn__alive=True\n"
                "f_ret=True err=0\nbogus line\nend\n")
        v = run.verify_log(text)
        self.assertEqual(v["total"], 3)
        self.assertEqual(v["err0"], 3)
        self.assertEqual(v["bad"], 0)
        self.assertTrue(v["has_end"])
        self.assertEqual(v["alive"].get("sn_"), "True")
        self.assertEqual(v["info"].get("f_ret"), "True")
        self.assertTrue(any("unparsed" in p for p in v["problems"]))

    def test_member_diff_missing(self):
        r = run.member_diff(Path("D:/nonexistent_i7.pph"))
        self.assertFalse(r["exists"])


class TestSampleInventory(unittest.TestCase):
    def test_scan_report_written(self):
        self.assertTrue(
            (ROOT / "_p12l_i7" / "i7_scan.json").is_file(),
            "I7 scan report missing")

    def test_report_records_real_catia(self):
        import json
        r = json.loads((ROOT / "_p12l_i7" / "i7_scan.json")
                       .read_text(encoding="utf-8"))
        real = [h for h in r["catia_rescan"]["hits"]
                if h.get("kind") in ("catia_v5_cfV2", "catia_like")
                and h.get("verdict", "").startswith("REAL")]
        self.assertGreaterEqual(len(real), 15)
        self.assertTrue(any(h["path"].endswith(".CATProduct")
                            for h in real))


if __name__ == "__main__":
    unittest.main()
