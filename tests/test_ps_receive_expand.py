"""P2-5 回归：pskernel 接收流的分区/装配展开。

背景（2026-09-13 审计 §15.4）：`PK_PART_receive` 返回的不是 body（class 5006），
而是**分区（5007）**或**装配（5008）**标签；直接当 body 喂 `PK_BODY_ask_*` /
faceting 会 `OSError: access violation`。CADthru 转出的 `**PART1;` STEP 流正是
装配形态（tag class 5008），修复前 `tessellate_xt` /**0 个部件**、`decode_brep` 崩溃。

夹具 `tests/box/_cadthru_step_asm.x_t` 由 P1-0 实测产出（CADthru
`OpenXtFile(STEP) + SaveXTFile` 的 `base v7.step` 转换结果），
宿主对该 STEP 的回读为 1 个部件、bbox 端点 -82.2 / 36。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ps_facet2_nodes as ps  # noqa: E402

ASM_XT = ROOT / "tests" / "box" / "_cadthru_step_asm.x_t"
BOX_XT = ROOT / "tests" / "box" / "box.x_t"


@unittest.skipUnless(ps.available(), "Cradle pskernel.dll not available")
class TestReceiveExpansion(unittest.TestCase):
    def test_assembly_stream_expands_to_bodies(self):
        """装配流（class 5008）必须展开出 body，且能剖分出三角面片。"""
        if not ASM_XT.is_file():
            self.skipTest("cadthru assembly fixture missing")
        raw = ASM_XT.read_bytes()
        sess = ps._get_session()
        tags = sess.receive_xt(raw)
        self.assertTrue(tags)
        self.assertEqual(sess._ask_class(tags[0]), 5008,
                         "夹具应为装配形态（class 5008）")
        bodies = sess.bodies_of(tags)
        self.assertGreaterEqual(len(bodies), 1)
        self.assertNotEqual(bodies, list(tags),
                            "装配标签不得原样当作 body 返回")
        for b in bodies:
            self.assertEqual(sess._ask_class(b), 5006)
        parts = ps.tessellate_xt(raw, adaptive=False)
        self.assertGreaterEqual(len(parts), 1)
        self.assertGreater(sum(len(p.triangles) for p in parts), 1000)

    def test_decode_brep_on_assembly_stream(self):
        """decode_brep 不得再崩（修复前 access violation reading 0x5C）。"""
        if not ASM_XT.is_file():
            self.skipTest("cadthru assembly fixture missing")
        br = ps.decode_brep(ASM_XT.read_bytes())
        self.assertGreaterEqual(len(br["bodies"]), 1)
        self.assertGreater(len(br["faces"]), 0)
        self.assertGreater(len(br["vertices"]), 0)

    def test_plain_body_stream_still_works(self):
        """既有 body 流（box.x_t = 5 个 class 5006）行为不回归。"""
        raw = BOX_XT.read_bytes()
        sess = ps._get_session()
        tags = sess.receive_xt(raw)
        self.assertTrue(tags)
        self.assertTrue(all(sess._ask_class(t) == 5006 for t in tags))
        self.assertEqual(sess.bodies_of(tags), [int(t) for t in tags])
        parts = ps.tessellate_xt(raw, adaptive=False)
        self.assertGreaterEqual(len(parts), 1)


if __name__ == "__main__":
    unittest.main()
