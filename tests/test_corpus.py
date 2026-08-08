#!/usr/bin/env python3
"""黄金语料清单构建工具测试。"""

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.build_corpus import build_corpus, member_record  # noqa: E402
from pph_parser import PphArchive  # noqa: E402


class TestBuildCorpus(unittest.TestCase):
    def _make_pph(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("main.xml", "<scFLOWpre><version>2025</version></scFLOWpre>")
            z.writestr("main.xenv", '<?xml version="1.0"?><Data type="env"/>')
            z.writestr("meshinggroup1.gph", b"\x00\x01\x02")

    def test_build_corpus(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "case.pph"
            self._make_pph(p)
            corpus = build_corpus(root)
            self.assertEqual(corpus["sample_count"], 1)
            sample = corpus["samples"][0]
            self.assertEqual(sample["member_count"], 3)
            names = [m["name"] for m in sample["members"]]
            self.assertEqual(names, ["main.xml", "main.xenv",
                                     "meshinggroup1.gph"])
            gph = sample["members"][2]
            self.assertEqual(gph["role"], "volume_mesh_gph")
            self.assertEqual(gph["sha256"],
                             hashlib.sha256(b"\x00\x01\x02").hexdigest())

    def test_member_record(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "case.pph"
            self._make_pph(p)
            arch = PphArchive.open(str(p))
            rec = member_record(arch, "meshinggroup1.gph")
            self.assertEqual(rec["size"], 3)
            self.assertGreaterEqual(rec["compress_size"], 3)

    def test_corpus_json_serializable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_pph(root / "case.pph")
            corpus = build_corpus(root)
            json.dumps(corpus)


if __name__ == "__main__":
    unittest.main()
