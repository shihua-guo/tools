from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import subprocess
import hashlib
import sqlite3
from pathlib import Path
from datetime import datetime

from asr import ASRProcessor
from llm import LLMProcessor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = Path(__file__).resolve().parent

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VIDEO_ROOT = Path(os.environ.get("VIDEO_ROOT", PROJECT_ROOT / "videos")).resolve()
OUTPUT_ROOT = Path(os.environ.get("OUTPUT_ROOT", BACKEND_ROOT / "output")).resolve()
DB_PATH = Path(os.environ.get("TASK_DB_PATH", BACKEND_ROOT / "tasks.db")).resolve()

VIDEO_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


class TaskCreateReq(BaseModel):
    video_path: str


class TaskStepReq(BaseModel):
    style: str = "小红书"
    generate_content: bool = True
    generate_titles: bool = False
    generate_cover_prompt: bool = False


def now_str():
    return datetime.utcnow().isoformat()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_task_columns(conn):
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    required = {
        "titles_text": "TEXT",
        "cover_prompt": "TEXT",
        "llm_enabled": "INTEGER DEFAULT 0",
        "generate_content": "INTEGER DEFAULT 0",
        "generate_titles": "INTEGER DEFAULT 0",
        "generate_cover_prompt": "INTEGER DEFAULT 0",
    }
    for name, column_type in required.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {column_type}")


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            video_path TEXT NOT NULL,
            filename TEXT NOT NULL,
            status TEXT NOT NULL,
            audio_path TEXT,
            transcript_path TEXT,
            refined_path TEXT,
            asr_text TEXT,
            polished_text TEXT,
            titles_text TEXT,
            cover_prompt TEXT,
            style TEXT,
            llm_enabled INTEGER DEFAULT 0,
            generate_content INTEGER DEFAULT 0,
            generate_titles INTEGER DEFAULT 0,
            generate_cover_prompt INTEGER DEFAULT 0,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    ensure_task_columns(conn)
    conn.commit()
    conn.close()


def file_md5(path: Path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


asr_processor = None
llm_processor = None


def get_asr():
    global asr_processor
    if asr_processor is None:
        asr_processor = ASRProcessor(
            str(BACKEND_ROOT / "models" / "paraformer-offline-zh"),
            str(BACKEND_ROOT / "models" / "punc_ct-transformer_cn-en")
        )
    return asr_processor


def get_llm():
    global llm_processor
    if llm_processor is None:
        api_key = os.environ.get("QWEN_API_KEY")
        if not api_key:
            raise Exception("QWEN_API_KEY not set")
        llm_processor = LLMProcessor(api_key)
    return llm_processor


def get_task(task_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    conn.close()
    return row


def update_task(task_id: str, **kwargs):
    if not kwargs:
        return
    kwargs["updated_at"] = now_str()
    keys = list(kwargs.keys())
    values = [kwargs[k] for k in keys]
    set_sql = ", ".join([f"{k}=?" for k in keys])
    conn = get_conn()
    conn.execute(f"UPDATE tasks SET {set_sql} WHERE task_id=?", (*values, task_id))
    conn.commit()
    conn.close()


def resolve_video_path(relative_path: str) -> Path:
    full_path = (VIDEO_ROOT / relative_path).resolve()
    if full_path != VIDEO_ROOT and VIDEO_ROOT not in full_path.parents:
        raise HTTPException(status_code=400, detail="invalid video path")
    return full_path


def build_refined_markdown(style: str, content: str, titles: str, cover_prompt: str) -> str:
    sections = []
    if titles:
        sections.append(f"# 标题建议\n\n{titles}")
    if cover_prompt:
        sections.append(f"# 封面图提示词\n\n{cover_prompt}")
    if content:
        sections.append(f"# {style}文案\n\n{content}")
    return "\n\n".join(sections)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/meta")
def get_meta():
    return {"video_root": str(VIDEO_ROOT)}


@app.get("/files")
def list_files(path: str = ""):
    full_path = resolve_video_path(path)
    if not full_path.exists() or not full_path.is_dir():
        return {"error": "Invalid path"}

    items = []
    for item in sorted(full_path.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower())):
        items.append({
            "name": item.name,
            "is_dir": item.is_dir(),
            "path": str(item.relative_to(VIDEO_ROOT))
        })
    return items


@app.post("/tasks/create")
def create_task(req: TaskCreateReq):
    video_file = resolve_video_path(req.video_path)
    if not video_file.exists() or not video_file.is_file():
        raise HTTPException(status_code=400, detail="video file not found")

    task_id = file_md5(video_file)
    row = get_task(task_id)
    if row:
        return dict(row)

    now = now_str()
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO tasks(task_id, video_path, filename, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (task_id, req.video_path, video_file.name, "UPLOADED", now, now)
    )
    conn.commit()
    conn.close()
    return dict(get_task(task_id))


@app.get("/tasks")
def list_tasks():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tasks ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/tasks/{task_id}")
def task_detail(task_id: str):
    row = get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    return dict(row)


@app.post("/tasks/{task_id}/extract-audio")
def extract_audio(task_id: str):
    row = get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="task not found")

    video_file = resolve_video_path(row["video_path"])
    out_dir = OUTPUT_ROOT / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = out_dir / f"{video_file.stem}.wav"

    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(video_file),
            "-ar", "16000", "-ac", "1", "-vn", str(audio_path)
        ], check=True, capture_output=True)
        update_task(
            task_id,
            status="AUDIO_DONE",
            audio_path=str(audio_path),
            transcript_path=None,
            refined_path=None,
            asr_text=None,
            polished_text=None,
            titles_text=None,
            cover_prompt=None,
            style=None,
            llm_enabled=0,
            generate_content=0,
            generate_titles=0,
            generate_cover_prompt=0,
            error=None,
        )
    except Exception as e:
        update_task(task_id, status="FAILED", error=str(e))
        raise HTTPException(status_code=500, detail=f"extract audio failed: {e}")

    return dict(get_task(task_id))


