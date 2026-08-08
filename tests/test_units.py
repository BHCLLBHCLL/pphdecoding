#!/usr/bin/env python3
"""单位注册表与换算引擎测试。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pph_parser import PphArchive  # noqa: E402
from units import (UnitRegistry, convert, is_supported_unit,  # noqa: E402
                   resolve_snapshot_unit, snapshot_unit_type_to_key)

BOX_PPH = ROOT / "box.pph"


class TestConvert(unittest.TestCase):
    def test_length(self):
        self.assertAlmostEqual(convert(1.0, "m", "mm"), 1000.0)
        self.assertAlmostEqual(convert(1.0, "inch", "mm"), 25.4)
        self.assertAlmostEqual(convert(2.0, "km", "m"), 2000.0)

    def test_time_and_speed(self):
        self.assertAlmostEqual(convert(1.0, "h", "s"), 3600.0)
        self.assertAlmostEqual(convert(1.0, "m/s", "km/h"), 3.6)
        self.assertAlmostEqual(convert(1000.0, "kg/m3", "g/cm3"), 1.0)

    def test_pressure(self):
        self.assertAlmostEqual(convert(1.0, "bar", "Pa"), 1e5)
        self.assertAlmostEqual(convert(1.0, "atm", "kPa"), 101.325)

    def test_temperature(self):
        self.assertAlmostEqual(convert(0.0, "degC", "K"), 273.15)
        self.assertAlmostEqual(convert(100.0, "degC", "degF"), 212.0)
        self.assertAlmostEqual(convert(32.0, "degF", "degC"), 0.0)

    def test_unsupported(self):
        with self.assertRaises(ValueError):
            convert(1.0, "parsec", "m")
        self.assertFalse(is_supported_unit("parsec"))


class TestUnitRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arch = PphArchive.open(str(BOX_PPH))
        cls.reg = UnitRegistry.from_xenv_bytes(cls.arch.read_member("main.xenv"))

    def test_model_length_unit(self):
        self.assertEqual(self.reg.unit("MODEL_LENGTH_UNIT"), "m")
        self.assertEqual(self.reg.unit("DEFAULT_SPEED_UNIT"), "m/s")

    def test_convert_key(self):
        self.assertAlmostEqual(
            self.reg.convert_key(1.0, "MODEL_LENGTH_UNIT", "DEFAULT_LENGTH_UNIT"),
            1.0)

    def test_snapshot_unit(self):
        self.assertEqual(snapshot_unit_type_to_key(1), "MODEL_LENGTH_UNIT")
        self.assertIsNone(snapshot_unit_type_to_key(99))
        xenv = self.reg.units
        self.assertEqual(
            resolve_snapshot_unit(1, _xenv_like(xenv)), "m")


def _xenv_like(units):
    class _X:
        def __init__(self, units):
            self.units = units

        def get(self, section, key, default=None):
            if section == "UNIT":
                return self.units.get(key, default)
            return default
    return _X(units)


if __name__ == "__main__":
    unittest.main()
