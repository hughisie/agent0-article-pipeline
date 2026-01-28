import json
import shutil
import threading
import time
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from agent0_translator import translate_headline_json, translate_headline_md
from agent0_utils import now_iso
from config import load_config

from .db import init_db, get_conn
from .fingerprint import compute_fingerprint
from .models import RunItem, RunRequest, ScanRequest, SettingsPayload, TranslateRequest, RescanRequest
from .pipeline_runner import run_pipeline_stream
from .quick_article import process_quick_article
from .scanner import scan_paths
from .settings import get_settings, update_settings
from .profile_manager import (
    get_active_profile,
    get_all_profiles,
    get_profile_by_id,
    create_profile,
    update_profile,
    delete_profile,
    set_active_profile,
    get_all_profile_prompts,
    set_profile_prompt,
    delete_profile_prompt,
    get_profile_directories,
    PROMPT_KEYS,
)
from primary_sources_registry import filter_registry
from .auth import (
    verify_google_token,
    create_access_token,
    get_current_user,
    require_auth,
    create_state_token,
    verify_state_token,
    AuthError
)
from .gdrive import (
    list_files_in_folder,
    download_file_content,
    get_file_metadata,
    search_files,
    get_folder_breadcrumbs,
    DriveError
)
import requests


app = FastAPI(title="Agent 0 GUI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_cache_control_headers(request: Request, call_next):
    """Add cache-control headers to prevent browser caching of frontend assets"""
    response = await call_next(request)
    # Disable caching for HTML and JS files to ensure users always get latest version
    if request.url.path.endswith(('.html', '.js', '.css')) or request.url.path == '/':
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Use /tmp for workspace on Cloud Run (read-only filesystem), local dir otherwise
if os.path.exists("/.dockerenv") or os.getenv("K_SERVICE"):
    # Running in Docker/Cloud Run - use /tmp
    WORKSPACE_ROOT = Path("/tmp/agent0_workspace")
else:
    # Running locally - use workspace subdirectory
    WORKSPACE_ROOT = Path(__file__).resolve().parent / "workspace"

UPLOADS_DIR = WORKSPACE_ROOT / "uploads"
CURRENT_DIR = WORKSPACE_ROOT / "current"

RUN_STATE: dict[str, dict] = {}
RUN_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_log(msg: str) -> str:
    config = load_config()
    secrets = [
        config.get("DEEPSEEK_API_KEY"),
        config.get("GEMINI_API_KEY"),
        config.get("WP_APPLICATION_PASSWORD"),
        config.get("WP_USERNAME"),
    ]
    cleaned = msg
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "***")
    return cleaned


def _emit_event(run_id: str, event: str, data: dict) -> None:
    with RUN_LOCK:
        state = RUN_STATE.get(run_id)
        if not state:
            return
        state["last_id"] += 1
        state["events"].append(
            {"id": state["last_id"], "event": event, "data": data}
        )
        if len(state["events"]) > 5000:
            state["events"] = state["events"][-5000:]


def emit_log(run_id: str, level: str, msg: str, stage: str | None = None, article_id: str | None = None) -> None:
    payload = {
        "ts": _now_iso(),
        "level": level,
        "msg": _sanitize_log(msg),
        "stage": stage,
        "article_id": article_id,
    }
    _emit_event(run_id, "log", payload)


def emit_article(run_id: str, article_id: str, status: str, wp_post_id=None, wp_url=None, error: str | None = None) -> None:
    with RUN_LOCK:
        state = RUN_STATE.get(run_id)
        if state:
            state["articles"][article_id] = {
                "status": status,
                "wp_post_id": wp_post_id,
                "wp_url": wp_url,
                "error": error,
            }
    _emit_event(
        run_id,
        "article",
        {
            "article_id": article_id,
            "status": status,
            "wp_post_id": wp_post_id,
            "wp_url": wp_url,
            "error": error,
        },
    )


def emit_status(run_id: str, run_status: str, progress: dict) -> None:
    with RUN_LOCK:
        state = RUN_STATE.get(run_id)
        if state:
            state["status"] = run_status
            state["progress"] = progress
    _emit_event(run_id, "status", {"run_status": run_status, "progress": progress})


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/settings")
def api_get_settings() -> dict:
    return get_settings()


@app.post("/api/settings")
def api_update_settings(payload: SettingsPayload) -> dict:
    return update_settings(payload.data)


@app.post("/api/scan")
def api_scan(request: ScanRequest) -> dict:
    # Use active profile's input directory if no paths specified
    paths = request.paths
    if not paths:
        directories = get_profile_directories()
        paths = [str(directories["input_dir"])]

    items = scan_paths(paths, skip_duplicates=request.skip_duplicates)

    # Log scan to history
    if items and paths:
        with get_conn() as conn:
            for path in paths:
                conn.execute(
                    "INSERT INTO scan_history (folder_path, scanned_at, item_count, scan_mode) VALUES (?, ?, ?, ?)",
                    (path, _now_iso(), len(items), "manual")
                )

    return {"items": [item.__dict__ for item in items], "scanned_paths": paths}


