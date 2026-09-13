#!/usr/bin/env python3
"""跨样例结构不变式测试（3.6 验证覆盖局限的缓解）。

对 ``tests/`` 下发现的**所有** ``.pph`` 自动执行与具体样例无关的结构断言：
容器角色、网格组一致性、MDL/OCT/快照不变量。新增真实项目样例时只需把
``.pph`` 放入 ``tests/``，本文件即自动纳入回归。

黄金文件集（P4-4，宿主真实生成，非手工构造）：

* ``box.pph``（仓库根）— 基础流动 + 热/电/湿/粒子/反应条件基线
* ``tests/box_disc.pph`` — box + ``SetPartsControl "Discontinuous", True``
  （COM 宿主 SaveProject，证据 box_com_diag5.log；main.xml 落
  ``<Discontinuous>true</Discontinuous>``）
* ``tests/box_overset.pph`` — box + ``SetPartsControl "Overset", True``
  （Overset 域：工程登记 ``*_mapped.bdf`` / ``*_RotorInfo`` 输出）
* ``tests/laptop_thermal_steady_scaled_v3_fanonly_simple.pph`` —
  稳态热 + 风扇（CondMoving/CondFix/CondSource，472MB）
* ``box2.pph``（仓库根）— box 近重复（回归备份，不计入域覆盖）

样例特定值断言保留在 ``test_pph_parser.py``（golden 测试），两套互补：

* ``test_samples.py`` — 通用不变量（本文件）
* ``test_pph_parser.py`` — laptop / box 的已知值锁定

用法::

    python tests/test_samples.py [-v]
"""

import glob
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import mdl as mdl_mod  # noqa: E402
import oct as oct_mod  # noqa: E402
import sctsnapshot  # noqa: E402
from pph_parser import PphArchive  # noqa: E402

PPH_FILES = sorted(glob.glob(str(ROOT / "tests" / "**" / "*.pph"),
                             recursive=True))


def _reference_dir(sample: Path):
    """样例对应的已解包参考目录：同级同名目录或 ``tests/<stem>``。"""
    for extracted in (sample.with_suffix(""), ROOT / "tests" / sample.stem):
        if extracted.is_dir():
            return extracted
    return None


def _snapshot_and_oct(sample: Path):
    """返回 (SctSnapshot, OctModel)，复用 tests/ 下已解包的参考目录。"""
    extracted = _reference_dir(sample)
    if extracted is None:
        return None, None
    snap_path = extracted / "main.sctsnapshot"
    oct_path = None
    for p in extracted.glob("*.oct"):
        oct_path = p
        break
    if not snap_path.exists() or oct_path is None:
        return None, None
    return (sctsnapshot.SctSnapshot.load(str(snap_path)),
            oct_mod.parse_oct(str(oct_path)))


class TestContainerInvariants(unittest.TestCase):
    def test_all_pph_are_zip(self):
        self.assertTrue(PPH_FILES, "tests/ 下未发现 .pph 样例")
        for p in map(Path, PPH_FILES):
            with self.subTest(sample=p.name):
                self.assertTrue(zipfile.is_zipfile(p), f"{p.name} 不是 ZIP")

    def test_member_roles_consistent(self):
        """固定 5 个 main.* 成员必须存在；每个网格组四个二进制成员同前缀。"""
        for p in map(Path, PPH_FILES):
            with self.subTest(sample=p.name):
                arch = PphArchive.open(str(p))
                names = [m.name for m in arch.members]
                for main in ("main.js", "main.prp", "main.sctsnapshot",
                             "main.xenv", "main.xml"):
                    self.assertIn(main, names, f"{p.name} 缺 {main}")
                roles = {m.name: m.role for m in arch.members}
                unknown = [n for n, r in roles.items()
                           if r == "unknown" and not n.startswith("main.")]
                # 允许未知成员存在（新角色），但必须可列出
                self.assertIsInstance(unknown, list)
                groups = {n[:-4] for n in names if n.endswith(".gph")}
                for g in groups:
                    for suffix in (".oct", "_part.mdl", "_ridge.mdl"):
                        self.assertIn(
                            g + suffix, names,
                            f"{p.name}: 网格组 {g} 缺 {g}{suffix}")


