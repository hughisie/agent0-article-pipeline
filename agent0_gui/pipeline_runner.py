import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .db import get_conn
from .settings import get_settings
from config import load_config, save_config


def now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _parse_wp_line(line: str) -> tuple[int | None, str | None]:
    post_id = None
    link = None
    if line.strip().startswith("- ID:"):
        try:
            post_id = int(line.split(":", 1)[1].strip())
        except ValueError:
            post_id = None
    if line.strip().startswith("- Link:"):
        link = line.split(":", 1)[1].strip()
    if not link:
        match = re.search(r"https?://[^\s]+", line)
        if match:
            link = match.group(0)
    return post_id, link


def _extract_wp_from_log(log_path: Path) -> tuple[int | None, str | None]:
    if not log_path.exists():
        return None, None
    size = log_path.stat().st_size
    read_size = min(size, 20000)
    with log_path.open("rb") as handle:
        handle.seek(-read_size, 2)
        chunk = handle.read().decode("utf-8", errors="replace")
    post_id = None
    link = None
    for line in chunk.splitlines():
        parsed_id, parsed_link = _parse_wp_line(line)
        if parsed_id:
            post_id = parsed_id
        if parsed_link:
            link = parsed_link
    return post_id, link


def _process_single_article(
    file_path: str,
    run_uuid: str,
    db_run_id: int,
    log_handle,
    log_path: Path,
    emit_log,
    emit_article,
) -> dict:
    """Process a single article and return result."""
    article_id = file_path
    emit_article(run_uuid, article_id, status="running")
    emit_log(run_uuid, "info", f"Starting pipeline for {file_path}", stage="start", article_id=article_id)
    started = time.time()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO run_items (run_id, file_path, status, errors)
            VALUES (?, ?, ?, ?)
            """,
            (db_run_id, file_path, "running", json.dumps([])),
        )

    wp_post_id = None
    wp_link = None
    link_report = None
    errors = []

    # Get the project root directory (parent of agent0_gui)
    project_root = Path(__file__).resolve().parent.parent
    main_py = project_root / "main.py"
    
    cmd = [sys.executable, str(main_py), "--input-path", file_path, "--non-interactive"]
    env = dict(os.environ)
    env["AGENT0_RUN_ID"] = run_uuid
    env["PYTHONUNBUFFERED"] = "1"
    
    # Pass config values to subprocess (critical for Cloud Run)
    from config import load_config
    config = load_config()
    config_keys = [
        "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "WP_BASE_URL", "WP_USERNAME",
        "WP_APPLICATION_PASSWORD", "GOOGLE_CLIENT_ID", "JWT_SECRET",
        "GOOGLE_ACCESS_TOKEN", "MODEL_TRANSLATION", "MODEL_PRIMARY_SOURCE",
        "MODEL_ARTICLE", "MODEL_INTERNAL_LINK", "PRIMARY_SOURCE_STRICT",
        "VALIDATE_OUTBOUND_URLS", "ENFORCE_IMAGE_SPACING", "IMAGE_SPACER_HEIGHT_PX"
    ]
    for key in config_keys:
        if key in config and config[key] is not None:
            env[key] = str(config[key])
    emit_log(run_uuid, "info", f"Worker command: {' '.join(cmd)}", stage="worker", article_id=article_id)
    emit_log(run_uuid, "info", f"Worker working directory: {project_root}", stage="worker", article_id=article_id)
    emit_log(run_uuid, "info", f"Worker output → {log_path}", stage="worker", article_id=article_id)

    # Check if file exists
    if not Path(file_path).exists():
        emit_log(run_uuid, "error", f"Input file not found: {file_path}", stage="worker", article_id=article_id)
        returncode = 1
        duration = 0
    else:
        try:
            emit_log(run_uuid, "info", "Starting subprocess...", stage="worker", article_id=article_id)
            returncode = subprocess.call(cmd, stdout=log_handle, stderr=log_handle, env=env, cwd=str(project_root))
            log_handle.flush()
            emit_log(run_uuid, "info", f"Subprocess completed with code {returncode}", stage="worker", article_id=article_id)
            wp_post_id, wp_link = _extract_wp_from_log(log_path)

            if wp_post_id:
                emit_log(run_uuid, "info", f"WordPress draft created: ID {wp_post_id}", stage="publish", article_id=article_id)
                emit_article(run_uuid, article_id, status="success", wp_post_id=wp_post_id, wp_url=wp_link)
        except Exception as e:
            emit_log(run_uuid, "error", f"Subprocess exception: {e}", stage="worker", article_id=article_id)
            returncode = 1
        duration = round(time.time() - started, 2)

    status = "success" if returncode == 0 else "failed"
    if status != "success":
        # Try to extract actual error from log
        actual_error = "Worker process failed"
        if log_path.exists():
            try:
                # Read last 2000 chars of log to find actual error
                with log_path.open("rb") as f:
                    f.seek(0, 2)  # Go to end
                    size = f.tell()
                    read_size = min(size, 2000)
                    f.seek(-read_size, 2)
                    log_tail = f.read().decode("utf-8", errors="replace")
                    
                # Look for common error patterns
                for line in reversed(log_tail.splitlines()):
                    line_lower = line.lower()
                    if any(err in line_lower for err in ["error:", "exception:", "failed:", "traceback"]):
                        actual_error = line.strip()[:200]
                        break
            except Exception:
                pass
        
        errors.append(actual_error)
        emit_log(
            run_uuid,
            "error",
            f"Worker failed (exit {returncode}): {actual_error}",
            stage="worker",
            article_id=article_id,
        )

    emit_log(run_uuid, "info", f"Worker exit code: {returncode} (duration: {duration}s)", stage="worker", article_id=article_id)
    emit_article(run_uuid, article_id, status=status, wp_post_id=wp_post_id, wp_url=wp_link, error="; ".join(errors) if errors else None)

    # Update database
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE run_items
            SET status = ?, wp_post_id = ?, wp_link = ?, link_report = ?, errors = ?, duration_s = ?
            WHERE run_id = ? AND file_path = ?
            """,
            (
                status,
                wp_post_id,
                wp_link,
                json.dumps(link_report) if link_report else None,
                json.dumps(errors),
                duration,
                db_run_id,
                file_path,
            ),
        )

        # Track published articles
        if status == "success" and wp_post_id and wp_link:
            try:
                article_path = Path(file_path)
                headline = article_path.stem
                english_headline = None
                meta_title = None
                primary_keyword = None
                fingerprint = None
                llm_model = None

                if article_path.exists() and article_path.suffix == '.json':
                    import json as json_lib
                    with open(article_path, 'r', encoding='utf-8') as f:
                        article_data = json_lib.load(f)
                        headline = article_data.get('headline', headline)
                        english_headline = article_data.get('headline_en_gb')
                        fingerprint = article_data.get('fingerprint')

                wp_json_path = article_path.parent / f"{article_path.stem}.wp.json"
                if wp_json_path.exists():
                    with open(wp_json_path, 'r', encoding='utf-8') as f:
                        wp_data = json_lib.load(f)
                        meta_title = wp_data.get('meta_title')
                        primary_keyword = wp_data.get('primary_keyword')
                
                # Extract LLM model from config or settings
                config = load_config()
                llm_model = config.get('MODEL_ARTICLE') or config.get('GEMINI_MODEL') or 'gemini-2.0-flash-exp'

                conn.execute(
                    """
                    INSERT OR REPLACE INTO published_articles
                    (file_path, headline, english_headline, wp_post_id, wp_url, published_at, fingerprint, meta_title, primary_keyword, llm_model)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (file_path, headline, english_headline, wp_post_id, wp_link, now_iso(), fingerprint, meta_title, primary_keyword, llm_model),
                )
                emit_log(run_uuid, "info", f"Tracked published article: {headline}", stage="publish", article_id=article_id)
            except Exception as e:
                emit_log(run_uuid, "warning", f"Failed to track published article: {e}", stage="publish", article_id=article_id)

    return {"status": status, "wp_post_id": wp_post_id, "wp_link": wp_link, "errors": errors}


def _is_run_cancelled(run_uuid: str) -> bool:
    """Check if a run has been cancelled."""
    try:
        from .app import RUN_STATE, RUN_LOCK
        with RUN_LOCK:
            state = RUN_STATE.get(run_uuid)
            if state and state.get("cancelled"):
                return True
    except ImportError:
        pass
    return False


def run_pipeline_stream(
    file_paths: list[str],
    run_uuid: str,
    db_run_id: int,
    log_path: Path,
    emit_log,
    emit_status,
    emit_article,
) -> dict:
    settings = get_settings()
    config = load_config()
    config["PRIMARY_SOURCE_STRICT"] = bool(settings.get("primary_source_strict", True))
    config["VALIDATE_OUTBOUND_URLS"] = bool(settings.get("validate_outbound_urls", True))
    config["ENFORCE_IMAGE_SPACING"] = bool(settings.get("enforce_image_spacing", True))
    config["IMAGE_SPACER_HEIGHT_PX"] = int(settings.get("image_spacer_height_px", 24))
    for stage in settings.get("stages", []) or []:
        values = stage.get("values") if isinstance(stage, dict) else {}
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            if key.startswith(("MODEL_", "TEMPERATURE_", "PROMPT_")) or key.endswith("_STRICT"):
                config[key] = value
    if settings.get("analysis_model"):
        config["MODEL_TRANSLATION"] = settings.get("analysis_model")
    if settings.get("primary_source_model"):
        config["MODEL_PRIMARY_SOURCE"] = settings.get("primary_source_model")
    if settings.get("article_model"):
        config["MODEL_ARTICLE"] = settings.get("article_model")
    if settings.get("internal_link_model"):
        config["MODEL_INTERNAL_LINK"] = settings.get("internal_link_model")
    if settings.get("headline_prompt"):
        config["PROMPT_HEADLINE_USER"] = settings.get("headline_prompt")
    if settings.get("analysis_prompt"):
        config["PROMPT_TRANSLATION_USER"] = settings.get("analysis_prompt")
    if settings.get("primary_source_prompt"):
        config["PROMPT_PRIMARY_USER"] = settings.get("primary_source_prompt")
    if settings.get("article_prompt"):
        config["PROMPT_ARTICLE_USER"] = settings.get("article_prompt")
    if settings.get("internal_link_prompt"):
        config["PROMPT_RELATED_USER"] = settings.get("internal_link_prompt")
    save_config(config)

    total = len(file_paths)
    summary = {"total": total, "success": 0, "failed": 0, "skipped": 0}
    emit_status(run_uuid, "running", summary)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("ab")

    # Mark all articles as pending
    for file_path in file_paths:
        emit_article(run_uuid, file_path, status="pending")

    # Process articles in parallel (5 at a time)
    emit_log(run_uuid, "info", f"Starting parallel processing of {total} articles (max 2 concurrent)", stage="start")

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit all tasks
            futures = {
                executor.submit(
                    _process_single_article,
                    file_path,
                    run_uuid,
                    db_run_id,
                    log_handle,
                    log_path,
                    emit_log,
                    emit_article,
                ): file_path
                for file_path in file_paths
            }

            # Process completed tasks as they finish
            for future in as_completed(futures):
                # Check for cancellation
                if _is_run_cancelled(run_uuid):
                    emit_log(run_uuid, "warn", "Run cancelled, stopping processing", stage="cancel")
                    # Cancel remaining futures
                    for f in futures:
                        f.cancel()
                    summary["skipped"] = total - summary["success"] - summary["failed"]
                    emit_status(run_uuid, "cancelled", summary)
                    break

                file_path = futures[future]
                try:
                    result = future.result()
                    if result["status"] == "success":
                        summary["success"] += 1
                    else:
                        summary["failed"] += 1
                    emit_status(run_uuid, "running", summary)
                except Exception as exc:
                    emit_log(run_uuid, "error", f"Article {file_path} generated exception: {exc}", stage="worker")
                    summary["failed"] += 1
                    emit_status(run_uuid, "running", summary)
    finally:
        # Check if cancelled to emit correct final status
        if _is_run_cancelled(run_uuid):
            final_status = "cancelled"
        elif summary["failed"] == 0:
            final_status = "done"
        else:
            final_status = "failed"
        emit_status(run_uuid, final_status, summary)
        log_handle.close()
    return summary


def run_pipeline(file_paths: list[str]) -> list[dict]:
    settings = get_settings()
    config = load_config()
    config["PRIMARY_SOURCE_STRICT"] = bool(settings.get("primary_source_strict", True))
    config["VALIDATE_OUTBOUND_URLS"] = bool(settings.get("validate_outbound_urls", True))
    config["ENFORCE_IMAGE_SPACING"] = bool(settings.get("enforce_image_spacing", True))
    config["IMAGE_SPACER_HEIGHT_PX"] = int(settings.get("image_spacer_height_px", 24))
    for stage in settings.get("stages", []) or []:
        values = stage.get("values") if isinstance(stage, dict) else {}
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            if key.startswith(("MODEL_", "TEMPERATURE_", "PROMPT_")) or key.endswith("_STRICT"):
                config[key] = value
    if settings.get("analysis_model"):
        config["MODEL_TRANSLATION"] = settings.get("analysis_model")
    if settings.get("primary_source_model"):
        config["MODEL_PRIMARY_SOURCE"] = settings.get("primary_source_model")
    if settings.get("article_model"):
        config["MODEL_ARTICLE"] = settings.get("article_model")
    if settings.get("internal_link_model"):
        config["MODEL_INTERNAL_LINK"] = settings.get("internal_link_model")
    if settings.get("headline_prompt"):
        config["PROMPT_HEADLINE_USER"] = settings.get("headline_prompt")
    if settings.get("analysis_prompt"):
        config["PROMPT_TRANSLATION_USER"] = settings.get("analysis_prompt")
    if settings.get("primary_source_prompt"):
        config["PROMPT_PRIMARY_USER"] = settings.get("primary_source_prompt")
    if settings.get("article_prompt"):
        config["PROMPT_ARTICLE_USER"] = settings.get("article_prompt")
    if settings.get("internal_link_prompt"):
        config["PROMPT_RELATED_USER"] = settings.get("internal_link_prompt")
    save_config(config)

    started_at = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, ?)",
            (started_at, "running"),
        )
        run_id = cursor.lastrowid

    results_path = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    targets_path = Path(tempfile.mkstemp(suffix=".txt")[1])
    targets_path.write_text("\n".join(file_paths), encoding="utf-8")

    cmd = [
        sys.executable,
        "agent0.py",
        "--input-dir",
        settings.get("root_path") or ".",
        "--targets-file",
        str(targets_path),
        "--non-interactive",
        "--emit-results-jsonl",
        str(results_path),
    ]
    if settings.get("dry_run"):
        cmd.append("--dry-run")
    env = dict(**os.environ)
    env["AGENT0_RUN_ID"] = str(run_id)
    proc = subprocess.run(cmd, check=False, env=env)

    results = []
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    with get_conn() as conn:
        for item in results:
            conn.execute(
                """
                INSERT INTO run_items (run_id, file_path, status, wp_post_id, wp_link, link_report, errors, duration_s)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    item.get("file_path"),
                    item.get("status"),
                    item.get("wp_post_id"),
                    item.get("wp_link"),
                    json.dumps(item.get("link_report")) if item.get("link_report") else None,
                    json.dumps(item.get("errors", [])),
                    item.get("duration_s"),
                ),
            )
        conn.execute(
            "UPDATE runs SET status = ? WHERE id = ?",
            ("success" if proc.returncode == 0 else "failed", run_id),
        )

    return results
