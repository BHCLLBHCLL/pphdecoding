"""P12-J5 集群派发壳 CLI——骨架抽象 + 本地端到端。

DEV_PLAN §21.1 J5 / §9.6-4 部署层豁免：集群作业推送属部署编排层
（sph + 工程件分发 → 多节点 JobLauncher_Bx64.exe/mpiexec → 许可
服务可达），不在双 100% 口径内。本模块定义派发抽象：

- ``ClusterConfig``：JSON 集群配置（nodes + defaults）。
- ``Transport`` 接口 + ``LocalTransport``（包装 solver_run.run_solve）
  + ``SSHTransport``（stub，三方法均 NotImplementedError）。
- ``Dispatcher``：round-robin 腿分配 → dispatch → collect。
- ``build_legs_from_i5``：I5 双跑桥接（复制 .pph 到子目录 → Leg 列表）。

本地传输端到端可用；SSH 传输待集群资源可用时实现三方法即可接入。
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class NodeConfig:
    name: str
    host: str = "localhost"
    user: Optional[str] = None
    work_dir: str = "."
    transport: str = "local"


@dataclass
class DefaultsConfig:
    wait_timeout: float = 1800.0
    sph_name: str = "scFLOWpre.sph"
    poll_interval: float = 5.0


@dataclass
class ClusterConfig:
    nodes: list[NodeConfig]
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)

    @classmethod
    def from_dict(cls, data: dict) -> ClusterConfig:
        raw_nodes = data.get("nodes")
        if not raw_nodes:
            raise ValueError("ClusterConfig: 'nodes' must be a non-empty list")
        nodes = []
        for i, nd in enumerate(raw_nodes):
            if not isinstance(nd, dict):
                raise ValueError(f"nodes[{i}]: expected dict, got {type(nd).__name__}")
            name = nd.get("name")
            if not name:
                raise ValueError(f"nodes[{i}]: missing required field 'name'")
            work_dir = nd.get("work_dir")
            if not work_dir:
                raise ValueError(f"nodes[{i}]: missing required field 'work_dir'")
            transport = nd.get("transport", "local")
            if transport not in ("local", "ssh"):
                raise ValueError(
                    f"nodes[{i}] ({name}): transport must be 'local' or 'ssh', got '{transport}'")
            nodes.append(NodeConfig(
                name=name,
                host=nd.get("host", "localhost"),
                user=nd.get("user"),
                work_dir=work_dir,
                transport=transport,
            ))
        raw_def = data.get("defaults", {})
        defaults = DefaultsConfig(
            wait_timeout=raw_def.get("wait_timeout", 1800.0),
            sph_name=raw_def.get("sph_name", "scFLOWpre.sph"),
            poll_interval=raw_def.get("poll_interval", 5.0),
        )
        return cls(nodes=nodes, defaults=defaults)

    @classmethod
    def from_file(cls, path: str | Path) -> ClusterConfig:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def to_dict(self) -> dict:
        return {
            "nodes": [
                {"name": n.name, "host": n.host, "user": n.user,
                 "work_dir": n.work_dir, "transport": n.transport}
                for n in self.nodes
            ],
            "defaults": {
                "wait_timeout": self.defaults.wait_timeout,
                "sph_name": self.defaults.sph_name,
                "poll_interval": self.defaults.poll_interval,
            },
        }


@dataclass
class Leg:
    tag: str
    pph: str
    work_dir: str
    case: Optional[str] = None


@dataclass
class JobRecord:
    job_id: str
    leg_tag: str
    node_name: str
    status: str = "pending"
    result: dict = field(default_factory=dict)
    artifact_paths: list[str] = field(default_factory=list)


class Transport:
    """Base transport interface. Subclass and override submit/poll/fetch_artifacts."""

    kind: str = "base"

    def __init__(self, node: NodeConfig):
        self.node = node

    def submit(self, leg: Leg, defaults: DefaultsConfig) -> str:
        raise NotImplementedError

    def poll(self, job_id: str) -> dict:
        raise NotImplementedError

    def fetch_artifacts(self, job_id: str, local_dir: str | Path) -> list[str]:
        raise NotImplementedError


class LocalTransport(Transport):
    """Local transport: wraps solver_run.run_solve synchronously."""

    kind = "local"

    def __init__(self, node: NodeConfig, solve_fn=None):
        super().__init__(node)
        self._solve = solve_fn
        self._results: dict[str, dict] = {}
        self._status: dict[str, str] = {}
        self._legs: dict[str, Leg] = {}

    def _ensure_solve(self):
        if self._solve is None:
            from automation import solver_run
            self._solve = solver_run.run_solve

    def submit(self, leg: Leg, defaults: DefaultsConfig) -> str:
        self._ensure_solve()
        job_id = uuid.uuid4().hex[:12]
        self._legs[job_id] = leg
        self._status[job_id] = "running"
        try:
            rep = self._solve(
                leg.pph, leg.work_dir,
                case=leg.case,
                wait_timeout=defaults.wait_timeout,
                sph_name=defaults.sph_name,
            )
            self._results[job_id] = rep
            self._status[job_id] = "done"
        except Exception as exc:
            self._results[job_id] = {"error": str(exc)}
            self._status[job_id] = "error"
        return job_id

    def poll(self, job_id: str) -> dict:
        if job_id not in self._status:
            raise KeyError(f"Unknown job_id: {job_id}")
        return {"status": self._status[job_id], "result": self._results.get(job_id, {})}

    def fetch_artifacts(self, job_id: str, local_dir: str | Path) -> list[str]:
        if job_id not in self._legs:
            raise KeyError(f"Unknown job_id: {job_id}")
        leg = self._legs[job_id]
        work = Path(leg.work_dir)
        if not work.is_dir():
            return []
        patterns = ["*.fph", "*.rph", "*.log", "*.l", "*.fld", "*.ifld"]
        found = []
        for pat in patterns:
            found.extend(str(p) for p in work.glob(pat))
        return sorted(set(found))


class SSHTransport(Transport):
    """SSH transport stub — §9.6-4 部署层豁免，待集群资源可用时实现。"""

    kind = "ssh"

    _MSG = ("SSHTransport: remote cluster dispatch not yet implemented "
            "(§9.6-4 deployment layer exemption)")

    def submit(self, leg: Leg, defaults: DefaultsConfig) -> str:
        raise NotImplementedError(self._MSG)

    def poll(self, job_id: str) -> dict:
        raise NotImplementedError(self._MSG)

    def fetch_artifacts(self, job_id: str, local_dir: str | Path) -> list[str]:
        raise NotImplementedError(self._MSG)


def make_transport(node: NodeConfig) -> Transport:
    if node.transport == "local":
        return LocalTransport(node)
    if node.transport == "ssh":
        return SSHTransport(node)
    raise ValueError(f"Unknown transport kind: {node.transport}")


class Dispatcher:
    """Round-robin leg assignment + dispatch + collect."""

    def __init__(self, config: ClusterConfig, transport_factory=None):
        self.config = config
        factory = transport_factory or make_transport
        self._transports: dict[str, Transport] = {}
        for node in config.nodes:
            self._transports[node.name] = factory(node)

    def assign_legs(self, legs: list[Leg]) -> list[tuple[Leg, NodeConfig]]:
        nodes = self.config.nodes
        if not nodes:
            raise ValueError("No nodes configured")
        return [(leg, nodes[i % len(nodes)]) for i, leg in enumerate(legs)]

    def dispatch(self, legs: list[Leg]) -> list[JobRecord]:
        assignments = self.assign_legs(legs)
        records = []
        for leg, node in assignments:
            transport = self._transports[node.name]
            job_id = transport.submit(leg, self.config.defaults)
            poll_rep = transport.poll(job_id)
            records.append(JobRecord(
                job_id=job_id,
                leg_tag=leg.tag,
                node_name=node.name,
                status=poll_rep["status"],
                result=poll_rep.get("result", {}),
            ))
        return records

    def poll_all(self, records: list[JobRecord]) -> list[dict]:
        results = []
        for rec in records:
            transport = self._transports.get(rec.node_name)
            if transport is None:
                results.append({"job_id": rec.job_id, "error": "unknown node"})
                continue
            results.append({"job_id": rec.job_id, **transport.poll(rec.job_id)})
        return results

    def collect_all(self, records: list[JobRecord],
                    output_dir: str | Path) -> dict:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        legs_summary = {}
        for rec in records:
            transport = self._transports.get(rec.node_name)
            if transport is None:
                legs_summary[rec.leg_tag] = {"error": "unknown node"}
                continue
            leg_dir = output / rec.leg_tag
            leg_dir.mkdir(exist_ok=True)
            paths = transport.fetch_artifacts(rec.job_id, leg_dir)
            rec.artifact_paths = paths
            legs_summary[rec.leg_tag] = {
                "node": rec.node_name,
                "status": rec.status,
                "ok": bool(rec.result.get("ok")),
                "artifacts": paths,
            }
        summary = {"legs": legs_summary, "ok": all(
            v.get("ok") for v in legs_summary.values())}
        (output / "j5_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
        return summary


def build_legs_from_i5(src_pph: str | Path,
                       work_dir: str | Path,
                       tags: tuple[str, ...] = ("b1", "b2")) -> list[Leg]:
    """I5 桥接：复制 .pph 到 per-tag 子目录，返回 Leg 列表。"""
    src = Path(src_pph)
    if not src.is_file():
        raise FileNotFoundError(str(src))
    work = Path(work_dir)
    legs = []
    for tag in tags:
        d = work / tag
        d.mkdir(parents=True, exist_ok=True)
        dst = d / f"{src.stem}_{tag}.pph"
        shutil.copyfile(src, dst)
        legs.append(Leg(tag=tag, pph=str(dst),
                        work_dir=str(d), case=f"{src.stem}_{tag}"))
    return legs
