#!/usr/bin/env python3
"""pskernel Parasolid 编码（PK_PART_transmit）round-trip 回归。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ps_facet2_nodes  # noqa: E402

BOX_XT = ROOT / "tests" / "box" / "box.x_t"


class TestTransmitRoundtrip(unittest.TestCase):
    def test_transmit_and_rereceive(self):
        if not ps_facet2_nodes.available():
            self.skipTest("pskernel.dll not available")
        raw = BOX_XT.read_bytes()
        out = ps_facet2_nodes.transmit_xt(raw)
        self.assertGreater(len(out), 0)
        self.assertIn(b"TRANSMIT FILE", out[:256])
        # re-receive 输出的 x_t → 得到合法 body
        sess = ps_facet2_nodes._get_session()
        tags2 = sess.receive_xt(out)
        self.assertTrue(tags2)


if __name__ == "__main__":
    unittest.main()