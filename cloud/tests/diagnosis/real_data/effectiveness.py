"""原始记录效果实验：标准对象 Pipeline、独立采集分母与显式条件情景。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .common import json_value, load_manifest, resolve_data_root, resolve_source_path


def load_record(entry, root):
    if entry["dataset_id"].endswith("bearing"):
        from .bearing import load_record as loader
    else:
        from .gear import load_record as loader
    return loader(entry, root)


def aggregate_channels(channels: dict[str, dict]) -> dict:
    """记录级规则预先固定；通道阳性取并集，缺证据不可被阴性掩盖。"""
    values = list(channels.values())
    conclusions = [v["diagnosis_conclusion"] for v in values]
    if any(c in {"warning", "fault"} for c in conclusions):
        return {
            "evaluation_status": "evaluated",
            "diagnosis_conclusion": "fault" if "fault" in conclusions else "warning",
            "prediction": "anomaly",
        }
    if values and all(
        c == "normal" and v["evaluation_status"] == "evaluated"
        for c, v in zip(conclusions, values)
    ):
        return {
            "evaluation_status": "evaluated",
            "diagnosis_conclusion": "normal",
            "prediction": "normal",
        }
    return {
        "evaluation_status": "indeterminate"
        if any(v["evaluation_status"] == "indeterminate" for v in values)
        else "not_evaluable",
        "diagnosis_conclusion": "unknown",
        "prediction": "unknown",
    }


def summarize(records: list[dict]) -> dict:
    """检出率与误报率的分母含所有已选故障/健康记录，包括失败及unknown。"""
    matrix = {
        truth: {pred: 0 for pred in ("normal", "anomaly", "unknown")}
        for truth in ("healthy", "fault")
    }
    for row in records:
        truth = "healthy" if row["label"] == "healthy" else "fault"
        matrix[truth][row["prediction"]] += 1
    healthy, fault = sum(matrix["healthy"].values()), sum(matrix["fault"].values())
    unknown = sum(v["unknown"] for v in matrix.values())
    return {
        "record_count": len(records),
        "healthy_count": healthy,
        "fault_count": fault,
        "detected_fault_count": matrix["fault"]["anomaly"],
        "false_alarm_count": matrix["healthy"]["anomaly"],
        "unknown_count": unknown,
        "detection_rate": matrix["fault"]["anomaly"] / fault if fault else None,
        "healthy_false_alarm_rate": matrix["healthy"]["anomaly"] / healthy
        if healthy
        else None,
        "unknown_rate": unknown / len(records) if records else None,
        "confusion_matrix": matrix,
    }


def grouped_summary(records: list[dict]) -> dict:
    result = {"all": summarize(records)}
    for dimension in (
        "dataset_id",
        "label",
        "speed_group",
        "load_group",
        "duration_seconds",
        "severity",
        "installation_batch",
        "noise_group",
    ):
        groups = defaultdict(list)
        for row in records:
            groups[str(row.get(dimension, "unknown"))].append(row)
        result[dimension] = {
            key: summarize(rows) for key, rows in sorted(groups.items())
        }
    return result


def _canonical(evaluation, signal, entry, channel, method, physical, reason=None):
    from app.services.diagnosis.adapters import adapt_method_result
    from app.services.diagnosis.domain import DiagnosisKey

    return adapt_method_result(
        {
            "method": method,
            "evaluation": asdict(evaluation),
            "reason": reason,
            "analysis": {"status": "computed"},
        },
        key=DiagnosisKey(entry["sample_id"], 1, channel, "none"),
        object_id="bearing" if method == "envelope" else "gear",
        method=method,
        signal=signal,
        physical_parameters=physical,
    )


def _compact(value):
    """谱数组不写报告；原指标、canonical评估、证据与不可判定原因保留。"""
    return {
        k: v
        for k, v in value.items()
        if k not in {"spectrum", "envelope_spectrum", "order_spectrum"}
    }


def _speed_summary(order):
    from app.services.diagnosis.engine import DiagnosisEngine

    frequency, deviation = DiagnosisEngine._order_speed_summary(order)
    return {
        "status": order.status,
        "tracking_method": order.tracking_method,
        "frequency_hz": frequency,
        "std_hz": deviation,
        "source": "estimated_from_same_vibration_not_independent_truth",
        "reason": order.reason,
    }


def bearing_results(signal, fs, entry, channel_index, assumed_geometry):
    from app.algorithms.order import AutomaticOrderPipeline
    from app.algorithms.pipelines.bearing import BearingEnvelopePipeline
    from app.services.diagnosis.domain import DiagnosisKey
    from app.services.diagnosis.engine import DiagnosisEngine
    from app.services.diagnosis.signal_utils import prepare_signal

    values = prepare_signal(signal, detrend=True)
    order = AutomaticOrderPipeline().run(values, fs)
    key = DiagnosisKey(entry["sample_id"], 1, channel_index, "none")
    # Ottawa原文已给n/d/D，接触角由现有产品默认0；实验不额外发明门控。
    geometry = entry["metadata"]["bearing_geometry"]
    current_params = (
        {
            "n": geometry["ball_count"],
            "d": geometry["ball_diameter_mm"],
            "D": geometry["pitch_diameter_mm"],
        }
        if "pitch_diameter_mm" in geometry
        else None
    )
    current = DiagnosisEngine(
        bearing_params=current_params, diagnosis_key=key
    ).analyze_bearing(values, fs, preprocess=False, _cached_order=order)
    # HUST恒速20Hz仅为名义情景；所有变速仍走真实估计/变速门控。
    nominal = entry.get("metadata", {}).get("nominal_rotation_hz")
    conditional = DiagnosisEngine(
        bearing_params=assumed_geometry, diagnosis_key=key
    ).analyze_bearing(
        values,
        fs,
        rot_freq=nominal,
        preprocess=False,
        _cached_order=None if nominal else order,
    )
    observation = BearingEnvelopePipeline().analyze(values, fs)
    return {
        "current_contract": _compact(current),
        "conditional_physical_parameters": _compact(conditional),
    }, {
        "pipeline": "BearingEnvelopePipeline via DiagnosisEngine",
        "speed": _speed_summary(order),
        "conditional_speed_source": "nominal_condition_not_measured"
        if nominal
        else "estimated_from_vibration",
        "conditional_geometry": assumed_geometry,
        "geometry_evidence_gap": "Ottawa contact_angle_unverified"
        if entry["dataset_id"] == "ottawa_bearing"
        else "HUST pitch_diameter_and_contact_angle_unverified",
        "envelope_band_hz": [
            observation.representation.band.low_hz,
            observation.representation.band.high_hz,
        ],
        "envelope_statistics": asdict(
            observation.envelope_analysis.features.statistics
        ),
    }


def fixed_results(signal, fs, entry, channel_index):
    from app.algorithms.mechanics import FixedAxisGearGeometry
    from app.algorithms.order import AutomaticOrderPipeline, ScalarSpeed
    from app.algorithms.pipelines.gear.fixed_axis import FixedAxisGearPipeline
    from app.services.diagnosis.domain import DiagnosisKey
    from app.services.diagnosis.engine import DiagnosisEngine
    from app.services.diagnosis.signal_utils import prepare_signal

    values = prepare_signal(signal, detrend=True)
    order = AutomaticOrderPipeline().run(values, fs)
    mechanics = entry["mechanics"]
    pipeline = FixedAxisGearPipeline(
        FixedAxisGearGeometry(mechanics["pinion_teeth"], mechanics["gear_teeth"])
    )
    current = _compact(
        DiagnosisEngine(
            gear_teeth={
                "input": mechanics["pinion_teeth"],
                "output": mechanics["gear_teeth"],
            },
            diagnosis_key=DiagnosisKey(entry["sample_id"], 1, channel_index, "none"),
        ).analyze_gear(values, fs, preprocess=False, _cached_order=order)
    )
    nominal = entry["speed"]["nominal_hz"]
    conditional = pipeline.run(
        values, fs, speed=ScalarSpeed(nominal, "nominal_hz_assumed_pinion_not_measured")
    )
    assessment = _canonical(
        conditional.evaluation, values, entry, channel_index, "standard", True
    )
    return {
        "current_contract": current,
        "conditional_physical_parameters": assessment,
    }, {
        "pipeline": "FixedAxisGearPipeline",
        "speed": _speed_summary(order),
        "conditional_speed_hz": nominal,
        "conditional_speed_source": "nominal_hz_assumed_pinion_not_measured",
        "conditional_metrics": {
            k: asdict(getattr(conditional.analysis, k))
            for k in ("fm0", "fm4", "car", "na4", "nb4")
        },
        "ser": asdict(conditional.analysis.sideband_analysis.ser),
        "order_statistics": asdict(conditional.analysis.order_statistics),
    }


class PlanetaryExperiment:
    """每个表示键独立用N1训练；N2及故障绝不参与阈值选择。"""

    def __init__(self, entries, root):
        self.entries, self.root, self.cache, self.training = entries, root, {}, []

    @staticmethod
    def pipeline(entry):
        from app.algorithms.mechanics.planetary import PlanetaryGearGeometry
        from app.algorithms.pipelines.gear.planetary import PlanetaryGearPipeline

        geometry = entry["mechanics"]
        return PlanetaryGearPipeline(
            PlanetaryGearGeometry(
                geometry["sun_teeth"],
                geometry["ring_teeth"],
                geometry["planet_teeth"],
                geometry["n_planets"],
                geometry["reference_axis"],
            )
        )

    def baseline(
        self,
        hz,
        channel,
        duration=5.0,
        scale=1.0,
        methods=("narrowband", "fullband", "highpass", "tsa_residual"),
    ):
        from app.algorithms.gear.planetary.evaluation import collect_planetary_metrics
        from app.algorithms.gear.planetary.types import (
            PlanetaryBaseline,
            PlanetaryThreshold,
        )
        from app.algorithms.order import ScalarSpeed

        cache_key = hz, channel, duration, scale, methods
        if cache_key in self.cache:
            return self.cache[cache_key]
        train = next(e for e in self.entries if e["sample_id"] == f"wt_N1_{hz}")
        metrics = []
        for start in (0, 10, 20):
            record = load_record(
                {
                    **train,
                    "_window": {"start_seconds": start, "duration_seconds": duration},
                },
                self.root,
            )
            analysis = self.pipeline(train).analyze(
                record.vibration[channel],
                record.sample_rate_hz,
                ScalarSpeed(hz * scale, "nominal_sun_hz_not_encoder_measured"),
                include_tsa=True,
                methods=methods,
            )
            metrics.append(collect_planetary_metrics(analysis))
        common = set.intersection(*(set(m) for m in metrics))
        thresholds = []
        # 只校准有明确太阳轮候选意义的包络峰；不让无定位阶矩/边带投票。
        for key in sorted(common):
            if not key.endswith(".sun_mesh_encounter.amplitude_to_background"):
                continue
            values = np.array([m[key] for m in metrics])
            median = float(np.median(values))
            margin = max(
                3 * 1.4826 * float(np.median(np.abs(values - median))),
                abs(median) * 0.25,
                1e-9,
            )
            warning = float(max(values) + margin)
            thresholds.append(PlanetaryThreshold(key, warning, warning + margin))
        baseline = PlanetaryBaseline(
            analysis.representation_key,
            tuple(thresholds),
            f"experimental_N1_{hz}_{channel}_windows_0_10_20_no_test_labels",
        )
        self.cache[cache_key] = baseline
        self.training.append(
            {
                "training_sample_id": train["sample_id"],
                "channel": channel,
                "duration_seconds": duration,
                "nominal_speed_scale": scale,
                "methods": methods,
                "metrics_by_window": metrics,
                "thresholds": [asdict(t) for t in thresholds],
                "source": baseline.source,
            }
        )
        return baseline

    def run(
        self,
        signal,
        fs,
        entry,
        channel,
        channel_index,
        *,
        duration=5.0,
        scale=1.0,
        methods=("narrowband", "fullband", "highpass", "tsa_residual"),
        current_result=None,
    ):
        from app.algorithms.gear.planetary.evaluation import collect_planetary_metrics
        from app.algorithms.order import ScalarSpeed

        pipeline = self.pipeline(entry)
        if current_result is None:
            from app.services.diagnosis.domain import DiagnosisKey
            from app.services.diagnosis.engine import DiagnosisEngine

            current_result = _compact(
                DiagnosisEngine(
                    gear_teeth={
                        "gear_type": "planetary",
                        "sun": entry["mechanics"]["sun_teeth"],
                        "ring": entry["mechanics"]["ring_teeth"],
                        "planet": entry["mechanics"]["planet_teeth"],
                        "planet_count": entry["mechanics"]["n_planets"],
                        "reference_axis": entry["mechanics"]["reference_axis"],
                        "fixed_member": "ring",
                    },
                    diagnosis_key=DiagnosisKey(
                        entry["sample_id"], 1, channel_index, "none"
                    ),
                ).analyze_gear(signal, fs)
            )
        hz = entry["speed"]["nominal_hz"]
        analysis = pipeline.analyze(
            signal[: round(duration * fs)],
            fs,
            ScalarSpeed(hz * scale, "nominal_sun_hz_not_encoder_measured"),
            include_tsa=True,
            methods=methods,
        )
        baseline = self.baseline(hz, channel, duration, scale, methods)
        evaluation = pipeline.evaluate(analysis, baseline)
        return {
            "current_contract": current_result,
            "conditional_physical_parameters": _canonical(
                evaluation, signal, entry, channel_index, "planetary_gear", True
            ),
        }, {
            "pipeline": "PlanetaryGearPipeline",
            "analysis_status": analysis.status,
            "analysis_reason": analysis.reason,
            "conditional_speed_hz": hz * scale,
            "conditional_speed_source": "nominal_sun_hz_not_measured",
            "baseline_source": baseline.source,
            "baseline_status": "experimental_calibration_independent_installation_test_not_production_validated",
            "raw_metrics": collect_planetary_metrics(analysis),
            "method_status": [
                {
                    "method": m.method,
                    "status": m.status,
                    "reason": m.reason,
                    "peaks": [asdict(p) for p in m.peaks],
                }
                for m in analysis.methods
            ],
            "metric_availability": {k: asdict(v) for k, v in analysis.metrics.items()},
        }


def _row(entry, channels, scenario, duration):
    metadata = entry.get("metadata", {})
    return {
        "sample_id": entry["sample_id"],
        "dataset_id": entry["dataset_id"],
        "group_id": entry["group_id"],
        "label": entry["label"],
        "fault_types": entry["fault_types"],
        "scenario": scenario,
        "evaluation_split": entry.get("evaluation_split", "test"),
        "severity": entry.get("severity", "unspecified"),
        "speed_group": str(
            entry.get("speed", {}).get(
                "nominal_hz",
                metadata.get("condition", metadata.get("speed_mode", "unknown")),
            )
        ),
        "load_group": str(entry.get("load", {}).get("torque_nm", "unknown")),
        "installation_batch": entry.get("installation_batch", "unknown"),
        "duration_seconds": duration,
        "noise_group": "observed_noise_not_calibrated",
        **aggregate_channels(channels),
        "channel_reasons": {
            key: value.get("reason") for key, value in channels.items()
        },
        "channels": channels,
    }


def run_experiment(entries, root, output, plan):
    from app.services.diagnosis.adapters import unavailable_result
    from app.services.diagnosis.domain import DiagnosisKey

    np.random.seed(plan["seed"])
    planetary = PlanetaryExperiment(entries, root)
    rows, observations, sensitivity, errors = [], [], [], []
    started = time.perf_counter()
    for position, entry in enumerate(entries, 1):
        before = time.perf_counter()
        duration = float(
            plan["hust_gearbox_window_seconds"]
            if entry["dataset_id"] == "hust_gearbox"
            else plan["primary_window_seconds"]
        )
        channel_results = {
            "current_contract": {},
            "conditional_physical_parameters": {},
        }
        try:
            source = resolve_source_path(root, entry["source_path"])
            actual_hash = hashlib.file_digest(source.open("rb"), "sha256").hexdigest()
            if actual_hash != entry["sha256"]:
                raise ValueError("raw source SHA256 differs from frozen manifest")
            record = load_record(
                {
                    **entry,
                    "_window": {"start_seconds": 0, "duration_seconds": duration},
                },
                root,
            )
            for channel_index, (name, values) in enumerate(record.vibration.items(), 1):
                if entry["dataset_id"].endswith("bearing"):
                    result, observation = bearing_results(
                        values,
                        record.sample_rate_hz,
                        entry,
                        channel_index,
                        plan["conditional_bearing_geometry"],
                    )
                elif entry["dataset_id"] == "hust_gearbox":
                    result, observation = fixed_results(
                        values, record.sample_rate_hz, entry, channel_index
                    )
                else:
                    result, observation = planetary.run(
                        values, record.sample_rate_hz, entry, name, channel_index
                    )
                for scenario, value in result.items():
                    channel_results[scenario][name] = value
                observations.append(
                    {
                        "sample_id": entry["sample_id"],
                        "channel": name,
                        "sample_count": len(values),
                        "sample_rate_hz": record.sample_rate_hz,
                        "duration_seconds": len(values) / record.sample_rate_hz,
                        "rms": float(np.sqrt(np.mean(values**2))),
                        **observation,
                    }
                )
            if entry["sample_id"] in plan["sensitivity_records"]:
                settings = [
                    (
                        "speed_0.95",
                        5.0,
                        0.95,
                        ("narrowband", "fullband", "highpass", "tsa_residual"),
                    ),
                    (
                        "speed_1.05",
                        5.0,
                        1.05,
                        ("narrowband", "fullband", "highpass", "tsa_residual"),
                    ),
                    (
                        "window_3s",
                        3.0,
                        1.0,
                        ("narrowband", "fullband", "highpass", "tsa_residual"),
                    ),
                ]
                settings += [
                    ("only_" + m, 5.0, 1.0, (m,))
                    for m in plan["sensitivity"]["single_methods"]
                ]
                for experiment, length, scale, methods in settings:
                    variant = {}
                    for channel_index, (name, values) in enumerate(
                        record.vibration.items(), 1
                    ):
                        result, observation = planetary.run(
                            values,
                            record.sample_rate_hz,
                            entry,
                            name,
                            channel_index,
                            duration=length,
                            scale=scale,
                            methods=methods,
                            current_result=channel_results["current_contract"][name],
                        )
                        variant[name] = {
                            **result["conditional_physical_parameters"],
                            "raw_metrics": observation["raw_metrics"],
                        }
                    sensitivity.append(
                        {
                            **_row(entry, variant, experiment, length),
                            "nominal_speed_scale": scale,
                            "methods": methods,
                        }
                    )
        except Exception as exc:  # noqa: BLE001 - 每个预定采集始终保留分母；异常显式记录。
            errors.append(
                {
                    "sample_id": entry["sample_id"],
                    "error_type": type(exc).__name__,
                    "reason": str(exc),
                }
            )
            failed = unavailable_result(
                f"{type(exc).__name__}: {exc}",
                key=DiagnosisKey(entry["sample_id"], 1, 1, "none"),
                object_id="bearing"
                if entry["dataset_id"].endswith("bearing")
                else "gear",
                method="envelope"
                if entry["dataset_id"].endswith("bearing")
                else "standard",
            )
            for result in channel_results.values():
                result["record_failure"] = failed
        for scenario, channels in channel_results.items():
            rows.append(_row(entry, channels, scenario, duration))
        print(
            f"[{position}/{len(entries)}] {entry['sample_id']} "
            + " ".join(
                f"{s}={aggregate_channels(c)['prediction']}"
                for s, c in channel_results.items()
            )
            + f" seconds={time.perf_counter() - before:.2f}",
            flush=True,
        )
        # 长实验逐采集落盘，故障不会丢掉之前的实际结果。
        output.parent.mkdir(parents=True, exist_ok=True)
        output.with_suffix(".progress.json").write_text(
            json.dumps(
                json_value({"records": rows, "errors": errors}), ensure_ascii=False
            ),
            encoding="utf-8",
        )
    tests = [row for row in rows if row["evaluation_split"] != "calibration"]
    summaries = {
        scenario: grouped_summary([r for r in tests if r["scenario"] == scenario])
        for scenario in ("current_contract", "conditional_physical_parameters")
    }
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "purpose": "record_level_current_pipeline_effectiveness_with_explicit_conditional_scenarios",
        "elapsed_seconds": time.perf_counter() - started,
        "plan": plan,
        "selected_record_count": len(entries),
        "test_record_count": len(tests) // 2,
        "calibration_record_count": sum(
            e.get("evaluation_split") == "calibration" for e in entries
        ),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": {p: importlib.metadata.version(p) for p in ("numpy", "scipy")},
        },
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[4],
            text=True,
        ).strip(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "records": rows,
        "observations": observations,
        "training": planetary.training,
        "summaries": summaries,
        "sensitivity": sensitivity,
        "sensitivity_summaries": {
            key: grouped_summary([r for r in sensitivity if r["scenario"] == key])
            for key in sorted({r["scenario"] for r in sensitivity})
        },
        "errors": errors,
        "unavailable_scope": {
            "speed_truth": "encoder pulses_per_revolution unverified; no measured-speed accuracy claim",
        },
    }
    output.write_text(
        json.dumps(json_value(report), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    return report


def render_report(report: dict, path: Path) -> None:
    """只由已落盘JSON生成报告数字，重新渲染不执行信号算法。"""

    def rate(value):
        return "—" if value is None else f"{100 * value:.1f}%"

    names = {
        "ottawa_bearing": "Ottawa轴承",
        "hust_bearing": "HUSTbear轴承",
        "hust_gearbox": "HUST定轴齿轮",
        "wt_planetary": "WT行星齿轮",
    }
    lines = [
        "# 真实原始数据算法效果基线",
        "",
        "运行日期：2026-11-12。本文数字由冻结实验 JSON 生成，统计单位是原始采集记录；范围为四套公开来源。",
        "",
        f"本轮选取 {report['selected_record_count']} 次采集，{report['calibration_record_count']} 条 WT N1 健康记录专用于阈值训练，其余 {report['test_record_count']} 条进入测试分母。训练记录中的不同窗口与同记录多通道均不增加独立样本数。异常 {len(report['errors'])} 条，失败与 unknown 全部保留在分母。",
        "",
        "## 当前产品结果与条件结果",
        "",
        "`current_contract` 实际执行标准 DiagnosisEngine，按现有产品接口生成 canonical 两维状态。Ottawa 使用原文 n=9、d=7.94、D=38.52，接触角沿用产品默认0°；速度来自当前振动估计器。HUSTbear 不移植另一来源的已证实节径。HUST定轴按18齿输入轮调用产品自动估计；估计量是否对应小轮轴尚无独立测速证据。WT使用28/100/36/4固定齿圈模型与太阳轮参考轴，当前前提门控和基线门控由产品决定。",
        "",
        "`conditional_physical_parameters` 是明确参数假设下的实验：轴承按 ER16K 的 n9/d7.94/D38.52/α0 模型，HUST恒速使用文件名20Hz，其余保留自动估计及产品变速门控；定轴假设名义Hz为18齿输入轮转频；WT假设名义Hz为恒定太阳轮转频，另用N1训练临时界限。HUST节径与这些速度都不是已校准真值，临时界限未部署。两组结果不得混称现场检出率。",
        "",
        "| 情景 | 数据来源 | 故障检出/故障总数 | 检出率 | 健康误报/健康总数 | 误报率 | 不可判定/记录总数 | 不可判定率 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for scenario, title in (
        ("current_contract", "当前产品"),
        ("conditional_physical_parameters", "条件实验"),
    ):
        groups = report["summaries"][scenario]
        for key, value in [("all", groups["all"]), *groups["dataset_id"].items()]:
            lines.append(
                f"| {title} | {names.get(key, '总计')} | {value['detected_fault_count']}/{value['fault_count']} | {rate(value['detection_rate'])} | {value['false_alarm_count']}/{value['healthy_count']} | {rate(value['healthy_false_alarm_rate'])} | {value['unknown_count']}/{value['record_count']} | {rate(value['unknown_rate'])} |"
            )
    lines += [
        "",
        "记录聚合规则在运行前固定：任一通道异常则记录异常；所有通道均已评估正常才记正常；其余记unknown。阳性合并包括warning与fault，表示异常检出，不代表已定位断齿、裂纹或轴承部位。",
        "",
        "## 混淆矩阵",
        "",
        "| 情景 | 真值 | 判正常 | 判异常 | unknown |",
        "|---|---|---:|---:|---:|",
    ]
    for scenario, title in (
        ("current_contract", "当前产品"),
        ("conditional_physical_parameters", "条件实验"),
    ):
        for truth, values in report["summaries"][scenario]["all"][
            "confusion_matrix"
        ].items():
            lines.append(
                f"| {title} | {truth} | {values['normal']} | {values['anomaly']} | {values['unknown']} |"
            )
    lines += [
        "",
        "## 故障与工况分组",
        "",
        "完整分组保留在JSON的 `summaries`：故障标签、速度模式/名义速度、载荷、记录长度、严重度、拆装批次和噪声信息。噪声幅度未独立标定，本轮不把一个unknown噪声层解释为抗噪能力。HUST齿轮速度与载荷严格配对，不能推断独立载荷效应。",
        "",
        "| 情景 | 故障标签 | 检出/故障总数 | 健康误报/健康总数 | unknown/总数 |",
        "|---|---|---:|---:|---:|",
    ]
    for scenario, title in (
        ("current_contract", "当前产品"),
        ("conditional_physical_parameters", "条件实验"),
    ):
        for label, value in report["summaries"][scenario]["label"].items():
            lines.append(
                f"| {title} | {label} | {value['detected_fault_count']}/{value['fault_count']} | {value['false_alarm_count']}/{value['healthy_count']} | {value['unknown_count']}/{value['record_count']} |"
            )
    lines += [
        "",
        "## WT健康基线与消融",
        "",
        "同速度同通道的N1健康采集在0、10、20秒取三个不重叠5秒窗，只校准每种方法太阳轮局部事件候选峰的幅值/背景比。界限为训练最大值加 `max(3×1.4826×MAD, |median|×0.25, 1e-9)`，critical再加同一余量。训练仅来自一次安装，N2是另一次拆装后的健康测试；3个窗口不构成3次独立健康试验。所有原始指标与实际界限保留在JSON。",
        "",
        "固定代表组为20Hz的N2/B2/M2/R2/W2，共1健康、4故障。改变窗口/速度/方法时，N1训练表示同步改变以满足产品严格表示键；不会把不兼容基线强行套入新表示。速度±5%表示同一系统性速度标定偏差的敏感性，不能证明估速误差为5%。",
        "",
        "| 表示 | 检出/故障总数 | 健康误报/健康总数 | unknown/总数 |",
        "|---|---:|---:|---:|",
    ]
    representatives = [
        row
        for row in report["records"]
        if row["scenario"] == "conditional_physical_parameters"
        and row["sample_id"] in report["plan"]["sensitivity_records"]
    ]
    value = summarize(representatives)
    lines.append(
        f"| 完整方法5秒 | {value['detected_fault_count']}/{value['fault_count']} | {value['false_alarm_count']}/{value['healthy_count']} | {value['unknown_count']}/{value['record_count']} |"
    )
    for key, groups in report["sensitivity_summaries"].items():
        value = groups["all"]
        lines.append(
            f"| {key} | {value['detected_fault_count']}/{value['fault_count']} | {value['false_alarm_count']}/{value['healthy_count']} | {value['unknown_count']}/{value['record_count']} |"
        )
    lines += [
        "",
        "## 失败与不可判定",
        "",
        "以下按记录计原因，同一记录多通道相同原因只计一次；一条记录可包含多个原因。完整逐通道 canonical evaluation_status、diagnosis_conclusion、指标、证据、健康分与原因保留在JSON。",
        "",
        "| 情景 | 原因 | 涉及记录数 |",
        "|---|---|---:|",
    ]
    for scenario in ("current_contract", "conditional_physical_parameters"):
        counts = defaultdict(int)
        for row in report["records"]:
            if row["scenario"] == scenario and row["evaluation_split"] != "calibration":
                for reason in set(row["channel_reasons"].values()) - {None}:
                    counts[reason] += 1
        for reason, count in sorted(counts.items()):
            lines.append(f"| {scenario} | `{reason}` | {count} |")
    for error in report["errors"]:
        lines.append(
            f"- `{error['sample_id']}`：{error['error_type']} / {error['reason']}"
        )
    lines += ["", "| 情景 | 健康误报记录 | 故障判正常记录 |", "|---|---|---|"]
    for scenario in ("current_contract", "conditional_physical_parameters"):
        rows = [
            r
            for r in report["records"]
            if r["scenario"] == scenario and r["evaluation_split"] != "calibration"
        ]
        fp = [
            r["sample_id"]
            for r in rows
            if r["label"] == "healthy" and r["prediction"] == "anomaly"
        ]
        fn = [
            r["sample_id"]
            for r in rows
            if r["label"] != "healthy" and r["prediction"] == "normal"
        ]
        lines.append(
            f"| {scenario} | {', '.join(fp) or '无'} | {', '.join(fn) or '无'} |"
        )
    lines += [
        "",
        "## 业务结论与后续策略",
        "",
        "本轮不能支持自动告警已有效。条件情景增加了可评估范围，也同时暴露健康误报；缺参数补齐后仍需验证阈值，不能把unknown减少直接当作准确性提高。保留当前canonical状态，缺前提继续输出unknown，不把它计成正常。",
        "",
        "1. 优先解决测速与连续相位消费：Ottawa的变速记录既有脊线不可判定，也有快速变速包络接口尚未迁移；HUST定轴的1.28秒合法连续块无法被当前自动入口可靠解释。窗口不能为绕过门控而跨块拼接。原始频谱、包络及估速原因保留作问题定位，本轮没有据此证明数值算法公式错误。",
        "2. 轴承统计与定轴工程阈值应先在独立健康记录上校准，再评估故障检出。Ottawa健康误报涉及统计峰SNR及BPFI/BPFO候选；条件HUSTbear健康存在包络峰/峭度告警；条件HUST定轴健康同时有SER、边带计数及阶次统计告警。单纯提高检出率会掩盖这些假阳性，不据本轮标签调生产阈值。",
        "3. WT暂不提升为可生产告警的通用基线。N1到N2跨拆装出现健康误报，20Hz窄带方法是该代表组误报来源；fullband/highpass单方法在这一小组不误报但仍漏检。下一次校准应纳入更多独立健康安装，再检查方法级阈值，不因为当前小样本结果删除窄带实现或选择性丢弃N2。",
        "4. 太阳轮名义速度±5%与3/5秒窗口改变检出结果，说明当前表征和界限对这些前提敏感。补校准PPR与速度参考轴证据后，再做同一冻结清单定向复验；本轮不将名义速度或振动估计冒充实测速度。",
        "",
        "## 可复现运行",
        "",
        "冻结样本与原文件SHA256见仓库 cloud/tests/diagnosis/real_data/manifests/effectiveness.json。完整逐记录证据、生成报告和原始大文件保留本地data目录，不入库。",
        "",
        "```powershell",
        "$env:CNN_DATA_ROOT='D:/code/CNN/data'",
        "cd cloud",
        "uv run python -m tests.diagnosis.real_data.effectiveness --data-root $env:CNN_DATA_ROOT --output D:/code/CNN/data/real_diagnosis/effectiveness/results.json --markdown-output D:/code/CNN/data/real_diagnosis/effectiveness/diagnosis_effectiveness_report.md",
        "uv run python -m unittest tests.diagnosis.real_data.test_effectiveness",
        "```",
        "",
        "已有结果重新生成报告，无需重跑算法：",
        "",
        "```bash",
        "cd cloud",
        "uv run python -m tests.diagnosis.real_data.effectiveness --render-results D:/code/CNN/data/real_diagnosis/effectiveness/results.json --markdown-output D:/code/CNN/data/real_diagnosis/effectiveness/diagnosis_effectiveness_report.md",
        "```",
        "",
        f"随机种子 `{report['plan']['seed']}`；代码修订 `{report['source_revision']}`；Python `{report['environment']['python']}`，NumPy `{report['environment']['packages']['numpy']}`，SciPy `{report['environment']['packages']['scipy']}`。运行器SHA256与完整环境记录在JSON。本轮未修改产品算法；统计测试只检查unknown分母和通道不增样本。",
        "",
        "样本是受控选样的小规模证据，无法据此宣称跨设备/跨日期泛化；WT只有2个独立健康测试记录。编码器PPR在本地原文中未核实，本轮没有把脉冲数反推为独立机械速度真值。",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).parent / "manifests/effectiveness.json",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--render-results", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    if args.render_results:
        if args.markdown_output is None:
            parser.error("--render-results requires --markdown-output")
        render_report(
            json.loads(args.render_results.read_text(encoding="utf-8")),
            args.markdown_output,
        )
        return 0
    root = resolve_data_root(args.data_root)
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = run_experiment(
        load_manifest(args.manifest),
        root,
        args.output or root / "real_diagnosis/effectiveness/results.json",
        payload["plan"],
    )
    if args.markdown_output:
        render_report(report, args.markdown_output)
    print(json.dumps(report["summaries"], ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
