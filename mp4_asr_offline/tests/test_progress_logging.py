from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CLI = load_module("mp4_asr_offline_progress_test", "mp4_asr_offline.py")
WEBUI = load_module("mp4_asr_offline_webui_progress_test", "webui.py")


class ProgressLoggingTest(unittest.TestCase):
    def test_reset_progress_discards_previous_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = CLI.AppConfig(output_dir=Path(temp_dir))
            path = CLI.progress_path(cfg)
            path.write_text('{"status":"old"}\n', encoding="utf-8")

            CLI.reset_progress(cfg)
            CLI.append_progress(cfg, {"status": "queued"})

            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "queued")

    def test_webui_restarts_reading_after_progress_file_is_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "progress.jsonl"
            path.write_text('{"status":"old","padding":"xxxxxxxxxxxxxxxx"}\n', encoding="utf-8")
            state = WEBUI.JobState()
            state.progress_path = path
            state.progress_offset = path.stat().st_size

            path.write_text('{"status":"queued"}\n', encoding="utf-8")
            state._read_progress()

            self.assertEqual(state.records, [{"status": "queued"}])
            self.assertEqual(state.progress_offset, path.stat().st_size)


if __name__ == "__main__":
    unittest.main()
