"""固定向量、隔离进程与操作系统内存峰值的离线基准。

cloud/ 中运行：uv run --group benchmark python -m tests.diagnosis.benchmarks.run
--data-root /path/to/data。输入 I/O、预热和结果汇总不计入算法计时。
每个 case 新建进程，Windows Job Object 约束整个 worker 的提交内存，
RSS 使用 Windows PeakWorkingSetSize；不拿轮询 RSS 冒充真实峰值。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import ctypes
import hashlib
import importlib.metadata
import io
import json
import math
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOB_HANDLE = None


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def constrain(config):
    """约束实际被测进程；不以模拟内存账代替操作系统限制。"""
    import psutil

    process = psutil.Process()
    process.cpu_affinity(config["logical_cpus"])
    evidence = {
        "affinity": process.cpu_affinity(),
        "memory_limit_bytes": config["job_commit_limit_bytes"],
    }
    if sys.platform != "win32":
        raise RuntimeError(
            "This campaign requires Windows Job Object evidence; use a separately documented Linux cgroup campaign"
        )
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IOCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint64)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits),
            ("IoInfo", IOCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    global JOB_HANDLE
    JOB_HANDLE = kernel.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    # JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    limits.BasicLimitInformation.LimitFlags = 0x200 | 0x2000
    limits.JobMemoryLimit = config["job_commit_limit_bytes"]
    if not JOB_HANDLE or not kernel.SetInformationJobObject(
        JOB_HANDLE, 9, ctypes.byref(limits), ctypes.sizeof(limits)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.AssignProcessToJobObject(JOB_HANDLE, kernel.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())
    actual = ExtendedLimits()
    kernel.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    if not kernel.QueryInformationJobObject(
        JOB_HANDLE, 9, ctypes.byref(actual), ctypes.sizeof(actual), None
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    evidence.update(
        memory_limit_kind="Windows Job Object total committed bytes; not whole-machine RAM",
        actual_job_limit_bytes=actual.JobMemoryLimit,
    )
    return evidence


def prepare(data_root, output, config):
    """原记录只加载一次；生成有 SHA256 的独立短窗/长窗，算法计时不含 I/O。"""
    import numpy as np
    from scipy.signal import resample_poly

    from tests.diagnosis.real_data.bearing import load_record as bearing_record
    from tests.diagnosis.real_data.common import load_manifest
    from tests.diagnosis.real_data.gear import load_record as gear_record

    manifest_dir = HERE.parent / "real_data" / "manifests"
    entries = {
        entry["sample_id"]: entry
        for name in ("bearing", "gear")
        for entry in load_manifest(manifest_dir / f"{name}.json")
    }
    vectors = []

    def save(vector_id, values, fs, source):
        values = np.ascontiguousarray(values, dtype="<f8")
        path = output / "vectors" / f"{vector_id}.npy"
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, values, allow_pickle=False)
        vectors.append(
            {
                "id": vector_id,
                "file": str(path.relative_to(output)),
                "sample_rate_hz": fs,
                "samples": len(values),
                "duration_seconds": len(values) / fs,
                "sha256_float64_le": hashlib.sha256(values.tobytes()).hexdigest(),
                **source,
            }
        )

    for sample_id in config["sample_ids"]:
        entry = entries[sample_id]
        entry = {
            **entry,
            "_window": {
                "duration_seconds": max(config["window_seconds"]),
                "start_seconds": 0,
            },
        }
        reader = (
            bearing_record
            if entry["dataset_id"] in {"ottawa_bearing", "hust_bearing"}
            else gear_record
        )
        record = reader(entry, data_root)
        channel = next(iter(record.vibration))
        values = record.vibration[channel]
        fs = record.sample_rate_hz
        source = {
            "sample_id": sample_id,
            "dataset_id": entry["dataset_id"],
            "channel": channel,
            "source_path": entry["source_path"],
            "source_sha256": entry["sha256"],
            "unit": "source vibration unit unknown",
            "start_sample": 0,
            "true_speed_hz": None,
            "source_file_sha256_verified_by_this_run": False,
        }
        save(
            f"{sample_id}__short",
            values[: config["decomposition_samples"]],
            fs,
            {**source, "window_policy": "explicit first 4096 native samples"},
        )
        for seconds in config["window_seconds"]:
            count = min(round(fs * seconds), len(values))
            save(
                f"{sample_id}__{seconds}s",
                values[:count],
                fs,
                {
                    **source,
                    "requested_duration_seconds": seconds,
                    "window_policy": "native fs; limited to reader continuous block",
                },
            )
        derived_fs = config["derived_sample_rate_hz"]
        divisor = math.gcd(int(fs), derived_fs)
        derived = resample_poly(
            values[: round(fs)], derived_fs // divisor, int(fs) // divisor
        )
        save(
            f"{sample_id}__derived",
            derived,
            derived_fs,
            {
                **source,
                "native_sample_rate_hz": fs,
                "window_policy": "first 1 native second then scipy resample_poly; no algorithm truncation",
            },
        )

    fs = 8192
    rng = np.random.default_rng(config["seed"])
    t = np.arange(fs * 5) / fs
    # 30 Hz 基频、90 Hz 谐波与100 Hz调制载波；速度仅此合成向量有真值。
    values = (
        np.sin(2 * np.pi * 30 * t)
        + 0.35 * np.sin(2 * np.pi * 90 * t)
        + 0.4 * (1 + 0.7 * np.cos(2 * np.pi * 100 * t)) * np.sin(2 * np.pi * 1000 * t)
        + 0.03 * rng.standard_normal(len(t))
    )
    source = {
        "sample_id": "synthetic",
        "dataset_id": "synthetic",
        "channel": "vibration",
        "unit": "arbitrary amplitude",
        "true_speed_hz": 30.0,
        "seed": config["seed"],
        "start_sample": 0,
    }
    save("synthetic__short", values[: config["decomposition_samples"]], fs, source)
    for seconds in config["window_seconds"]:
        save(f"synthetic__{seconds}s", values[: fs * seconds], fs, source)
    write_json(output / "vectors.json", vectors)
    return vectors


def cases_for(vectors):
    cases = []
    for vector in vectors:
        short = vector["id"].endswith("__short")
        algorithms = (
            [
                "emd",
                "eemd",
                "ceemdan",
                "pyemd_emd",
                "pyemd_eemd",
                "pyemd_ceemdan",
                "vmd",
                "med",
                "mckd",
                "decomposition_pipeline",
            ]
            if short
            else ["speed_scalar", "speed_ridge", "sc", "msb", "standard_pipeline"]
        )
        for algorithm in algorithms:
            cases.append(
                {
                    "id": f"{vector['id']}__{algorithm}",
                    "vector": vector["id"],
                    "algorithm": algorithm,
                    "schedule": "single",
                }
            )
    for algorithm in (
        "emd",
        "eemd",
        "ceemdan",
        "pyemd_emd",
        "pyemd_eemd",
        "pyemd_ceemdan",
    ):
        cases.append(
            {
                "id": f"synthetic__production__{algorithm}",
                "vector": "synthetic__short",
                "algorithm": algorithm,
                "schedule": "single",
                "profile": "production",
            }
        )
    cases.append(
        {
            "id": "synthetic__5s__configured_standard_pipeline",
            "vector": "synthetic__5s",
            "algorithm": "standard_pipeline",
            "schedule": "single",
            "physical_parameters": True,
        }
    )
    # 两任务实验：同一向量、同一函数、同一2逻辑CPU/2GiB Job。
    for algorithm, vector_id in (
        ("med", "hust_I_20Hz__short"),
        ("sc", "ottawa_I-A-1__5s"),
        ("standard_pipeline", "ottawa_I-A-1__5s"),
    ):
        for schedule in ("serial_pair", "threads2", "threads2_sem1"):
            cases.append(
                {
                    "id": f"concurrency__{algorithm}__{schedule}",
                    "vector": vector_id,
                    "algorithm": algorithm,
                    "schedule": schedule,
                }
            )
    return cases


def build_call(case, vector, signal, config):
    from app.algorithms.bearing.cyclostationary import compute_sc_scoh
    from app.algorithms.bearing.deconvolution import (
        MCKDParameters,
        MEDParameters,
        maximum_correlated_kurtosis_deconvolution,
        minimum_entropy_deconvolution,
    )
    from app.algorithms.composite.msb import (
        MSBParameters,
        compute_modulation_bispectrum,
    )
    from app.algorithms.decomposition.emd import (
        EMDParameters,
        EnsembleParameters,
        decompose_ceemdan,
        decompose_eemd,
        decompose_emd,
    )
    from app.algorithms.decomposition.vmd import VMDParameters, decompose_vmd
    from app.algorithms.order.estimation import (
        estimate_spectrum_speed,
        estimate_stft_speed_trajectory,
    )
    from app.algorithms.pipelines.decomposition import (
        EMDDenoisingPipeline,
        SensitiveComponentEnvelopePipeline,
    )
    from app.services.diagnosis.engine import DiagnosisEngine

    name, fs = case["algorithm"], vector["sample_rate_hz"]
    emd_values, ensemble_values = config["emd"], config["ensemble"]
    if case.get("profile") == "production":
        emd_values = {**emd_values, "max_imfs": 8, "max_sifts": 100}
        ensemble_values = {**ensemble_values, "ensemble_size": 50}
    emd = EMDParameters(**emd_values)
    ensemble = EnsembleParameters(emd=emd, **ensemble_values)
    params = {"emd": emd_values, "ensemble": ensemble_values, "seed": config["seed"]}
    if name.startswith("pyemd_"):
        from .pyemd_adapter import decompose

        return lambda: decompose(
            signal,
            fs,
            name.removeprefix("pyemd_"),
            emd_values,
            ensemble_values,
            config["seed"],
        ), params
    if name == "emd":
        return lambda: decompose_emd(signal, fs, emd), params
    if name in {"eemd", "ceemdan"}:
        function = decompose_eemd if name == "eemd" else decompose_ceemdan
        return lambda: function(
            signal, fs, seed=config["seed"], parameters=ensemble
        ), params
    if name == "vmd":
        return lambda: decompose_vmd(
            signal, fs, VMDParameters(**config["vmd"])
        ), config["vmd"]
    if name == "med":
        return lambda: minimum_entropy_deconvolution(
            signal, MEDParameters(**config["med"])
        ), config["med"]
    if name == "mckd":
        # 真实信号仅测试指定40点周期的数值核；不是赋予其BPFO物理真值。
        return lambda: maximum_correlated_kurtosis_deconvolution(
            signal, config["mckd"]["period_samples"], MCKDParameters(**config["mckd"])
        ), config["mckd"]
    if name == "speed_scalar":
        return lambda: estimate_spectrum_speed(signal, fs), {
            "search_hz": [10, 100],
            "harmonics_num": 5,
            "bandwidth_hz": 3,
            "smooth_win_hz": 1.5,
        }
    if name == "speed_ridge":
        return lambda: estimate_stft_speed_trajectory(signal, fs), {
            "search_hz": [10, 100],
            "ridge_parameters": "source defaults at recorded git revision",
        }
    if name == "sc":
        return lambda: compute_sc_scoh(signal, fs, **config["sc"]), config["sc"]
    if name == "msb":
        values = config["msb"]
        return lambda: compute_modulation_bispectrum(
            signal,
            fs,
            values["carrier_frequency_hz"],
            values["modulation_frequency_hz"],
            MSBParameters(
                **{
                    key: values[key]
                    for key in ("segment_length", "overlap", "minimum_segments")
                }
            ),
        ), values
    if name == "decomposition_pipeline":
        pipeline = EMDDenoisingPipeline(emd, ensemble)
        sensitive = SensitiveComponentEnvelopePipeline()

        def full_decomposition():
            analysis = pipeline.analyze(
                signal, fs, method="ceemdan", seed=config["seed"]
            )
            # 此路径分解一次，复用其IMF与质量状态；未知几何/速度保留不可判定。
            return sensitive.run(
                analysis.decomposition.imfs,
                signal,
                fs,
                decomposition=analysis.decomposition,
            )

        return full_decomposition, {
            **params,
            "top_n": 1,
            "geometry": None,
            "rot_frequency_hz": None,
        }
    if name == "standard_pipeline":
        bearing_params = (
            {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0.0}
            if case.get("physical_parameters")
            else {}
        )
        gear_teeth = (
            {"input": 18, "output": 27} if case.get("physical_parameters") else {}
        )
        engine = DiagnosisEngine(bearing_params=bearing_params, gear_teeth=gear_teeth)
        return lambda: engine.analyze_comprehensive(
            signal, fs, rot_freq=vector["true_speed_hz"]
        ), {
            "strategy": "standard",
            "denoise_method": "none",
            "bearing_params": bearing_params,
            "gear_teeth": gear_teeth,
            "rot_freq": vector["true_speed_hz"],
        }
    raise ValueError(name)


def summarize(value, algorithm, signal, vector):
    """指标不在计时范围内；重构误差只验完备性，不声称 IMF 唯一或诊断正确。"""
    import numpy as np
    from scipy.stats import kurtosis

    fs = vector["sample_rate_hz"]
    norm = max(float(np.linalg.norm(signal)), np.finfo(float).tiny)
    if algorithm in {"emd", "eemd", "ceemdan", "vmd"} or algorithm.startswith("pyemd_"):
        if algorithm.startswith("pyemd_"):
            modes, residual = value.components, value.residual
            metrics = {"status": "computed", "converged": None, **value.metadata}
        elif algorithm == "vmd":
            modes, residual = value.modes, value.residual
            metrics = {
                "status": value.status,
                "converged": value.converged,
                "iterations": value.iterations,
                "reason": value.reason,
                "center_frequencies_hz": value.center_frequencies_hz.tolist(),
            }
        else:
            modes, residual = np.array(value.imfs), value.residual
            metrics = {
                "status": value.status,
                "converged": list(value.converged),
                "sift_iterations": list(value.sift_iterations),
                "reason": value.reason,
            }
        modes = np.reshape(modes, (-1, len(signal)))
        aggregate = np.sum(modes, axis=0)
        metrics.update(
            reconstruction_relative_l2=float(
                np.linalg.norm(aggregate + residual - signal) / norm
            ),
            residual_relative_l2=float(np.linalg.norm(residual) / norm),
            mode_count=len(modes),
            component_energy_input_ratio=float(np.sum(modes**2) / norm**2),
            component_dominant_frequency_hz=[
                float(
                    np.fft.rfftfreq(len(signal), 1 / fs)[
                        np.argmax(np.abs(np.fft.rfft(mode)))
                    ]
                )
                for mode in modes
            ],
            max_component_kurtosis_pearson=float(
                max((kurtosis(mode, fisher=False) for mode in modes), default=0)
            ),
        )
        return np.concatenate([modes.ravel(), residual]), metrics
    if algorithm in {"med", "mckd"}:
        reference = np.convolve(
            signal - np.mean(signal), value.filter_coefficients[::-1], mode="same"
        )
        return value.signal, {
            "status": "computed",
            "converged": value.converged,
            "iterations": value.iterations,
            "objective_history": list(value.objective_history),
            "fir_reference_relative_l2": float(
                np.linalg.norm(value.signal - reference)
                / max(np.linalg.norm(reference), np.finfo(float).tiny)
            ),
        }
    if algorithm == "speed_scalar":
        frequency = value.frequency_hz
        return np.array([frequency or 0]), {
            "status": value.status,
            "reason": value.reason,
            "frequency_hz": frequency,
            "true_speed_error_hz": None
            if frequency is None or vector["true_speed_hz"] is None
            else abs(frequency - vector["true_speed_hz"]),
        }
    if algorithm == "speed_ridge":
        track = value.trajectory
        return (track.frequency_hz if track is not None else np.array([])), {
            "status": value.status,
            "reason": value.reason,
            "reliable_frame_count": value.reliable_frame_count,
            "total_frame_count": value.total_frame_count,
            "true_speed_rmse_hz": None
            if track is None or vector["true_speed_hz"] is None
            else float(
                np.sqrt(np.mean((track.frequency_hz - vector["true_speed_hz"]) ** 2))
            ),
        }
    if algorithm == "sc":
        coherence = value.spectral_coherence
        return np.r_[value.spectral_correlation.ravel(), coherence.ravel()], {
            "status": "computed",
            "segment_count": value.segment_count,
            "coherence_min": float(np.min(coherence)),
            "coherence_max": float(np.max(coherence)),
            "cyclic_resolution_hz": value.cyclic_resolution_hz,
        }
    if algorithm == "msb":
        return value.complex_mean[value.valid], {
            "status": "computed",
            "segments": value.segments,
            "valid_cells": int(np.count_nonzero(value.valid)),
            "coherence_max": float(np.nanmax(value.coherence)),
            "frequency_resolution_hz": value.frequency_resolution_hz,
        }
    if algorithm == "decomposition_pipeline":
        analysis, evaluation = value
        spectrum = (
            analysis.spectrum.amplitude
            if analysis.spectrum is not None
            else np.array([])
        )
        return spectrum, {
            "status": evaluation.status,
            "selection_status": analysis.selection.status,
            "quality_status": analysis.selection.quality_status,
            "reason": analysis.selection.reason,
            "selected_indices": list(analysis.selection.selected_indices),
        }
    # 业务结果只提取稳定数值摘要，避免把大型返回JSON序列化计入算法耗时。
    numeric = [
        float(v)
        for v in value["time_features"].values()
        if isinstance(v, (int, float)) and np.isfinite(v)
    ]
    return np.array(numeric), {
        "status": value.get("evaluation_status"),
        "conclusion": value.get("diagnosis_conclusion"),
        "rot_freq_hz": value.get("rot_freq_hz"),
        "bearing_status": value.get("bearing", {}).get("evaluation_status"),
        "gear_status": value.get("gear", {}).get("evaluation_status"),
        "reason": value.get("reason"),
        "bearing_reason": value.get("bearing", {}).get("reason"),
        "gear_reason": value.get("gear", {}).get("reason"),
        "coverage": value.get("coverage"),
    }


def worker(output, case_id):
    config = json.loads((output / "config.json").read_text(encoding="utf-8"))
    constraints = constrain(config)
    import numpy as np
    import psutil

    case = next(
        row
        for row in json.loads((output / "cases.json").read_text(encoding="utf-8"))
        if row["id"] == case_id
    )
    vector = next(
        row
        for row in json.loads((output / "vectors.json").read_text(encoding="utf-8"))
        if row["id"] == case["vector"]
    )
    signal = np.load(output / vector["file"], allow_pickle=False)
    actual_hash = hashlib.sha256(signal.tobytes()).hexdigest()
    if actual_hash != vector["sha256_float64_le"]:
        raise ValueError("Benchmark vector hash mismatch")
    call, parameters = build_call(case, vector, signal, config)
    process = psutil.Process()
    initial_rss = process.memory_info().rss
    semaphore = threading.Semaphore(1)
    executor = (
        concurrent.futures.ThreadPoolExecutor(max_workers=2)
        if case["schedule"].startswith("threads")
        else None
    )

    def one_call():
        if case["schedule"] == "threads2_sem1":
            with semaphore:
                return call()
        return call()

    def iteration():
        if executor is not None:
            pending = [executor.submit(one_call) for _ in range(2)]
            return [future.result() for future in pending]
        return [call() for _ in range(2 if case["schedule"] == "serial_pair" else 1)]

    warnings = io.StringIO()
    durations, differences, metrics = [], [], []
    with contextlib.redirect_stdout(warnings):
        for _ in range(config["warmups"]):
            iteration()
        reference = None
        for _ in range(config["repeats"]):
            started = time.perf_counter()
            values = iteration()
            durations.append(time.perf_counter() - started)
            for value in values:
                array, metric = summarize(value, case["algorithm"], signal, vector)
                if reference is None:
                    reference = array.copy()
                differences.append(
                    float(np.max(np.abs(array - reference))) if len(array) else 0.0
                )
                metrics.append(metric)
            del values
    if executor is not None:
        executor.shutdown()
    profile_rows = []
    if case_id in {
        "synthetic__production__ceemdan",
        "hust_I_20Hz__short__med",
        "hust_I_20Hz__short__mckd",
        "ottawa_I-A-1__5s__sc",
        "ottawa_I-A-1__5s__msb",
        "ottawa_I-A-1__5s__standard_pipeline",
        "synthetic__short__vmd",
    }:
        import cProfile
        import pstats

        profiler = cProfile.Profile()
        profiler.runcall(call)
        stats = pstats.Stats(profiler)
        for (filename, line, function), (
            primitive_calls,
            total_calls,
            self_s,
            cumulative_s,
            callers,
        ) in sorted(stats.stats.items(), key=lambda pair: pair[1][3], reverse=True)[
            :30
        ]:
            # 文件名去掉机器目录；保留函数和调用次数用于热点归因。
            profile_rows.append(
                {
                    "file": Path(filename).name,
                    "line": line,
                    "function": function,
                    "primitive_calls": primitive_calls,
                    "total_calls": total_calls,
                    "self_seconds": self_s,
                    "cumulative_seconds": cumulative_s,
                }
            )
    memory = process.memory_info()
    tasks = 1 if case["schedule"] == "single" else 2
    median = float(np.median(durations))
    result = {
        **case,
        "parameters": parameters,
        "vector": vector,
        "constraints": constraints,
        "native_thread_environment": {
            key: os.environ[key]
            for key in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
        "warmups": config["warmups"],
        "repeats": config["repeats"],
        "tasks_per_iteration": tasks,
        "seconds": durations,
        "median_seconds": median,
        "p95_seconds": float(np.percentile(durations, 95, method="linear")),
        "tasks_per_second": tasks / median,
        "samples_per_second": len(signal) * tasks / median,
        "initial_rss_bytes": initial_rss,
        "peak_rss_bytes": memory.peak_wset,
        "peak_rss_method": "Windows GetProcessMemoryInfo PeakWorkingSetSize; entire fresh worker lifetime including imports/warmup/results",
        "peak_rss_increment_from_initial_bytes": max(0, memory.peak_wset - initial_rss),
        "repeat_max_absolute_difference": max(differences),
        "metrics": metrics[0],
        "all_repeat_statuses": [metric.get("status") for metric in metrics],
        "all_repeat_reasons": [
            {
                key: metric.get(key)
                for key in ("reason", "bearing_reason", "gear_reason")
            }
            for metric in metrics
        ],
        "profile_separate_untimed_call": profile_rows,
        "stdout": warnings.getvalue(),
    }
    write_json(output / "cases" / f"{case_id}.json", result)


def campaign(args):
    import psutil

    data_root = Path(args.data_root).expanduser().resolve()
    output = (
        Path(args.output).resolve()
        if args.output
        else data_root / "real_diagnosis" / "performance" / "20261112"
    )
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    if not args.resume:
        write_json(output / "config.json", config)
        vectors = prepare(data_root, output, config)
        write_json(output / "cases.json", cases_for(vectors))
    else:
        config = json.loads((output / "config.json").read_text(encoding="utf-8"))
    environment = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor(),
        "logical_cpus": psutil.cpu_count(),
        "physical_cores": psutil.cpu_count(logical=False),
        "host_physical_memory_bytes": psutil.virtual_memory().total,
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "git_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        ),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "EMD-signal", "psutil")
        },
        "p95_estimator": "linear percentile of five measured iteration totals; preliminary tail estimate, not production SLO",
        "timing_exclusions": [
            "source loading",
            "vector loading",
            "imports",
            "warmup",
            "metrics serialization",
        ],
        "production_equivalence": "Windows 2 logical CPU affinity + 2GiB Job commit limit; not Ubuntu ECS or entire 2GiB machine",
    }
    write_json(output / "environment.json", environment)
    cases = json.loads((output / "cases.json").read_text(encoding="utf-8"))
    env = {
        **os.environ,
        **{
            key: str(config["native_threads"])
            for key in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
    }
    errors = []
    for index, case in enumerate(cases, 1):
        if args.case and case["id"] not in args.case:
            continue
        result_path = output / "cases" / f"{case['id']}.json"
        if args.resume and result_path.exists():
            continue
        print(f"[{index}/{len(cases)}] {case['id']}", flush=True)
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.diagnosis.benchmarks.run",
                "--worker",
                case["id"],
                "--output",
                str(output),
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=1800,
            check=False,
        )
        if completed.returncode:
            error = {
                "id": case["id"],
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
            errors.append(error)
            print(completed.stderr[-1200:], flush=True)
            write_json(output / "errors.json", errors)
        else:
            result = json.loads(result_path.read_text(encoding="utf-8"))
            print(
                f"  median={result['median_seconds']:.4f}s P95={result['p95_seconds']:.4f}s peakRSS={result['peak_rss_bytes'] / 2**20:.1f}MiB status={result['metrics'].get('status')}",
                flush=True,
            )
    results = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((output / "cases").glob("*.json"))
    ]
    write_json(
        output / "results.json",
        {
            "environment": environment,
            "config": config,
            "cases": results,
            "errors": errors,
        },
    )
    print(f"Saved {len(results)}/{len(cases)} cases to {output}", flush=True)
    if errors:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        default=os.environ.get("CNN_DATA_ROOT", str(HERE.parents[3] / "data")),
    )
    parser.add_argument("--output")
    parser.add_argument("--config", default=str(HERE / "config.json"))
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse fixed vector cache and completed cases; target failed cases with --case",
    )
    parser.add_argument("--case", action="append")
    parser.add_argument("--worker")
    args = parser.parse_args()
    if args.worker:
        worker(Path(args.output), args.worker)
    else:
        campaign(args)


if __name__ == "__main__":
    main()
