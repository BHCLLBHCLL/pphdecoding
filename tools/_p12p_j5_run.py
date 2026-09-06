"""P12-J5 集群派发壳 CLI——骨架抽象 + 本地端到端。

DEV_PLAN §21.1 J5 / §9.6-4 部署层豁免。用法：

- ``validate --config CFG``：校验集群配置。
- ``submit --config CFG --pph SRC --work DIR [--legs b1,b2]``：派发腿。
- ``status --config CFG --jobs JSON``：轮询作业状态。
- ``collect --config CFG --jobs JSON --output DIR [--delta]``：收集产物。
- ``run --pph SRC --work DIR [--legs b1,b2] [--delta]``：本地一站式。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import cluster_dispatch


def _load_config(path: str) -> cluster_dispatch.ClusterConfig:
    return cluster_dispatch.ClusterConfig.from_file(path)


def _save_jobs(records: list[cluster_dispatch.JobRecord], path: Path) -> None:
    data = []
    for r in records:
        data.append({
            "job_id": r.job_id, "leg_tag": r.leg_tag,
            "node_name": r.node_name, "status": r.status,
            "result": r.result, "artifact_paths": r.artifact_paths,
        })
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str),
                    encoding="utf-8")


def _load_jobs(path: str) -> list[cluster_dispatch.JobRecord]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    records = []
    for d in data:
        records.append(cluster_dispatch.JobRecord(
            job_id=d["job_id"], leg_tag=d["leg_tag"],
            node_name=d["node_name"], status=d.get("status", "pending"),
            result=d.get("result", {}),
            artifact_paths=d.get("artifact_paths", [])))
    return records


def cmd_validate(args) -> int:
    cfg = _load_config(args.config)
    print(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=1))
    print(f"OK: {len(cfg.nodes)} node(s)")
    return 0


def cmd_submit(args) -> int:
    cfg = _load_config(args.config)
    tags = tuple(t.strip() for t in args.legs.split(","))
    legs = cluster_dispatch.build_legs_from_i5(args.pph, args.work, tags=tags)
    disp = cluster_dispatch.Dispatcher(cfg)
    records = disp.dispatch(legs)
    out = Path(args.work) / "j5_jobs.json"
    _save_jobs(records, out)
    print(json.dumps([{"job_id": r.job_id, "leg": r.leg_tag,
                       "node": r.node_name, "status": r.status,
                       "ok": bool(r.result.get("ok"))}
                      for r in records], ensure_ascii=False, indent=1))
    print(f"Jobs saved to {out}")
    return 0 if all(r.result.get("ok") for r in records) else 1


def cmd_status(args) -> int:
    cfg = _load_config(args.config)
    records = _load_jobs(args.jobs)
    disp = cluster_dispatch.Dispatcher(cfg)
    statuses = disp.poll_all(records)
    print(json.dumps(statuses, ensure_ascii=False, indent=1, default=str))
    return 0


def cmd_collect(args) -> int:
    cfg = _load_config(args.config)
    records = _load_jobs(args.jobs)
    disp = cluster_dispatch.Dispatcher(cfg)
    summary = disp.collect_all(records, args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    if args.delta:
        _try_delta(records, args.output)
    return 0 if summary.get("ok") else 1


def _try_delta(records: list[cluster_dispatch.JobRecord],
               output_dir: str) -> None:
    fph_paths = []
    for rec in records:
        for p in rec.artifact_paths:
            if p.endswith(".fph"):
                fph_paths.append(p)
                break
    if len(fph_paths) >= 2:
        import solver_delta
        rep = solver_delta.compare_fph(fph_paths[0], fph_paths[1])
        md = solver_delta.delta_table_markdown(
            rep, title="J5 cluster dispatch FPH delta")
        out = Path(output_dir)
        (out / "delta_table.md").write_text(md, encoding="utf-8")
        (out / "delta_table.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
        print(f"Delta table: {out / 'delta_table.md'}")


def cmd_run(args) -> int:
    tags = tuple(t.strip() for t in args.legs.split(","))
    legs = cluster_dispatch.build_legs_from_i5(args.pph, args.work, tags=tags)
    if args.config:
        cfg = _load_config(args.config)
    else:
        cfg = cluster_dispatch.ClusterConfig.from_dict({
            "nodes": [{"name": "local", "host": "localhost",
                        "work_dir": args.work, "transport": "local"}],
        })
    disp = cluster_dispatch.Dispatcher(cfg)
    records = disp.dispatch(legs)
    summary = disp.collect_all(records, Path(args.work) / "output")
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    if args.delta:
        _try_delta(records, str(Path(args.work) / "output"))
    return 0 if summary.get("ok") else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="J5 集群派发壳 CLI（§9.6-4 部署层豁免骨架）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="校验集群配置")
    p_val.add_argument("--config", required=True, help="集群 JSON 配置")

    p_sub = sub.add_parser("submit", help="派发腿到集群节点")
    p_sub.add_argument("--config", required=True)
    p_sub.add_argument("--pph", required=True, help="源 .pph 文件")
    p_sub.add_argument("--work", required=True, help="基础工作目录")
    p_sub.add_argument("--legs", default="b1,b2", help="腿标签（逗号分隔）")

    p_st = sub.add_parser("status", help="轮询作业状态")
    p_st.add_argument("--config", required=True)
    p_st.add_argument("--jobs", required=True, help="j5_jobs.json 路径")

    p_col = sub.add_parser("collect", help="收集产物")
    p_col.add_argument("--config", required=True)
    p_col.add_argument("--jobs", required=True)
    p_col.add_argument("--output", required=True, help="产物输出目录")
    p_col.add_argument("--delta", action="store_true",
                       help="收集后自动跑 FPH delta")

    p_run = sub.add_parser("run", help="本地一站式（派发+收集）")
    p_run.add_argument("--pph", required=True)
    p_run.add_argument("--work", required=True)
    p_run.add_argument("--config", default=None, help="可选集群配置")
    p_run.add_argument("--legs", default="b1,b2")
    p_run.add_argument("--delta", action="store_true")

    args = ap.parse_args(argv)
    dispatch = {
        "validate": cmd_validate, "submit": cmd_submit,
        "status": cmd_status, "collect": cmd_collect, "run": cmd_run,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
