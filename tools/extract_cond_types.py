#!/usr/bin/env python3
"""从 scFLOWpre 二进制提取权威 ``Cond*`` 条件类型目录。

数据源（双编码 latin-1 / UTF-16-LE 扫描）：

* ``scFLOWpreGUI_Bx64net.dll`` —— GUI 侧对话框注册（≈141 token）
* ``scFLOWpreCmd_Bx64net.dll`` —— 命令/序列化侧（≈259 token，含 ``*Impl``
  C++ 实现类名与 ``*_`` 内部变体，需规范化）

产出 ``schemas/cond_types.json``：每个规范类型含
``category``（向导页归类）、``display``（首批人工核对 + 规则回退）、
``evidence``（命中哪些二进制）、``lineage``、可选 ``help``（HTML 帮助页，
由 :mod:`tools.html_cond_extract` 交叉核对回填）与 ``sample``（本地
pph 样本中出现过 → 字段 schema 可用）。

用法::

    python tools/extract_cond_types.py            # 生成 JSON
    python tools/extract_cond_types.py --check    # 摘要 + 与本地样本交叉核对
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"
OUT = SCHEMAS / "cond_types.json"

DEFAULT_PROGRAMS = Path(
    r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64")
BINARIES = [
    ("GUI", "scFLOWpreGUI_Bx64net.dll"),
    ("Cmd", "scFLOWpreCmd_Bx64net.dll"),
]

# 首批人工核对的显示名（scFLOWpre UI 英文标签）
_DISPLAY: dict[str, str] = {
    "CondBoundaryFlowIO": "Inflow and outflow condition",
    "CondBoundaryFlowIOLiquidFilm":
        "Inflow and outflow condition (Liquid film)",
    "CondBoundaryGTSuite": "GT-SUITE boundary condition",
    "CondBoundaryDiffusiveSpecies":
        "Diffusive species boundary condition",
    "CondBoundaryElectric": "Electric boundary condition",
    "CondBoundaryHumidity": "Humidity boundary condition",
    "CondBoundaryRadiation": "Radiation boundary condition",
    "CondBoundarySolarRadiation":
        "Solar radiation boundary condition",
    "CondBoundaryWallStress": "Wall shear stress condition",
    "CondBoundaryWallThermal": "Wall heat transfer condition",
    "CondSymmetricalBoundary": "Symmetrical boundary condition",
    "CondParticleSymmBoundaryDEM":
        "Particle symmetrical boundary condition (DEM)",
    "CondParticleSymmHeatBoundaryDEM":
        "Particle symmetrical thermal boundary condition (DEM)",
    "CondPeriodicBoundary": "Periodic boundary condition",
    "CondInitial": "Initial condition",
    "CondInitialRandVel":
        "Initial turbulence of velocity (LES)",
    "CondInitialShapeModify": "Initial shape modification",
    "CondSource": "Source condition",
    "CondSourceDEM": "Source condition (DEM)",
    "CondSourceMass": "Mass source condition",
    "CondAcceleration": "Acceleration condition",
    "CondAccelerationDEM": "Acceleration condition (DEM)",
    "CondFrictionalHeat": "Frictional heat",
    "CondFacePressureDrop": "Pressure drop (Face)",
    "CondRadiationLamp": "Lamp (radiation source)",
    "CondFanDetail": "Fan detail setting",
    "CondBoundaryDetail": "Boundary detail setting",
    "CondFixDEM": "Fixed value (DEM)",
    "CondParticleBoundary": "Particle boundary condition",
    "CondParticleBoundaryDEM":
        "Particle outflow boundary condition (DEM)",
    "CondParticleRestitutionDEM":
        "Restitution boundary condition (DEM)",
    "CondParticleGeneration": "Particle generation condition",
    "CondParticleGenerationDEM":
        "Particle generation condition (DEM)",
    "CondParticlePropertyDEM": "Particle property (DEM)",
    "CondParticlePropertyMemberDEM": "Particle property member (DEM)",
    "CondParticleDomainDEM": "Particle domain (DEM)",
    "CondParticleTracking": "Particle tracking condition",
    "CondParticleHistogram": "Particle histogram",
    "CondParticleCounter": "Particle counter",
    "CondSprayGeneration": "Spray generation condition",
    "CondSprayParticle": "Spray particle",
    "CondVofToParticle": "VOF to particle conversion",
    "CondPorousMedia": "Porous media condition",
    "CondHumidity": "Humidity condition",
    "CondMixedGas": "Mixed gas condition",
    "CondMoving": "Moving condition",
    "CondMovingStability": "Moving condition (stability)",
    "CondBladeShape": "Blade shape condition",
    "CondReaction": "Reaction condition",
    "CondSurfaceReaction": "Surface reaction condition",
    "CondReactionIncompSpecies":
        "Reaction (incompressible species)",
    "CondCombustion": "Combustion condition",
    "CondFreeSurface": "Free surface condition",
    "CondCavitation": "Cavitation condition",
    "CondSolidification": "Solidification condition",
    "CondMultiphaseMaterial": "Multiphase material",
    "CondMultiphasePhaseChange": "Multiphase phase change",
    "CondMultiphaseSurfaceTension": "Multiphase surface tension",
    "CondMultiphaseHandling": "Multiphase handling",
    "CondWaveGeneration": "Wave generation condition",
    "CondWaveDamping": "Wave damping condition",
    "CondOutputCSV": "CSV output",
    "CondOutputPclFile": "Particle file output",
    "CondOutputTimeSeries": "Time series output",
    "CondOutputPartialFPH": "Partial FPH output",
    "CondOutputFlowNoise": "Flow noise output",
    "CondDiscontinuous": "Discontinuous surface condition",
    "CondPartition": "Partition condition",
    "CondAnalysisControl": "Analysis control condition",
    "CondBoussinesqBaseTemp": "Boussinesq base temperature",
    "CondJOSModel": "Thermoregulation model (JOS)",
    "CondJOSInitial": "Initial condition (JOS)",
    "CondJOSBodyType": "Body type (JOS)",
    "CondJOSClothing": "Clothing (JOS)",
    "CondPassiveScalar": "Passive scalar condition",
    "CondOversetGap": "Overset gap",
    "CondOversetRegionOption": "Overset region option",
    "CondLDCMorphingALE": "Morphing (LDC/ALE)",
}

# 别名：本地 pph 样本中的旧式类型名 → 规范 Cond* 名
_ALIASES: dict[str, str] = {
    "Electric": "CondBoundaryElectric",
    "HumidityBoundary": "CondHumidity",
    "ParticleCounter": "CondParticleCounter",
    "Reaction": "CondReaction",
}

# HTML 帮助页（HTML_STpre_Eng，人工核对首批；由 html_cond_extract 交叉验证）
_HELP: dict[str, str] = {
    "CondBoundaryFlowIO": "Flux_Inout.html",
    "CondBoundaryFlowIOLiquidFilm": "FreeSurface_Type.html",
    "CondBoundaryRadiation": "radiation_bc.html",
    "CondBoundarySolarRadiation": "SOLAR_Boundary.html",
    "CondBoundaryWallThermal": "Aent_Condition.html",
    "CondBoundaryWallStress": "Wall_Condition.html",
    "CondSymmetricalBoundary": "SymBd.html",
    "CondPeriodicBoundary": "Period_Explain.html",
    "CondSource": "Source_Condition.html",
    "CondPorousMedia": "PorousMedia_Main.html",
    "CondHumidity": "Humidity_Condition.html",
    "CondParticleTracking": "Particle_Kind.html",
    "CondMoving": "Moving_Body_Condition.html",
    "CondReaction": "Reaction_Type.html",
    "CondFreeSurface": "FreeSurface_Type.html",
    "CondInitial": "LES_Init.html",
    "CondCavitation": "hydrostatic.html",
    "CondBoussinesqBaseTemp": "BaseTemperature.html",
    "CondJOSModel": "JOS_TSV.html",
    "CondWaveGeneration": "MARS_Wave_Source.html",
    "CondWaveDamping": "MARS_Wave_Source.html",
}


def _classify(name: str) -> str:
    """规则归类到向导页 category（顺序敏感）。"""
    n = name
    if n.startswith("CondOutput"):
        return "output"
    if "SolarRadiation" in n or n.startswith("CondSolar"):
        return "solar"
    if "Radiation" in n or n.startswith("CondRad"):
        return "radiation"
    if "Humidity" in n:
        return "humidity"
    if "WallThermal" in n or "HeatBoundary" in n:
        return "bc_thermal"
    if "WallStress" in n:
        return "bc_wall"
    if "Symm" in n:
        return "bc_sym"
    if "Periodic" in n:
        return "bc_periodic"
    if n.startswith("CondBoundary"):
        return "bc_flow"
    if n.startswith("CondInitial"):
        return "initial"
    if ("Particle" in n or "DEM" in n or "Spray" in n
            or n == "CondVofToParticle"):
        return "particle"
    if n.startswith(("CondMoving", "CondLDC", "CondBladeShape")):
        return "moving"
    if "Porous" in n:
        return "porous"
    if n.startswith(("CondSource", "CondAcceleration", "CondFriction",
                     "CondFacePressureDrop", "CondSted")):
        return "source"
    if n.startswith("CondFix"):
        return "fixed"
    if n.startswith(("CondReaction", "CondCombustion")):
        return "reaction"
    if n.startswith(("CondMultiphase", "CondFreeSurface", "CondWave",
                     "CondCavitation", "CondSolidification",
                     "CondMixedGas")):
        return "multiphase"
    if n.startswith(("CondCosim", "CondCoSim", "CondNastran", "CondFMI",
                     "CondActran")):
        return "cosim"
    if n.startswith("CondBattery"):
        return "battery"
    if n.startswith("CondOverset"):
        return "overset"
    if n.startswith(("CondJOS",)):
        return "human"
    if n in ("CondPartition", "CondAnalysisControl", "CondMovingStability",
             "CondUPWDOption", "CondWavelet", "CondWaveletOption",
             "CondBoussinesqBaseTemp", "CondCavitation_"):
        return "basic"
    return "misc"


def _prettify(name: str) -> str:
    """CamelCase → 句子式回退显示名。"""
    s = re.sub(r"(?<!^)(?=[A-Z])", " ", name)
    s = s.replace("Cond ", "").replace("DEM", "(DEM)")
    return s.strip()


def scan_binaries(programs_dir: Path) -> dict[str, set[str]]:
    """返回 {tag: {Cond* token}}（latin-1 + UTF-16-LE 双扫描）。"""
    pat = re.compile(r"\bCond[A-Z][A-Za-z0-9_]{5,58}\b")
    out: dict[str, set[str]] = {}
    for tag, fname in BINARIES:
        path = programs_dir / fname
        if not path.is_file():
            continue
        data = path.read_bytes()
        toks: set[str] = set()
        for m in pat.finditer(data.decode("latin-1", errors="ignore")):
            toks.add(m.group())
        u16 = data.decode("utf-16-le", errors="ignore")
        for m in pat.finditer(u16):
            toks.add(m.group())
        out[tag] = toks
    return out


def canonicalize(per_bin: dict[str, set[str]]) -> dict[str, dict]:
    """去掉 ``*Impl`` / ``*_`` 实现类变体 → 规范类型 + 证据。"""
    merged: dict[str, set[str]] = {}
    for tag, toks in per_bin.items():
        for t in toks:
            base = t
            if base.endswith("Impl"):
                base = base[:-4]
            while base.endswith("_"):
                base = base[:-1]
            merged.setdefault(base, set()).add(tag)
    # GUI 命中 = 对话框真实存在；仅 Cmd 命中的保留（序列化层类型）
    types: dict[str, dict] = {}
    for base, ev in merged.items():
        if base.endswith(("Dlg", "Class", "Base", "Window")):
            continue
        if "GUI" in ev:
            lineage = "gui"
        else:
            lineage = "cmd"
        types[base] = {
            "category": _classify(base),
            "display": _DISPLAY.get(base) or _prettify(base),
            "evidence": sorted(ev),
            "lineage": lineage,
            "help": _HELP.get(base, ""),
        }
    return types


def mark_samples(types: dict[str, dict],
                 samples: dict[str, int]) -> dict[str, list[str]]:
    """把本地 pph 样本计数标到 ``sample`` 字段；返回别名命中报告。"""
    alias_hits: list[str] = []
    for name, cnt in samples.items():
        canon = _ALIASES.get(name, name)
        if canon in types:
            types[canon]["sample"] = cnt
            if canon != name:
                alias_hits.append(f"{name} -> {canon}")
        elif name not in alias_hits:
            alias_hits.append(f"{name} -> (unmatched)")
    return alias_hits


def local_sample_types() -> dict[str, int]:
    """从本地 pph 样本统计条件类型出现次数（缺样本时为空）。"""
    sys.path.insert(0, str(ROOT))
    from pph_parser import PphArchive  # noqa: PLC0415
    from schema_extract import extract_archive_schema  # noqa: PLC0415
    paths = [
        ROOT / "box.pph", ROOT / "box2.pph",
        ROOT.parent / "examples" / "box" / "box.pph",
        ROOT.parent / "examples" / "box" / "box_ansa.pph",
        ROOT.parent / "examples" / "tr03_gph" / "tr03_bcall.pph",
        ROOT.parent / "examples" / "tr03_gph" / "tr03_gph.pph",
    ]
    counts: dict[str, int] = {}
    for p in paths:
        if not p.is_file():
            continue
        try:
            sch = extract_archive_schema(PphArchive.open(str(p)))
        except Exception:  # noqa: BLE001
            continue
        for t, e in sch.get("conditions", {}).get("types", {}).items():
            counts[t] = counts.get(t, 0) + int(e.get("count", 0))
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--programs", type=Path, default=DEFAULT_PROGRAMS)
    ap.add_argument("--check", action="store_true",
                    help="打印摘要与样本交叉核对，不写 JSON")
    args = ap.parse_args(argv)

    per_bin = scan_binaries(args.programs)
    if not per_bin:
        print(f"no binaries found under {args.programs}", file=sys.stderr)
        return 1
    types = canonicalize(per_bin)
    samples = local_sample_types()
    alias_report = mark_samples(types, samples)

    by_cat: dict[str, int] = {}
    for t in types.values():
        by_cat[t["category"]] = by_cat.get(t["category"], 0) + 1

    print(f"binaries: {sorted(per_bin)}")
    print(f"canonical Cond* types: {len(types)}")
    print("by category:")
    for cat in sorted(by_cat, key=lambda c: -by_cat[c]):
        print(f"  {cat:<12} {by_cat[cat]}")
    gui_only = sum(1 for t in types.values() if t["lineage"] == "gui")
    print(f"lineage: gui={gui_only} cmd-only={len(types) - gui_only}")
    print(f"sample-backed: {sum(1 for t in types.values() if t.get('sample'))}")
    if alias_report:
        print("sample aliases:", "; ".join(alias_report))

    if not args.check:
        SCHEMAS.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "sources": dict(BINARIES),
            "aliases": _ALIASES,
            "types": types,
        }
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"written: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
