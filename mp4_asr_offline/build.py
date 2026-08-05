from __future__ import annotations

import shutil
import subprocess
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist" / "mp4_asr_offline"


def copy_tool(name: str) -> None:
    found = find_real_tool(name)
    if not found:
        raise RuntimeError(f"未找到 {name}，请先在本机准备好 ffmpeg/ffprobe")
    shutil.copy2(found, DIST / name)


def find_real_tool(name: str) -> Path | None:
    found = shutil.which(name)
    if found:
        path = Path(found)
        if path.exists() and path.stat().st_size > 1024 * 1024:
            return path

    roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
        Path(os.environ.get("ProgramFiles", "")),
        Path(os.environ.get("ProgramFiles(x86)", "")),
    ]
    candidates: list[Path] = []
    for root in roots:
        if root.exists():
            candidates.extend(root.rglob(name))
    candidates = [p for p in candidates if p.is_file() and p.stat().st_size > 1024 * 1024]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_size)


def main() -> None:
    subprocess.run(
        [
            "pyinstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--name",
            "mp4_asr_offline",
            "--hidden-import",
            "numpy",
            "--hidden-import",
            "onnxruntime",
            "--hidden-import",
            "pydub",
            "--hidden-import",
            "audioop",
            "--hidden-import",
            "gguf",
            "--hidden-import",
            "srt",
            "--collect-all",
            "numpy",
            "--collect-all",
            "onnxruntime",
            "--collect-all",
            "pydub",
            "--collect-all",
            "gguf",
            "--hidden-import",
            "logging.handlers",
            "--hidden-import",
            "multiprocessing",
            "--hidden-import",
            "multiprocessing.queues",
            "--hidden-import",
            "multiprocessing.synchronize",
            "--hidden-import",
            "multiprocessing.spawn",
            "--hidden-import",
            "multiprocessing.context",
            "--hidden-import",
            "queue",
            "--hidden-import",
            "threading",
            str(ROOT / "mp4_asr_offline.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    DIST.mkdir(parents=True, exist_ok=True)
    copy_tool("ffmpeg.exe")
    copy_tool("ffprobe.exe")
    copy_runtime_package("numpy")
    copy_runtime_package("numpy.libs")
    copy_runtime_module("srt")
    shutil.copy2(ROOT / "config.yaml", DIST / "config.yaml")
    shutil.copy2(ROOT / "README.md", DIST / "README.md")
    print(f"便携目录已生成: {DIST}")


def copy_runtime_package(name: str) -> None:
    import importlib.util

    spec = importlib.util.find_spec(name)
    if not spec or not spec.submodule_search_locations:
        return
    src = Path(next(iter(spec.submodule_search_locations)))
    dst = DIST / "_internal" / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def copy_runtime_module(name: str) -> None:
    import importlib.util

    spec = importlib.util.find_spec(name)
    if not spec or not spec.origin:
        return
    shutil.copy2(spec.origin, DIST / "_internal" / Path(spec.origin).name)


if __name__ == "__main__":
    main()
