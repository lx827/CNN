"""验证 HUSTbear 的分类、真实三轴映射和上传前的设备归属检查。"""
import os
import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "edge"))
import edge_client as edge
import replay


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset_env = patch.dict(os.environ, {"REPLAY_DATASET": "hustbear"})
        cls.dataset_env.start()
        importlib.reload(edge)

    @classmethod
    def tearDownClass(cls):
        cls.dataset_env.stop()
        importlib.reload(edge)

    def test_axis_mapping_preserves_each_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            for axis, value in [("X", 1), ("Y", 2), ("Z", 3)]:
                np.save(Path(directory) / f"0.5X_I_20Hz-{axis}.npy", np.full(8192, value))
            groups = edge.scan_data_groups(directory)
            signals = edge.load_group_data(groups, "0.5X_I_20Hz", 1, 3)
            self.assertEqual(set(signals), {"ch1", "ch2", "ch3"})
            for index in range(1, 4):
                self.assertTrue(all(v == index for v in signals[f"ch{index}"]))

    def test_fault_tokens_do_not_confuse_load_with_label(self):
        groups = {name: {} for name in ["0.5X_I_20Hz", "IR_VS_0_40_0Hz", "H_20Hz", "N_20Hz", "B_20Hz", "C_20Hz", "OR_20Hz", "0.5X_O_20Hz"]}
        self.assertEqual(edge.matching_groups(groups, edge.HUSTBEAR_DATA_DIR, "inner"), ["0.5X_I_20Hz", "IR_VS_0_40_0Hz"])
        self.assertEqual(edge.matching_groups(groups, edge.HUSTBEAR_DATA_DIR, "healthy"), ["H_20Hz", "N_20Hz"])
        self.assertEqual(edge.matching_groups(groups, edge.HUSTBEAR_DATA_DIR, "outer"), ["OR_20Hz", "0.5X_O_20Hz"])
        self.assertTrue(all(dev.startswith("HUST-") for dev in edge.DEVICE_IDS))

    def test_missing_or_mismatched_cloud_device_blocks_upload(self):
        response = Mock()
        response.json.return_value = {"data": []}
        with patch.object(edge.requests, "get", return_value=response):
            with self.assertRaisesRegex(ValueError, "缺少 HUST-001"):
                replay.check_cloud(edge)
            response.json.return_value = {"data": [{"device_id": "HUST-001", "bearing_params": {"n": 1}}]}
            with self.assertRaisesRegex(ValueError, "不匹配"):
                replay.check_cloud(edge)

    def test_registered_hustbear_devices_pass_preflight(self):
        response = Mock()
        response.json.return_value = {"data": [
            {"device_id": dev, "bearing_params": replay.HUST_PARAMS.copy(),
             "gear_teeth": None, "channel_names": {"1": "X", "2": "Y", "3": "Z"},
             "sample_rate": 8192, "channel_count": 3}
            for dev in edge.DEVICE_IDS
        ]}
        with patch.object(edge.requests, "get", return_value=response):
            replay.check_cloud(edge)

    def test_incomplete_axes_rejected_before_padding(self):
        with tempfile.TemporaryDirectory() as directory:
            np.save(Path(directory) / "I_20Hz-X.npy", np.ones(8192))
            with patch.object(edge, "DEVICE_DATA_MAP", {"HUST-003": (directory, "inner", 3)}), patch.object(edge, "HUSTBEAR_DATA_DIR", directory):
                with self.assertRaisesRegex(ValueError, "完整通道"):
                    replay.check_data(edge)


if __name__ == "__main__":
    unittest.main()
