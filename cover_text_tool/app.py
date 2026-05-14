from __future__ import annotations

import os
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from cover_renderer import CoverOptions, SUPPORTED_IMAGE_EXTENSIONS, default_font_path, render_cover


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
ALLOWED_FONT_EXTENSIONS = {".ttf", ".ttc", ".otf"}

app = Flask(__name__)
app.secret_key = "local-cover-text-tool"
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024


@app.get("/")
def index():
    return render_template(
        "index.html",
        results=[],
        zip_name=None,
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
        flash("请先填写主标题。")
        return redirect(url_for("index"))

    selected_files = [(kind, label, file) for kind, label, file in files if file and file.filename]
    if not selected_files:
        flash("请至少上传一张图片，建议同时上传竖屏和横屏各一张。")
        return redirect(url_for("index"))

    font_path = _save_optional_font()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_id = f"{timestamp}_{uuid4().hex[:8]}"
    options = CoverOptions(
        title=form["title"],
        subtitle=form["subtitle"],
        badge=form["badge"],
        position=form["position"],
        align=form["align"],
        style=form["style"],
        text_color=form["text_color"],
        accent_color=form["accent_color"],
        title_size_percent=form["title_size_percent"],
        output_format=form["output_format"],
        font_path=str(font_path) if font_path else None,
    )

    results = []
    for kind, label, file in selected_files:
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
    return render_template(
        "index.html",
        results=results,
        zip_name=zip_name,
        default_font=font_path or default_font_path() or "Pillow default",
        form=form,
    )


@app.get("/outputs/<path:filename>")
def output_file(filename: str):
    return send_from_directory(OUTPUT_DIR, filename)


@app.get("/download/<path:filename>")
def download_file(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


def _default_form() -> dict[str, object]:
    return {
        "title": "这里输入你的封面标题",
        "subtitle": "可选副标题，比如账号定位、视频亮点或一句补充说明",
        "badge": "封面",
        "position": "bottom",
        "align": "left",
        "style": "gradient",
        "text_color": "#FFFFFF",
        "accent_color": "#FFD166",
        "title_size_percent": 8.0,
        "output_format": "png",
    }


def _read_form() -> dict[str, object]:
    form = _default_form()
    form.update(
        {
            "title": request.form.get("title", "").strip(),
            "subtitle": request.form.get("subtitle", "").strip(),
            "badge": request.form.get("badge", "").strip(),
            "position": _choice(request.form.get("position"), {"top", "center", "bottom"}, "bottom"),
            "align": _choice(request.form.get("align"), {"left", "center", "right"}, "left"),
            "style": _choice(request.form.get("style"), {"gradient", "panel", "stroke"}, "gradient"),
            "text_color": request.form.get("text_color", "#FFFFFF"),
            "accent_color": request.form.get("accent_color", "#FFD166"),
            "title_size_percent": _float_range(request.form.get("title_size_percent"), 4.0, 14.0, 8.0),
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
    font_name = f"font_{uuid4().hex[:8]}_{secure_filename(font.filename)}"
    font_path = UPLOAD_DIR / font_name
    font.save(font_path)
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
