import json
import os
import re
import subprocess
import time
from pathlib import Path


def _parse_wp_result(stdout: str) -> tuple[int | None, str | None]:
    post_id = None
    link = None
    for line in stdout.splitlines():
        if line.strip().startswith("- ID:"):
            try:
                post_id = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        if line.strip().startswith("- Link:"):
            link = line.split(":", 1)[1].strip()
    if not link:
        match = re.search(r"https?://[^\s]+", stdout)
        if match:
            link = match.group(0)
    return post_id, link


def _parse_link_report(stdout: str) -> dict | None:
    for line in stdout.splitlines():
        if line.startswith("LINK_VALIDATION_REPORT:"):
            raw = line.split(":", 1)[1].strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
    return None


def send_to_agent1(
    paths: list[Path],
    agent1_command: list[str] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    run_id: str | None = None,
) -> dict[Path, dict]:
    results: dict[Path, dict] = {}
    for path in paths:
        if dry_run:
            results[path] = {
                "status": "dry_run",
                "wp_post_id": None,
                "wp_link": None,
                "errors": [],
                "duration_s": 0.0,
            }
            continue
        cmd = agent1_command or ["python3", "main.py", "--input-path", str(path), "--non-interactive"]
        if verbose:
            print(f"Handing off to Agent 1: {' '.join(cmd)}")
        start = time.time()
        try:
            env = os.environ.copy()
            if run_id:
                env["AGENT0_RUN_ID"] = str(run_id)
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
            duration = time.time() - start
            post_id, link = _parse_wp_result(proc.stdout)
            link_report = _parse_link_report(proc.stdout)
            status = "success" if proc.returncode == 0 else "failed"
            errors = []
            if proc.stderr:
                errors.append(proc.stderr.strip())
            results[path] = {
                "status": status,
                "wp_post_id": post_id,
                "wp_link": link,
                "link_report": link_report,
                "errors": errors,
                "duration_s": round(duration, 2),
            }
        except OSError as exc:
            duration = time.time() - start
            results[path] = {
                "status": "failed",
                "wp_post_id": None,
                "wp_link": None,
                "link_report": None,
                "errors": [str(exc)],
                "duration_s": round(duration, 2),
            }
    return results
