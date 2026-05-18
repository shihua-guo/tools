import os
import sys
from pathlib import Path


def main():
    project_dir = Path(__file__).resolve().parent
    entry_file = project_dir / "build_entry.py"
    icon_file = project_dir / "assets" / "app.ico"

    try:
        import PyInstaller.__main__
    except ImportError:
        print("PyInstaller is not installed. Run: pip install -r requirements.txt")
        return 1

    entry_file.write_text(
        "from src.main import ReminderApp\n\n"
        "if __name__ == '__main__':\n"
        "    ReminderApp().run()\n",
        encoding="utf-8",
    )

    args = [
        str(entry_file),
        "--name=Windows-Reminder",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        f"--paths={project_dir}",
        "--collect-all=PySide6",
        "--hidden-import=keyboard",
        f"--distpath={project_dir / 'dist'}",
        f"--workpath={project_dir / 'build'}",
        f"--specpath={project_dir / 'build'}",
    ]

    if icon_file.exists():
        args.append(f"--icon={icon_file}")
        args.append(f"--add-data={icon_file}{os.pathsep}assets")

    try:
        PyInstaller.__main__.run(args)
    finally:
        try:
            entry_file.unlink()
        except FileNotFoundError:
            pass

    exe_path = project_dir / "dist" / "Windows-Reminder.exe"
    print(f"Build complete: {exe_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
