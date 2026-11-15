"""运行：CNN_DATA_ROOT指定数据根后 uv run python -m unittest tests.diagnosis.real_data.test_bearing。"""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import savemat

from .bearing import load_record
from .common import resolve_data_root


class BearingFormatTests(unittest.TestCase):
    def setUp(self):
        root = resolve_data_root()
        if not root.is_dir():
            self.skipTest("Local data root unavailable; set CNN_DATA_ROOT")
        temp_root = root / "_reader_test_tmp"
        temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="bearing_", dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def entry(self, dataset, filename, count):
        return {
            "sample_id": "fixture",
            "dataset_id": dataset,
            "source_path": filename,
            "fs_hz": 200000 if dataset == "ottawa_bearing" else 25600,
            "expected_samples": count,
            "group_id": "one-acquisition",
            "fault_types": [],
        }

    def write_tsv(self, *, legend="Speed\tX\tY\tZ", speed=(0.1, 4.9, 0.2, 5.0)):
        path = self.root / "H_20Hz.xls"
        rows = [
            f"{index / 25600:.6f}\t{value}\t1\t2\t3"
            for index, value in enumerate(speed)
        ]
        path.write_text(
            "Title:\tH_20Hz\nFrequency Limit\t10000\nTotal Data Rows\t4\nLegend\t"
            + legend
            + "\nData\n"
            + "\n".join(rows)
            + "\n",
            encoding="utf-8",
        )
        return path.name

    def test_ottawa_preserves_both_raw_channels_and_sampling_rate(self):
        path = self.root / "H-A-1.mat"
        vibration = np.array([0.02, -0.03, 0.01, 0.04])[:, None]
        encoder = np.array([4.2, 0.025, 4.1, 0.037])[:, None]
        savemat(path, {"Channel_1": vibration, "Channel_2": encoder})
        record = load_record(self.entry("ottawa_bearing", path.name, 4), self.root)
        np.testing.assert_array_equal(record.vibration["Channel_1"], vibration[:, 0])
        np.testing.assert_array_equal(record.auxiliary["Channel_2"], encoder[:, 0])
        self.assertEqual(record.sample_rate_hz, 200000)
        self.assertEqual(record.metadata["duration_seconds"], 4 / 200000)
        self.assertFalse(record.metadata["auxiliary_is_calibrated_speed_hz"])

    def test_hust_text_xls_keeps_xyz_time_and_electrical_speed(self):
        entry = self.entry("hust_bearing", self.write_tsv(), 4)
        record = load_record(entry, self.root)
        self.assertEqual(set(record.vibration), {"X", "Y", "Z"})
        self.assertEqual(set(record.auxiliary), {"time", "Speed"})
        np.testing.assert_array_equal(record.auxiliary["Speed"], [0.1, 4.9, 0.2, 5.0])
        self.assertEqual(record.sample_rate_hz, 25600)  # Frequency Limit不是fs。
        self.assertFalse(record.metadata["auxiliary_is_calibrated_speed_hz"])
        self.assertEqual(record.metadata["group_id"], "one-acquisition")

    def test_hust_rejects_wrong_columns_and_count(self):
        filename = self.write_tsv(legend="X\tSpeed\tY\tZ")
        with self.assertRaisesRegex(ValueError, "legend"):
            load_record(self.entry("hust_bearing", filename, 4), self.root)
        filename = self.write_tsv()
        with self.assertRaisesRegex(ValueError, "Expected 5"):
            load_record(self.entry("hust_bearing", filename, 5), self.root)

    def test_window_keeps_original_sample_grid_and_raw_speed(self):
        entry = self.entry("hust_bearing", self.write_tsv(), 4)
        entry["_window"] = {"start_seconds": 1 / 25600, "duration_seconds": 2 / 25600}
        record = load_record(entry, self.root)
        np.testing.assert_array_equal(record.auxiliary["Speed"], [4.9, 0.2])
        self.assertEqual(record.metadata["full_sample_count"], 4)
        self.assertEqual(record.metadata["n_samples"], 2)
        self.assertEqual(record.metadata["loaded_start_seconds"], 1 / 25600)
        self.assertEqual(record.sample_rate_hz, 25600)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            load_record(
                {
                    **entry,
                    "_window": {"start_seconds": 0, "duration_seconds": 5 / 25600},
                },
                self.root,
            )

    def test_rejects_wrong_rate_escaping_path_and_nonfinite_signals(self):
        entry = self.entry("hust_bearing", self.write_tsv(), 4)
        with self.assertRaisesRegex(ValueError, "sample rate"):
            load_record({**entry, "fs_hz": 10000}, self.root)
        with self.assertRaisesRegex(ValueError, "escapes data_root"):
            load_record({**entry, "source_path": "../H_20Hz.xls"}, self.root)
        self.write_tsv(speed=[0.1, float("nan"), 0.2, 5.0])
        with self.assertRaisesRegex(ValueError, "finite"):
            load_record(entry, self.root)


class LocalBearingRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = resolve_data_root()
        manifest = Path(__file__).parent / "manifests/bearing.json"
        cls.entries = json.loads(manifest.read_text(encoding="utf-8-sig"))["samples"]
        if not all(
            (cls.root / entry["source_path"]).is_file() for entry in cls.entries
        ):
            raise unittest.SkipTest(
                "Selected raw bearing records unavailable; set CNN_DATA_ROOT"
            )

    def test_selected_real_records_have_original_duration_and_channels(self):
        self.assertEqual(len(self.entries), 11)
        self.assertEqual(len({entry["group_id"] for entry in self.entries}), 11)
        for entry in self.entries:
            with self.subTest(sample=entry["sample_id"]):
                record = load_record(entry, self.root)
                self.assertEqual(
                    record.metadata["n_samples"], entry["expected_samples"]
                )
                self.assertEqual(
                    record.metadata["duration_seconds"],
                    entry["expected_duration_seconds"],
                )
                self.assertEqual(record.sample_rate_hz, entry["fs_hz"])
                self.assertFalse(record.metadata["resampled"])
                self.assertFalse(record.metadata["auxiliary_is_calibrated_speed_hz"])
                self.assertIn("unknown", record.metadata["speed_unit"])
                if entry["dataset_id"] == "ottawa_bearing":
                    self.assertEqual(set(record.vibration), {"Channel_1"})
                    self.assertEqual(set(record.auxiliary), {"Channel_2"})
                else:
                    self.assertEqual(set(record.vibration), {"X", "Y", "Z"})
                    self.assertEqual(set(record.auxiliary), {"time", "Speed"})
                    self.assertLess(float(np.max(record.auxiliary["Speed"])), 10)
                    self.assertAlmostEqual(
                        float(record.auxiliary["time"][-1]),
                        (262144 - 1) / 25600,
                        places=6,
                    )


if __name__ == "__main__":
    unittest.main()
