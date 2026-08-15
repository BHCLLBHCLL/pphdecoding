#!/usr/bin/env python3
"""scFLOWpre VBS 验收（automation/vbs_acceptance）回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import vbs_acceptance as va  # noqa: E402


class TestBuildOpenVbs(unittest.TestCase):
    def test_vbs_is_utf16_and_opens_project(self):
        out = va.build_open_vbs(ROOT / "_a.txt", ROOT / "box.pph")
        raw = out.read_bytes()
        # UTF-16LE + BOM
        self.assertTrue(raw.startswith(b"\xff\xfe"))
        text = raw.decode("utf-16")
        self.assertIn("GetApplication", text)
        self.assertIn("OpenProject", text)
        self.assertIn("box.pph", text)
        out.unlink(missing_ok=True)


class TestRunOpen(unittest.TestCase):
    def test_open_box_pph(self):
        r = va.run_open(ROOT / "box.pph")
        if not r.get("ok") and "scFLOWpre" in str(r.get("error", "")):
            self.skipTest("scFLOWpre host not available")
        self.assertTrue(r.get("ok"), r)


if __name__ == "__main__":
    unittest.main()