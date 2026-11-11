"""齿轮原数据reader契约；小型格式反例与可选本地五记录验收。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat, whosmat

from .common import resolve_data_root
from .gear import load_record


class GearLoaderTests(unittest.TestCase):
    def setUp(self):
        # 所有临时样本也在统一data目录，不使用系统C盘TEMP。
        data_root = resolve_data_root()
        data_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="gear_loader_", dir=data_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _mat(self, **changes):
        data = np.arange(80, dtype=float).reshape(20, 4)
        content = {"Data": data, "DataCount": 20., "ChannelCount": 4.,
                   "SampleRate": 10., "Interval": .1}
        content.update(changes)
        savemat(self.root / "record.mat", content, do_compression=False)
        return {"sample_id": "synthetic", "dataset_id": "wt_planetary",
                "source_path": "record.mat", "fs_hz": 10}, data

    def test_mat_window_preserves_encoder_and_unknown_channel(self):
        entry, expected = self._mat()
        entry["_window"] = {"start_seconds": .5, "duration_seconds": .3}
        record = load_record(entry, self.root)
        np.testing.assert_array_equal(record.vibration["X"], expected[5:8, 0])
        np.testing.assert_array_equal(record.vibration["Y"], expected[5:8, 1])
        np.testing.assert_array_equal(record.auxiliary["encoder"], expected[5:8, 2])
        np.testing.assert_array_equal(record.auxiliary["raw_channel_4"], expected[5:8, 3])
        self.assertEqual(record.metadata["full_sample_count"], 20)
        self.assertEqual(record.metadata["loaded_start_seconds"], .5)

    def test_mat_rejects_false_sampling_metadata_and_truncation(self):
        entry, _ = self._mat(SampleRate=12.)
        with self.assertRaisesRegex(ValueError, "SampleRate/Interval"):
            load_record(entry, self.root)
        entry, _ = self._mat()
        path = self.root / "record.mat"
        path.write_bytes(path.read_bytes()[:-10])
        with self.assertRaisesRegex(ValueError, "Truncated"):
            load_record(entry, self.root)

    def test_mat_rejects_compression_and_wrong_channel_semantics(self):
        entry, _ = self._mat(ChannelCount=3.)
        with self.assertRaisesRegex(ValueError, "four-channel"):
            load_record(entry, self.root)
        savemat(self.root / "record.mat", {"Data": np.zeros((20, 4))}, do_compression=True)
        with self.assertRaisesRegex(ValueError, "uncompressed"):
            load_record(entry, self.root)

    def test_hust_never_joins_timestamp_reset_blocks(self):
        path = self.root / "hust.txt"
        with path.open("w", encoding="utf-8") as stream:
            stream.write("Number of Blocks\t2\nTotal Data Rows\t8\n")
            stream.write("Time (seconds) and Data Channels\n")
            for index in range(8):
                stream.write(f"{index % 4 / 10}\t{100+index}\t{index}\t{index+1}\t{index+2}\n")
        entry = {"sample_id": "synthetic_hust", "dataset_id": "hust_gearbox",
                 "source_path": "hust.txt", "fs_hz": 10}
        first = load_record(entry, self.root)
        self.assertEqual(first.vibration["X"].size, 4)
        self.assertEqual(first.metadata["block_continuity"], "unknown")
        entry["_window"] = {"start_seconds": .6, "duration_seconds": 1}
        second = load_record(entry, self.root)
        np.testing.assert_array_equal(second.vibration["X"], [6, 7])
        np.testing.assert_array_equal(second.auxiliary["time"], [.2, .3])
        np.testing.assert_array_equal(second.auxiliary["speed"], [106, 107])

    def test_window_and_source_path_cannot_escape_limits(self):
        entry, _ = self._mat()
        entry["_window"] = {"duration_seconds": 5.1}
        with self.assertRaises(ValueError):
            load_record(entry, self.root)
        entry["source_path"] = "../outside.mat"
        with self.assertRaisesRegex(ValueError, "within data_root"):
            load_record(entry, self.root)


class LocalGearAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = resolve_data_root()
        manifest = cls.root / "real_diagnosis" / "gear_manifest.json"
        if not manifest.exists():
            raise unittest.SkipTest("Local raw gear manifest not installed")
        cls.entries = json.loads(manifest.read_text(encoding="utf-8"))["samples"]

    def test_five_local_records_match_verified_metadata_and_values(self):
        self.assertEqual(len(self.entries), 5)
        for entry in self.entries:
            with self.subTest(sample=entry["sample_id"]):
                record = load_record(entry, self.root)
                actual_first = ([record.auxiliary["time"][0], record.auxiliary["speed"][0]]
                                + [record.vibration[key][0] for key in ("X", "Y", "Z")]
                                if entry["dataset_id"] == "hust_gearbox" else
                                [record.vibration["X"][0], record.vibration["Y"][0],
                                 record.auxiliary["encoder"][0], record.auxiliary["raw_channel_4"][0]])
                np.testing.assert_allclose(actual_first, entry["verification"]["first_row"], rtol=1e-12, atol=1e-12)
                self.assertEqual(record.metadata["source_shape"], entry["verification"]["source_shape"])
                self.assertEqual(record.sample_rate_hz, entry["fs_hz"])
                expected_count = 32768 if entry["dataset_id"] == "hust_gearbox" else 240000
                self.assertEqual(len(record.vibration["X"]), expected_count)
                if entry["dataset_id"] == "wt_planetary":
                    variables = {name: shape for name, shape, _ in whosmat(self.root / entry["source_path"])}
                    self.assertEqual(list(variables["Data"]), entry["verification"]["source_shape"])
                    self.assertEqual(record.metadata["mat_scalars"], entry["verification"]["mat_scalars"])

    def test_one_real_mat_against_scipy_reference_once(self):
        # 只对健康MAT做一次独立scipy参考读取，顺序释放，不跑整记录算法。
        entry = next(e for e in self.entries if e["sample_id"] == "wt_N1_20")
        record = load_record(entry, self.root)
        reference = loadmat(self.root / entry["source_path"], variable_names=["Data"])["Data"]
        self.assertEqual(list(reference.shape), record.metadata["source_shape"])
        for key, column in (("X", 0), ("Y", 1)):
            np.testing.assert_array_equal(record.vibration[key], reference[:240000, column])
        for key, column in (("encoder", 2), ("raw_channel_4", 3)):
            np.testing.assert_array_equal(record.auxiliary[key], reference[:240000, column])
        del reference


if __name__ == "__main__":
    unittest.main()
