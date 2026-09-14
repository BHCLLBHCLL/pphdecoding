"""R32-1：由「实测键账本」推出重核用例；getter 名从**目录**核对（不猜）。"""
import json, sys, pathlib
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
from automation import scflowpre_api as api

LEDGER = [
    # (setter, value, 期望键)
    ("SetFacetSimpleChordTol", "0.25", "FACET.SIMPLE_CHORD_TOLERANCE"),
    ("SetFacetSimpleMaxAngle", "8.0", "FACET.SIMPLE_MAX_ANGLE"),
    ("SetFacetSimpleMaxWidth", "9.0", "FACET.SIMPLE_MAX_WIDTH"),
    ("SetFacetUseDetailMaxWidth", "false", "FACET.USE_DETAIL_MAX_WIDTH"),
    ("SetFacetUseSimpleSetting", "false", "FACET.USE_SIMPLE_SETTING"),
    ("SetMDLMethod", "0", "FACET.MDL_METHOD"),
    ("SetFacetDetailChordAngle", "20.0", "FACET.DETAIL_CHORD_ANGLE"),
    ("SetAFFaceterLengthFactor", "0.3", "FACET.SOLID_BASE_LENGTH_FACTOR"),
    ("SetIntersectionDetectionDepth", "9", "FACET.INTERSECTION_DETECTION_DEPTH"),
    ("SetAFFaceterMinimumAngle", "12.0", "FACET.SOLID_BASE_MINIMUM_ANGLE"),
    ("SetAFFaceterLengthFactorForOctree", "0.3",
     "FACET.SOLID_BASE_LENGTH_FACTOR_FOR_OCTREE"),
    ("SetAFFaceterMinimumAngleForOctree", "8.0",
     "FACET.SOLID_BASE_MINIMUM_ANGLE_FOR_OCTREE"),
    ("SetSolidFacetLengthFactor", "0.7", "OCT_MESH.FACET_LENGTH_FACTOR"),
    ("SetSolidFacetAngle", "9.0", "OCT_MESH.FACET_ANGLE"),
    ("SetSolidFacetMaxWidthFactor", "7.0", "OCT_MESH.FACET_MAX_WIDTH_FACTOR"),
    ("SetSolidFacetSpecifyEachRegionFlag", "true",
     "OCT_MESH.FACET_SPECIFY_EACH_REGION"),
    ("SetCompleteParallelFlag", "true", "OCT_MESH.COMPLETE_PARALLEL"),
    ("SetVoxelOctRefineType", "speed", "OCT_MESH.VOXEL_OCT_REFINE_TYPE"),
]
cat = api.load_catalog()
mgs = cat["classes"]["MeshingGroupSetting"]["methods"]
cases, missing = [], []
for setter, value, key in LEDGER:
    getter = "Get" + setter[len("Set"):]
    if getter not in mgs:
        missing.append((setter, getter))
        getter = None
    cases.append((setter, value, getter))
print("ledger keys:", len(LEDGER))
print("getter 在目录中缺失:", missing)
args = []
for setter, value, getter in cases:
    spec = setter + "=" + value
    if getter:
        spec += ":" + getter
    args += ["--case", spec]
pathlib.Path("_p12u_gate/r32/cases.json").write_text(
    json.dumps({"ledger": LEDGER,
                "cases": [{"setter": s, "value": v, "getter": g,
                           "expect_key": k}
                          for (s, v, k), (_s2, _v2, g) in zip(LEDGER, cases)]},
               ensure_ascii=False, indent=1), encoding="utf-8")
print("CLI:", " ".join(args))