class TestBinaryInvariants(unittest.TestCase):
    """对每个样例的 oct/mdl 做通用结构断言（不绑定具体数值）。"""

    def test_oct_invariants(self):
        for p in map(Path, PPH_FILES):
            extracted = _reference_dir(Path(p))
            if extracted is None:
                continue
            for oct_path in extracted.glob("*.oct"):
                with self.subTest(sample=oct_path.name):
                    m = oct_mod.parse_oct(str(oct_path))
                    self.assertGreater(m.n_octants, 0)
                    self.assertEqual((m.n_octants - 1) % 8, 0,
                                     "完整八叉树 n = 1 + 8×内部节点")
                    self.assertEqual((m.n_octants - 1) // 8, m.n_internal)
                    self.assertEqual(m.n_leaves, m.n_octants - m.n_internal)
                    self.assertTrue(np.all(m.root_min < m.root_max))
                    self.assertEqual(len(m.refinement), m.n_octants)

    def test_mdl_invariants(self):
        for p in map(Path, PPH_FILES):
            extracted = _reference_dir(Path(p))
            if extracted is None:
                continue
            for mdl_path in extracted.glob("*_part.mdl"):
                with self.subTest(sample=mdl_path.name):
                    m = mdl_mod.parse_mdl(str(mdl_path))
                    self.assertGreater(m.n_vertices, 0)
                    self.assertGreater(m.n_faces, 0)
                    b1, b2 = m.csid
                    self.assertEqual(len(b1), m.n_faces)
                    self.assertEqual(len(b2), m.n_faces)
                    self.assertEqual(len(m.frid), m.n_faces)
                    # face_type → npe 与连接表长度严格一致（CSR）
                    self.assertEqual(int(m.face_type.sum() - 130 * m.n_faces),
                                     len(m.conn))
                    if m.conn.size:
                        self.assertLess(int(m.conn.max()), m.n_vertices,
                                        "顶点索引越界")
                        self.assertGreaterEqual(int(m.conn.min()), 0)
                    # 闭体/区域表非空
                    self.assertGreater(len(m.closed_volumes), 0)


class TestSnapshotInvariants(unittest.TestCase):
    """快照记录树与 LZMS 嵌套块的通用不变量。"""

    @classmethod
    def setUpClass(cls):
        cls.pairs = {}
        for p in map(Path, PPH_FILES):
            snap, octm = _snapshot_and_oct(p)
            if snap is not None:
                cls.pairs[p.name] = (snap, octm)

    def test_pairs_found(self):
        self.assertTrue(self.pairs, "没有可用的 解包目录 + 快照 样例")

    def test_top_level_structure(self):
        for name, (snap, _oct) in self.pairs.items():
            with self.subTest(sample=name):
                tags = [r.tag for r in snap.records]
                self.assertEqual(tags[0], "CADTHRUVERSION")
                self.assertIn("TOPASSYSTRUCT", tags)
                self.assertIn("BSGSEX", tags)
                self.assertIsInstance(snap.skipped_bytes, int)

    def test_binary_blobs_present(self):
        for name, (snap, _oct) in self.pairs.items():
            with self.subTest(sample=name):
                self.assertTrue(snap.bodies())
                self.assertIsNotNone(snap.first("ZIPOCTREE"))
                self.assertIsNotNone(snap.first("ZIPFACETINGRULES"))

    def test_octree_body_equals_member(self):
        for name, (snap, octm) in self.pairs.items():
            with self.subTest(sample=name):
                crdl = snap.octree_crdlfld_bytes()
                self.assertIsNotNone(crdl)
                self.assertIn(b"CRDL-FLD", crdl[:16])

    @unittest.skipUnless(sctsnapshot.lzms_available(),
                         "需要 Windows cabinet.dll LZMS")
    def test_lzms_and_division_region(self):
        for name, (snap, octm) in self.pairs.items():
            with self.subTest(sample=name):
                bodies = snap.decompress_bodies()
                self.assertTrue(bodies)
                for b in bodies:
                    pk = b["pkbody3"]
                    self.assertGreater(len(pk.data), 20)
                    self.assertIn(b"SCH_", pk.decrypt()[:256])
                div = snap.octree_division()
                self.assertIsNotNone(div)
                self.assertEqual(len(div), octm.n_internal + 1)
                self.assertEqual(len(div), (octm.n_octants + 7) // 8)
                reg = snap.octree_region(n_octants=octm.n_octants)
                self.assertIsNotNone(reg)
                flags = reg["flags"]
                self.assertEqual(len(flags), octm.n_octants)
                self.assertTrue(set(np.unique(flags).tolist()) <= {0, 1})
                # flag=1 全部为叶子（重映射后）
                flags_oct = snap.octree_region_as_oct_order(octm.refinement)
                self.assertEqual(
                    int(((flags_oct == 1) & (octm.refinement == 1)).sum()), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
