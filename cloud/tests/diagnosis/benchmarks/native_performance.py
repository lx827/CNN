"""#106 冻结的 EMD 双后端验收；生成材料仅写显式数据根。

在 cloud/ 中以 uv run --no-sync python -m tests.diagnosis.benchmarks.native_performance
调用。prepare/check/measure/profile/report 分阶段运行；正式计时要求所有正确性项通过。
Linux 的新 worker 由 systemd 创建独立受限 scope，不修改生产服务。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CONFIG = HERE / "native_performance_config.json"
THREAD_KEYS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def cases(config):
    return [
        {
            "id": f"{vector['id']}__{profile}__{algorithm}",
            "vector": vector,
            "profile": profile,
            "algorithm": algorithm,
        }
        for vector in config["vectors"]
        for profile in config["profiles"]
        for algorithm in config["algorithms"]
    ]


def text_command(command):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def source_identity():
    # 源码归档在独立 Linux/ECS 目录无 .git；使用归档随附的身份，另核对源码哈希。
    manifest = ROOT / "benchmark_source.json"
    git = (
        read_json(manifest)
        if manifest.exists()
        else {
            "commit": text_command(["git", "-C", str(ROOT), "rev-parse", "HEAD"])[
                "stdout"
            ],
            "dirty": text_command(["git", "-C", str(ROOT), "status", "--porcelain"])[
                "stdout"
            ],
        }
    )
    tracked = [
        CONFIG,
        HERE / "native_emd_contract.json",
        Path(__file__),
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    ]
    for directory in (ROOT / "lib", ROOT / "bind"):
        for pattern in ("*.cpp", "*.hpp", "*.hpp.in", "CMakeLists.txt", "LICENSE.*"):
            tracked += sorted(directory.rglob(pattern))
    tracked += sorted((ROOT / "cloud/app/algorithms").rglob("*.py"))
    tracked += sorted((ROOT / "cnn_compute").glob("*.py"))
    tracked += [
        ROOT / "CMakeLists.txt",
        HERE.parents[0] / "algorithms/emd_reference_contract.py",
    ]
    return {
        "git": git,
        "sha256": {
            path.relative_to(ROOT).as_posix(): digest_file(path) for path in tracked
        },
    }


def measurement_identity():
    """仅读安装元数据/扩展字节，Python 基线不导入原生模块。"""
    distribution = importlib.metadata.distribution("cnn-compute")
    extension = next(
        distribution.locate_file(path)
        for path in distribution.files
        if path.name.startswith("_native.") and path.suffix in (".so", ".pyd")
    )
    return {
        "source_sha256": source_identity()["sha256"],
        "extension_sha256": digest_file(extension),
        "python": platform.python_version(),
        "platform": sys.platform,
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "psutil", "cnn-compute")
        },
    }


def verify_identity(output):
    actual = measurement_identity()
    if actual != read_json(output / "identity.json"):
        raise ValueError(
            "Campaign source/extension/environment identity changed; start a new campaign"
        )
    return actual


def environment():
    import psutil

    from cnn_compute import _native, build_info

    extension = Path(_native.__file__)
    return {
        "platform": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "cpu": platform.processor(),
        "logical_cpus": psutil.cpu_count(),
        "physical_cores": psutil.cpu_count(logical=False),
        "host_memory_bytes": psutil.virtual_memory().total,
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "psutil", "cnn-compute")
        },
        "build_info": build_info(),
        "extension_sha256": digest_file(extension),
        "extension": str(extension),
        "source": source_identity(),
        "linux_cpu": text_command(["lscpu"]) if sys.platform == "linux" else None,
        "thread_environment": {key: os.environ.get(key) for key in THREAD_KEYS},
    }


def prepare(args):
    import shutil

    import numpy as np

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    config = read_json(CONFIG)
    source = read_json(args.source_cache / "vectors.json")
    vectors = []
    for expected in config["vectors"]:
        actual = next(entry for entry in source if entry["id"] == expected["id"])
        for key in expected:
            if actual[key] != expected[key]:
                raise ValueError(
                    f"Frozen vector identity differs: {expected['id']} {key}"
                )
        source_path = args.source_cache / actual["file"].replace("\\", "/")
        relative = f"vectors/{expected['id']}.npy"
        target = output / relative
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source_path, target)
        values = np.load(target, allow_pickle=False)
        if values.dtype != np.float64 or values.shape != (expected["samples"],):
            raise ValueError("Frozen vector dtype/shape mismatch")
        if (
            hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()
            != expected["sha256_float64_le"]
        ):
            raise ValueError("Frozen vector bytes mismatch")
        vectors.append({**actual, "file": relative, "npy_sha256": digest_file(target)})
    write_json(output / "vectors.json", vectors)
    write_json(output / "config.json", config)
    write_json(
        output / "numerical_contract.json", read_json(HERE / "native_emd_contract.json")
    )
    write_json(output / "cases.json", cases(config))
    write_json(
        output / "campaign.json",
        {"mode": args.mode, "prepared_source": source_identity()},
    )
    write_json(output / "environment.json", environment())
    write_json(output / "identity.json", measurement_identity())
    print(
        f"Prepared {len(vectors)} unchanged vectors / {len(cases(config))} cases: {output}"
    )


def load_case(output, case_id):
    import numpy as np

    config = read_json(output / "config.json")
    if config != read_json(CONFIG) or read_json(
        output / "numerical_contract.json"
    ) != read_json(HERE / "native_emd_contract.json"):
        raise ValueError("Frozen configuration or numerical contract changed")
    case = next(row for row in read_json(output / "cases.json") if row["id"] == case_id)
    entry = next(
        row
        for row in read_json(output / "vectors.json")
        if row["id"] == case["vector"]["id"]
    )
    signal = np.load(output / entry["file"], allow_pickle=False)
    if (
        hashlib.sha256(np.asarray(signal, dtype="<f8").tobytes()).hexdigest()
        != entry["sha256_float64_le"]
    ):
        raise ValueError("Frozen input bytes changed")
    prepared = np.ascontiguousarray(signal)
    copied = 0 if np.shares_memory(prepared, signal) else prepared.nbytes
    prepared.flags.writeable = False
    return (
        config,
        case,
        prepared,
        {"input_bytes": prepared.nbytes, "preparation_copy_bytes": copied},
    )


def build_call(config, case, signal, backend):
    from app.algorithms.decomposition.emd import (
        EMDParameters,
        EnsembleParameters,
        PythonEMDImplementation,
        decompose_ceemdan,
        decompose_eemd,
        decompose_emd,
    )

    profile = config["profiles"][case["profile"]]
    parameters = EMDParameters(
        **config["emd"], max_imfs=profile["max_imfs"], max_sifts=profile["max_sifts"]
    )
    implementation = PythonEMDImplementation()
    if backend == "native":
        from app.algorithms.decomposition.emd import NativeEMDImplementation

        implementation = NativeEMDImplementation()
        # 计时排除导入，内存包含真实原生扩展驻留；Python 基线不强制加载该扩展。
        import cnn_compute  # noqa: F401
    fs = case["vector"]["sample_rate_hz"]
    ensemble = EnsembleParameters(
        emd=parameters,
        ensemble_size=profile["ensemble_size"],
        noise_scale=config["noise_scale"],
    )
    if case["algorithm"] == "emd":
        return lambda: decompose_emd(signal, fs, parameters, implementation)
    function = decompose_eemd if case["algorithm"] == "eemd" else decompose_ceemdan
    return lambda: function(
        signal,
        fs,
        seed=config["seed"],
        parameters=ensemble,
        implementation=implementation,
    )


def result_metadata(result):
    return {
        "method": result.method,
        "status": result.status,
        "reason": result.reason,
        "mode_count": len(result.imfs),
        "sift_iterations": result.sift_iterations,
        "converged": result.converged,
        "seed": result.seed,
        "input_length": result.input_length,
        "sample_rate_hz": result.sample_rate_hz,
        "valid_interval": [
            result.valid_interval.start_index,
            result.valid_interval.stop_index,
        ],
    }


def correctness(config, case, signal, artifact):
    import numpy as np
    from app.algorithms.decomposition.selection import compute_component_metrics_batch
    from app.algorithms.pipelines.decomposition import (
        DecompositionDenoisingAnalysis,
        EMDDenoisingPipeline,
        SensitiveComponentEnvelopePipeline,
    )

    from tests.diagnosis.algorithms.emd_reference_contract import assert_result_close

    test = unittest.TestCase()
    results = {}
    for backend in config["backends"]:
        call = build_call(config, case, signal, backend)
        first, repeated = call(), call()
        test.assertEqual(result_metadata(first), result_metadata(repeated))
        for a, b in zip(
            (*first.imfs, first.residual), (*repeated.imfs, repeated.residual)
        ):
            np.testing.assert_array_equal(a, b)
        results[backend] = first
    reference, actual = results["python"], results["native"]
    artifact.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        artifact,
        **{
            f"{backend}_imf_{index}": mode
            for backend, value in results.items()
            for index, mode in enumerate(value.imfs)
        },
        **{f"{backend}_residual": value.residual for backend, value in results.items()},
    )
    quality = {}
    for backend, value in results.items():
        metrics = compute_component_metrics_batch(
            value.imfs, value.sample_rate_hz, signal
        )
        selection = EMDDenoisingPipeline().evaluate(
            DecompositionDenoisingAnalysis(value, metrics, signal)
        )
        sensitive = SensitiveComponentEnvelopePipeline()
        analysis = sensitive.analyze(
            value.imfs, signal, value.sample_rate_hz, decomposition=value
        )
        quality[backend] = {
            "denoising": {
                key: getattr(selection, key)
                for key in ("selected_indices", "status", "quality_status", "reason")
            },
            "sensitive": {
                key: getattr(analysis.selection, key)
                for key in ("selected_indices", "status", "quality_status", "reason")
            },
            "evaluate_status": sensitive.evaluate(analysis).status,
        }
    failure = None
    try:
        assert_result_close(test, actual, reference, signal)
        test.assertEqual(quality["python"], quality["native"])
    except AssertionError as error:
        failure = str(error)
    differences = [
        float(np.max(np.abs(a - b)))
        for a, b in zip(
            (*actual.imfs, actual.residual), (*reference.imfs, reference.residual)
        )
    ]
    return {
        "passed": failure is None,
        "equivalence_pass": failure is None,
        "quality_eligible": all(
            value["sensitive"]["quality_status"] == "accepted"
            for value in quality.values()
        ),
        "diagnosis_evaluable": all(
            value["evaluate_status"] != "indeterminate" for value in quality.values()
        ),
        "failure": failure,
        "metadata": {key: result_metadata(value) for key, value in results.items()},
        "quality": quality,
        "max_absolute_difference": max(differences),
        "same_backend_repeat_exact": True,
        "frozen_array_budget": read_json(HERE / "native_emd_contract.json")[
            "decomposition"
        ],
    }


def linux_group():
    line = next(
        line
        for line in Path("/proc/self/cgroup").read_text().splitlines()
        if line.startswith("0::")
    )
    return Path("/sys/fs/cgroup") / line[3:].lstrip("/")


def constraints(config, mode):
    import psutil

    cpus = config["ecs_logical_cpus"] if mode == "ecs" else config["logical_cpus"]
    if sys.platform == "win32":
        from .run import constrain

        result = constrain(
            {
                "logical_cpus": cpus,
                "job_commit_limit_bytes": config["resources"][
                    "windows_job_commit_limit_bytes"
                ],
            }
        )
        result["kind"] = "Windows Job commit limit; not a physical RAM limit"
        return result
    if sys.platform != "linux":
        raise RuntimeError("Only Windows/Linux measurements are specified")
    process = psutil.Process()
    process.cpu_affinity(cpus)
    group = linux_group()
    maximum = config["resources"][
        "ecs_measurement_memory_max_bytes"
        if mode == "ecs"
        else "wsl_measurement_memory_max_bytes"
    ]
    evidence = {
        name: (group / name).read_text().strip()
        for name in (
            "memory.max",
            "memory.swap.max",
            "cpu.max",
            "cpuset.cpus.effective",
            "memory.events",
        )
    }
    if evidence["memory.max"] != str(maximum) or evidence["memory.swap.max"] != "0":
        raise RuntimeError(f"Incorrect Linux memory/swap limit: {evidence}")
    quota, period = evidence["cpu.max"].split()
    if quota == "max" or int(quota) / int(period) != 2:
        raise RuntimeError("Linux CPUQuota must be two CPU equivalents")
    if process.cpu_affinity() != cpus:
        raise RuntimeError("CPU affinity differs")
    return {
        "kind": "cgroup v2 memory/CPU/swap limit; not whole-machine RAM",
        "affinity": process.cpu_affinity(),
        "cgroup": str(group),
        "readback": evidence,
        "memory_peak_supported": (group / "memory.peak").exists(),
    }


def process_peak_rss():
    if sys.platform == "win32":
        import psutil

        return (
            psutil.Process().memory_info().peak_wset,
            "Windows GetProcessMemoryInfo PeakWorkingSetSize",
        )
    import resource

    return resource.getrusage(
        resource.RUSAGE_SELF
    ).ru_maxrss * 1024, "Linux getrusage(RUSAGE_SELF).ru_maxrss KiB converted to bytes"


def final_cgroup_evidence():
    if sys.platform != "linux":
        return None
    group = linux_group()
    return {
        name: (group / name).read_text().strip() if (group / name).exists() else None
        for name in (
            "memory.current",
            "memory.peak",
            "memory.events",
            "memory.swap.current",
            "cpu.stat",
        )
    }


def measure(config, case, signal, backend):
    import numpy as np
    import psutil

    call = build_call(config, case, signal, backend)
    initial_rss = psutil.Process().memory_info().rss
    for _ in range(config["warmups_per_worker"]):
        result = call()
        del result
    samples = []
    for _ in range(config["samples_per_worker"]):
        started = time.perf_counter()
        result = call()
        samples.append(time.perf_counter() - started)
        # 只保留末次结果；前次结果不与下次分解共存。
        if len(samples) < config["samples_per_worker"]:
            del result
    peak, method = process_peak_rss()
    cgroup = final_cgroup_evidence()
    # 峰值在任何结果指标/数组复制之前读取，profile 位于另一个 worker。
    return {
        "seconds": samples,
        "median_seconds": statistics.median(samples),
        "p95_seconds": float(np.percentile(samples, 95, method="linear")),
        "peak_rss_bytes": peak,
        "peak_rss_method": method,
        "cgroup_after_last_call": cgroup,
        "initial_rss_bytes": initial_rss,
        "peak_increment_bytes_diagnostic_only": max(0, peak - initial_rss),
        "output_payload_bytes": sum(
            array.nbytes for array in (*result.imfs, result.residual)
        ),
        "metadata": result_metadata(result),
    }


def profile(config, case, signal, backend):
    import cProfile
    import pstats

    call = build_call(config, case, signal, backend)
    profiler = cProfile.Profile()
    result = profiler.runcall(call)
    rows = []
    for (filename, line, function), (primitive, total, own, cumulative, _) in sorted(
        pstats.Stats(profiler).stats.items(), key=lambda row: row[1][3], reverse=True
    )[:40]:
        rows.append(
            {
                "file": Path(filename).name,
                "line": line,
                "function": function,
                "primitive_calls": primitive,
                "total_calls": total,
                "self_seconds": own,
                "cumulative_seconds": cumulative,
            }
        )
    return {
        "excluded_from_gates": True,
        "rows": rows,
        "metadata": result_metadata(result),
        "native_visibility": "cProfile sees the binding as a single call; it does not measure individual C++ helpers",
    }


def worker(args):
    identity = verify_identity(args.output)
    config = read_json(args.output / "config.json")
    mode = read_json(args.output / "campaign.json")["mode"]
    resource = constraints(config, mode)
    config, case, signal, preparation = load_case(args.output, args.case)
    if any(os.environ.get(key) != str(config["native_threads"]) for key in THREAD_KEYS):
        raise RuntimeError("Native thread environment must be frozen before imports")
    if args.worker == "check":
        try:
            result = correctness(
                config, case, signal, args.output / "check_arrays" / f"{args.case}.npz"
            )
        except (AssertionError, ValueError, RuntimeError, FloatingPointError):
            import traceback

            result = {
                "passed": False,
                "equivalence_pass": False,
                "quality_eligible": False,
                "failure": traceback.format_exc(),
            }
    elif args.worker == "measure":
        result = measure(config, case, signal, args.backend)
    else:
        result = profile(config, case, signal, args.backend)
    if (
        hashlib.sha256(signal.tobytes()).hexdigest()
        != case["vector"]["sha256_float64_le"]
    ):
        raise AssertionError("Input modified")
    write_json(
        args.result,
        {
            "case": case,
            "backend": args.backend,
            "block": args.block,
            "phase": args.worker,
            "constraints": resource,
            "preparation": preparation,
            "identity": identity,
            **result,
        },
    )


def selected_cases(args):
    selected = read_json(args.output / "cases.json")
    if args.case:
        if read_json(args.output / "campaign.json")["mode"] != "ecs":
            raise ValueError(
                "Windows/WSL campaigns must run the complete frozen matrix"
            )
        selected = [row for row in selected if row["id"] in args.case]
        if set(args.case) != {row["id"] for row in selected}:
            raise ValueError("Unknown ECS case")
    return selected


def start_worker(args, phase, case, backend="both", block=None):
    import psutil

    config = read_json(args.output / "config.json")
    mode = read_json(args.output / "campaign.json")["mode"]
    suffix = f"__{backend}" + (f"__block{block}" if block is not None else "")
    result = args.output / phase / f"{case['id']}{suffix}.json"
    if result.exists():
        existing = read_json(result)
        if existing.get("identity") != read_json(args.output / "identity.json"):
            raise ValueError("Existing worker identity differs")
        return existing
    result.parent.mkdir(parents=True, exist_ok=True)
    marker = result.with_suffix(".started")
    env = {**os.environ, **{key: str(config["native_threads"]) for key in THREAD_KEYS}}
    command = [
        sys.executable,
        "-m",
        "tests.diagnosis.benchmarks.native_performance",
        "--worker",
        phase,
        "--output",
        str(args.output),
        "--case",
        case["id"],
        "--backend",
        backend,
        "--result",
        str(result),
    ]
    if block is not None:
        command += ["--block", str(block)]
    if sys.platform == "linux":
        maximum = config["resources"][
            "ecs_measurement_memory_max_bytes"
            if mode == "ecs"
            else "wsl_measurement_memory_max_bytes"
        ]
        if (
            mode == "ecs"
            and psutil.virtual_memory().available
            < maximum + config["resources"]["ecs_available_margin_bytes"]
        ):
            raise RuntimeError(
                "ECS MemAvailable below frozen worker budget plus reserve; no worker started"
            )
        cpus = config["ecs_logical_cpus"] if mode == "ecs" else config["logical_cpus"]
        unit = f"cnn106-{os.getpid()}-{phase}-{time.time_ns()}"
        # systemd 的独立 transient service 是独立 cgroup；不触碰 CNN.service。
        command = (
            [
                "systemd-run",
                "--quiet",
                "--wait",
                "--pipe",
                "--collect",
                f"--unit={unit}",
                f"--working-directory={Path.cwd()}",
                f"--property=MemoryMax={maximum}",
                "--property=MemorySwapMax=0",
                "--property=CPUQuota=200%",
                f"--property=AllowedCPUs={','.join(map(str, cpus))}",
            ]
            + [
                f"--setenv={key}={value}"
                for key, value in env.items()
                if key in THREAD_KEYS
            ]
            + command
        )
    # 资源检查在开始标记之前；已经开始的项失败后不得选择性重测。
    with marker.open("x", encoding="utf-8") as stream:
        stream.write(time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    print(f"{phase}: {case['id']} {backend} block={block}", flush=True)
    completed = subprocess.run(
        command,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
        check=False,
    )
    result.with_suffix(".stdout.txt").write_text(completed.stdout, encoding="utf-8")
    result.with_suffix(".stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode or not result.exists():
        raise RuntimeError(
            f"Worker failed ({completed.returncode}): {result}; {completed.stderr[-2000:]}"
        )
    return read_json(result)


def host_sample():
    import psutil

    memory, swap = psutil.virtual_memory(), psutil.swap_memory()
    sample = {
        "time_ns": time.time_ns(),
        "mem_total_bytes": memory.total,
        "mem_available_bytes": memory.available,
        "swap_used_bytes": swap.used,
        "cpu_times": psutil.cpu_times()._asdict(),
    }
    if sys.platform == "linux":
        cg = Path("/sys/fs/cgroup/system.slice/CNN.service")
        sample["production_service"] = {
            name: (cg / name).read_text().strip() if (cg / name).exists() else None
            for name in (
                "memory.current",
                "memory.peak",
                "memory.swap.current",
                "memory.events",
                "cpu.stat",
            )
        }
    return sample


def run_phase(args):
    verify_identity(args.output)
    config = read_json(args.output / "config.json")
    selected = selected_cases(args)
    if args.phase != "check":
        eligible = []
        for case in selected:
            path = args.output / "check" / f"{case['id']}__both.json"
            if not path.exists():
                raise RuntimeError(
                    "All selected correctness checks must complete before timing/profile"
                )
            if read_json(path).get("passed"):
                eligible.append(case)
            else:
                print(
                    f"Excluded from performance equivalence: {case['id']} correctness failed",
                    flush=True,
                )
        selected = eligible
    stop = threading.Event()
    samples = []
    mode = read_json(args.output / "campaign.json")["mode"]

    def monitor():
        while not stop.is_set():
            samples.append(host_sample())
            stop.wait(1.0)

    thread = threading.Thread(target=monitor) if mode == "ecs" else None
    if thread:
        thread.start()
    try:
        for case in selected:
            if args.phase == "check":
                start_worker(args, "check", case)
            elif args.phase == "measure":
                for block, order in enumerate(config["block_orders"]):
                    for backend in order:
                        start_worker(args, "measure", case, backend, block)
            else:
                for backend in config["backends"]:
                    start_worker(args, "profile", case, backend)
    finally:
        stop.set()
        if thread:
            thread.join()
            # 取样序列不冒充全机/服务真实峰值；每次阶段执行保存独立记录。
            write_json(
                args.output / "host" / f"{args.phase}-{time.time_ns()}.json",
                {
                    "sampling_interval_seconds": 1,
                    "is_true_peak": False,
                    "samples": samples,
                    "service_state_after": text_command(
                        [
                            "systemctl",
                            "show",
                            "CNN.service",
                            "-p",
                            "ActiveState,SubState,MainPID,MemoryCurrent,ControlGroup",
                        ]
                    ),
                },
            )


def median(values):
    return statistics.median(values)


def aggregate(config, case, rows):
    by_backend = {
        backend: sorted(
            [row for row in rows if row["backend"] == backend],
            key=lambda row: row["block"],
        )
        for backend in config["backends"]
    }
    expected_blocks = list(range(len(config["block_orders"])))
    for group in by_backend.values():
        if [row["block"] for row in group] != expected_blocks or any(
            len(row["seconds"]) != config["samples_per_worker"] for row in group
        ):
            raise ValueError("Incomplete scheduled blocks/samples")
    gates = config["gates"]
    backend_rows = {}
    noisy = []
    for backend, group in by_backend.items():
        samples = [sample for row in group for sample in row["seconds"]]
        middles = [median(row["seconds"]) for row in group]
        deviations = [
            gates["worker_noise_mad_scale"]
            * median([abs(value - median(row["seconds"])) for value in row["seconds"]])
            / median(row["seconds"])
            for row in group
        ]
        spread = (max(middles) - min(middles)) / median(middles)
        if (
            any(value > gates["worker_noise_scaled_mad_max"] for value in deviations)
            or spread > gates["between_blocks_median_range_over_median_max"]
        ):
            noisy.append(backend)
        # 15 点线性百分位，不借用第三方导入以保持分析工具轻量。
        ordered = sorted(samples)
        position = (len(samples) - 1) * 0.95
        lower = int(position)
        p95 = ordered[lower] + (
            ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]
        ) * (position - lower)
        backend_rows[backend] = {
            "seconds": samples,
            "block_medians_seconds": middles,
            "median_seconds": median(samples),
            "p95_seconds": p95,
            "worker_scaled_mad": deviations,
            "block_median_spread": spread,
            "worker_peak_rss_bytes": [row["peak_rss_bytes"] for row in group],
            "peak_rss_bytes": max(row["peak_rss_bytes"] for row in group),
        }
    python, native = backend_rows["python"], backend_rows["native"]
    ratio = native["median_seconds"] / python["median_seconds"]
    limit = (
        gates["emd_eemd_native_over_python_max"]
        if case["algorithm"] in {"emd", "eemd"}
        else gates["production_ceemdan_native_over_python_max"]
        if case["profile"] == "production"
        else None
    )
    time_pass = None if limit is None else ratio <= limit
    memory_pass = native["peak_rss_bytes"] <= python["peak_rss_bytes"]
    return {
        "case": case,
        "backends": backend_rows,
        "native_over_python": ratio,
        "time_limit": limit,
        "time_pass": time_pass,
        "time_gate": "report_only" if limit is None else "required",
        "memory_pass": memory_pass,
        "noisy_backends": noisy,
        "decision": "inconclusive"
        if noisy
        else "pass"
        if time_pass is not False and memory_pass
        else "candidate",
    }


def workspace_notes(config):
    # 这是源文件显式数组的保守线性载荷包络，不是 malloc 跟踪或 RSS。
    # 1024*N 覆盖工作数组/掩码/索引、极值/镜像、查询/求值及系数；256*M
    # 覆盖节点级暂存。std::vector capacity、分配器、Eigen 对齐和 Python 外层另计。
    return {
        "kind": "source-derived explicit buffer payload envelope; not measured native allocations or RSS",
        "per_sift_explicit_buffer_envelope": "1024*N + 256*(N + 2*(mirror_extrema+1)) + 4096 bytes",
        "exclusions": [
            "allocator overhead/capacity slack/alignment",
            "Python outer ensemble retention",
            "NumPy/SciPy imports and internal workspaces",
        ],
        "cpp_input_work_copy": "one N-double work copy per single-IMF sift; current/updated buffers swap each iteration",
        "boundary": "float64 C-contiguous inputs borrow; existing outer loops create contiguous arrays, so no extra contiguous conversion; capsule output exposes native allocation without boundary copy",
        "scope": "budget applies to this PCHIP/SD matrix; cubic DGTSV additionally owns 4*M-2 doubles and remains linear",
        "N": config["vectors"][0]["samples"],
        "example_explicit_buffer_envelope_bytes": 1024 * 4096
        + 256 * (4096 + 2 * (config["emd"]["mirror_extrema"] + 1))
        + 4096,
        "claim": "boundary copy counts follow reviewed source, preparation/output sizes are observed ndarray.nbytes; no total allocation instrumentation",
    }


def validate_worker(row, case, backend, phase, identity, metadata):
    """结果文件数量不能替代特定 case/backend/源码与输出的关联证据。"""
    if (
        row.get("case") != case
        or row.get("backend") != backend
        or row.get("phase") != phase
        or row.get("identity") != identity
        or row.get("metadata") != metadata
    ):
        raise ValueError(f"Mismatched {phase} worker case/backend/identity/metadata")


def report(args):
    identity = verify_identity(args.output)
    config = read_json(args.output / "config.json")
    selected = selected_cases(args)
    complete, incomplete, profiles = [], [], 0
    for case in selected:
        rows = [
            read_json(path)
            for path in sorted((args.output / "measure").glob(f"{case['id']}__*.json"))
        ]
        try:
            check_path = args.output / "check" / f"{case['id']}__both.json"
            if not check_path.exists() or not read_json(check_path).get(
                "equivalence_pass"
            ):
                raise ValueError(
                    "Correctness missing/failed; no performance equivalence conclusion"
                )
            check = read_json(check_path)
            if check.get("identity") != identity or any(
                row.get("identity") != identity for row in rows
            ):
                raise ValueError("Mixed worker/check identity")
            for row in rows:
                validate_worker(
                    row,
                    case,
                    row["backend"],
                    "measure",
                    identity,
                    check["metadata"][row["backend"]],
                )
            for backend in config["backends"]:
                path = args.output / "profile" / f"{case['id']}__{backend}.json"
                if not path.exists():
                    raise ValueError(f"Missing separate profile: {backend}")
                validate_worker(
                    read_json(path),
                    case,
                    backend,
                    "profile",
                    identity,
                    check["metadata"][backend],
                )
                profiles += 1
            complete.append(aggregate(config, case, rows))
        except ValueError as error:
            incomplete.append(
                {"case": case["id"], "reason": str(error), "workers": len(rows)}
            )
    correctness_rows = [
        read_json(args.output / "check" / f"{case['id']}__both.json")
        for case in selected
        if (args.output / "check" / f"{case['id']}__both.json").exists()
    ]
    summary = {
        "config_sha256": digest_file(args.output / "config.json"),
        "environment": read_json(args.output / "environment.json"),
        "campaign": read_json(args.output / "campaign.json"),
        "expected_cases": len(selected),
        "completed_cases": len(complete),
        "incomplete": incomplete,
        "cases": complete,
        "correctness": correctness_rows,
        "profile_workers": profiles,
        "workspace": workspace_notes(config),
        "local_cost_gate": "candidate"
        if incomplete
        or profiles != len(selected) * 2
        or any(row["decision"] != "pass" for row in complete)
        else "pass",
        "adoption": "candidate; overall adoption requires complete Windows + WSL matrices and target ECS build/service-headroom evidence; no production switch",
        "limits": [
            "finite five-sample blocks; P95 descriptive",
            "no dataset effect/diagnosis accuracy claim",
            "Windows/WSL do not establish target ECS service headroom",
        ],
    }
    write_json(args.output / "comparison.json", summary)
    with (args.output / "comparison.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        fields = [
            "case",
            "python_median_s",
            "native_median_s",
            "ratio",
            "python_peak_bytes",
            "native_peak_bytes",
            "time_gate",
            "time_pass",
            "memory_pass",
            "noise",
            "decision",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in complete:
            writer.writerow(
                {
                    "case": row["case"]["id"],
                    "python_median_s": row["backends"]["python"]["median_seconds"],
                    "native_median_s": row["backends"]["native"]["median_seconds"],
                    "ratio": row["native_over_python"],
                    "python_peak_bytes": row["backends"]["python"]["peak_rss_bytes"],
                    "native_peak_bytes": row["backends"]["native"]["peak_rss_bytes"],
                    **{
                        key: row[key]
                        for key in ("time_gate", "time_pass", "memory_pass", "decision")
                    },
                    "noise": ",".join(row["noisy_backends"]),
                }
            )
    lines = [
        "# EMD 原生候选固定矩阵验收",
        "",
        f"采用结论：{summary['adoption']}。完成 {len(complete)}/{len(selected)} 项。",
        "",
        "| 用例 | Python/native ms | native/Python | Python/native peak MiB | 时间/内存/噪声 | 结论 |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in complete:
        p, n = row["backends"]["python"], row["backends"]["native"]
        lines.append(
            f"| {row['case']['id']} | {p['median_seconds'] * 1000:.3f}/{n['median_seconds'] * 1000:.3f} | {row['native_over_python']:.4f} | {p['peak_rss_bytes'] / 2**20:.3f}/{n['peak_rss_bytes'] / 2**20:.3f} | {row['time_pass']}/{row['memory_pass']}/{','.join(row['noisy_backends']) or 'clear'} | {row['decision']} |"
        )
    lines += [
        "",
        "时间门槛只对生产档 CEEMDAN 要求两倍；受控档 CEEMDAN 时间仅报告。噪声项不准入，内存零容差。",
        "profile/正确性独立进程；未切换生产默认。完整原始样本、限制读回、数组规模与口径见 JSON。",
    ]
    (args.output / "comparison.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(
        f"{summary['adoption']}: {len(complete)}/{len(selected)} cases; {profiles} separate profiles"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", nargs="?", choices=("prepare", "check", "measure", "profile", "report")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-cache", type=Path)
    parser.add_argument(
        "--mode",
        choices=("windows", "wsl", "ecs"),
        default="windows" if sys.platform == "win32" else "wsl",
    )
    parser.add_argument("--case", action="append")
    parser.add_argument("--worker", choices=("check", "measure", "profile"))
    parser.add_argument(
        "--backend", choices=("python", "native", "both"), default="both"
    )
    parser.add_argument("--block", type=int)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.worker:
        args.case = args.case[0]
        worker(args)
    elif args.phase == "prepare":
        if not args.source_cache:
            parser.error("prepare requires --source-cache")
        prepare(args)
    elif args.phase == "report":
        report(args)
    elif args.phase:
        run_phase(args)
    else:
        parser.error("phase or --worker required")


if __name__ == "__main__":
    main()
