from __future__ import annotations

import json
import io
import os
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, send_file, send_from_directory, url_for
from PIL import Image, ImageFont, ImageOps
from werkzeug.utils import secure_filename

from cover_renderer import CoverOptions, SUPPORTED_IMAGE_EXTENSIONS, default_font_path, render_cover


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
HISTORY_PATH = OUTPUT_DIR / "history.json"
ALLOWED_FONT_EXTENSIONS = {".ttf", ".ttc", ".otf"}
MAX_HISTORY_ITEMS = 50

app = Flask(__name__)
app.secret_key = "local-cover-text-tool"
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024


@app.get("/")
def index():
    return render_template(
        "index.html",
        results=[],
        zip_name=None,
        history=_load_history(),
        default_font=default_font_path() or "Pillow default",
        form=_default_form(),
    )


@app.post("/generate")
def generate():
    form = _read_form()
    files = [
        ("vertical", "竖屏封面", request.files.get("vertical_image")),
        ("horizontal", "横屏封面", request.files.get("horizontal_image")),
    ]

    if not form["title"]:
        flash("请先填写封面文字。")
        return redirect(url_for("index"))

    selected_files = [(kind, label, file) for kind, label, file in files if file and file.filename]
    if not selected_files:
        flash("请至少上传一张图片，建议同时上传竖屏和横屏各一张。")
        return redirect(url_for("index"))

    font_path = _save_optional_font()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_id = f"{timestamp}_{uuid4().hex[:8]}"
    results = []
    for kind, label, file in selected_files:
        options = CoverOptions(
            title=form["title"],
            subtitle="",
            badge="",
            position="custom",
            align="left",
            style=form["style"],
            text_color=form["text_color"],
            accent_color=form["accent_color"],
            title_size_percent=form["title_size_percent"],
            text_x_percent=form[f"{kind}_text_x"],
            text_y_percent=form[f"{kind}_text_y"],
            output_format=form["output_format"],
            font_path=str(font_path) if font_path else None,
        )
        source_path = _save_upload(file, batch_id, kind)
        output_ext = "jpg" if options.output_format == "jpg" else "png"
        output_name = f"{source_path.stem}_cover.{output_ext}"
        output_path = OUTPUT_DIR / output_name
        render_cover(source_path, output_path, options)
        results.append(
            {
                "label": label,
                "name": output_name,
                "url": url_for("output_file", filename=output_name),
                "download_url": url_for("download_file", filename=output_name),
            }
        )

    zip_name = _make_zip(results, batch_id) if len(results) > 1 else None
    history = _record_history(
        {
            "id": batch_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "title": _history_title(form["title"]),
            "subtitle": "",
            "badge": "",
            "zip_name": zip_name,
            "items": [
                {
                    "label": result["label"],
                    "name": result["name"],
                }
                for result in results
            ],
        }
    )
    return render_template(
        "index.html",
        results=results,
        zip_name=zip_name,
        history=history,
        default_font=font_path or default_font_path() or "Pillow default",
        form=form,
    )


@app.get("/outputs/<path:filename>")
def output_file(filename: str):
    return send_from_directory(OUTPUT_DIR, filename)


@app.get("/download/<path:filename>")
def download_file(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


@app.post("/preview-image")
def preview_image():
    file = request.files.get("image")
    if not file or not file.filename:
        return "没有收到图片文件。", 400

    extension = Path(file.filename).suffix.lower()
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        return f"不支持的图片格式: {extension}", 400

    try:
        image = Image.open(file.stream)
        image = ImageOps.exif_transpose(image).convert("RGB")
    except OSError:
        return "图片读取失败，请确认文件没有损坏。", 400

    image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


def _default_form() -> dict[str, object]:
    return {
        "title": "这里输入你的封面文字\n支持手动换行",
        "position": "bottom",
        "align": "left",
        "style": "gradient",
        "text_color": "#FFFFFF",
        "accent_color": "#FFD166",
        "title_size_percent": 8.0,
        "vertical_text_x": 8.0,
        "vertical_text_y": 68.0,
        "horizontal_text_x": 8.0,
        "horizontal_text_y": 58.0,
        "output_format": "png",
    }


def _read_form() -> dict[str, object]:
    form = _default_form()
    form.update(
        {
            "title": request.form.get("title", "").strip(),
            "position": _choice(request.form.get("position"), {"top", "center", "bottom"}, "bottom"),
            "align": _choice(request.form.get("align"), {"left", "center", "right"}, "left"),
            "style": _choice(request.form.get("style"), {"gradient", "panel", "stroke"}, "gradient"),
            "text_color": request.form.get("text_color", "#FFFFFF"),
            "accent_color": request.form.get("accent_color", "#FFD166"),
            "title_size_percent": _float_range(request.form.get("title_size_percent"), 4.0, 14.0, 8.0),
            "vertical_text_x": _float_range(request.form.get("vertical_text_x"), 0.0, 100.0, 8.0),
            "vertical_text_y": _float_range(request.form.get("vertical_text_y"), 0.0, 100.0, 68.0),
            "horizontal_text_x": _float_range(request.form.get("horizontal_text_x"), 0.0, 100.0, 8.0),
            "horizontal_text_y": _float_range(request.form.get("horizontal_text_y"), 0.0, 100.0, 58.0),
            "output_format": _choice(request.form.get("output_format"), {"png", "jpg"}, "png"),
        }
    )
    return form


def _save_optional_font() -> Path | None:
    font = request.files.get("font_file")
    if not font or not font.filename:
        return None
    extension = Path(font.filename).suffix.lower()
    if extension not in ALLOWED_FONT_EXTENSIONS:
        flash("字体文件只支持 .ttf / .ttc / .otf，本次已使用默认字体。")
        return None
    safe_stem = secure_filename(Path(font.filename).stem) or "custom_font"
    font_name = f"font_{uuid4().hex[:8]}_{safe_stem}{extension}"
    font_path = UPLOAD_DIR / font_name
    font.save(font_path)
    try:
        ImageFont.truetype(str(font_path), size=32)
    except OSError:
        font_path.unlink(missing_ok=True)
        flash("这个字体文件暂时无法被图片生成器读取，本次已使用默认字体。")
        return None
    return font_path


def _save_upload(file, batch_id: str, kind: str) -> Path:
    extension = Path(file.filename).suffix.lower()
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"不支持的图片格式: {extension}")
    safe_name = secure_filename(Path(file.filename).stem) or kind
    target = UPLOAD_DIR / f"{batch_id}_{kind}_{safe_name}{extension}"
    file.save(target)
    return target


