"""验收报告必须拒绝噪声、峰值回归、遗漏样本及混用身份。"""

import copy
import unittest

from .native_performance import (
    CONFIG,
    aggregate,
    cases,
    read_json,
    source_identity,
    validate_worker,
)


class PerformanceGateTests(unittest.TestCase):
    def test_source_identity_covers_shared_core_algorithms_and_bindings(self):
        hashes = source_identity()["sha256"]
        for path in (
            "lib/core/interpolation.cpp",
            "lib/core/tridiagonal.hpp",
            "lib/core/build_config.hpp.in",
            "lib/emd/sift.cpp",
            "lib/emd/CMakeLists.txt",
            "bind/arrays.cpp",
            "bind/module.cpp",
            "bind/CMakeLists.txt",
            "cnn_compute/core.py",
        ):
            self.assertIn(path, hashes)
        self.assertFalse(any(path.startswith("native/") for path in hashes))

    def setUp(self):
        self.config = read_json(CONFIG)
        self.case = cases(self.config)[2]
        self.rows = [
            {
                "backend": backend,
                "block": block,
                "seconds": [duration] * 5,
                "peak_rss_bytes": peak,
            }
            for block in range(3)
            for backend, duration, peak in (
                ("python", 1.0, 1000),
                ("native", 0.5, 1000),
            )
        ]

    def test_exact_gates_and_controlled_ceemdan_is_report_only(self):
        row = aggregate(self.config, self.case, self.rows)
        self.assertEqual(row["time_gate"], "report_only")
        self.assertIsNone(row["time_pass"])
        self.assertEqual(row["decision"], "pass")
        production = {**self.case, "profile": "production"}
        self.assertTrue(aggregate(self.config, production, self.rows)["time_pass"])
        slower = copy.deepcopy(self.rows)
        for row in slower:
            if row["backend"] == "native":
                row["seconds"] = [0.5000001] * 5
        self.assertFalse(aggregate(self.config, production, slower)["time_pass"])

    def test_one_byte_peak_regression_is_not_rounded_away(self):
        self.rows[-1]["peak_rss_bytes"] = 1001
        row = aggregate(self.config, self.case, self.rows)
        self.assertFalse(row["memory_pass"])
        self.assertEqual(row["backends"]["native"]["peak_rss_bytes"], 1001)

    def test_mad_and_between_block_noise_invalidate_cost_claim(self):
        self.rows[0]["seconds"] = [0.8, 0.9, 1, 1.1, 1.2]
        self.assertEqual(
            aggregate(self.config, self.case, self.rows)["decision"], "inconclusive"
        )
        self.rows[0]["seconds"] = [1] * 5
        self.rows[2]["seconds"] = [1.101] * 5
        self.assertIn(
            "python", aggregate(self.config, self.case, self.rows)["noisy_backends"]
        )

    def test_missing_or_duplicate_blocks_cannot_pass(self):
        with self.assertRaises(ValueError):
            aggregate(self.config, self.case, self.rows[:-1])
        self.rows[-1]["block"] = 1
        with self.assertRaises(ValueError):
            aggregate(self.config, self.case, self.rows)

    def test_emd_eemd_five_percent_boundary(self):
        for row in self.rows:
            if row["backend"] == "native":
                row["seconds"] = [1.05] * 5
        case = {**self.case, "algorithm": "eemd"}
        self.assertTrue(aggregate(self.config, case, self.rows)["time_pass"])
        for row in self.rows:
            if row["backend"] == "native":
                row["seconds"] = [1.050001] * 5
        self.assertFalse(aggregate(self.config, case, self.rows)["time_pass"])

    def test_profile_count_cannot_substitute_identity_and_case(self):
        identity, metadata = {"extension": "a"}, {"status": "valid"}
        row = {
            "case": self.case,
            "backend": "native",
            "phase": "profile",
            "identity": identity,
            "metadata": metadata,
        }
        validate_worker(row, self.case, "native", "profile", identity, metadata)
        for field, changed in (
            ("case", {}),
            ("backend", "python"),
            ("phase", "measure"),
            ("identity", {"extension": "b"}),
            ("metadata", {"status": "indeterminate"}),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_worker(
                    {**row, field: changed},
                    self.case,
                    "native",
                    "profile",
                    identity,
                    metadata,
                )


if __name__ == "__main__":
    unittest.main()
