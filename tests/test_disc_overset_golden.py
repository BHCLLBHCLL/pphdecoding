#!/usr/bin/env python3
"""Disc/Overset 黄金指纹回归（冲刺 E · 域 11）：判别键 + 同类判定。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import disc_overset  # noqa: E402

DISC = ROOT / "tests" / "box_disc.pph"
OVERSET = ROOT / "tests" / "box_overset.pph"


@unittest.skipUnless(DISC.is_file() and OVERSET.is_file(),
                     "disc/overset goldens missing")
class TestGoldenFingerprints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.disc = disc_overset.golden_fingerprint(DISC)
        cls.overset = disc_overset.golden_fingerprint(OVERSET)

    def test_discriminating_flags(self):
        self.assertTrue(self.disc["flags"]["discontinuous"])
        self.assertFalse(self.overset["flags"]["discontinuous"])
        # 实测钉死：两黄金 parts_control/overset 均 false（语义在条件块）
        self.assertFalse(self.disc["flags"]["overset"])
        self.assertFalse(self.overset["flags"]["overset"])

    def test_rotor_filename_follows_stem(self):
        self.assertEqual(self.disc["rotor_filename"], "box_disc_RotorInfo")
        self.assertEqual(self.overset["rotor_filename"],
                         "box_overset_RotorInfo")
        self.assertEqual(disc_overset.rotor_stem(
            self.disc["rotor_filename"]), "box_disc")

    def test_shared_skeleton(self):
        for fp in (self.disc, self.overset):
            self.assertEqual(fp["overset_skeleton"],
                             list(disc_overset.OVERSET_SKELETON))
            self.assertTrue(fp["has_movinggroup"])
            self.assertEqual(fp["movinggroup_names"], ["box"])
            self.assertEqual(fp["gph_members"], ["meshinggroup1.gph"])

    def test_same_class_self_and_cross(self):
        ok, diffs = disc_overset.fingerprint_same_class(self.disc, self.disc)
        self.assertTrue(ok)
        self.assertEqual(diffs, [])
        ok, diffs = disc_overset.fingerprint_same_class(self.overset,
                                                        self.disc)
        self.assertFalse(ok)
        keys = {d["key"] for d in diffs}
        self.assertIn("flags", keys)
        # rotor 文件名被忽略，不进 diffs
        self.assertNotIn("rotor_filename", keys)


class TestSameClassLogic(unittest.TestCase):
    def test_ignore_key_not_compared(self):
        a = {"flags": {"discontinuous": True}, "rotor_filename": "x_RotorInfo"}
        b = {"flags": {"discontinuous": True}, "rotor_filename": "y_RotorInfo"}
        ok, diffs = disc_overset.fingerprint_same_class(a, b)
        self.assertTrue(ok)

    def test_missing_key_reported(self):
        a = {"flags": {"discontinuous": True}}
        b = {"flags": {"discontinuous": True}, "has_movinggroup": True}
        ok, diffs = disc_overset.fingerprint_same_class(a, b)
        self.assertFalse(ok)
        self.assertEqual(diffs[0]["key"], "has_movinggroup")


if __name__ == "__main__":
    unittest.main()
