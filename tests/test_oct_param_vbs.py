"""OctParam SetParams / SECTITEM 生成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation.pipeline_plan import (  # noqa: E402
    build_execute_vbs, build_oct_param_pairs, oct_param_actions,
    oct_param_sect_summary, _oct_sect_name,
)
from automation.history_vbs import decode_vbs  # noqa: E402


class TestOctSectName(unittest.TestCase):
    def test_part_surface(self):
        self.assertEqual(_oct_sect_name("Part surface (@Part)"),
                         "@PartSurface_Part")

    def test_named_part_surface(self):
        self.assertEqual(_oct_sect_name("Part surface (@case1)"),
                         "@PartSurface_case1")


class TestOctParamPairs(unittest.TestCase):
    def test_sectitem_from_region_size(self):
        sess = {
            "mode": "octant",
            "detail": {
                "input_by": "length",
                "min_oct_size": 0.001,
                "region_size": {
                    "Part surface (@Part)": {"size": 0.0005, "range": 0},
                },
            },
        }
        pairs = dict(build_oct_param_pairs(sess))
        self.assertEqual(pairs["SECTITEM.N"], "1")
        self.assertEqual(pairs["SECTITEM[0].NAME"], "@PartSurface_Part")
        self.assertEqual(float(pairs["SECTITEM[0].SIZE"]), 0.0005)
        self.assertEqual(pairs["SECTITEM[0].NEIGHBOR"], "0")

    def test_summary(self):
        sess = {
            "detail": {
                "region_size": {
                    "Part surface (@Part)": {"size": 0.0005, "range": 0},
                },
            },
        }
        s = oct_param_sect_summary(sess)
        self.assertEqual(len(s), 1)
        self.assertIn("@PartSurface_Part", s[0])
        self.assertIn("0.0005", s[0])


class TestOctParamVbs(unittest.TestCase):
    def test_actions_contain_setparams(self):
        sess = {
            "mode": "octant",
            "detail": {
                "region_size": {
                    "Part surface (@Part)": {"size": 0.0005, "range": 0},
                },
            },
        }
        actions = oct_param_actions(sess)
        joined = "\n".join(actions)
        self.assertIn("GetOctParam(False)", joined)
        self.assertIn("OctParam_.Initialize", joined)
        self.assertIn("OctParam_.SetParams ArrayParam1_", joined)
        self.assertIn('@PartSurface_Part', joined)
        self.assertIn("0.0005", joined)

    def test_build_execute_includes_octparam(self):
        sess = {
            "mode": "octant",
            "detail": {
                "region_size": {
                    "Part surface (@Part)": {"size": 0.0005, "range": 0},
                },
            },
        }
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "t.vbs"
            build_execute_vbs(
                "D:/proj/box.pph",
                {"bam": True, "oct": True, "mesh": True, "use_api": True},
                out, include_save=False, octree_sess=sess)
            text = decode_vbs(out.read_bytes())
            self.assertIn("OctParam_.SetParams", text)
            self.assertIn("@PartSurface_Part", text)
            self.assertIn("0.0005", text)
            # SetParams 必须在 CreateOctree 之前
            self.assertLess(text.index("OctParam_.SetParams"),
                            text.index("CreateOctree"))


if __name__ == "__main__":
    unittest.main()
