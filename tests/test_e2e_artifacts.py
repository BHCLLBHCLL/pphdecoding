"""R1-6：宿主 E2E 证据入回归 —— 让"截断日志当成功凭证"永久失效。

背景（审计 §4-E / §5-O6）：仓库根目录的 p12*_e2e.log 是**手工运行**宿主流程留下的
证据（不在 pytest 内），此前**没有任何测试解析它们**。后果是两个真实案例：

* p12e_wrapping_e2e.log 被文档引为"3100 步全 err=0"，实为 **814 步、无 end 标记**（截断）；
* p12e_bam_e2e.log 同样无 end。

本文件把证据语料纳入回归：逐日志校验 end 标记与 err 计数，并对**已知截断**的日志
显式登记理由（而非静默忽略）。语料规模另有下限断言，防止样本被"静默降级"。
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 允许缺少 end 标记的日志（均为已登记的真实截断/旧版流程，附理由）
KNOWN_TRUNCATED: dict[str, str] = {
    "p12a_edit_e2e.log": "legacy edit_ops 流程，早于统一 logged_script（无 end）",
    "p12e_bam_e2e.log": "BAM 流截断：工作进程返回但脚本未走完（审计 §5-O6）",
    "p12e_disc_e2e.log": "Disc 建组流截断（同上）",
    "p12e_wrapping_e2e.log": "Wrapping 流截断：文档曾引为 3100 步，实为 814 步无 end",
}

#: 允许出现非零 err 的日志 → 上限（业务性拒绝/预期错误，非脚本缺陷）
ALLOWED_NONZERO: dict[str, int] = {
    "p12a_edit_e2e.log": 9,          # legacy 流
    "p12i_cvrestore_e2e.log": 10,    # Restore Closed Volume 产品闸门拒绝（预期）
    "p12n_catia_mdl_e2e.log": 1,     # CATPart 空组 → s424（审计 §5-O7）
    "p12n_catia_mdl2_e2e.log": 1,    # 同上
}

#: 关键流程必须出现的 alive 探针（缺失即说明该流程未真正跑通）
REQUIRED_ALIVE: dict[str, tuple[str, ...]] = {
    "p12d_region_e2e.log": ("fr_", "qr_"),
    "p12d_region_reopen_e2e.log": ("doc_",),
    "p12e_mesh_e2e.log": ("mg_", "vmdl_"),
    "p12m_wiz_e2e.log": ("mdlwizard_", "mgw_"),
    "p12r3_ctrl_xt_e2e.log": ("sn_", "sn2_"),
    "p12r3_step_base_e2e.log": ("sn_",),
}

#: 语料规模下限（防止证据文件被误删/样本降级而测试仍绿）
MIN_LOGS = 40
MIN_TOTAL_STEPS = 5000

_STEP_RE = re.compile("^s[0-9]+=-?[0-9]+$")
# 注意：探针名含数字（sn2_/sn3_/mdl2_），字符类必须允许 [0-9]
_ALIVE_RE = re.compile("^([A-Za-z_][A-Za-z_0-9]*)_alive=(True|False)", re.M)


def _parse(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    steps = [ln for ln in lines if _STEP_RE.match(ln)]
    codes = [int(ln.split("=", 1)[1]) for ln in steps]
    alive = {m.group(1): m.group(2) for m in _ALIVE_RE.finditer(text)}
    return {
        "lines": lines,
        "steps": len(steps),
        "err0": sum(1 for c in codes if c == 0),
        "nonzero": sum(1 for c in codes if c != 0),
        "has_end": "end" in lines,
        "alive": alive,
    }


class TestE2EArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logs = sorted(ROOT.glob("p12*_e2e.log"))
        cls.parsed = {p.name: _parse(p) for p in cls.logs}

    def test_corpus_not_silently_shrunk(self):
        """语料规模下限：日志数/总步数不足即失败（防样本降级）。"""
        self.assertGreaterEqual(len(self.logs), MIN_LOGS,
                                f"E2E 日志数 {len(self.logs)} < {MIN_LOGS}")
        total = sum(v["steps"] for v in self.parsed.values())
        self.assertGreaterEqual(total, MIN_TOTAL_STEPS,
                                f"E2E 总步数 {total} < {MIN_TOTAL_STEPS}")

    def test_every_log_completes_unless_registered(self):
        """除已登记截断外，所有日志必须有 end 标记。"""
        bad = [n for n, v in self.parsed.items()
               if not v["has_end"] and n not in KNOWN_TRUNCATED]
        self.assertEqual(bad, [], f"未登记的截断日志: {bad}")

    def test_truncated_registry_is_accurate(self):
        """登记表必须与实况一致：声称截断的确实截断，且都带理由。"""
        for name, reason in KNOWN_TRUNCATED.items():
            self.assertTrue(reason.strip(), f"{name} 缺理由")
            if name in self.parsed:
                self.assertFalse(self.parsed[name]["has_end"],
                                 f"{name} 已含 end，应从 KNOWN_TRUNCATED 移除")

    def test_err_counts_within_policy(self):
        """非零 err 不得超过登记上限（默认 0）。"""
        for name, v in self.parsed.items():
            allowed = ALLOWED_NONZERO.get(name, 0)
            nz = v["nonzero"]
            self.assertLessEqual(nz, allowed,
                                 f"{name}: 非零 err {nz} > 允许 {allowed}")

    def test_required_alive_probes_present(self):
        """关键流程必须出现约定的 alive 探针。"""
        for name, keys in REQUIRED_ALIVE.items():
            if name not in self.parsed:
                continue
            with self.subTest(log=name):
                for k in keys:
                    self.assertIn(k, self.parsed[name]["alive"],
                                  f"{name} 缺 alive 探针 {k}")

    def test_p2_acceptance_evidence_complete(self):
        """R0/P2 验收证据：p2_accept_reopen.log 必须全 err=0 且有 end。"""
        p = ROOT / "p2_accept_reopen.log"
        if not p.is_file():
            self.skipTest("P2 验收日志不在位")
        v = _parse(p)
        self.assertTrue(v["has_end"])
        self.assertEqual(v["nonzero"], 0)
        for k in ("sn_", "mg_", "mdl_", "oct_"):
            self.assertIn(k, v["alive"])
            self.assertEqual(v["alive"][k], "True",
                             f"P2 验收探针 {k} 应为 True（宿主已加载本仓写端产物）")

    def test_hang_ledger_parseable_and_has_outcomes(self):
        """挂起台账必须可解析，且 outcome 至少含 ok/error 两类。"""
        p = ROOT / "hang_characterization.jsonl"
        if not p.is_file():
            self.skipTest("台账不在位")
        rows = [json.loads(ln) for ln in
                p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertGreater(len(rows), 50)
        outcomes = {r.get("outcome") for r in rows}
        self.assertTrue({"ok", "error"} <= outcomes,
                        f"台账 outcome 缺项: {outcomes}")
        for r in rows[:20]:
            self.assertIn("flow", r)
            self.assertIn("elapsed_s", r)


if __name__ == "__main__":
    unittest.main()