def _make_zip(results: list[dict[str, str]], batch_id: str) -> str:
    zip_name = f"covers_{batch_id}.zip"
    zip_path = OUTPUT_DIR / zip_name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for result in results:
            archive.write(OUTPUT_DIR / result["name"], result["name"])
    return zip_name


def _load_history() -> list[dict[str, object]]:
    recorded_names: set[str] = set()
    history: list[dict[str, object]] = []
    if not HISTORY_PATH.exists():
        return _history_from_existing_outputs(recorded_names)[:MAX_HISTORY_ITEMS]

    try:
        raw_history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw_history = []
    if not isinstance(raw_history, list):
        raw_history = []

    for entry in raw_history:
        if not isinstance(entry, dict):
            continue
        items = []
        for item in entry.get("items", []):
            if not isinstance(item, dict):
                continue
            name = item.get("name", "")
            if not name or not (OUTPUT_DIR / name).exists():
                continue
            recorded_names.add(name)
            items.append(
                {
                    "label": item.get("label", "封面"),
                    "name": name,
                    "url": url_for("output_file", filename=name),
                    "download_url": url_for("download_file", filename=name),
                }
            )

        if not items:
            continue

        zip_name = entry.get("zip_name")
        zip_url = None
        if zip_name and (OUTPUT_DIR / zip_name).exists():
            zip_url = url_for("download_file", filename=zip_name)

        history.append(
            {
                "id": entry.get("id", ""),
                "created_at": entry.get("created_at", ""),
                "title": entry.get("title", ""),
                "subtitle": entry.get("subtitle", ""),
                "badge": entry.get("badge", ""),
                "zip_url": zip_url,
                "items": items,
            }
        )

    history.extend(_history_from_existing_outputs(recorded_names))
    return history[:MAX_HISTORY_ITEMS]


def _record_history(entry: dict[str, object]) -> list[dict[str, object]]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_history = []
    if HISTORY_PATH.exists():
        try:
            raw_history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw_history = []
    if not isinstance(raw_history, list):
        raw_history = []

    raw_history.insert(0, entry)
    raw_history = raw_history[:MAX_HISTORY_ITEMS]
    temp_path = HISTORY_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(raw_history, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(HISTORY_PATH)
    return _load_history()


def _history_from_existing_outputs(recorded_names: set[str]) -> list[dict[str, object]]:
    if not OUTPUT_DIR.exists():
        return []

    batches: dict[str, dict[str, object]] = {}
    for output_path in sorted(OUTPUT_DIR.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True):
        if output_path.name in recorded_names or not _is_cover_output(output_path):
            continue

        batch_id = _batch_id_from_output_name(output_path.name)
        created_at = datetime.fromtimestamp(output_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        batch = batches.setdefault(
            batch_id,
            {
                "id": batch_id,
                "created_at": created_at,
                "title": f"旧生成文件 {created_at}",
                "subtitle": "",
                "badge": "",
                "zip_url": None,
                "items": [],
            },
        )
        batch["items"].append(
            {
                "label": _label_from_output_name(output_path.name),
                "name": output_path.name,
                "url": url_for("output_file", filename=output_path.name),
                "download_url": url_for("download_file", filename=output_path.name),
            }
        )

        zip_name = f"covers_{batch_id}.zip"
        if (OUTPUT_DIR / zip_name).exists():
            batch["zip_url"] = url_for("download_file", filename=zip_name)

    return list(batches.values())


def _is_cover_output(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and "_cover" in path.stem


def _batch_id_from_output_name(filename: str) -> str:
    parts = filename.split("_")
    if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
        return "_".join(parts[:3])
    return Path(filename).stem


def _label_from_output_name(filename: str) -> str:
    lowered = filename.lower()
    if "_vertical_" in lowered:
        return "竖屏封面"
    if "_horizontal_" in lowered:
        return "横屏封面"
    return "封面"


def _history_title(text: str) -> str:
    cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if not cleaned:
        return "未命名封面"
    return cleaned[:48] + ("..." if len(cleaned) > 48 else "")


def _choice(value: str | None, allowed: set[str], default: str) -> str:
    return value if value in allowed else default


def _float_range(value: str | None, minimum: float, maximum: float, default: float) -> float:
    try:
        parsed = float(value or default)
    except ValueError:
        return default
    return min(max(parsed, minimum), maximum)


@app.errorhandler(ValueError)
def handle_value_error(error: ValueError):
    flash(str(error))
    return redirect(url_for("index"))


if __name__ == "__main__":
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "7860")), debug=False)
