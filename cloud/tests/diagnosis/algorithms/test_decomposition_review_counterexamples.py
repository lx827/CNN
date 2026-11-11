"""独立review提出的包络概率熵、幅值尺度和停止质量反例。"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from app.algorithms.decomposition.selection import compute_component_metrics
from app.algorithms.decomposition.emd import EMDParameters
from app.algorithms.decomposition.vmd import VMDParameters
from app.algorithms.decomposition.wavelet import denoise_wavelet
from app.algorithms.pipelines.decomposition import (
    select_ranked_components,
    VMDDenoisingPipeline,
    EMDDenoisingPipeline,
    SensitiveComponentEnvelopePipeline,
    require_representation,
)
from app.services.diagnosis.signal_utils import denoise_signal
from app.services.diagnosis.modality_bearing import emd_bearing_analysis


class ReviewCounterexamples(unittest.TestCase):
    def test_constant_envelope_entropy_is_log2_n_including_roundoff_equivalent_inputs(
        self,
    ):
        time = np.arange(1024) / 1024
        exact = np.tile([1.0, 0.0, -1.0, 0.0], 256)
        cosine = np.cos(2 * np.pi * 256 * time)
        for signal in (exact, cosine, exact * 1e-15, cosine * 1e9):
            self.assertAlmostEqual(
                compute_component_metrics(signal, 1024).envelope_entropy, 10, places=12
            )
        tied = select_ranked_components(
            [exact, cosine], exact, 1024, weights={"env_entropy": 1}
        )
        self.assertEqual(tied.selected_indices, (0,))
        self.assertAlmostEqual(
            tied.scores[0]["score"], tied.scores[1]["score"], places=12
        )

    def test_standard_probability_entropy_prefers_am_to_constant_envelope(self):
        time = np.arange(1024) / 1024
        exact = np.tile([1.0, 0.0, -1.0, 0.0], 256)
        cosine = np.cos(2 * np.pi * 256 * time)
        am = (1 + 0.2 * np.cos(2 * np.pi * 16 * time)) * cosine
        envelope = 1 + 0.2 * np.cos(2 * np.pi * 16 * time)
        probability = envelope / envelope.sum()
        expected = -np.sum(probability * np.log2(probability))
        self.assertAlmostEqual(
            compute_component_metrics(am, 1024).envelope_entropy, expected, places=12
        )
        for carrier in (exact, cosine):
            for scale in (1.0, 1e-15, 1e9):
                selection = select_ranked_components(
                    [carrier * scale, am * scale],
                    am * scale,
                    1024,
                    weights={"env_entropy": 1},
                )
                self.assertEqual(selection.selected_indices, (1,))

    def test_preprocessing_entry_is_same_scale_stable_wavelet_implementation(self):
        signal = np.random.default_rng(4).normal(size=1024)
        original = denoise_signal(signal, "wavelet")
        small = denoise_signal(signal * 1e-15, "wavelet") / 1e-15
        self.assertLess(
            np.linalg.norm(original - small) / np.linalg.norm(original), 1e-12
        )

    def test_vmd_finite_iteration_representation_is_retained_but_not_accepted(self):
        time = np.arange(1024) / 1024
        signal = np.sin(2 * np.pi * 30 * time) + 0.6 * np.sin(2 * np.pi * 150 * time)
        pipeline = VMDDenoisingPipeline(
            VMDParameters(modes=2, max_iterations=1, max_samples=None)
        )
        analysis = pipeline.analyze(signal, 1024)
        selection = pipeline.evaluate(analysis, correlation_threshold=0)
        self.assertFalse(analysis.decomposition.converged)
        self.assertEqual(selection.status, "approximate")
        self.assertEqual(selection.quality_status, "insufficient")
        self.assertEqual(selection.reason, "maximum_iterations_reached")
        self.assertIsNotNone(selection.representation)
        with self.assertRaisesRegex(ValueError, "maximum_iterations_reached"):
            require_representation(selection)
        sensitive = SensitiveComponentEnvelopePipeline()
        envelope = sensitive.analyze(
            analysis.decomposition.modes,
            signal,
            1024,
            decomposition=analysis.decomposition,
        )
        self.assertIsNotNone(envelope.spectrum)  # 研究仍可检查近似表示
        self.assertEqual(sensitive.evaluate(envelope).status, "indeterminate")

    def test_emd_exhausted_sifts_propagate_quality_to_real_business(self):
        time = np.arange(1024) / 1024
        signal = np.sin(2 * np.pi * 30 * time) + 0.6 * np.sin(2 * np.pi * 150 * time)
        pipeline = EMDDenoisingPipeline(
            EMDParameters(max_imfs=2, max_sifts=1, sd_threshold=1e-30)
        )
        analysis = pipeline.analyze(signal, 1024)
        selection = pipeline.evaluate(analysis, correlation_threshold=0)
        self.assertEqual(selection.quality_status, "insufficient")
        self.assertEqual(selection.reason, "maximum_sifts_reached")
        # 业务入口使用默认SD阈值；加趋势保证首轮确实未达到该阈值，
        # 不把“只运行一轮但已收敛”的有效结果当成负例。
        response = emd_bearing_analysis(
            signal + np.linspace(-1, 1, 1024), 1024, max_imfs=2, max_sifts=1
        )
        self.assertEqual(response["status"], "indeterminate")
        self.assertEqual(response["quality_status"], "insufficient")
        self.assertEqual(response["reason"], "maximum_sifts_reached")
        self.assertEqual(response["envelope_amp"], [])

    def test_converged_vmd_normal_control_remains_accepted(self):
        time = np.arange(1024) / 1024
        signal = np.sin(2 * np.pi * 30 * time) + 0.6 * np.sin(2 * np.pi * 150 * time)
        pipeline = VMDDenoisingPipeline(VMDParameters(modes=2, max_iterations=500))
        analysis, selection = pipeline.run(signal, 1024, correlation_threshold=0)
        self.assertTrue(analysis.decomposition.converged)
        self.assertEqual(selection.status, "computed")
        self.assertEqual(selection.quality_status, "accepted")
        self.assertIsNone(selection.reason)


if __name__ == "__main__":
    unittest.main()
