#!/usr/bin/env python3
"""scFLOW 单位注册表与换算引擎。

覆盖 ``main.xenv`` 的 UNIT Section（127+ 键）与快照 ``LENGTHVWU``/
``DPOINTU`` 的 ``unit_type``。换算基于 SI 因子表，温度（K/degC/degF）
使用偏移换算，复合单位（``m/s``、``m3/s``、``kg/m3``）按幂次拆分。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import pphxml


# 简单单位 → 换算到 SI 的因子；温度单独处理
_SI_FACTOR: dict[str, float] = {
    # 长度
    "m": 1.0, "cm": 0.01, "mm": 0.001, "um": 1e-6, "µm": 1e-6,
    "km": 1000.0, "inch": 0.0254, "in": 0.0254, "ft": 0.3048,
    "mile": 1609.344,
    # 时间
    "s": 1.0, "sec": 1.0, "min": 60.0, "h": 3600.0, "hr": 3600.0,
    "day": 86400.0,
    # 质量
    "kg": 1.0, "g": 0.001, "mg": 1e-6, "t": 1000.0, "ton": 1000.0,
    # 压力
    "Pa": 1.0, "kPa": 1e3, "MPa": 1e6, "GPa": 1e9,
    "bar": 1e5, "mbar": 1e2, "atm": 101325.0, "psi": 6894.757293168,
    # 角度
    "rad": 1.0, "deg": 0.017453292519943295, "degree": 0.017453292519943295,
    # 能量/功率/力
    "J": 1.0, "kJ": 1e3, "MJ": 1e6, "W": 1.0, "kW": 1e3, "MW": 1e6,
    "N": 1.0, "kN": 1e3,
    # 频率
    "Hz": 1.0, "kHz": 1e3, "MHz": 1e6,
}

_TEMPERATURE_UNITS = {"K", "degC", "C", "degF", "F"}


def _temperature_to_kelvin(value: float, unit: str) -> float:
    if unit in ("K",):
        return value
    if unit in ("degC", "C"):
        return value + 273.15
    if unit in ("degF", "F"):
        return (value - 32.0) * 5.0 / 9.0 + 273.15
    raise ValueError(f"unsupported temperature unit: {unit}")


def _kelvin_to_temperature(value: float, unit: str) -> float:
    if unit in ("K",):
        return value
    if unit in ("degC", "C"):
        return value - 273.15
    if unit in ("degF", "F"):
        return (value - 273.15) * 9.0 / 5.0 + 32.0
    raise ValueError(f"unsupported temperature unit: {unit}")


def _split_compound(unit: str) -> tuple[list[tuple[str, int]],
                                       list[tuple[str, int]]]:
    """把 ``m3/s``、``kg/(m·s2)`` 拆成 (分子, 分母) 的 (符号, 幂) 列表。"""
    unit = unit.strip().replace("·", "*").replace(" ", "")
    if not unit or unit == "-":
        return [], []
    parts = unit.split("/")
    if len(parts) > 2:
        raise ValueError(f"unsupported compound unit: {unit}")
    nums = parts[0].split("*") if parts[0] else []
    dens = parts[1].split("*") if len(parts) == 2 and parts[1] else []

    def _tokens(items: list[str]) -> list[tuple[str, int]]:
        out: list[tuple[str, int]] = []
        for item in items:
            m = re.fullmatch(r"([A-Za-zµ°]+)(\d*)", item)
            if not m:
                raise ValueError(f"unsupported unit token: {item!r}")
            power = int(m.group(2) or 1)
            out.append((m.group(1), power))
        return out

    return _tokens(nums), _tokens(dens)


def _factor(unit: str) -> Optional[float]:
    """返回单位到 SI 的纯量因子；温度/未知单位返回 None。"""
    if unit in _TEMPERATURE_UNITS:
        return None
    num, den = _split_compound(unit)
    factor = 1.0
    for sym, power in num:
        base = _SI_FACTOR.get(sym)
        if base is None:
            return None
        factor *= base ** power
    for sym, power in den:
        base = _SI_FACTOR.get(sym)
        if base is None:
            return None
        factor /= base ** power
    return factor


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """数值单位换算；温度支持偏移。"""
    from_unit = (from_unit or "").strip()
    to_unit = (to_unit or "").strip()
    if from_unit == to_unit:
        return float(value)
    if from_unit in _TEMPERATURE_UNITS or to_unit in _TEMPERATURE_UNITS:
        if from_unit not in _TEMPERATURE_UNITS or \
                to_unit not in _TEMPERATURE_UNITS:
            raise ValueError("cannot mix temperature and non-temperature units")
        return _kelvin_to_temperature(
            _temperature_to_kelvin(float(value), from_unit), to_unit)
    f = _factor(from_unit)
    t = _factor(to_unit)
    if f is None or t is None:
        raise ValueError(f"unsupported unit conversion: {from_unit} -> {to_unit}")
    return float(value) * f / t


def is_supported_unit(unit: str) -> bool:
    unit = (unit or "").strip()
    if unit in _TEMPERATURE_UNITS:
        return True
    try:
        return _factor(unit) is not None
    except ValueError:
        return False


@dataclass
class UnitRegistry:
    """从 ``main.xenv`` 的 UNIT Section 构建的键 → 单位映射。"""

    units: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.units is None:
            self.units = {}

    @classmethod
    def from_xenv(cls, xenv: pphxml.XenvSettings) -> "UnitRegistry":
        units = dict(xenv.sections.get("UNIT", {}))
        return cls(units=units)

    @classmethod
    def from_xenv_bytes(cls, data: bytes) -> "UnitRegistry":
        return cls.from_xenv(pphxml.parse_xenv(data))

    def unit(self, key: str, default: str = "") -> str:
        return (self.units or {}).get(key, default)

    def convert_key(self, value: float, from_key: str, to_key: str) -> float:
        return convert(value, self.unit(from_key), self.unit(to_key))

    def quantity_keys(self) -> dict[str, str]:
        """键名 → 当前单位，供编辑器/状态栏展示。"""
        return dict(self.units or {})


# 快照 VWU 标签 → xenv 单位键（量纲感知）。
# unit_type 码目前实测恒为 1（= SI/模型单位制）；「码值→单位系统」的完整枚举
# 仍需多单位制样例（或 SCTprime 逆向）确认。这里把「哪个量纲用哪个键」与
# 「码值选哪个单位系统」解耦：量纲由 VWU 标签决定，单位串取自 xenv。
VWU_TAG_TO_XENV_KEY: dict[str, str] = {
    "LENGTHVWU": "MODEL_LENGTH_UNIT",
    "ANGLEVWU": "DEFAULT_ANGLE_UNIT",
    "AREAVWU": "DEFAULT_AREA_UNIT",
    "DENSITYVWU": "DEFAULT_DENSITY_UNIT",
    "ENERGYVWU": "DEFAULT_ENERGY_UNIT",
    "FORCEVWU": "DEFAULT_FORCE_UNIT",
    "TIMEVWU": "DEFAULT_TIME_UNIT",
    "VOLUMEVWU": "DEFAULT_VOLUME_UNIT",
    "DPOINTU": "DEFAULT_COORDX_UNIT",
}

# 已确认的 unit_type 码 → 单位系统（1 = SI/模型单位制）；待多单位制样例补全
UNIT_TYPE_TO_XENV_KEY: dict[int, str] = {1: "MODEL_LENGTH_UNIT"}


def snapshot_unit_type_to_key(unit_type: int) -> Optional[str]:
    return UNIT_TYPE_TO_XENV_KEY.get(unit_type)


def resolve_snapshot_unit(unit_type: int,
                          xenv: pphxml.XenvSettings,
                          tag: str = "LENGTHVWU") -> Optional[str]:
    """把快照 VWU/DPOINTU 记录的 ``unit_type`` 解析为 xenv 单位串。

    ``tag`` 指定记录量纲（``LENGTHVWU``/``TIMEVWU``/``DPOINTU``…），决定
    取哪个 DEFAULT_*_UNIT 键；``unit_type`` 目前仅支持 1（SI）。
    """
    if unit_type != 1:
        return None
    key = VWU_TAG_TO_XENV_KEY.get(tag, "MODEL_LENGTH_UNIT")
    return xenv.get("UNIT", key)
