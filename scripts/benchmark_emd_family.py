"""完整业务 EMD 族的端到端时间/OS 峰值；不改变 #106 冻结筛分测量。

根目录 uv run --no-sync python scripts/benchmark_emd_family.py
每个算法/后端使用独立进程；计时包含参数、输入布局、输出所有权交接，
排除导入/信号构造/预热。Python 与原生随机源不同，不宣称逐成员同迭代。
"""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from benchmark_emd import peak_memory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cloud"))


def worker(args):
    from app.algorithms.decomposition.emd import (
        EMDParameters,
        EnsembleParameters,
        NativeEMDImplementation,
        PythonEMDImplementation,
        decompose_ceemdan,
        decompose_eemd,
        decompose_emd,
    )

    from cnn_compute import build_info, sift_imf

    def legacy_sift(values, parameters):
        options = asdict(parameters)
        options.pop("max_imfs")
        return sift_imf(values, **options)

    implementations = {
        "python": PythonEMDImplementation(),
        "hybrid": PythonEMDImplementation(sift_kernel=legacy_sift),
        "native": NativeEMDImplementation(),
    }
    implementation = implementations[args.backend]
    t = np.arange(args.samples) / args.samples
    signal = (
        (1 + 0.2 * np.cos(2 * np.pi * 3 * t)) * np.sin(2 * np.pi * 137 * t)
        + 0.4 * np.sin(2 * np.pi * 19 * t + 0.3)
        + 0.1 * t
    )
    parameters = EMDParameters(max_imfs=4, max_sifts=50)
    ensemble = EnsembleParameters(
        parameters, ensemble_size=args.members, noise_scale=0.15
    )

    def call():
        if args.method == "emd":
            return decompose_emd(signal, args.samples, parameters, implementation)
        entry = decompose_eemd if args.method == "eemd" else decompose_ceemdan
        return entry(
            signal,
            args.samples,
            seed=20261114,
            parameters=ensemble,
            implementation=implementation,
        )

    result = call()
    np.testing.assert_allclose(result.reconstructed, signal, atol=1e-10)
    samples = []
    for _ in range(args.repeats):
        # 前次输出先释放，峰值包含一次真实结果的持有期。
        del result
        start = time.perf_counter()
        result = call()
        samples.append(time.perf_counter() - start)
    print(
        json.dumps(
            {
                "backend": args.backend,
                "method": args.method,
                "samples": args.samples,
                "members": args.members,
                "seconds": samples,
                "median_seconds": float(np.median(samples)),
                "p95_seconds": float(np.percentile(samples, 95)),
                "peak_mib": peak_memory() / 2**20,
                "mode_count": len(result.imfs),
                "iterations": result.sift_iterations,
                "converged": result.converged,
                "build": build_info(),
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("python", "hybrid", "native"))
    parser.add_argument("--method", choices=("emd", "eemd", "ceemdan"))
    parser.add_argument("--samples", type=int, default=4096)
    parser.add_argument("--members", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.backend:
        worker(args)
        return
    for method in ("emd", "eemd", "ceemdan"):
        for backend in ("python", "hybrid", "native"):
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--backend",
                    backend,
                    "--method",
                    method,
                    "--samples",
                    str(args.samples),
                    "--members",
                    str(args.members),
                    "--repeats",
                    str(args.repeats),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            print(completed.stdout.strip(), flush=True)


if __name__ == "__main__":
    main()
