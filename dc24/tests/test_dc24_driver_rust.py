"""Rust 可选驱动经公共接口进入现有单次采集宿主的回环契约。"""

import csv
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dc24"))
sys.path.insert(0, str(ROOT / "dc24/tests"))

from dc24_capture import create_driver, record
from test_dc24_edge_pi import data_frame, free_port, run_fake_device


class RustDriverInterfaceTests(unittest.TestCase):
    def test_record_receives_original_frames_and_int32_samples(self):
        port = free_port()
        errors = []
        device = threading.Thread(
            target=run_fake_device, args=(port, errors, 0.001), daemon=True
        )
        device.start()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "record"
            with patch.dict(os.environ, {"DC24_DRIVER": "rust"}):
                driver = create_driver(host="127.0.0.1", peer="127.0.0.1", port=port)
                metadata = record(
                    output,
                    0.05,
                    host="127.0.0.1",
                    peer="127.0.0.1",
                    sample_rate=1000,
                    driver=driver,
                )
            device.join(timeout=5)
            self.assertEqual(errors, [])
            self.assertEqual(metadata["transport"], "rust_tcp")
            self.assertTrue(metadata["complete"])
            self.assertEqual(metadata["samples_per_channel"], 254)
            self.assertEqual((output / "rx_stream.bin").read_bytes(), data_frame(0))
            with (output / "samples.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 254)
            self.assertEqual(
                [int(rows[0][f"ch{channel}_counts"]) for channel in range(4)],
                [-8388608, 8388607, -1, 12345],
            )
            events = (output / "commands.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertTrue(events)
            self.assertTrue(all(json.loads(line)["direction"] for line in events))


if __name__ == "__main__":
    unittest.main()
