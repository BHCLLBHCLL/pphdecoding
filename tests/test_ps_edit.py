#!/usr/bin/env python3
"""pskernel Parasolid 编辑算子（PK_BODY_boolean_2 / PK_FACE_delete_2）回归。"""

import ctypes
import sys
import unittest
from ctypes import POINTER, byref, c_double, c_int, c_void_p
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ps_facet2_nodes as psf  # noqa: E402


class TestBooleanEdit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not psf.available():
            raise unittest.SkipTest("pskernel.dll not available")
        cls.sess = psf._get_session()

    def test_unite_two_overlapping_blocks(self):
        b1 = self.sess.create_solid_block((1.0, 1.0, 1.0))
        b2 = self.sess.create_solid_block((1.0, 1.0, 1.0), (0.5, 0.0, 0.0))
        res = self.sess.body_boolean(b1, [b2], "unite")
        self.assertTrue(res)
        p = self.sess.facet_body(res[0])
        lo = p.points.min(axis=0)
        hi = p.points.max(axis=0)
        self.assertAlmostEqual(hi[0] - lo[0], 1.5, delta=0.05)
        self.assertAlmostEqual(hi[1] - lo[1], 1.0, delta=0.05)

    def test_subtract(self):
        b1 = self.sess.create_solid_block((1.0, 1.0, 1.0))
        b2 = self.sess.create_solid_block((1.0, 1.0, 1.0), (0.5, 0.0, 0.0))
        res = self.sess.body_boolean(b1, [b2], "subtract")
        self.assertTrue(res)


class TestFaceDelete(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not psf.available():
            raise unittest.SkipTest("pskernel.dll not available")
        cls.sess = psf._get_session()
        cls.pk = cls.sess.pk

    def test_delete_one_face(self):
        body = self.sess.create_solid_block((1.0, 1.0, 1.0))
        n = c_int(0)
        faces = c_void_p()
        self.pk.PK_BODY_ask_faces.restype = c_int
        self.pk.PK_BODY_ask_faces.argtypes = [c_int, POINTER(c_int), POINTER(c_void_p)]
        rc = self.pk.PK_BODY_ask_faces(body, byref(n), byref(faces))
        self.assertEqual(rc, 0)
        self.assertGreater(n.value, 0)
        fl = [int(ctypes.cast(faces, POINTER(c_int * n.value)).contents[i])
              for i in range(n.value)]
        self.sess.face_delete([fl[0]], heal="cap")


class TestTransform(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not psf.available():
            raise unittest.SkipTest("pskernel.dll not available")
        cls.sess = psf._get_session()

    def test_translate_body(self):
        body = self.sess.create_solid_block((1.0, 1.0, 1.0))
        p1 = self.sess.facet_body(body)
        lo1 = p1.points.min(axis=0)
        self.sess.transform_body(body, dx=10.0)
        p2 = self.sess.facet_body(body)
        lo2 = p2.points.min(axis=0)
        self.assertAlmostEqual(lo2[0] - lo1[0], 10.0, delta=0.05)


if __name__ == "__main__":
    unittest.main()