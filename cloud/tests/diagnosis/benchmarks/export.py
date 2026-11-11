"""在数据根导出小型原始计时/身份/指标；所有生成结果均不提交仓库。"""

import argparse
import csv
import json
from pathlib import Path

from .run import write_json


def export(source: Path, destination: Path):
    campaign = json.loads((source / "results.json").read_text(encoding="utf-8"))
    expected = json.loads((source / "cases.json").read_text(encoding="utf-8"))
    vectors = json.loads((source / "vectors.json").read_text(encoding="utf-8"))
    rows = campaign["cases"]
    checks = []
    for row in rows:
        assert len(row["seconds"]) == campaign["config"]["repeats"]
        assert (
            row["constraints"]["actual_job_limit_bytes"]
            == campaign["config"]["job_commit_limit_bytes"]
        )
        assert row["constraints"]["affinity"] == campaign["config"]["logical_cpus"]
        assert row["repeat_max_absolute_difference"] == 0.0, row["id"]
        metric = row["metrics"]
        for field in ("reconstruction_relative_l2", "fir_reference_relative_l2"):
            if field in metric:
                assert metric[field] < 1e-10, (row["id"], field, metric[field])
        if row["algorithm"] in {"sc", "msb"}:
            assert metric["coherence_max"] <= 1.0 + 1e-12
        if (
            row["algorithm"].startswith("speed_")
            and row["vector"]["dataset_id"] == "synthetic"
        ):
            field = (
                "true_speed_error_hz"
                if row["algorithm"] == "speed_scalar"
                else "true_speed_rmse_hz"
            )
            assert metric["status"] == "valid" and metric[field] < 0.1
        checks.append(row["id"])
    compact = []
    for row in rows:
        compact.append(
            {
                key: (value["id"] if key == "vector" else value)
                for key, value in row.items()
                if key not in {"stdout", "peak_rss_method", "native_thread_environment"}
            }
        )
    vector_rows = [
        {key: value for key, value in vector.items() if key != "file"}
        for vector in vectors
    ]
    payload = {
        "schema_version": 1,
        "environment": campaign["environment"],
        "config": campaign["config"],
        "measurement_notes": {
            "rss": "OS PeakWorkingSetSize over fresh worker imports, warmup, measured calls, metrics, and explicitly separate profiling call",
            "memory_cap": "Windows Job Object total committed bytes 2GiB; host OS and other services outside cap",
            "parallel_activity": "Host not exclusively reserved; other agents prepared code/docs/raw copies; CPU-heavy #78 campaign deferred until this campaign completed",
            "native_threads": "OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1 before worker imports",
            "source_identity": "manifest source SHA256 retained; run checks cached float64 bytes SHA256 per worker; source file SHA check delegated to raw intake verification",
            "convergence": "non-converged and indeterminate results remain measurements, not accepted diagnostic results",
        },
        "vectors": vector_rows,
        "expected_case_count": len(expected),
        "completed_case_count": len(rows),
        "errors": campaign["errors"],
        "validation": {
            "checked_cases": len(checks),
            "repeat_identity": "all reported output arrays equal within a case",
            "numeric_gates": "reconstruction/direct FIR relative L2<1e-10; coherence<=1+1e-12; synthetic speed error<0.1Hz",
        },
        "cases": compact,
    }
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / "20261112-windows-2cpu.json", payload)
    with (destination / "20261112-windows-2cpu.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        fields = [
            "id",
            "vector",
            "algorithm",
            "schedule",
            "samples",
            "fs_hz",
            "median_ms",
            "p95_ms",
            "peak_rss_mib",
            "tasks_per_second",
            "samples_per_second",
            "status",
            "seconds_1",
            "seconds_2",
            "seconds_3",
            "seconds_4",
            "seconds_5",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "id": row["id"],
                    "vector": row["vector"]["id"],
                    "algorithm": row["algorithm"],
                    "schedule": row["schedule"],
                    "samples": row["vector"]["samples"],
                    "fs_hz": row["vector"]["sample_rate_hz"],
                    "median_ms": row["median_seconds"] * 1000,
                    "p95_ms": row["p95_seconds"] * 1000,
                    "peak_rss_mib": row["peak_rss_bytes"] / 2**20,
                    "tasks_per_second": row["tasks_per_second"],
                    "samples_per_second": row["samples_per_second"],
                    "status": row["metrics"]["status"],
                    **{
                        f"seconds_{index}": seconds
                        for index, seconds in enumerate(row["seconds"], 1)
                    },
                }
            )
    print(
        f"Exported {len(rows)}/{len(expected)} cases; {len(campaign['errors'])} worker failures"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, help="default: INPUT/export, outside the repository"
    )
    args = parser.parse_args()
    export(args.input, args.output or args.input / "export")


if __name__ == "__main__":
    main()