@app.post("/api/upload")
async def api_upload(files: list[UploadFile] = File(...)) -> dict:
    """Upload files with detailed progress tracking and error handling."""
    print(f"[UPLOAD] Starting upload with {len(files)} files")
    
    if not files:
        print("[UPLOAD] ERROR: No files provided")
        raise HTTPException(status_code=400, detail="No files provided.")
    
    try:
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        CURRENT_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[UPLOAD] Created directories: {UPLOADS_DIR}, {CURRENT_DIR}")
    except Exception as e:
        print(f"[UPLOAD] ERROR creating directories: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create upload directories: {str(e)}")
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    upload_root = UPLOADS_DIR / timestamp
    
    try:
        upload_root.mkdir(parents=True, exist_ok=True)
        print(f"[UPLOAD] Created upload root: {upload_root}")
    except Exception as e:
        print(f"[UPLOAD] ERROR creating upload root: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create upload directory: {str(e)}")
    
    saved = 0
    skipped = 0
    errors = []
    
    for idx, upload in enumerate(files, 1):
        filename = upload.filename or ""
        print(f"[UPLOAD] Processing file {idx}/{len(files)}: {filename}")
        
        # Accept both .json and .md/.markdown files
        if not (filename.lower().endswith(".json") or filename.lower().endswith(".md") or filename.lower().endswith(".markdown")):
            print(f"[UPLOAD] Skipping non-article file: {filename}")
            skipped += 1
            continue
        
        try:
            rel = Path(filename)
            safe_parts = [part for part in rel.parts if part not in {"", ".", ".."}]
            rel_path = Path(*safe_parts) if safe_parts else Path(rel.name)
            dest = upload_root / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            with dest.open("wb") as handle:
                shutil.copyfileobj(upload.file, handle)
            
            print(f"[UPLOAD] Saved: {dest}")
            saved += 1
            
            try:
                upload.file.close()
            except Exception:
                pass
                
        except Exception as e:
            error_msg = f"Failed to save {filename}: {str(e)}"
            print(f"[UPLOAD] ERROR: {error_msg}")
            errors.append(error_msg)
    
    print(f"[UPLOAD] Upload complete: {saved} saved, {skipped} skipped, {len(errors)} errors")
    
    if saved == 0:
        detail = "No JSON or Markdown files saved."
        if errors:
            detail += f" Errors: {'; '.join(errors[:3])}"
        print(f"[UPLOAD] ERROR: {detail}")
        raise HTTPException(status_code=400, detail=detail)
    
    # Set up current directory symlink/copy
    try:
        if CURRENT_DIR.exists():
            if CURRENT_DIR.is_symlink() or CURRENT_DIR.is_file():
                CURRENT_DIR.unlink()
            else:
                shutil.rmtree(CURRENT_DIR)
        
        try:
            CURRENT_DIR.symlink_to(upload_root, target_is_directory=True)
            print(f"[UPLOAD] Created symlink: {CURRENT_DIR} -> {upload_root}")
        except OSError as e:
            print(f"[UPLOAD] Symlink failed ({e}), using copy instead")
            if CURRENT_DIR.exists():
                shutil.rmtree(CURRENT_DIR)
            shutil.copytree(upload_root, CURRENT_DIR)
            print(f"[UPLOAD] Copied to: {CURRENT_DIR}")
            
    except Exception as e:
        print(f"[UPLOAD] ERROR setting up current directory: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to set up workspace: {str(e)}")
    
    update_settings({"active_scan_root": str(CURRENT_DIR), "scan_mode": "upload"})
    print(f"[UPLOAD] Updated settings with active_scan_root: {CURRENT_DIR}")
    
    # Auto-scan uploaded files immediately
    print(f"[UPLOAD] Starting auto-scan of uploaded files...")
    try:
        items = scan_paths([str(CURRENT_DIR)], skip_duplicates=True)
        print(f"[UPLOAD] Scan complete: found {len(items)} items")
    except Exception as e:
        print(f"[UPLOAD] ERROR during scan: {e}")
        # Don't fail the upload if scan fails - return what we have
        items = []
        errors.append(f"Scan failed: {str(e)}")
    
    result = {
        "ok": True, 
        "saved_count": saved,
        "skipped_count": skipped,
        "root": str(CURRENT_DIR), 
        "scanned_items": len(items),
        "errors": errors if errors else None
    }
    print(f"[UPLOAD] Returning result: {result}")
    return result


@app.post("/api/rescan")
def api_rescan(request: RescanRequest) -> dict:
    """Rescan directories with detailed logging and error handling."""
    print(f"[RESCAN] Starting rescan request")
    
    settings = get_settings()
    mode = (request.mode or settings.get("scan_mode") or "upload").lower()
    skip_duplicates = request.skip_duplicates
    if skip_duplicates is None:
        skip_duplicates = settings.get("skip_duplicates", True)
    
    print(f"[RESCAN] Mode: {mode}, Skip duplicates: {skip_duplicates}")
    
    paths = []
    if mode == "manual" and request.paths:
        paths = request.paths
        update_settings({"scan_mode": "manual"})
        print(f"[RESCAN] Manual mode with paths: {paths}")
    else:
        active_root = settings.get("active_scan_root")
        if active_root and Path(active_root).exists():
            paths = [active_root]
            update_settings({"scan_mode": "upload"})
            print(f"[RESCAN] Using active scan root: {active_root}")
        else:
            paths = [settings.get("root_path") or "."]
            update_settings({"scan_mode": "manual"})
            print(f"[RESCAN] Using default root path: {paths}")
    
    # Clear headline cache for paths not in current scan to prevent stale data
    # This ensures we don't show articles from previous scans
    if paths:
        try:
            with get_conn() as conn:
                # Get all cached paths
                cached_paths = conn.execute("SELECT file_path FROM headline_cache").fetchall()
                current_scan_roots = set(str(Path(p).resolve()) for p in paths)
                
                cleared_count = 0
                # Remove cache entries that don't belong to current scan roots
                for row in cached_paths:
                    cached_path = row["file_path"]
                    # Check if this cached path is under any of the current scan roots
                    is_current_scan = any(
                        cached_path.startswith(root) for root in current_scan_roots
                    )
                    if not is_current_scan:
                        conn.execute("DELETE FROM headline_cache WHERE file_path = ?", (cached_path,))
                        cleared_count += 1
                conn.commit()
                if cleared_count > 0:
                    print(f"[RESCAN] Cleared {cleared_count} stale cache entries")
        except Exception as e:
            print(f"[RESCAN] WARNING: Failed to clear cache: {e}")
    
    print(f"[RESCAN] Starting scan of paths: {paths}")
    
    try:
        items = scan_paths(paths, skip_duplicates=bool(skip_duplicates))
        print(f"[RESCAN] Scan complete: found {len(items)} items")
    except Exception as e:
        print(f"[RESCAN] ERROR during scan: {e}")
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")

    # Log rescan to history
    if items and paths:
        try:
            with get_conn() as conn:
                for path in paths:
                    conn.execute(
                        "INSERT INTO scan_history (folder_path, scanned_at, item_count, scan_mode) VALUES (?, ?, ?, ?)",
                        (path, _now_iso(), len(items), mode)
                    )
            print(f"[RESCAN] Logged scan to history")
        except Exception as e:
            print(f"[RESCAN] WARNING: Failed to log scan history: {e}")

    result = {"items": [item.__dict__ for item in items], "root": paths[0] if paths else None}
    print(f"[RESCAN] Returning {len(items)} items")
    return result