@app.post("/tasks/{task_id}/asr")
def run_asr(task_id: str):
    row = get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    if not row["audio_path"]:
        raise HTTPException(status_code=400, detail="audio not ready")

    audio_path = Path(row["audio_path"])
    transcript_path = OUTPUT_ROOT / task_id / "transcript.txt"

    try:
        text = get_asr().process(str(audio_path))
        transcript_path.write_text(text, encoding="utf-8")
        update_task(
            task_id,
            status="ASR_DONE",
            transcript_path=str(transcript_path),
            asr_text=text,
            refined_path=None,
            polished_text=None,
            titles_text=None,
            cover_prompt=None,
            style=None,
            llm_enabled=0,
            generate_content=0,
            generate_titles=0,
            generate_cover_prompt=0,
            error=None,
        )
    except Exception as e:
        update_task(task_id, status="FAILED", error=str(e))
        raise HTTPException(status_code=500, detail=f"asr failed: {e}")

    return dict(get_task(task_id))


@app.post("/tasks/{task_id}/polish")
def run_polish(task_id: str, req: TaskStepReq):
    row = get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    if not row["asr_text"]:
        raise HTTPException(status_code=400, detail="asr text not ready")
    if not any((req.generate_content, req.generate_titles, req.generate_cover_prompt)):
        raise HTTPException(status_code=400, detail="no llm output selected")

    refined_path = OUTPUT_ROOT / task_id / "refined.md"

    try:
        res = get_llm().process(
            row["asr_text"],
            req.style,
            generate_content=req.generate_content,
            generate_titles=req.generate_titles,
            generate_cover_prompt=req.generate_cover_prompt,
        )
        polished_text = build_refined_markdown(
            req.style,
            res["content"],
            res["titles"],
            res["cover_prompt"],
        )
        refined_path.write_text(polished_text, encoding="utf-8")
        update_task(
            task_id,
            status="LLM_DONE",
            refined_path=str(refined_path),
            polished_text=res["content"],
            titles_text=res["titles"],
            cover_prompt=res["cover_prompt"],
            style=req.style,
            llm_enabled=1,
            generate_content=int(req.generate_content),
            generate_titles=int(req.generate_titles),
            generate_cover_prompt=int(req.generate_cover_prompt),
            error=None,
        )
    except Exception as e:
        update_task(task_id, status="FAILED", error=str(e))
        raise HTTPException(status_code=500, detail=f"llm polish failed: {e}")

    return dict(get_task(task_id))


@app.get("/tasks/{task_id}/audio")
def download_audio(task_id: str):
    row = get_task(task_id)
    if not row or not row["audio_path"]:
        raise HTTPException(status_code=404, detail="audio not found")
    p = Path(row["audio_path"])
    if not p.exists():
        raise HTTPException(status_code=404, detail="audio file missing")
    return FileResponse(str(p), filename=p.name, media_type="audio/wav")


# legacy endpoints kept for compatibility
@app.post("/process")
def process_video(video_path: str, style: str = "小红书"):
    task = create_task(TaskCreateReq(video_path=video_path))
    task_id = task["task_id"]
    if task["status"] == "UPLOADED":
        extract_audio(task_id)
    if get_task(task_id)["status"] == "AUDIO_DONE":
        run_asr(task_id)
    if get_task(task_id)["status"] == "ASR_DONE":
        run_polish(task_id, TaskStepReq(style=style))
    return dict(get_task(task_id))


@app.get("/result/{video_name}")
def get_result(video_name: str):
    # compatibility: search latest task by filename stem prefix
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tasks WHERE filename LIKE ? ORDER BY updated_at DESC", (f"{video_name}%",)).fetchall()
    conn.close()
    if not rows:
        return {"status": "processing"}
    row = rows[0]
    if row["status"] == "FAILED":
        return {"status": "failed", "error": row["error"] or "unknown error"}
    if row["status"] not in {"ASR_DONE", "LLM_DONE"}:
        return {"status": "processing"}
    return {
        "status": "success",
        "mode": "llm" if row["status"] == "LLM_DONE" else "transcript",
        "data": {
            "transcript": row["asr_text"] or "",
            "content": row["polished_text"] or "",
            "titles": row["titles_text"] or "",
            "cover_prompt": row["cover_prompt"] or "",
            "style": row["style"] or "",
        },
    }


frontend_dir = PROJECT_ROOT / "frontend"
if frontend_dir.exists():
    app.mount("/frontend", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.get("/")
def index():
    return RedirectResponse(url="/frontend/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
