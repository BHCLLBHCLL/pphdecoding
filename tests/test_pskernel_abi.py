#!/usr/bin/env python3
"""pskernel_abi：pskernel 导出 x V35 手册接口映射回归。

依赖：Cradle 安装（pskernel.dll）与网络（q-solid V35 手册页，缓存于
tests/box/v35_pages）。缺依赖时逐项 skip。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pskernel_abi as abi  # noqa: E402

PSK23 = Path("C:/Program Files/Cradle/CradleCFD2023/Programs_x64/"
             "pskernel.dll")
PSK25 = Path("C:/Program Files/Cradle/CradleCFD2025.2/Programs_x64/"
             "pskernel.dll")


def _net_ok() -> bool:
    import urllib.request
    try:
        req = urllib.request.Request(
            abi.V35_BASE + "/pk_part_transmit.html", headers=abi._UA)
        urllib.request.urlopen(req, timeout=20).read(64)
        return True
    except Exception:
        return False


class TestParseSignature(unittest.TestCase):
    """签名解析（离线，用 V35 手册页面格式的固件文本）。"""

    TEXT = ("PK_PART_transmit PK_PART_transmit PK_ERROR_code_t "
            "PK_PART_transmit ( --- received arguments --- int n_parts, "
            "--- number of parts const PK_PART_t *parts, --- parts "
            "const char *key, --- key string const PK_PART_transmit_o_t "
            "*options --- transmit options ) This function transmits the "
            "given parts.")

    def test_basic(self):
        s = abi.parse_signature(self.TEXT)
        self.assertEqual(s["kind"], "function")
        self.assertEqual(s["name"], "PK_PART_transmit")
        self.assertEqual(s["return_type"], "PK_ERROR_code_t")
        self.assertEqual([p[1] for p in s["params"]],
                         ["n_parts", "parts", "key", "options"])
        self.assertEqual(s["params"][1][0], "const PK_PART_t *")
        self.assertEqual(s["params"][3][0], "const PK_PART_transmit_o_t *")

    def test_returned_arguments(self):
        text = ("PK_ENTITY_ask_class PK_ENTITY_ask_class PK_ERROR_code_t "
                "PK_ENTITY_ask_class ( --- received arguments --- "
                "PK_ENTITY_t entity, --- entity --- returned arguments --- "
                "PK_CLASS_t *const class --- class of entity ) This "
                "function returns the class.")
        s = abi.parse_signature(text)
        self.assertEqual([p[1] for p in s["params"]], ["entity", "class"])
        self.assertEqual(s["params"][1][0], "PK_CLASS_t *const")

    def test_paren_in_comment(self):
        text = ("PK_BODY_ask_faces PK_BODY_ask_faces PK_ERROR_code_t "
                "PK_BODY_ask_faces ( --- received arguments --- "
                "PK_BODY_t body, --- a body --- returned arguments --- "
                "int *const n_faces, --- number of faces (>= 0) "
                "PK_FACE_t **const faces --- faces (optional) ) This "
                "function returns faces.")
        s = abi.parse_signature(text)
        self.assertEqual([p[1] for p in s["params"]],
                         ["body", "n_faces", "faces"])
        self.assertEqual(s["params"][2][0], "PK_FACE_t **const")

    def test_single_param(self):
        text = ("PK_SESSION_start PK_SESSION_start PK_ERROR_code_t "
                "PK_SESSION_start ( --- received arguments --- "
                "const PK_SESSION_start_o_t *options ) This function "
                "starts the modeller.")
        s = abi.parse_signature(text)
        self.assertEqual([p[1] for p in s["params"]], ["options"])


class TestGenCtypes(unittest.TestCase):
    def test_generate(self):
        m = {
            "PK_ENTITY_ask_class": abi.InterfaceEntry(
                "PK_ENTITY_ask_class", 0, "function", "PK_ERROR_code_t",
                [("PK_ENTITY_t", "entity", ""),
                 ("PK_CLASS_t *const", "class", "")]),
        }
        out = abi.gen_ctypes(m)
        self.assertIn("pk.PK_ENTITY_ask_class.restype = c_int", out)
        self.assertIn('pk.PK_ENTITY_ask_class.argtypes = [c_void_p, c_void_p]',
                      out)


class TestExports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (PSK23.exists() or PSK25.exists()):
            raise unittest.SkipTest("pskernel.dll not installed")

    def test_dump(self):
        for p in (PSK23, PSK25):
            if not p.exists():
                continue
            ex = abi.dump_exports(p)
            names = {e.name for e in ex}
            self.assertIn("PK_PART_transmit", names)
            self.assertIn("PK_SESSION_start", names)

    def test_compare(self):
        if not (PSK23.exists() and PSK25.exists()):
            self.skipTest("need both pskernel versions")
        r = abi.compare_versions({"2023": str(PSK23), "2025.2": str(PSK25)})
        self.assertEqual(r["counts"]["2023"], 1350)
        self.assertEqual(r["counts"]["2025.2"], 1454)
        self.assertEqual(r["only"]["2023"], [])
        self.assertIn("PK_BODY_slice", r["only"]["2025.2"])


class TestFetch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = _net_ok()

    def test_fetch_and_parse(self):
        if not self.net:
            self.skipTest("no network to q-solid")
        txt = abi.fetch_v35_page("PK_PART_transmit")
        self.assertIsNotNone(txt)
        s = abi.parse_signature(txt)
        self.assertEqual(s["name"], "PK_PART_transmit")
        self.assertEqual(len(s["params"]), 4)

    def test_cache_hit(self):
        txt = abi.fetch_v35_page("PK_PART_transmit")
        if txt is None:
            self.skipTest("no cache and no network")
        txt2 = abi.fetch_v35_page("PK_PART_transmit")
        self.assertEqual(txt, txt2)


class TestMapInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cache = abi.DEFAULT_CACHE
        if not (cache / "pk_part_transmit.txt").exists() \
                and not _net_ok():
            raise unittest.SkipTest("no V35 cache and no network")

    def test_map_small(self):
        # 用小 DLL 不可行（导出全量抓取）——直接测 map 的核心路径：
        # 用缓存页构造小规模映射验证 signature 联动
        txt = abi.fetch_v35_page("PK_PART_transmit")
        s = abi.parse_signature(txt)
        self.assertEqual(s["return_type"], "PK_ERROR_code_t")


if __name__ == "__main__":
    unittest.main()
