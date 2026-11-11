"""只验证效果统计的分母与采集隔离，不重跑reader或算法正确性。"""

import unittest

from .effectiveness import aggregate_channels, summarize


class EffectivenessAccountingTests(unittest.TestCase):
    def test_unknown_and_failures_remain_in_rates(self):
        rows = [
            {"label": label, "prediction": prediction}
            for label, prediction in [
                ("healthy", "normal"),
                ("healthy", "unknown"),
                ("healthy", "anomaly"),
                ("inner_race", "anomaly"),
                ("outer_race", "unknown"),
                ("ball", "normal"),
            ]
        ]
        value = summarize(rows)
        self.assertEqual(value["record_count"], 6)
        self.assertEqual(value["detection_rate"], 1 / 3)
        self.assertEqual(value["healthy_false_alarm_rate"], 1 / 3)
        self.assertEqual(value["unknown_rate"], 2 / 6)
        self.assertEqual(
            sum(sum(v.values()) for v in value["confusion_matrix"].values()), 6
        )

    def test_channels_never_become_independent_records(self):
        channels = {
            "X": {"evaluation_status": "evaluated", "diagnosis_conclusion": "normal"},
            "Y": {
                "evaluation_status": "not_evaluable",
                "diagnosis_conclusion": "unknown",
            },
        }
        self.assertEqual(aggregate_channels(channels)["prediction"], "unknown")
        channels["Z"] = {
            "evaluation_status": "evaluated",
            "diagnosis_conclusion": "warning",
        }
        self.assertEqual(aggregate_channels(channels)["prediction"], "anomaly")
        result = summarize([{"label": "healthy", **aggregate_channels(channels)}])
        self.assertEqual(result["record_count"], 1)
        self.assertEqual(result["false_alarm_count"], 1)


if __name__ == "__main__":
    unittest.main()
