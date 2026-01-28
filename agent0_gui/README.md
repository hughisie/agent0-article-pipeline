# Agent 0 GUI (Local)

Local-first GUI on top of the existing Python pipeline (`agent0.py` + `main.py`).

## Prerequisites
- Python 3.11+
- Node 18+

## Backend
From repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn agent0_gui.app:app --reload --port 9000
```

## Frontend
From `agent0_gui/web`:

```bash
npm install
npm run build
```

The backend serves the built frontend at `http://localhost:9000`.

For live dev UI:

```bash
npm run dev
```

Then open `http://localhost:9001` (frontend dev server pointing at `http://localhost:9000`).

## Upload + Rescan Workflow
- Use the “Choose folder(s)” button or drag-and-drop to upload JSON files.
- The backend stores uploaded files under `agent0_gui/workspace/` and scans from the active upload root.
- “Rescan” uses the active upload root by default.
- Manual paths are available under “Advanced: Manual path”; quoted paths are accepted.

## Live Run Console
- “Build & Publish to WordPress” starts a background run and streams logs via SSE.
- The Run Console shows per-article status, stage, and draft links when available.
- Worker output is written to `agent0_gui/workspace/runs/<run_id>/worker.log` and the GUI tails the last lines.

## Notes
- Secrets remain in `config.json` and are never returned via the API.
- The GUI writes a `targets.txt` and invokes `agent0.py` in non-interactive mode.
- Results are collected from `--emit-results-jsonl` and shown in the UI.
