"""清单、路径和 runner 的失败语义；不需真实数据，也不重复算法测试。"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from .common import (
    LoadedRecord,
    json_value,
    load_manifest,
    resolve_data_root,
    resolve_source_path,
)
from .run import main, run_entries


class CommonContractTests(unittest.TestCase):
    def setUp(self):
        # 跟随显式 CNN_DATA_ROOT，最终验收的临时文件与报告均在数据盘。
        parent = resolve_data_root() / "real_diagnosis/test_tmp"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.entry = {
            "sample_id": "one",
            "dataset_id": "hust_bearing",
            "source_path": "one.xls",
            "fs_hz": 100,
            "label": "healthy",
            "fault_types": [],
            "group_id": "acquisition-one",
        }
        (self.root / "one.xls").write_text("fixture", encoding="utf-8")

    def manifest(self, samples):
        path = self.root / "manifest.json"
        path.write_text(
            json.dumps({"schema_version": 1, "samples": samples}), encoding="utf-8"
        )
        return path

    def test_root_precedence_and_source_confinement(self):
        with patch.dict(os.environ, {"CNN_DATA_ROOT": str(self.root)}):
            self.assertEqual(resolve_data_root(), self.root.resolve())
            self.assertEqual(
                resolve_data_root(self.root / "explicit"),
                (self.root / "explicit").resolve(),
            )
        self.assertEqual(
            resolve_source_path(self.root, "one.xls"), self.root / "one.xls"
        )
        for path in ("../outside.xls", str(self.root / "one.xls")):
            with self.assertRaises(ValueError):
                resolve_source_path(self.root, path)
        with self.assertRaises(FileNotFoundError):
            resolve_source_path(self.root, "missing.xls")

    def test_manifest_rejects_empty_duplicate_and_invalid_fs(self):
        self.assertEqual(load_manifest(self.manifest([self.entry])), [self.entry])
        for entries in (
            [],
            [self.entry, self.entry],
            [{**self.entry, "fs_hz": 0}],
            [{**self.entry, "fault_types": "outer"}],
        ):
            with self.assertRaises(ValueError):
                load_manifest(self.manifest(entries))

    def test_runner_counts_records_and_groups_separately_from_channels(self):
        record = LoadedRecord(
            "one",
            "hust_bearing",
            100,
            {"X": np.arange(40.0), "Y": np.arange(40.0)},
            {},
            {"block_continuity": "unknown"},
        )
        state = {
            "evaluation_status": "not_evaluable",
            "diagnosis_conclusion": "unknown",
            "health_score": None,
            "coverage": "none",
        }
        with (
            patch(
                "tests.diagnosis.real_data.run.load_record", return_value=record
            ) as loader,
            patch("tests.diagnosis.real_data.run.diagnose", return_value=state),
        ):
            report = run_entries([self.entry], self.root, window_seconds=1)
        self.assertEqual(report["loaded_record_count"], 1)
        self.assertEqual(report["acquisition_group_count"], 1)
        self.assertEqual(report["channel_result_count"], 2)
        self.assertEqual(
            report["records"][0]["channels"]["X"]["quality"]["duration_seconds"], 0.4
        )
        self.assertEqual(
            loader.call_args.args[0]["_window"],
            {"start_seconds": 0, "duration_seconds": 1},
        )

    def test_missing_record_and_channel_are_explicit_errors(self):
        report = run_entries([{**self.entry, "source_path": "missing.xls"}], self.root)
        self.assertEqual(report["loaded_record_count"], 0)
        self.assertEqual(report["error_count"], 1)
        record = LoadedRecord(
            "one", "hust_bearing", 100, {"X": np.arange(40.0)}, {}, {}
        )
        with patch("tests.diagnosis.real_data.run.load_record", return_value=record):
            report = run_entries([self.entry], self.root, channels=["Z"])
        self.assertEqual(report["error_count"], 1)

    def test_window_bounds_and_nonfinite_json(self):
        for seconds in (0, 5.01, float("nan")):
            with self.assertRaises(ValueError):
                run_entries([self.entry], self.root, window_seconds=seconds)
        self.assertEqual(json_value({"score": np.float64(np.nan)}), {"score": None})

    def test_cli_explicit_missing_selection_is_nonzero(self):
        manifest = self.manifest([self.entry])
        output = self.root / "report.json"
        with contextlib.redirect_stderr(io.StringIO()):
            code = main(
                [
                    "--data-root",
                    str(self.root),
                    "--manifest",
                    str(manifest),
                    "--sample-id",
                    "not-present",
                    "--output",
                    str(output),
                ]
            )
        self.assertEqual(code, 1)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
