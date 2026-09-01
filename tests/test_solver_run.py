#!/usr/bin/env python3
"""P12-B 求解链路（automation/solver_run）离线回归。

无宿主可跑：VBS 生成、产物收集、等待判定、FPH 场量验证全部离线。
宿主实机验收见 DEV_PLAN §18 Sprint B（求解完成日志 + FLD 场量非空）。
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import scflowpre_api as api  # noqa: E402
from automation import solver_run  # noqa: E402
from automation.history_vbs import decode_vbs  # noqa: E402


class _FakeDispatch:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []

    def _FlagAsMethod(self, *names):
        pass

    def __getattr__(self, name):
        if name.startswith("_") or name not in self.results:
            raise AttributeError(name)

        def _method(*args):
            self.calls.append((name,) + args)
            return self.results[name]

        return _method


class TestTypedSaveSphFile(unittest.TestCase):
    def test_save_sph_file_in_catalog(self):
        import json
        cat = json.loads(
            (ROOT / "schemas" / "vb_api_catalog.json")
            .read_text(encoding="utf-8"))
        m = cat["classes"]["Doc"]["methods"]["SaveSphFile"]
        names = [a["name"] for a in m["arguments"]]
        self.assertEqual(names, ["sphPath", "gphPath"])

    def test_save_sph_file_resolves_paths(self):
        fake = _FakeDispatch({"SaveSphFile": True})
        doc = api.ScFlowpreDoc(fake)
        with tempfile.TemporaryDirectory() as td:
            sph = Path(td) / "a.sph"
            gph = Path(td) / "a.gph"
            self.assertTrue(doc.SaveSphFile(sph, gph))
        (name, sph_arg, gph_arg), = fake.calls
        self.assertEqual(name, "SaveSphFile")
        self.assertTrue(sph_arg.endswith("a.sph"))
        self.assertTrue(gph_arg.endswith("a.gph"))
        self.assertIn(":", sph_arg)  # resolve 成绝对路径


class TestBuildSolveVbs(unittest.TestCase):
    def test_full_chain_order(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vbs = solver_run.build_solve_vbs(
                td / "box.pph", td / "work", td / "work" / "solve_vbs.log")
            text = decode_vbs(vbs.read_bytes())
            for needle in (
                'Doc_.OpenProject', 'Doc_.SetModeMesh',
                'Doc_.SavePolyFile', 'Doc_.SaveSphFile',
                'Doc_.ExecuteSolver',
            ):
                self.assertIn(needle, text)
            self.assertLess(text.index("SavePolyFile"),
                            text.index("SaveSphFile"))
            self.assertLess(text.index("SaveSphFile"),
                            text.index("ExecuteSolver"))
            # SaveSphFile 一行同时携带 sph 与 gph 两个参数
            sph_line = next(l for l in text.splitlines()
                            if "SaveSphFile" in l)
            self.assertIn("scFLOWpre.sph", sph_line)
            self.assertIn("scFLOWpre.gph", sph_line)
            self.assertIn('exec_ret=', text)
            self.assertTrue(text.rstrip().endswith("out_.Close"))

    def test_prep_mode_skips_execute(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vbs = solver_run.build_solve_vbs(
                td / "box.pph", td / "work", td / "work" / "solve_vbs.log",
                execute=False)
            text = decode_vbs(vbs.read_bytes())
            self.assertNotIn("ExecuteSolver", text)
            self.assertIn("SaveSphFile", text)

    def test_paths_forward_slash(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vbs = solver_run.build_solve_vbs(
                td / "box.pph", td / "work", td / "work" / "solve_vbs.log")
            text = decode_vbs(vbs.read_bytes())
            self.assertIn("scFLOWpre.gph", text)
            self.assertIn("scFLOWpre.sph", text)
            self.assertNotIn("\\\\", text)

    def test_quit_after_selects_quit_and_execute_solver(self):
        # P12-B 加固：QuitAndExecuteSolver 变体必须真正切到 catalog
        # 另一入口，并写出 exec_method= 元数据，便于 VBS 日志归因。
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vbs = solver_run.build_solve_vbs(
                td / "box.pph", td / "work", td / "work" / "solve_vbs.log",
                quit_after=True)
            text = decode_vbs(vbs.read_bytes())
            self.assertIn("QuitAndExecuteSolver", text)
            self.assertNotIn("Doc_.ExecuteSolver(", text)
            self.assertIn("exec_method=QuitAndExecuteSolver", text)

    def test_default_execute_writes_exec_method_and_no_quit(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vbs = solver_run.build_solve_vbs(
                td / "box.pph", td / "work", td / "work" / "solve_vbs.log")
            text = decode_vbs(vbs.read_bytes())
            self.assertIn("Doc_.ExecuteSolver(", text)
            self.assertNotIn("QuitAndExecuteSolver", text)
            self.assertIn("exec_method=ExecuteSolver", text)


class TestArtifacts(unittest.TestCase):
    def test_collect_and_classify(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "box_100.fph").write_bytes(b"x")
            (td / "box_200.fph").write_bytes(b"xy")
            (td / "box.rph").write_bytes(b"r")
            (td / "box.log").write_text("log")
            (td / "other.fph").write_bytes(b"z")
            arts = solver_run.find_solver_artifacts("box", dirs=[td])
            self.assertEqual(len(arts["fph"]), 2)
            self.assertEqual(len(arts["logs"]), 1)
            self.assertTrue(all("box" in Path(a["path"]).name
                                for a in arts["artifacts"]))

    def test_empty_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            arts = solver_run.find_solver_artifacts(
                "box", dirs=[Path(td)])
            self.assertEqual(arts["artifacts"], [])

    def test_no_case_falls_back_to_suffix_glob_not_default_box(self):
        # P12-B 加固：find_solver_artifacts(case=None, cases=None) 此前
        # 回退 DEFAULT_CASE="box"，会把与 box 无关的工程（如 car/wing）
        # 结果漏报——现改为按通用后缀全扫。
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "car_100.fph").write_bytes(b"car")
            (td / "wing.rph").write_bytes(b"w")
            (td / "wing_202.l").write_text("L log")
            (td / "other.bin").write_bytes(b"junk")
            arts = solver_run.find_solver_artifacts(dirs=[td])
            paths = {Path(a["path"]).name for a in arts["artifacts"]}
            self.assertIn("car_100.fph", paths)
            self.assertIn("wing.rph", paths)
            self.assertIn("wing_202.l", paths)
            self.assertNotIn("other.bin", paths)
            # 返回的 names 不应硬编码 "box"
            self.assertNotIn("box", arts.get("case", []))

    def test_no_case_empty_names_shape(self):
        # names=[] 时返回的 case 字段为空列表（诊断输出易读）。
        with tempfile.TemporaryDirectory() as td:
            arts = solver_run.find_solver_artifacts(dirs=[td])
            self.assertEqual(arts.get("case"), [])


class TestWaitForSolver(unittest.TestCase):
    def test_solver_seen_then_exits(self):
        seq = iter([[111], [111], []])
        with mock.patch.object(solver_run, "solver_processes",
                               side_effect=lambda: next(seq, [])), \
             mock.patch.object(solver_run, "find_solver_artifacts",
                               return_value={"fph": [], "logs": [],
                                             "artifacts": []}), \
             mock.patch.object(time, "sleep"):
            rep = solver_run.wait_for_solver(timeout=5, poll=0.01)
        self.assertTrue(rep["ok"])
        self.assertTrue(rep["saw_solver"])

    def test_no_solver_no_artifacts_times_out(self):
        with mock.patch.object(solver_run, "solver_processes",
                               return_value=[]), \
             mock.patch.object(solver_run, "find_solver_artifacts",
                               return_value={"fph": [], "logs": [],
                                             "artifacts": []}), \
             mock.patch.object(time, "sleep"):
            rep = solver_run.wait_for_solver(timeout=0.05, poll=0.01)
        self.assertFalse(rep["ok"])
        self.assertTrue(rep.get("timeout"))

    def test_artifact_stable_without_process(self):
        fph = {"path": "/tmp/box_100.fph", "size": 1, "mtime": 1.0}
        with mock.patch.object(solver_run, "solver_processes",
                               return_value=[]), \
             mock.patch.object(solver_run, "find_solver_artifacts",
                               return_value={"fph": [fph], "logs": [],
                                             "artifacts": [fph]}), \
             mock.patch.object(time, "sleep"):
            rep = solver_run.wait_for_solver(timeout=5, poll=0.01)
        self.assertTrue(rep["ok"])
        self.assertFalse(rep["saw_solver"])


class TestVerifyFph(unittest.TestCase):
    def _sample(self, name: str):
        import os
        for root in (os.environ.get("PROGRAMFILES",
                                    r"C:\Program Files"),):
            base = Path(root) / "Cradle"
            for ver in sorted(base.glob("CradleCFD*")) \
                    if base.is_dir() else []:
                p = ver / "Programs_x64" / "Samples_POST" / "FPH" / name
                if p.exists():
                    return p
        return None

    def test_official_sample_fields_nonempty(self):
        p = self._sample("minimumPolyhedral.fph")
        if p is None:
            self.skipTest("Samples_POST/FPH not installed")
        rep = solver_run.verify_fph_file(p)
        self.assertTrue(rep["ok"], rep.get("reason"))
        self.assertGreater(rep["n_cells"], 0)
        self.assertIn("EC_Scalar:PRES", rep["key_fields"])

    def test_garbage_file_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.fph"
            bad.write_bytes(b"not a crdl-fld file at all" * 8)
            rep = solver_run.verify_fph_file(bad)
            self.assertFalse(rep["ok"])


class TestCli(unittest.TestCase):
    def test_build_cli(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            rc = solver_run.main(["build", "--pph", str(td / "box.pph"),
                                  "--work", str(td / "work")])
            self.assertEqual(rc, 0)
            self.assertTrue((td / "work" / "solve_vbs.vbs").exists())

    def test_build_cli_quit_after_flag(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            rc = solver_run.main(
                ["build", "--pph", str(td / "box.pph"), "--work",
                 str(td / "work"), "--quit-after"])
            self.assertEqual(rc, 0)
            vbs = td / "work" / "solve_vbs.vbs"
            self.assertTrue(vbs.exists())
            self.assertIn("QuitAndExecuteSolver",
                          decode_vbs(vbs.read_bytes()))

    def test_verify_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.fph"
            bad.write_bytes(b"junk")
            rc = solver_run.main(["verify", str(bad)])
            self.assertEqual(rc, 1)

    def test_wait_cli_default_case_is_none(self):
        # P12-B 加固：wait --case 不再回退 DEFAULT_CASE="box"，改为无
        # case 时 wait_for_solver 也走 find_solver_artifacts 全扫路径。
        with mock.patch.object(solver_run, "wait_for_solver",
                               return_value={"ok": True}) as m:
            rc = solver_run.main(["wait", "--timeout", "0.05"])
        self.assertEqual(rc, 0)
        _, kwargs = m.call_args
        self.assertIsNone(kwargs.get("case"))


if __name__ == "__main__":
    unittest.main()