@app.post("/api/translate_headlines")
def api_translate_headlines(request: TranslateRequest) -> dict:
    config = load_config()
    api_key = config.get("DEEPSEEK_API_KEY")
    translated = []
    errors = []
    if not api_key:
        for path_str in request.file_paths:
            errors.append({"file_path": path_str, "error": "Missing DEEPSEEK_API_KEY"})
        return {"translated": translated, "errors": errors}
    for path_str in request.file_paths:
        path = Path(path_str)
        try:
            if path.suffix.lower() == ".json":
                result = translate_headline_json(path, api_key=api_key or "")
            else:
                result = translate_headline_md(path, api_key=api_key or "")
            translated.append({"file_path": path_str, "headline_en_gb": result.headline_en_gb})
            with get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO headline_cache (file_path, headline_en_gb, updated_at) VALUES (?, ?, ?)",
                    (path_str, result.headline_en_gb, now_iso()),
                )
        except Exception as exc:
            errors.append({"file_path": path_str, "error": str(exc)})
    return {"translated": translated, "errors": errors}


@app.post("/api/quick-article")
async def api_quick_article(
    text: str = Form(None),
    url: str = Form(None),
    image: UploadFile = File(None),
    additional_context: str = Form(None)
) -> dict:
    """Create a quick article from URL, image, or text."""

    image_data = None
    if image:
        image_data = await image.read()

    # Save to CURRENT_DIR so it gets picked up by scanner
    CURRENT_DIR.mkdir(parents=True, exist_ok=True)

    result = process_quick_article(
        text=text,
        url=url,
        image_data=image_data,
        additional_context=additional_context,
        output_dir=CURRENT_DIR
    )

    return result


@app.post("/api/process-url")
async def api_process_url(request: Request, background_tasks: BackgroundTasks) -> dict:
    """Process a URL through the complete pipeline to WordPress draft."""
    try:
        data = await request.json()
        url = data.get("url")
        additional_context = data.get("additional_context", "")
        
        if not url:
            raise HTTPException(status_code=400, detail="URL is required")
        
        # Step 1: Create quick article from URL
        CURRENT_DIR.mkdir(parents=True, exist_ok=True)
        
        result = process_quick_article(
            text=None,
            url=url,
            image_data=None,
            additional_context=additional_context,
            output_dir=CURRENT_DIR
        )
        
        if not result.get("success") or not result.get("file_path"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to create article from URL")
            )
        
        file_path = result["file_path"]
        
        # Step 2: Start pipeline processing
        run_uuid = str(uuid4())
        started_at = _now_iso()
        with get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO runs (run_uuid, started_at, status) VALUES (?, ?, ?)",
                (run_uuid, started_at, "running"),
            )
            db_run_id = cursor.lastrowid
        
        with RUN_LOCK:
            RUN_STATE[run_uuid] = {
                "events": [],
                "last_id": 0,
                "status": "queued",
                "progress": {"total": 1, "success": 0, "failed": 0, "skipped": 0},
                "articles": {file_path: {"status": "pending"}},
            }
        emit_status(run_uuid, "running", RUN_STATE[run_uuid]["progress"])
        emit_article(run_uuid, file_path, status="pending")
        
        # Start processing in background
        background_tasks.add_task(_process_run, run_uuid, db_run_id, [file_path])
        
        return {
            "success": True,
            "run_id": run_uuid,
            "file_path": file_path,
            "message": "Article created and processing started"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process URL: {str(e)}")


@app.post("/api/run")
def api_run(request: RunRequest, background_tasks: BackgroundTasks) -> dict:
    if not request.file_paths:
        raise HTTPException(status_code=400, detail="No files selected.")

    # Debug logging
    print(f"[API] Starting run with {len(request.file_paths)} files:")
    for idx, path in enumerate(request.file_paths, 1):
        print(f"  {idx}. {Path(path).name}")

    run_uuid = str(uuid4())
    started_at = _now_iso()
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO runs (run_uuid, started_at, status) VALUES (?, ?, ?)",
            (run_uuid, started_at, "running"),
        )
        db_run_id = cursor.lastrowid

    with RUN_LOCK:
        RUN_STATE[run_uuid] = {
            "events": [],
            "last_id": 0,
            "status": "queued",
            "progress": {"total": len(request.file_paths), "success": 0, "failed": 0, "skipped": 0},
            "articles": {path: {"status": "pending"} for path in request.file_paths},
        }
    emit_status(run_uuid, "running", RUN_STATE[run_uuid]["progress"])
    for path in request.file_paths:
        emit_article(run_uuid, path, status="pending")

    background_tasks.add_task(_process_run, run_uuid, db_run_id, request.file_paths)
    return {"run_id": run_uuid, "total_files": len(request.file_paths)}


@app.get("/api/runs")
def api_runs() -> dict:
    with get_conn() as conn:
        runs = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 50").fetchall()
        items = conn.execute("SELECT * FROM run_items ORDER BY id DESC LIMIT 200").fetchall()
    parsed_items = []
    for row in items:
        entry = dict(row)
        link_report = entry.get("link_report")
        if link_report:
            try:
                entry["link_report"] = json.loads(link_report)
            except json.JSONDecodeError:
                entry["link_report"] = None
        parsed_items.append(entry)
    parsed_runs = []
    for row in runs:
        entry = dict(row)
        summary = entry.get("summary_json")
        if summary:
            try:
                entry["summary_json"] = json.loads(summary)
            except json.JSONDecodeError:
                entry["summary_json"] = None
        parsed_runs.append(entry)
    return {
        "runs": parsed_runs,
        "items": parsed_items,
    }


