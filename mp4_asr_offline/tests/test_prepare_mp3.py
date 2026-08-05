from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "mp4_asr_offline.py"
MODULE_NAME = "mp4_asr_offline_module"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeProcess:
    def __init__(self) -> None:
        self.stdout = iter(())
        self.returncode = 0

    def communicate(self) -> tuple[None, None]:
        return None, None


class PrepareMp3Test(unittest.TestCase):
    def test_ffmpeg_normalizes_audio_before_asr_loading(self) -> None:
        cfg = MODULE.AppConfig(output_dir=Path("output"), overwrite=True)
        video = Path("input.mp4")
        mp3_path = Path("output/input.mp3")
        process = FakeProcess()

        with (
            patch.object(MODULE, "get_duration", return_value=60.0),
            patch.object(MODULE, "tool_path", side_effect=lambda name: name),
            patch.object(MODULE, "append_progress"),
            patch.object(MODULE.subprocess, "Popen", return_value=process) as popen,
        ):
            MODULE.prepare_mp3(cfg, video, mp3_path)

        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("-ac") + 1], "1")
        self.assertEqual(command[command.index("-ar") + 1], "16000")


if __name__ == "__main__":
    unittest.main()
