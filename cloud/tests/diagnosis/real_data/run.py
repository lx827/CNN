"""显式选择 manifest 的串行真实小窗核实入口，不作为准确率评估器。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .common import (
    LoadedRecord,
    json_value,
    load_manifest,
    resolve_data_root,
    resolve_source_path,
)


def load_record(entry: dict, data_root: Path) -> LoadedRecord:
    """按数据身份分派，不接受旧一维 npy 兼容格式。"""
    if entry["dataset_id"] in {"ottawa_bearing", "hust_bearing"}:
        from .bearing import load_record as loader
    else:
        from .gear import load_record as loader
    return loader(entry, data_root)


def _signal_quality(signal: np.ndarray, fs: float) -> dict:
    values = np.asarray(signal)
    if values.ndim != 1 or values.size < 16:
        raise ValueError(
            "vibration must be a one-dimensional window with at least 16 samples"
        )
    finite = bool(np.all(np.isfinite(values)))
    result = {
        "sample_count": values.size,
        "duration_seconds": values.size / fs,
        "all_finite": finite,
    }
    if not finite:
        raise ValueError("non-finite vibration samples")
    centered = values - np.mean(values)
    variance = float(np.mean(centered**2))
    result.update(
        mean=float(np.mean(values)),
        rms=float(np.sqrt(np.mean(values**2))),
        peak_absolute=float(np.max(np.abs(values))),
        kurtosis=float(np.mean(centered**4) / variance**2) if variance > 0 else None,
        constant=bool(variance == 0),
    )
    return result


def diagnose(signal: np.ndarray, fs: float, entry: dict, channel_index: int) -> dict:
    """调用现有对象 Pipeline，并经唯一业务适配器保留两维状态与 null 分。

    首批清单没有已标定连续速度。这里不从文件名、Speed 电压或编码器
    电平构造转频；轴承仍计算真实包络特征，行星运行其前提门控，定轴
    缺少参考轴转频时显式保留未执行原因。没有新阈值、基线或评分实现。
    """
    from app.algorithms.mechanics.planetary import PlanetaryGearGeometry
    from app.algorithms.pipelines.bearing import BearingEnvelopePipeline
    from app.algorithms.pipelines.gear.planetary import PlanetaryGearPipeline
    from app.services.diagnosis.adapters import adapt_method_result, unavailable_result
    from app.services.diagnosis.domain import DiagnosisKey

    key = DiagnosisKey(entry["sample_id"], 1, channel_index, "none")
    if entry["dataset_id"] in {"ottawa_bearing", "hust_bearing"}:
        result = BearingEnvelopePipeline().run(signal, fs, rot_frequency_hz=None)
        statistics = asdict(result.analysis.envelope_analysis.features.statistics)
        raw = {
            "method": "envelope",
            "evaluation": asdict(result.evaluation),
            "reason": "missing_calibrated_speed_and_complete_verified_geometry",
            "analysis": {"status": "computed", "statistics": statistics},
        }
        assessment = adapt_method_result(
            raw,
            key=key,
            object_id="bearing",
            method="envelope",
            signal=signal,
            physical_parameters=False,
        )
        return {
            "pipeline": "BearingEnvelopePipeline",
            "pipeline_invoked": True,
            **assessment,
        }
    if entry["dataset_id"] == "wt_planetary":
        mechanics = entry.get("mechanics", {})
        geometry = PlanetaryGearGeometry(
            sun_teeth=mechanics["sun_teeth"],
            ring_teeth=mechanics["ring_teeth"],
            planet_teeth=mechanics["planet_teeth"],
            planet_count=mechanics["n_planets"],
            reference_axis="sun",
        )
        result = PlanetaryGearPipeline(geometry).run(
            signal, fs, speed=None, include_tsa=False
        )
        raw = {
            "method": "planetary_gear",
            "evaluation": asdict(result.evaluation),
            "reason": result.analysis.reason or result.evaluation.reason,
            "analysis": {
                "status": result.analysis.status,
                "reason": result.analysis.reason,
            },
        }
        assessment = adapt_method_result(
            raw,
            key=key,
            object_id="gear",
            method="planetary_gear",
            signal=signal,
            physical_parameters=True,
        )
        return {
            "pipeline": "PlanetaryGearPipeline",
            "pipeline_invoked": True,
            **assessment,
        }
    assessment = unavailable_result(
        "missing_calibrated_pinion_reference_speed",
        key=key,
        object_id="gear",
        method="standard",
    )
    return {
        "pipeline": "FixedAxisGearPipeline",
        "pipeline_invoked": False,
        **assessment,
    }


def run_entries(
    entries: list[dict],
    data_root: Path,
    *,
    window_seconds: float = 1.0,
    start_seconds: float = 0.0,
    channels: list[str] | None = None,
) -> dict:
    """每次只加载一条采集、逐通道运行；失败记录入报告并使 CLI 非零。"""
    if not math.isfinite(window_seconds) or not 0 < window_seconds <= 5:
        raise ValueError("window_seconds must be in (0, 5]")
    if not math.isfinite(start_seconds) or start_seconds < 0:
        raise ValueError("start_seconds must be finite and nonnegative")
    if not entries:
        raise ValueError("no samples selected")
    results, errors = [], []
    for entry in entries:
        try:
            resolve_source_path(data_root, entry["source_path"])
            request = {
                **entry,
                "_window": {
                    "start_seconds": start_seconds,
                    "duration_seconds": window_seconds,
                },
            }
            record = load_record(request, data_root)
            fs = record.sample_rate_hz
            if not math.isfinite(fs) or fs <= 0 or fs != float(entry["fs_hz"]):
                raise ValueError("loaded sample rate differs from manifest")
            if (
                record.sample_id != entry["sample_id"]
                or record.dataset_id != entry["dataset_id"]
            ):
                raise ValueError("loaded record identity differs from manifest")
            selected = channels if channels is not None else list(record.vibration)
            if not selected or set(selected) - set(record.vibration):
                raise ValueError(
                    f"requested vibration channels unavailable: {selected}"
                )
            item = {
                "sample_id": record.sample_id,
                "dataset_id": record.dataset_id,
                "group_id": entry["group_id"],
                "label": entry["label"],
                "fault_types": entry["fault_types"],
                "source_path": entry["source_path"],
                "sample_rate_hz": fs,
                "metadata": record.metadata,
                "channels": {},
            }
            for index, channel in enumerate(selected, 1):
                # reader 返回较短的连续块合法；防御性截断仍绝不超过请求窗口。
                signal = np.asarray(record.vibration[channel])[
                    : int(fs * window_seconds)
                ]
                item["channels"][channel] = {
                    "quality": _signal_quality(signal, fs),
                    "diagnosis": diagnose(signal, fs, entry, index),
                }
            results.append(item)
            del record
        except Exception as exc:  # noqa: BLE001 - 每条真实采集失败入报告，最后统一非零退出。
            errors.append(
                {
                    "sample_id": entry["sample_id"],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    states = Counter(
        channel["diagnosis"]["evaluation_status"]
        for record in results
        for channel in record["channels"].values()
    )
    return json_value(
        {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "purpose": "raw_loader_and_bounded_pipeline_smoke_not_accuracy_evaluation",
            "requested_window_seconds": window_seconds,
            "requested_start_seconds": start_seconds,
            "selected_record_count": len(entries),
            "loaded_record_count": len(results),
            "acquisition_group_count": len(
                {(r["dataset_id"], r["group_id"]) for r in results}
            ),
            "channel_result_count": sum(len(r["channels"]) for r in results),
            "evaluation_status_counts": dict(states),
            "error_count": len(errors),
            "records": results,
            "errors": errors,
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        help="相对 data-root 或绝对路径，可重复；默认两套清单",
    )
    parser.add_argument(
        "--sample-id", action="append", help="显式采集身份，可重复；找不到即失败"
    )
    parser.add_argument("--channel", action="append", help="振动通道，可重复；默认全部")
    parser.add_argument(
        "--window-seconds", type=float, default=1.0, help="连续小窗，(0,5] 秒"
    )
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument(
        "--output",
        type=Path,
        help="JSON 路径；默认 data-root/real_diagnosis/reports/latest.json",
    )
    args = parser.parse_args(argv)
    root = resolve_data_root(args.data_root)
    try:
        paths = args.manifest or [
            Path(__file__).parent / "manifests/bearing.json",
            Path(__file__).parent / "manifests/gear.json",
        ]
        entries = [
            entry
            for path in paths
            for entry in load_manifest(path if path.is_absolute() else root / path)
        ]
        ids = [entry["sample_id"] for entry in entries]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate sample_id across manifests")
        if args.sample_id:
            missing = set(args.sample_id) - set(ids)
            if missing:
                raise ValueError(
                    f"requested samples not in manifest: {sorted(missing)}"
                )
            entries = [
                entry for entry in entries if entry["sample_id"] in args.sample_id
            ]
        report = run_entries(
            entries,
            root,
            window_seconds=args.window_seconds,
            start_seconds=args.start_seconds,
            channels=args.channel,
        )
        output = args.output or root / "real_diagnosis/reports/latest.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(
            f"records={report['loaded_record_count']}/{report['selected_record_count']} "
            f"acquisition_groups={report['acquisition_group_count']} channels={report['channel_result_count']} "
            f"errors={report['error_count']}"
        )
        print(
            f"evaluation_status={report['evaluation_status_counts']}; report={output}"
        )
        for record in report["records"]:
            for name, channel in record["channels"].items():
                state = channel["diagnosis"]
                print(
                    f"{record['sample_id']}/{name} label={record['label']} "
                    f"duration={channel['quality']['duration_seconds']:.4f}s "
                    f"{state['evaluation_status']}/{state['diagnosis_conclusion']} "
                    f"coverage={state.get('coverage')} score={state.get('health_score')} "
                    f"reason={state.get('reason')}"
                )
        return 1 if report["errors"] else 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"real-data runner failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