@app.get("/api/runs/{run_id}")
def api_run_detail(run_id: str) -> dict:
    with get_conn() as conn:
        run = conn.execute("SELECT * FROM runs WHERE run_uuid = ?", (run_id,)).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found.")
        items = conn.execute("SELECT * FROM run_items WHERE run_id = ?", (run["id"],)).fetchall()
    run_entry = dict(run)
    summary = run_entry.get("summary_json")
    if summary:
        try:
            run_entry["summary_json"] = json.loads(summary)
        except json.JSONDecodeError:
            run_entry["summary_json"] = None
    return {"run": run_entry, "items": [dict(row) for row in items]}


@app.get("/api/runs/{run_id}/events")
async def api_run_events(request: Request, run_id: str, since: int | None = None):
    async def event_stream():
        last_event_id = since
        if last_event_id is None:
            header_id = request.headers.get("last-event-id")
            if header_id and header_id.isdigit():
                last_event_id = int(header_id)
        if last_event_id is None:
            last_event_id = 0
        heartbeat_at = time.time()
        while True:
            if await request.is_disconnected():
                break
            with RUN_LOCK:
                state = RUN_STATE.get(run_id)
                events = []
                status = None
                last_id = last_event_id
                if state:
                    status = state.get("status")
                    events = [e for e in state["events"] if e["id"] > last_event_id]
                    if events:
                        last_id = events[-1]["id"]
            for event in events:
                payload = json.dumps(event["data"], ensure_ascii=False)
                yield f"id: {event['id']}\n" f"event: {event['event']}\n" f"data: {payload}\n\n"
            last_event_id = last_id
            now = time.time()
            if now - heartbeat_at >= 10:
                yield f"event: heartbeat\ndata: {json.dumps({'ts': _now_iso()})}\n\n"
                heartbeat_at = now
            if status in {"done", "failed"} and not events:
                break
            await asyncio.sleep(0.5)

    import asyncio

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/runs/{run_id}/log")
def api_run_log(run_id: str, lines: int = 40) -> dict:
    with get_conn() as conn:
        run = conn.execute("SELECT * FROM runs WHERE run_uuid = ?", (run_id,)).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found.")
        log_path = run["worker_log_path"]
    if not log_path or not Path(log_path).exists():
        return {"path": log_path, "tail_lines": [], "size_bytes": 0, "last_modified": None}
    path = Path(log_path)
    size = path.stat().st_size
    updated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    with path.open("rb") as handle:
        read_size = min(size, 32768)
        handle.seek(-read_size, 2)
        chunk = handle.read().decode("utf-8", errors="replace")
    tail_lines = chunk.splitlines()[-lines:]
    return {
        "path": str(path),
        "tail_lines": tail_lines,
        "size_bytes": size,
        "last_modified": updated_at,
    }


@app.post("/api/runs/{run_id}/cancel")
def api_cancel_run(run_id: str) -> dict:
    """Cancel a running pipeline"""
    with RUN_LOCK:
        state = RUN_STATE.get(run_id)
        if not state:
            raise HTTPException(status_code=404, detail="Run not found or already completed.")

        if state.get("status") not in {"queued", "running"}:
            return {"message": "Run is not in a cancellable state", "status": state.get("status")}

        # Mark as cancelled in state
        state["status"] = "cancelled"
        state["cancelled"] = True

    # Update database
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET status = ?, finished_at = ? WHERE run_uuid = ?",
            ("cancelled", _now_iso(), run_id)
        )

    emit_log(run_id, "warn", "Run cancelled by user")
    emit_status(run_id, "cancelled", state.get("progress", {}))

    return {"message": "Run cancelled successfully", "status": "cancelled"}


@app.get("/api/primary-sources")
def api_primary_sources(domain: str | None = None, source_type: str | None = None) -> dict:
    entries = filter_registry(domain=domain, source_type=source_type)
    return {"entries": entries}


@app.get("/api/health")
def api_health() -> dict:
    settings = get_settings()
    config = load_config()
    wp_base = config.get("WP_BASE_URL")
    wp_ok = False
    if wp_base:
        try:
            response = requests.get(f"{wp_base.rstrip('/')}/wp-json", timeout=10)
            wp_ok = response.status_code in {200, 301, 302}
        except requests.RequestException:
            wp_ok = False
    return {
        "ok": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "primary_source_strict": settings.get("primary_source_strict"),
        "wp_base_configured": bool(wp_base),
        "wp_reachable": wp_ok,
    }


@app.get("/api/scan-history")
def api_scan_history() -> dict:
    """Get scan history"""
    with get_conn() as conn:
        history = conn.execute(
            "SELECT * FROM scan_history ORDER BY id DESC LIMIT 50"
        ).fetchall()
    return {"history": [dict(row) for row in history]}


