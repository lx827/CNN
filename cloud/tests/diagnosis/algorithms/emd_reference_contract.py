"""原生实现比较前冻结的 EMD 数值对照资产，不保存生成波形或 golden 数组。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

CONTRACT = json.loads(
    (Path(__file__).parents[1] / "benchmarks" / "native_emd_contract.json").read_text(
        encoding="utf-8"
    )
)
SAMPLE_RATE_HZ = 512.0


def reference_signals():
    """返回可重建的尺度、平台峰、内部镜像轴和不可判定反例。"""
    time = np.arange(256) / SAMPLE_RATE_HZ
    tones = np.sin(2 * np.pi * 8 * time) + 0.6 * np.sin(2 * np.pi * 64 * time + 0.2)
    return {
        "two_tones": tones,
        "small_amplitude": tones * 1e-15,
        "large_amplitude": tones * 1e9,
        "trend": np.sin(2 * np.pi * 20 * time) + np.linspace(-0.2, 0.2, len(time)),
        "plateau": np.tile([0.0, 1.0, 1.0, 0.0, -1.0, -1.0, 0.0], 24),
        "internal_mirror_axes": np.array(
            [2.5, 0, 1, 0, -1, 0, 1, 0, -1, 0, 1, 0, -2.5], dtype=np.float64
        ),
        "near_flat_extrema": tones + np.finfo(np.float64).eps * np.arange(len(time)),
        "non_contiguous": np.column_stack((tones, np.zeros_like(tones))).ravel()[::2],
        "monotonic": np.linspace(-1.0, 1.0, 128),
        "constant": np.full(128, 4.0),
        "zero": np.zeros(128),
    }


def assert_array_close(testcase, actual, reference, signal, *, stage="decomposition"):
    """按冻结的输入/参考幅值尺度同时检查逐点误差与相对 L2。

    对零参考数组由逐点绝对预算判定；非零数组另外要求相对 L2。
    整个数组必须有限，不允许 NaN 相等掩盖数值失败。
    """
    actual = np.asarray(actual)
    reference = np.asarray(reference)
    testcase.assertEqual(actual.shape, reference.shape)
    testcase.assertTrue(np.all(np.isfinite(actual)))
    testcase.assertTrue(np.all(np.isfinite(reference)))
    scale = max(
        float(np.max(np.abs(signal))),
        float(np.max(np.abs(reference))),
        np.finfo(np.float64).tiny,
    )
    budget = CONTRACT[stage]
    expected = reference / scale
    observed = actual / scale
    np.testing.assert_allclose(
        observed, expected, rtol=budget["rtol"], atol=budget["atol_scaled"]
    )
    expected_norm = np.linalg.norm(expected)
    if expected_norm > 0:
        testcase.assertLessEqual(
            float(np.linalg.norm(observed - expected) / expected_norm),
            budget["relative_l2"],
        )


def assert_result_close(testcase, actual, reference, signal):
    """比较公开分解结果；普通用例要求状态/模态数/迭代等元数据一致。

    接近停止阈值的分支差异按契约另作专项核验，本函数不自动放宽状态。
    """
    for field in CONTRACT["metadata_equal"]:
        if field == "mode_count":
            testcase.assertEqual(len(actual.imfs), len(reference.imfs))
        else:
            testcase.assertEqual(
                getattr(actual, field), getattr(reference, field), field
            )
    testcase.assertEqual(actual.sift_iterations, reference.sift_iterations)
    for observed, expected in zip(actual.imfs, reference.imfs):
        assert_array_close(testcase, observed, expected, signal)
    assert_array_close(testcase, actual.residual, reference.residual, signal)
