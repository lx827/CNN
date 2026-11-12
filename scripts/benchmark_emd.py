"""在独立进程中对照正确 emd.sift 参考与原生候选，不宣称生产验收。

根目录 uv run --no-sync python scripts/benchmark_emd.py --output .temp/emd-benchmark
需先显式安装 emd-reference 组；输出数组和报告只能存忽略目录或库外。
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def peak_memory():
    """进程从启动起的 OS 高水位；包含导入、预热、输入与结果生命周期。"""
    if os.name == "nt":

        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ]

        data = Counters()
        data.cb = ctypes.sizeof(data)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_ulong,
        ]
        if not psapi.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(data), data.cb
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return data.PeakWorkingSetSize
    import resource

    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


def make_signal(samples):
    t = np.arange(samples, dtype=np.float64) / samples
    return (
        (1 + 0.2 * np.cos(2 * np.pi * 3 * t)) * np.sin(2 * np.pi * 37 * t)
        + 0.4 * np.sin(2 * np.pi * 9 * t + 0.3)
        + 0.1 * t
    )


def operation(backend, algorithm, x, trials):
    if backend == "reference":
        import emd

        module = emd.sift
        source = Path(emd.__file__).parent
        info = {"version": emd.__version__, "path": str(source)}
    else:
        from cnn_compute import build_info, emd

        module = emd
        info = build_info()
    options = {"max_imfs": 3}
    if algorithm in {"ensemble_sift", "complete_ensemble_sift"}:
        options.update(nensembles=trials, noise_seed=20261112, nprocesses=1)
    elif algorithm == "mask_sift":
        options.update(mask_freqs=[0.12, 0.045, 0.012])
    elif algorithm == "iterated_mask_sift":
        options.update(mask_0=[0.12, 0.045, 0.012], max_iter=3, sample_rate=1.0)
    return lambda: getattr(module, algorithm)(x, **options), info


def worker(args):
    x = make_signal(args.samples)
    call, info = operation(args.backend, args.algorithm, x, args.trials)
    result = call()  # 预热不计入算法耗时。
    timings = []
    for _ in range(args.repeats):
        start = time.perf_counter()
        result = call()
        timings.append(time.perf_counter() - start)
    peak = peak_memory()
    target = Path(args.worker)
    target.parent.mkdir(parents=True, exist_ok=True)
    np.save(target.with_suffix(".npy"), result)
    target.write_text(
        json.dumps(
            {
                "backend": args.backend,
                "algorithm": args.algorithm,
                "seconds": timings,
                "peak_rss_bytes": peak,
                "samples": args.samples,
                "trials": args.trials,
                "shape": list(result.shape),
                "build": info,
                "numpy": np.__version__,
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )


def main(args):
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if output.is_relative_to(ROOT):
        relative = output.relative_to(ROOT).as_posix()
        check = subprocess.run(
            ["git", "check-ignore", relative + "/probe.json"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if check.returncode:
            raise ValueError("输出必须位于 Git 忽略目录或仓库外")
    if any(output.iterdir()):
        raise ValueError("使用新的空输出目录，避免覆盖已完成测量")
    records = {name: {"reference": [], "native": []} for name in args.algorithms}
    for block, order in enumerate(
        (("reference", "native"), ("native", "reference"), ("reference", "native"))
    ):
        for algorithm in args.algorithms:
            for backend in order:
                target = output / f"{algorithm}-{backend}-{block}.json"
                command = [
                    "uv",
                    "run",
                    "--no-sync",
                    "python",
                    str(Path(__file__).resolve()),
                    "--worker",
                    str(target),
                    "--backend",
                    backend,
                    "--algorithm",
                    algorithm,
                    "--samples",
                    str(args.samples),
                    "--trials",
                    str(args.trials),
                    "--repeats",
                    str(args.repeats),
                ]
                env = dict(
                    os.environ,
                    OMP_NUM_THREADS="1",
                    OPENBLAS_NUM_THREADS="1",
                    MKL_NUM_THREADS="1",
                    NUMEXPR_NUM_THREADS="1",
                )
                run = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                if run.returncode:
                    raise RuntimeError(
                        f"{backend}/{algorithm} failed ({run.returncode}):\n{run.stdout}\n{run.stderr}"
                    )
                records[algorithm][backend].append(
                    json.loads(target.read_text("utf-8"))
                )
            a = np.load(output / f"{algorithm}-native-{block}.npy")
            b = np.load(output / f"{algorithm}-reference-{block}.npy")
            scale = max(
                abs(make_signal(args.samples)).max(), abs(b).max(), np.finfo(float).tiny
            )
            np.testing.assert_allclose(
                a / scale,
                b / scale,
                rtol=1e-7,
                atol=1e-9,
            )
            bound = 1e-7 * np.linalg.norm(b / scale) + 1e-9 * np.sqrt(b.size)
            if np.linalg.norm((a - b) / scale) > bound:
                raise AssertionError(f"{algorithm} normalized L2 budget exceeded")
    summary = {}
    for algorithm, values in records.items():
        summary[algorithm] = {}
        for backend, blocks in values.items():
            times = [sample for block in blocks for sample in block["seconds"]]
            summary[algorithm][backend] = {
                "median_seconds": statistics.median(times),
                "p95_seconds": float(np.percentile(times, 95)),
                "max_peak_rss_bytes": max(b["peak_rss_bytes"] for b in blocks),
                "raw_seconds": times,
            }
        summary[algorithm]["speedup"] = (
            summary[algorithm]["reference"]["median_seconds"]
            / summary[algorithm]["native"]["median_seconds"]
        )
    report = {
        "kind": "controlled local comparison; not production ECS acceptance",
        "samples": args.samples,
        "trials": args.trials,
        "boundary": "complete public call includes RNG/layout; OS process high-water includes imports/warmup",
        "summary": summary,
    }
    (output / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=".temp/emd-benchmark")
    parser.add_argument("--samples", type=int, default=1024)
    parser.add_argument("--trials", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--algorithms",
        nargs="+",
        default=[
            "sift",
            "ensemble_sift",
            "complete_ensemble_sift",
            "mask_sift",
            "iterated_mask_sift",
        ],
    )
    parser.add_argument("--worker")
    parser.add_argument("--backend", choices=("reference", "native"))
    parser.add_argument("--algorithm")
    parsed = parser.parse_args()
    worker(parsed) if parsed.worker else main(parsed)
