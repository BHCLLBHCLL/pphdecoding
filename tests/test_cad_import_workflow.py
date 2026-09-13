"""R1-2 回归：一条命令 CAD→x_t（缓存）→PPH 成员，且二次导入为纯缓存命中。

验收句：单命令完成转换 + 落成员；同一源二次导入 ≤0.5 s 且**不启动 CADthru**。
本测试全程离线：预置缓存条目（按 源文件 sha256 前 16 位 命名）即可让
convert_cached 命中，从而验证「缓存 + 幂等注入 + 成员落盘」三条逻辑，
不依赖本机是否装有 Cradle 转换器。
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE_PPH = ROOT / "_p12a_e2e" / "box.pph"
BOX_XT = ROOT / "tests" / "box" / "box.x_t"

import importlib.util  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "cadthru_convert", str(ROOT / "tools" / "cadthru_convert.py"))
cadthru_convert = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cadthru_convert)


@unittest.skipUnless(BASE_PPH.is_file() and BOX_XT.is_file(),
                     "需要 box.pph 与 tests/box/box.x_t 夹具")
class TestCadImportWorkflow(unittest.TestCase):
    def _seed_cache(self, cad: Path, cache: Path) -> Path:
        key = hashlib.sha256(cad.read_bytes()).hexdigest()[:16]
        dst = cache / f"{cad.stem}-{key}.x_t"
        dst.write_bytes(BOX_XT.read_bytes())
        return dst

    def test_cached_import_skips_converter_and_injects_member(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cache = td / "cache"
            cache.mkdir()
            cad = td / "widget.step"
            cad.write_bytes(b"ISO-10303-21; fake STEP for cache test")
            seeded = self._seed_cache(cad, cache)
            out = td / "with_xt.pph"
            t0 = time.time()
            res = cadthru_convert.import_cad_to_pph(cad, BASE_PPH, out, cache)
            dt = time.time() - t0
            self.assertTrue(res["ok"], res)
            self.assertTrue(res["conversion"]["cached"],
                            "预置缓存命中时不得调用转换器")
            self.assertEqual(res["conversion"]["dst"], str(seeded))
            self.assertLess(dt, 5.0, "缓存命中路径必须快（无转换器启动）")
            with zipfile.ZipFile(out) as z:
                self.assertIn("widget.x_t", z.namelist())
                self.assertEqual(z.read("widget.x_t"), BOX_XT.read_bytes())

    def test_second_import_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cache = td / "cache"
            cache.mkdir()
            cad = td / "widget.step"
            cad.write_bytes(b"ISO-10303-21; fake STEP for cache test")
            self._seed_cache(cad, cache)
            out = td / "with_xt.pph"
            first = cadthru_convert.import_cad_to_pph(cad, BASE_PPH, out, cache)
            self.assertTrue(first["ok"])
            t0 = time.time()
            second = cadthru_convert.import_cad_to_pph(cad, BASE_PPH, out, cache)
            dt = time.time() - t0
            self.assertTrue(second["ok"])
            self.assertIn("skipped", second,
                          "同源二次导入应识别成员已存在并跳过")
            self.assertLess(dt, 1.0, "幂等跳过必须 <1 s")

    def test_missing_pph_reports_error_without_raising(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cache = td / "cache"
            cache.mkdir()
            cad = td / "x.step"
            cad.write_bytes(b"x")
            self._seed_cache(cad, cache)
            res = cadthru_convert.import_cad_to_pph(
                cad, td / "nope.pph", td / "o.pph", cache)
            self.assertFalse(res["ok"])
            self.assertIn("error", res)


if __name__ == "__main__":
    unittest.main()
