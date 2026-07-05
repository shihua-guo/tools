from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist" / "mp4_asr_offline"


def main() -> None:
    subprocess.run(
        [
            "pyinstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            "mp4_asr_webui",
            str(ROOT / "webui.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    DIST.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "dist" / "mp4_asr_webui.exe", DIST / "mp4_asr_webui.exe")
    print(f"WebUI 已生成: {DIST / 'mp4_asr_webui.exe'}")


if __name__ == "__main__":
    main()