@app.get("/api/published-articles")
def api_published_articles(limit: int = 100, offset: int = 0) -> dict:
    """Get published articles history"""
    with get_conn() as conn:
        articles = conn.execute(
            """
            SELECT * FROM published_articles
            ORDER BY published_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) as count FROM published_articles").fetchone()["count"]
    return {
        "articles": [dict(row) for row in articles],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/api/runs/{run_id}/saved-log")
def api_run_saved_log(run_id: str) -> dict:
    """Get saved log text for a completed run"""
    with get_conn() as conn:
        run = conn.execute(
            "SELECT log_text, worker_log_path FROM runs WHERE run_uuid = ?",
            (run_id,)
        ).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found.")

    log_text = run["log_text"] or ""
    worker_log_path = run["worker_log_path"]

    # Also try to read from worker.log file if available
    worker_log = ""
    if worker_log_path:
        try:
            worker_log = Path(worker_log_path).read_text(encoding="utf-8")
        except Exception:
            pass

    return {
        "log_text": log_text,
        "worker_log": worker_log,
        "worker_log_path": worker_log_path
    }


@app.post("/api/clear-articles")
def api_clear_articles() -> dict:
    """Clear the current article list and workspace"""
    try:
        # Clear the current workspace directory
        if CURRENT_DIR.exists():
            shutil.rmtree(CURRENT_DIR)
            CURRENT_DIR.mkdir(parents=True, exist_ok=True)
        return {"items": [], "message": "Article list and workspace cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear workspace: {str(e)}")


# Profile Management Endpoints

@app.get("/api/profiles")
def api_get_profiles() -> dict:
    """Get all profiles"""
    profiles = get_all_profiles()
    active_profile = get_active_profile()
    return {
        "profiles": profiles,
        "active_profile_id": active_profile["id"] if active_profile else None
    }


@app.get("/api/profiles/active")
def api_get_active_profile() -> dict:
    """Get the currently active profile"""
    profile = get_active_profile()
    if not profile:
        raise HTTPException(status_code=404, detail="No active profile found")

    # Also include the directories
    directories = get_profile_directories(profile["id"])

    return {
        "profile": profile,
        "input_dir": str(directories["input_dir"]),
        "output_dir": str(directories["output_dir"])
    }


@app.get("/api/profiles/{profile_id}")
def api_get_profile(profile_id: int) -> dict:
    """Get a specific profile by ID"""
    profile = get_profile_by_id(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return {"profile": profile}


@app.post("/api/profiles")
async def api_create_profile(request: Request) -> dict:
    """Create a new profile"""
    try:
        data = await request.json()
        name = data.get("name")
        input_dir = data.get("input_dir")
        output_dir = data.get("output_dir")
        description = data.get("description", "")

        if not name or not input_dir or not output_dir:
            raise HTTPException(status_code=400, detail="name, input_dir, and output_dir are required")

        profile = create_profile(name, input_dir, output_dir, description)
        return {"profile": profile, "message": "Profile created successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create profile: {str(e)}")


@app.put("/api/profiles/{profile_id}")
async def api_update_profile(profile_id: int, request: Request) -> dict:
    """Update a profile"""
    try:
        data = await request.json()
        name = data.get("name")
        input_dir = data.get("input_dir")
        output_dir = data.get("output_dir")
        description = data.get("description")

        profile = update_profile(profile_id, name, input_dir, output_dir, description)
        return {"profile": profile, "message": "Profile updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")


@app.delete("/api/profiles/{profile_id}")
def api_delete_profile(profile_id: int) -> dict:
    """Delete a profile"""
    try:
        success = delete_profile(profile_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
        return {"message": "Profile deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete profile: {str(e)}")


@app.post("/api/profiles/{profile_id}/activate")
def api_activate_profile(profile_id: int) -> dict:
    """Set a profile as active"""
    try:
        profile = set_active_profile(profile_id)
        return {"profile": profile, "message": "Profile activated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to activate profile: {str(e)}")


# Prompt Management Endpoints

@app.get("/api/prompts/keys")
def api_get_prompt_keys() -> dict:
    """Get all available prompt keys"""
    return {"prompt_keys": PROMPT_KEYS}


@app.get("/api/profiles/{profile_id}/prompts")
def api_get_profile_prompts(profile_id: int) -> dict:
    """Get all prompts for a profile"""
    profile = get_profile_by_id(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    custom_prompts = get_all_profile_prompts(profile_id)

    # Import default prompts from prompts.py
    from prompts import TRANSLATION_SYSTEM, TRANSLATION_USER, PRIMARY_SYSTEM, PRIMARY_USER
    
    default_prompts = {
        "PROMPT_TRANSLATION_SYSTEM": TRANSLATION_SYSTEM,
        "PROMPT_TRANSLATION_USER": TRANSLATION_USER,
        "PROMPT_PRIMARY_SYSTEM": PRIMARY_SYSTEM,
        "PROMPT_PRIMARY_USER": PRIMARY_USER,
    }

    # Article writer prompts (from article_writer.py lines 140-344)
    default_prompts["PROMPT_ARTICLE_SYSTEM"] = (
        "You are a professional news journalist writing clear, modern articles for intelligent but busy readers.\n"
        "You write in British English with clarity, flow, and readability as top priorities.\n"
        "Your writing is factual, concrete, and accessible—like something published in a major newspaper, not a policy report.\n"
        "You follow Yoast SEO best practices for focus keyphrase, meta title, meta description, headings and readability.\n"
        "You respond ONLY with valid JSON and no extra commentary.\n"
        "Do not fabricate facts. If a detail is unknown, leave it out."
    )
    
    default_prompts["PROMPT_ARTICLE_USER"] = (
        "You will receive three JSON objects:\n"
        "  1. The original scraped article metadata and raw body.\n"
        "  2. A translation and analysis JSON.\n"
        "  3. A primary source JSON describing the original official report or announcement.\n\n"
        "Your tasks:\n"
        "  1. Identify the most appropriate primary SEO keyphrase for this news story.\n"
        "  2. Write a meta title (max ~60 chars) including the keyphrase near the start.\n"
        "  3. Write a meta description (max ~145 chars), compelling and human, including the keyphrase once.\n"
        "  4. Generate a slug for WordPress (lowercase, hyphen separated).\n"
        "  5. Suggest 3-6 SEO-friendly tags.\n"
        "  6. Write a short excerpt (1-2 sentences) summarising the story.\n"
        "  7. Write a full WordPress-ready article using Gutenberg block markup (see full instructions in default).\n\n"
        "Return ONLY valid JSON with: meta_title, meta_description, primary_keyword, slug, tags, excerpt, wp_block_content\n\n"
        "Here is the original article JSON:\n<ORIGINAL_ARTICLE_JSON_HERE>\n\n"
        "Here is the translation & analysis JSON:\n<ANALYSIS_JSON_HERE>\n\n"
        "Here is the primary source JSON:\n<PRIMARY_SOURCE_JSON_HERE>"
    )
    
    # Related articles prompts (from related_articles.py lines 15-90)
    default_prompts["PROMPT_RELATED_SYSTEM"] = (
        "You are an editorial assistant working on an online news site.\n"
        "You speak British English.\n"
        "You help identify related articles from the site's recent coverage and suggest natural ways to reference them inside a new article.\n"
        "You always respond with valid JSON and no extra commentary."
    )
    
    default_prompts["PROMPT_RELATED_USER"] = (
        "You will receive:\n"
        "  1. JSON describing a new story's article metadata and key analysis.\n"
        "  2. JSON describing its primary source.\n"
        "  3. A list of recent articles from the same site (title, URL, date, summary).\n\n"
        "Tasks:\n"
        "  - Identify 1-3 related articles that provide useful background, context, or continuation.\n"
        "  - Provide descriptive anchor text, a brief relevance note, and insertion placement.\n"
        "  - Prefer topical diversity; do not pick multiple links on the exact same subtopic.\n\n"
        "Return ONLY valid JSON with: related: [{url, title, anchor_text, why_relevant, suggested_insertion, style}]\n\n"
        "NEW STORY (article + analysis):\n<ARTICLE_AND_ANALYSIS_JSON_HERE>\n\n"
        "PRIMARY SOURCE:\n<PRIMARY_SOURCE_JSON_HERE>\n\n"
        "RECENT ARTICLES:\n<RECENT_POSTS_JSON_HERE>"
    )
    
    # Yoast optimizer prompts (from yoast_optimizer.py lines 19-80)
    default_prompts["PROMPT_YOAST_SYSTEM"] = (
        "You are an expert SEO editor familiar with Yoast SEO's content analysis.\n"
        "You write in British English and adjust articles to achieve a 100% Yoast SEO score.\n"
        "You must preserve the factual meaning and tone but are allowed to slightly rewrite text for SEO and clarity.\n"
        "You output ONLY valid JSON and no extra commentary. Do not add inline images; rely on the featured image alt text if needed."
    )
    
    default_prompts["PROMPT_YOAST_USER"] = (
        "You will receive the current SEO metadata and Gutenberg block content.\n\n"
        "Your goal is to adjust the metadata and content for a perfect Yoast SEO score.\n"
        "Focus on: outbound links, keyphrase in alt text, introduction, density, title, meta description, slug, subheadings.\n"
        "Keep passive voice under 10%, sentences under 20 words, transition words above 35%.\n\n"
        "Return ONLY JSON with: meta_title, meta_description, primary_keyword, slug, tags, excerpt, wp_block_content, yoast_notes\n\n"
        "Here is the metadata JSON:\n<ARTICLE_META_JSON_HERE>\n\n"
        "Here is the Gutenberg block content:\n<WP_BLOCK_CONTENT_HERE>\n\n"
        "Here is the list of previously used keyphrases:\n<USED_KEYPHRASES_JSON_HERE>"
    )
    
    # Tag generation prompts (from tag_generator.py lines 22-48)
    default_prompts["PROMPT_TAG_GEN_SYSTEM"] = (
        "You are an editorial taxonomy assistant for an online news site. "
        "You respond ONLY with valid JSON."
    )
    
    default_prompts["PROMPT_TAG_GEN_USER"] = (
        "You will receive an article object (title, body, metadata) and a list of existing WordPress tags.\n\n"
        "Task:\n"
        "- Suggest 5-7 concise, high-quality tags that reflect the article's core topic, places, entities, and themes.\n"
        "- Prefer existing tags when they match.\n"
        "- Do not include duplicates or near-duplicates.\n"
        "- Use British English unless the tag is a proper noun.\n\n"
        "Return ONLY JSON in this exact structure:\n"
        "{\n  \"tags\": [\n    {\"name\": \"Barcelona\"},\n    {\"name\": \"Taxi drivers\"}\n  ]\n}\n\n"
        "Article JSON:\n<ARTICLE_JSON_HERE>\n\nExisting tags:\n<WP_TAGS_JSON_HERE>"
    )
    
    # Taxonomy assignment prompts (from taxonomy_assigner.py lines 23-90)
    default_prompts["PROMPT_TAXONOMY_SYSTEM"] = (
        "You are an editorial taxonomy expert for an online news site.\n"
        "You speak British English.\n"
        "You assign categories and tags to news articles so they are consistent with existing site taxonomies and useful for readers and SEO.\n"
        "You respond ONLY with valid JSON and no extra commentary."
    )
    
    default_prompts["PROMPT_TAXONOMY_USER"] = (
        "You will receive: article object, translation/analysis, primary source, SEO metadata, existing WP categories and tags.\n\n"
        "Your tasks:\n"
        "  - Pick the single best primary category from the existing categories list (prefer specific over generic).\n"
        "  - Suggest 5-7 tags (reuse existing where possible, short phrases, British English).\n\n"
        "Return ONLY JSON with: category: {id, name, slug, is_new}, tags: [{id, name, slug, is_new}]\n\n"
        "Article JSON:\n<ARTICLE_JSON_HERE>\n\nAnalysis:\n<ANALYSIS_JSON_HERE>\n\n"
        "Primary source:\n<PRIMARY_SOURCE_JSON_HERE>\n\nSEO metadata:\n<ARTICLE_META_JSON_HERE>\n\n"
        "Existing categories:\n<WP_CATEGORIES_JSON_HERE>\n\nExisting tags:\n<WP_TAGS_JSON_HERE>"
    )
    
    # Headline translation prompts from agent0_translator.py
    default_prompts["PROMPT_HEADLINE_SYSTEM"] = (
        "You translate news headlines into British English (en-GB). "
        "Use British spelling: organise (not organize), colour (not color), centre (not center), etc. "
        "Return one line only, no quotes, no extra commentary."
    )
    default_prompts["PROMPT_HEADLINE_USER"] = (
        "Translate the headline into British English (en-GB). Keep it newsy, "
        "preserve proper nouns, and do not add facts. "
        "Use British spelling conventions: -ise endings (organise, realise), -our endings (colour, favour), "
        "-re endings (centre, theatre), -ence endings (defence, offence).\n\n"
        "Headline:\n<HEADLINE>"
    )

    # Define available models
    available_models = [
        {"id": "gemini-2.0-flash-exp", "name": "Gemini 2.0 Flash", "provider": "Google"},
        {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "provider": "Google"},
        {"id": "gemini-3-pro-preview", "name": "Gemini 3 Pro (Preview)", "provider": "Google"},
        {"id": "deepseek-chat", "name": "DeepSeek Chat", "provider": "DeepSeek"},
    ]
    
    # Merge with custom prompts (custom overrides default)
    prompts = {}
    for key in PROMPT_KEYS:
        custom_data = custom_prompts.get(key, {})
        if isinstance(custom_data, dict):
            prompt_value = custom_data.get("value", "")
            model_pref = custom_data.get("model", "gemini-2.0-flash-exp")
        else:
            # Backward compatibility if custom_prompts returns strings
            prompt_value = custom_data if isinstance(custom_data, str) else ""
            model_pref = "gemini-2.0-flash-exp"
            
        # Set default model based on prompt category
        if key in ["PROMPT_ARTICLE_SYSTEM", "PROMPT_ARTICLE_USER"]:
            default_model = "gemini-3-pro-preview"
        else:
            default_model = "gemini-2.0-flash-exp"
            
        prompts[key] = {
            "value": prompt_value if key in custom_prompts else default_prompts.get(key, ""),
            "is_custom": key in custom_prompts,
            "default_value": default_prompts.get(key, ""),
            "description": _get_prompt_description(key),
            "model": model_pref if key in custom_prompts else default_model,
            "default_model": default_model
        }

    return {"prompts": prompts, "available_models": available_models}


def _get_prompt_description(key: str) -> str:
    """Get a description for each prompt key"""
    descriptions = {
        "PROMPT_TRANSLATION_SYSTEM": "System prompt for translation analysis (translates articles and extracts key info)",
        "PROMPT_TRANSLATION_USER": "User prompt for translation analysis",
        "PROMPT_PRIMARY_SYSTEM": "System prompt for primary source finding (finds original official sources)",
        "PROMPT_PRIMARY_USER": "User prompt for primary source finding",
        "PROMPT_ARTICLE_SYSTEM": "System prompt for article writing (generates the full WordPress article)",
        "PROMPT_ARTICLE_USER": "User prompt for article writing",
        "PROMPT_RELATED_SYSTEM": "System prompt for related article detection (finds internal links)",
        "PROMPT_RELATED_USER": "User prompt for related article detection",
        "PROMPT_HEADLINE_SYSTEM": "System prompt for headline translation",
        "PROMPT_HEADLINE_USER": "User prompt for headline translation",
        "PROMPT_YOAST_SYSTEM": "System prompt for Yoast SEO optimization (adjusts content for perfect SEO score)",
        "PROMPT_YOAST_USER": "User prompt for Yoast SEO optimization",
        "PROMPT_TAG_GEN_SYSTEM": "System prompt for tag generation (suggests relevant WordPress tags)",
        "PROMPT_TAG_GEN_USER": "User prompt for tag generation",
        "PROMPT_TAXONOMY_SYSTEM": "System prompt for taxonomy assignment (assigns categories and tags)",
        "PROMPT_TAXONOMY_USER": "User prompt for taxonomy assignment",
    }
    return descriptions.get(key, "")


@app.put("/api/profiles/{profile_id}/prompts/{prompt_key}")
async def api_set_profile_prompt(profile_id: int, prompt_key: str, request: Request) -> dict:
    """Set/update a prompt for a profile"""
    try:
        data = await request.json()
        prompt_value = data.get("value")
        model_preference = data.get("model")

        if prompt_value is None:
            raise HTTPException(status_code=400, detail="value is required")

        set_profile_prompt(profile_id, prompt_key, prompt_value, model_preference)
        return {"message": "Prompt updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update prompt: {str(e)}")


@app.delete("/api/profiles/{profile_id}/prompts/{prompt_key}")
def api_delete_profile_prompt(profile_id: int, prompt_key: str) -> dict:
    """Delete a custom prompt (revert to default)"""
    try:
        delete_profile_prompt(profile_id, prompt_key)
        return {"message": "Prompt reset to default successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset prompt: {str(e)}")


def _mount_frontend(app: FastAPI) -> None:
    web_dist = Path(__file__).resolve().parent / "web" / "dist"
    if web_dist.exists():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
    else:
        @app.get("/")
        def _placeholder() -> JSONResponse:
            return JSONResponse({"message": "Frontend not built. Run `npm install && npm run build` in agent0_gui/web."})


_mount_frontend(app)


def _process_run(run_uuid: str, db_run_id: int, file_paths: list[str]) -> None:
    def _emit_log(run_id: str, level: str, msg: str, stage: str | None = None, article_id: str | None = None) -> None:
        emit_log(run_id, level, msg, stage=stage, article_id=article_id)

    def _emit_status(run_id: str, run_status: str, progress: dict) -> None:
        emit_status(run_id, run_status, progress)

    def _emit_article(run_id: str, article_id: str, status: str, wp_post_id=None, wp_url=None, error: str | None = None) -> None:
        emit_article(run_id, article_id, status, wp_post_id=wp_post_id, wp_url=wp_url, error=error)

    emit_log(run_uuid, "info", f"Run started with {len(file_paths)} articles.")
    run_dir = WORKSPACE_ROOT / "runs" / run_uuid
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "worker.log"
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET worker_log_path = ? WHERE id = ?",
            (str(log_path), db_run_id),
        )
    summary = {"total": len(file_paths), "success": 0, "failed": 0, "skipped": 0}
    try:
        summary = run_pipeline_stream(
            file_paths,
            run_uuid,
            db_run_id,
            log_path,
            _emit_log,
            _emit_status,
            _emit_article,
        )
    except Exception as exc:
        emit_log(run_uuid, "error", f"Run failed: {exc}")
        emit_status(run_uuid, "failed", summary)
    log_text = ""
    with RUN_LOCK:
        state = RUN_STATE.get(run_uuid)
        if state:
            log_text = "\n".join(
                f"{event['data'].get('ts', '')} [{event['data'].get('level', '')}] {event['data'].get('msg', '')}"
                for event in state["events"]
                if event["event"] == "log"
            )
    finished_at = _now_iso()
    status = "done" if summary.get("failed", 0) == 0 else "failed"
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = ?, status = ?, summary_json = ?, log_text = ? WHERE id = ?",
            (finished_at, status, json.dumps(summary), log_text, db_run_id),
        )
        rows = conn.execute(
            "SELECT file_path FROM run_items WHERE run_id = ? AND status = ?",
            (db_run_id, "success"),
        ).fetchall()
        for row in rows:
            path = row["file_path"]
            fingerprint = compute_fingerprint(Path(path))
            conn.execute(
                "INSERT OR REPLACE INTO processed (fingerprint, file_name, created_at) VALUES (?, ?, ?)",
                (fingerprint, Path(path).name, now_iso()),
            )


# OAuth and Authentication Endpoints

@app.post("/api/auth/google")
async def auth_google(request: Request) -> dict:
    """Authenticate with Google OAuth token"""
    try:
        data = await request.json()
        token = data.get("token")
        
        if not token:
            raise HTTPException(status_code=400, detail="Token is required")
        
        # Verify Google token
        user_info = verify_google_token(token)
        
        # Create JWT access token
        access_token = create_access_token(user_info)
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "email": user_info["email"],
                "name": user_info.get("name"),
                "picture": user_info.get("picture")
            }
        }
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@app.get("/api/auth/me")
async def get_me(user: dict = Depends(get_current_user)) -> dict:
    """Get current authenticated user"""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user": user}


@app.get("/api/auth/config")
def get_auth_config() -> dict:
    """Get OAuth configuration for frontend"""
    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    return {
        "google_client_id": google_client_id,
        "oauth_enabled": bool(google_client_id),
        "drive_folder_id": os.getenv("GOOGLE_DRIVE_FOLDER_ID", "17txivAocXR4R5qMsWi4vYUB6Kg2K1N1m")
    }


# Google Drive Endpoints

@app.get("/api/drive/files")
async def get_drive_files(
    folder_id: str = None,
    page_token: str = None,
    user: dict = Depends(require_auth)
) -> dict:
    """List files in Google Drive folder"""
    try:
        # In production, get access token from user session/database
        # For now, we'll need to get it from the request header
        access_token = os.getenv("GOOGLE_ACCESS_TOKEN")
        
        if not access_token:
            raise HTTPException(
                status_code=401, 
                detail="Google Drive access not configured. Please authenticate with Google."
            )
        
        result = list_files_in_folder(
            access_token=access_token,
            folder_id=folder_id,
            page_token=page_token,
            file_types=["application/json", "text/markdown", "text/plain"]
        )
        
        return result
    except DriveError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@app.get("/api/drive/files/{file_id}")
async def get_drive_file(
    file_id: str,
    user: dict = Depends(require_auth)
) -> dict:
    """Get file metadata from Google Drive"""
    try:
        access_token = os.getenv("GOOGLE_ACCESS_TOKEN")
        
        if not access_token:
            raise HTTPException(status_code=401, detail="Google Drive access not configured")
        
        metadata = get_file_metadata(access_token, file_id)
        return metadata
    except DriveError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get file: {str(e)}")


@app.get("/api/drive/files/{file_id}/download")
async def download_drive_file(
    file_id: str,
    user: dict = Depends(require_auth)
) -> dict:
    """Download file from Google Drive and save to workspace"""
    try:
        access_token = os.getenv("GOOGLE_ACCESS_TOKEN")
        
        if not access_token:
            raise HTTPException(status_code=401, detail="Google Drive access not configured")
        
        # Get file metadata
        metadata = get_file_metadata(access_token, file_id)
        file_name = metadata.get("name", "unknown.json")
        
        # Download content
        content = download_file_content(access_token, file_id)
        
        # Save to workspace
        CURRENT_DIR.mkdir(parents=True, exist_ok=True)
        file_path = CURRENT_DIR / file_name
        file_path.write_bytes(content)
        
        return {
            "success": True,
            "file_path": str(file_path),
            "file_name": file_name,
            "size": len(content)
        }
    except DriveError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download file: {str(e)}")


@app.post("/api/drive/files/bulk-download")
async def bulk_download_drive_files(
    request: Request,
    user: dict = Depends(require_auth)
) -> dict:
    """Download multiple files from Google Drive"""
    try:
        data = await request.json()
        file_ids = data.get("file_ids", [])
        
        if not file_ids:
            raise HTTPException(status_code=400, detail="No file IDs provided")
        
        access_token = os.getenv("GOOGLE_ACCESS_TOKEN")
        
        if not access_token:
            raise HTTPException(status_code=401, detail="Google Drive access not configured")
        
        CURRENT_DIR.mkdir(parents=True, exist_ok=True)
        downloaded = []
        errors = []
        
        for file_id in file_ids:
            try:
                metadata = get_file_metadata(access_token, file_id)
                file_name = metadata.get("name", f"{file_id}.json")
                content = download_file_content(access_token, file_id)
                
                file_path = CURRENT_DIR / file_name
                file_path.write_bytes(content)
                
                downloaded.append({
                    "file_id": file_id,
                    "file_name": file_name,
                    "file_path": str(file_path),
                    "size": len(content)
                })
            except Exception as e:
                errors.append({
                    "file_id": file_id,
                    "error": str(e)
                })
        
        return {
            "success": True,
            "downloaded": downloaded,
            "errors": errors,
            "total": len(file_ids),
            "succeeded": len(downloaded),
            "failed": len(errors)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk download failed: {str(e)}")


@app.get("/api/drive/search")
async def search_drive_files(
    query: str,
    folder_id: str = None,
    user: dict = Depends(require_auth)
) -> dict:
    """Search files in Google Drive"""
    try:
        access_token = os.getenv("GOOGLE_ACCESS_TOKEN")
        
        if not access_token:
            raise HTTPException(status_code=401, detail="Google Drive access not configured")
        
        files = search_files(access_token, query, folder_id)
        return {"files": files}
    except DriveError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/api/drive/breadcrumbs/{folder_id}")
async def get_drive_breadcrumbs(
    folder_id: str,
    user: dict = Depends(require_auth)
) -> dict:
    """Get breadcrumb trail for a folder"""
    try:
        access_token = os.getenv("GOOGLE_ACCESS_TOKEN")
        
        if not access_token:
            raise HTTPException(status_code=401, detail="Google Drive access not configured")
        
        breadcrumbs = get_folder_breadcrumbs(access_token, folder_id)
        return {"breadcrumbs": breadcrumbs}
    except DriveError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get breadcrumbs: {str(e)}")
