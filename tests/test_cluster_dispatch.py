"""J5 集群派发壳测试——全离线 mock，无真实求解器/SSH。"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import cluster_dispatch as cd


class TestClusterConfig(unittest.TestCase):
    """ClusterConfig 加载与校验。"""

    def test_from_dict_minimal(self):
        cfg = cd.ClusterConfig.from_dict({
            "nodes": [{"name": "n1", "work_dir": "/tmp/w"}]})
        self.assertEqual(len(cfg.nodes), 1)
        self.assertEqual(cfg.nodes[0].name, "n1")
        self.assertEqual(cfg.nodes[0].transport, "local")
        self.assertEqual(cfg.defaults.wait_timeout, 1800.0)

    def test_from_dict_full(self):
        cfg = cd.ClusterConfig.from_dict({
            "nodes": [{"name": "n1", "host": "10.0.0.1", "user": "cfd",
                        "work_dir": "/home/cfd", "transport": "ssh"}],
            "defaults": {"wait_timeout": 7200.0, "sph_name": "custom.sph",
                         "poll_interval": 10.0},
        })
        self.assertEqual(cfg.nodes[0].host, "10.0.0.1")
        self.assertEqual(cfg.nodes[0].user, "cfd")
        self.assertEqual(cfg.nodes[0].transport, "ssh")
        self.assertEqual(cfg.defaults.wait_timeout, 7200.0)

    def test_from_dict_empty_nodes_raises(self):
        with self.assertRaises(ValueError):
            cd.ClusterConfig.from_dict({"nodes": []})

    def test_from_dict_missing_name_raises(self):
        with self.assertRaises(ValueError):
            cd.ClusterConfig.from_dict({"nodes": [{"work_dir": "/tmp"}]})

    def test_from_dict_invalid_transport_raises(self):
        with self.assertRaises(ValueError):
            cd.ClusterConfig.from_dict({
                "nodes": [{"name": "n1", "work_dir": "/tmp",
                           "transport": "rdp"}]})

    def test_from_file_json(self):
        tmp = tempfile.mkdtemp(prefix="_j5_test_")
        try:
            p = Path(tmp) / "cfg.json"
            p.write_text(json.dumps({
                "nodes": [{"name": "local", "work_dir": tmp}]}),
                encoding="utf-8")
            cfg = cd.ClusterConfig.from_file(p)
            self.assertEqual(cfg.nodes[0].name, "local")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_defaults_applied(self):
        cfg = cd.ClusterConfig.from_dict({
            "nodes": [{"name": "n1", "work_dir": "/tmp"}]})
        self.assertEqual(cfg.defaults.sph_name, "scFLOWpre.sph")
        self.assertEqual(cfg.defaults.poll_interval, 5.0)

    def test_to_dict_roundtrip(self):
        data = {"nodes": [{"name": "n1", "host": "h1", "user": None,
                           "work_dir": "/w", "transport": "local"}],
                "defaults": {"wait_timeout": 1800.0,
                             "sph_name": "scFLOWpre.sph",
                             "poll_interval": 5.0}}
        cfg = cd.ClusterConfig.from_dict(data)
        self.assertEqual(cfg.to_dict(), data)


class TestLocalTransport(unittest.TestCase):
    """LocalTransport DI 模式测试。"""

    def _make_node(self):
        return cd.NodeConfig(name="test", work_dir="/tmp/test")

    def test_submit_calls_solve_fn(self):
        fake_solve = mock.Mock(return_value={"ok": True, "vbs_run": {}})
        t = cd.LocalTransport(self._make_node(), solve_fn=fake_solve)
        leg = cd.Leg(tag="b1", pph="/tmp/box.pph",
                     work_dir="/tmp/w", case="box_b1")
        defaults = cd.DefaultsConfig(wait_timeout=600.0)
        job_id = t.submit(leg, defaults)
        self.assertTrue(job_id)
        fake_solve.assert_called_once_with(
            "/tmp/box.pph", "/tmp/w",
            case="box_b1", wait_timeout=600.0,
            sph_name="scFLOWpre.sph")

    def test_submit_returns_job_id(self):
        t = cd.LocalTransport(self._make_node(),
                              solve_fn=mock.Mock(return_value={"ok": True}))
        leg = cd.Leg(tag="b1", pph="/x.pph", work_dir="/w")
        jid = t.submit(leg, cd.DefaultsConfig())
        self.assertEqual(len(jid), 12)

    def test_poll_after_submit(self):
        t = cd.LocalTransport(self._make_node(),
                              solve_fn=mock.Mock(return_value={"ok": True}))
        leg = cd.Leg(tag="b1", pph="/x.pph", work_dir="/w")
        jid = t.submit(leg, cd.DefaultsConfig())
        rep = t.poll(jid)
        self.assertEqual(rep["status"], "done")
        self.assertTrue(rep["result"]["ok"])

    def test_poll_unknown_job_raises(self):
        t = cd.LocalTransport(self._make_node(),
                              solve_fn=mock.Mock())
        with self.assertRaises(KeyError):
            t.poll("nonexistent")

    def test_submit_error_sets_error_status(self):
        t = cd.LocalTransport(self._make_node(),
                              solve_fn=mock.Mock(side_effect=RuntimeError("boom")))
        leg = cd.Leg(tag="b1", pph="/x.pph", work_dir="/w")
        jid = t.submit(leg, cd.DefaultsConfig())
        rep = t.poll(jid)
        self.assertEqual(rep["status"], "error")
        self.assertIn("boom", rep["result"]["error"])

    def test_fetch_artifacts_lists_files(self):
        tmp = tempfile.mkdtemp(prefix="_j5_test_")
        try:
            node = cd.NodeConfig(name="test", work_dir=tmp)
            t = cd.LocalTransport(node,
                                  solve_fn=mock.Mock(return_value={"ok": True}))
            leg = cd.Leg(tag="b1", pph="/x.pph", work_dir=tmp)
            (Path(tmp) / "box.fph").write_text("fph", encoding="utf-8")
            (Path(tmp) / "run.log").write_text("log", encoding="utf-8")
            jid = t.submit(leg, cd.DefaultsConfig())
            arts = t.fetch_artifacts(jid, tmp)
            self.assertTrue(any(p.endswith(".fph") for p in arts))
            self.assertTrue(any(p.endswith(".log") for p in arts))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestSSHTransport(unittest.TestCase):
    """SSHTransport stub 测试。"""

    def _make_node(self):
        return cd.NodeConfig(name="remote", host="10.0.0.1",
                             work_dir="/home/cfd", transport="ssh")

    def test_submit_raises(self):
        t = cd.SSHTransport(self._make_node())
        leg = cd.Leg(tag="b1", pph="/x.pph", work_dir="/w")
        with self.assertRaises(NotImplementedError) as ctx:
            t.submit(leg, cd.DefaultsConfig())
        self.assertIn("9.6-4", str(ctx.exception))

    def test_poll_raises(self):
        t = cd.SSHTransport(self._make_node())
        with self.assertRaises(NotImplementedError):
            t.poll("any")

    def test_fetch_artifacts_raises(self):
        t = cd.SSHTransport(self._make_node())
        with self.assertRaises(NotImplementedError):
            t.fetch_artifacts("any", "/tmp")

    def test_constructor_accepts_config(self):
        t = cd.SSHTransport(self._make_node())
        self.assertEqual(t.node.name, "remote")


class TestDispatcher(unittest.TestCase):
    """Dispatcher 腿分配与派发测试。"""

    def _cfg(self, n_nodes=1):
        nodes = [{"name": f"n{i}", "work_dir": f"/w{i}"}
                 for i in range(n_nodes)]
        return cd.ClusterConfig.from_dict({"nodes": nodes})

    def test_assign_single_node(self):
        cfg = self._cfg(1)
        disp = cd.Dispatcher(cfg, transport_factory=lambda n: mock.Mock())
        legs = [cd.Leg(tag="b1", pph="/a.pph", work_dir="/w"),
                cd.Leg(tag="b2", pph="/b.pph", work_dir="/w")]
        assigned = disp.assign_legs(legs)
        self.assertEqual(len(assigned), 2)
        self.assertTrue(all(node.name == "n0" for _, node in assigned))

    def test_assign_multi_node_round_robin(self):
        cfg = self._cfg(2)
        disp = cd.Dispatcher(cfg, transport_factory=lambda n: mock.Mock())
        legs = [cd.Leg(tag=f"l{i}", pph=f"/{i}.pph", work_dir="/w")
                for i in range(4)]
        assigned = disp.assign_legs(legs)
        names = [node.name for _, node in assigned]
        self.assertEqual(names, ["n0", "n1", "n0", "n1"])

    def test_dispatch_with_mock_transport(self):
        cfg = self._cfg(1)
        mock_transport = mock.Mock()
        mock_transport.submit.return_value = "job123"
        mock_transport.poll.return_value = {
            "status": "done", "result": {"ok": True}}
        disp = cd.Dispatcher(cfg,
                             transport_factory=lambda n: mock_transport)
        legs = [cd.Leg(tag="b1", pph="/a.pph", work_dir="/w")]
        records = disp.dispatch(legs)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, "done")
        self.assertTrue(records[0].result.get("ok"))
        mock_transport.submit.assert_called_once()

    def test_collect_all_gathers_artifacts(self):
        tmp = tempfile.mkdtemp(prefix="_j5_test_")
        try:
            cfg = self._cfg(1)
            mock_transport = mock.Mock()
            mock_transport.submit.return_value = "j1"
            mock_transport.poll.return_value = {
                "status": "done", "result": {"ok": True}}
            mock_transport.fetch_artifacts.return_value = [
                "/tmp/box.fph", "/tmp/run.log"]
            disp = cd.Dispatcher(cfg,
                                 transport_factory=lambda n: mock_transport)
            legs = [cd.Leg(tag="b1", pph="/a.pph", work_dir="/w")]
            records = disp.dispatch(legs)
            summary = disp.collect_all(records, tmp)
            self.assertIn("legs", summary)
            self.assertIn("b1", summary["legs"])
            self.assertTrue((Path(tmp) / "j5_summary.json").is_file())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestBuildLegsFromI5(unittest.TestCase):
    """I5 桥接函数测试。"""

    def test_creates_copies_and_legs(self):
        tmp = tempfile.mkdtemp(prefix="_j5_test_")
        try:
            src = Path(tmp) / "box.pph"
            src.write_text("fake pph", encoding="utf-8")
            work = Path(tmp) / "work"
            legs = cd.build_legs_from_i5(src, work, tags=("b1", "b2"))
            self.assertEqual(len(legs), 2)
            self.assertEqual(legs[0].tag, "b1")
            self.assertEqual(legs[1].tag, "b2")
            self.assertTrue(Path(legs[0].pph).is_file())
            self.assertTrue(Path(legs[1].pph).is_file())
            self.assertEqual(legs[0].case, "box_b1")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_src_raises(self):
        with self.assertRaises(FileNotFoundError):
            cd.build_legs_from_i5("/nonexistent.pph", "/tmp/work")


class TestMakeTransport(unittest.TestCase):
    """传输工厂函数测试。"""

    def test_local(self):
        node = cd.NodeConfig(name="n", work_dir="/w", transport="local")
        t = cd.make_transport(node)
        self.assertIsInstance(t, cd.LocalTransport)

    def test_ssh(self):
        node = cd.NodeConfig(name="n", work_dir="/w", transport="ssh")
        t = cd.make_transport(node)
        self.assertIsInstance(t, cd.SSHTransport)


class TestCli(unittest.TestCase):
    """CLI 子命令测试。"""

    def _write_config(self, tmp: str) -> str:
        p = Path(tmp) / "cfg.json"
        p.write_text(json.dumps({
            "nodes": [{"name": "local", "host": "localhost",
                        "work_dir": tmp, "transport": "local"}],
        }), encoding="utf-8")
        return str(p)

    def test_validate_subcommand(self):
        tmp = tempfile.mkdtemp(prefix="_j5_test_")
        try:
            cfg_path = self._write_config(tmp)
            from tools._p12p_j5_run import main
            rc = main(["validate", "--config", cfg_path])
            self.assertEqual(rc, 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_validate_invalid_config(self):
        tmp = tempfile.mkdtemp(prefix="_j5_test_")
        try:
            bad = Path(tmp) / "bad.json"
            bad.write_text('{"nodes": []}', encoding="utf-8")
            from tools._p12p_j5_run import main
            with self.assertRaises(ValueError):
                main(["validate", "--config", str(bad)])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_run_with_mock_dispatch(self):
        tmp = tempfile.mkdtemp(prefix="_j5_test_")
        try:
            src = Path(tmp) / "box.pph"
            src.write_text("fake", encoding="utf-8")
            work = Path(tmp) / "work"
            fake_solve = mock.Mock(return_value={"ok": True})
            from tools._p12p_j5_run import main
            with mock.patch.object(cd, "make_transport") as mf:
                mock_t = mock.Mock()
                mock_t.submit.return_value = "j1"
                mock_t.poll.return_value = {
                    "status": "done", "result": {"ok": True}}
                mock_t.fetch_artifacts.return_value = []
                mf.return_value = mock_t
                rc = main(["run", "--pph", str(src),
                           "--work", str(work)])
            self.assertEqual(rc, 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
