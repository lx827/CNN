"""清单、路径和 JSON 合同；不需真实数据。"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from .common import (
    json_value,
    load_manifest,
    resolve_data_root,
    resolve_source_path,
)


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

    def test_nonfinite_json_is_null(self):
        self.assertEqual(json_value({"score": np.float64(np.nan)}), {"score": None})


if __name__ == "__main__":
    unittest.main()
