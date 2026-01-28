import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify_headline(text: str, max_len: int = 90) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = cleaned.strip("\"'“”")
    cleaned = cleaned.replace("\n", " ").strip()
    cleaned = re.sub(r"[\\/:*?\"<>|]", "", cleaned)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return cleaned


def extract_article_no(path: Path) -> str:
    name = path.name
    # Try dot separator first (format: 1.Title.json, 12.Title.json)
    if "." in name:
        prefix = name.split(".", 1)[0]
        if prefix.isdigit():
            return prefix
    # Try dash separator (legacy format: 001-Title.json)
    if "-" in name:
        prefix = name.split("-", 1)[0]
        if prefix.isdigit() or (prefix.startswith("0") and prefix[:3].isdigit()):
            return prefix
    # Try underscore separator (format: 001_Title.md)
    if "_" in name:
        prefix = name.split("_", 1)[0]
        if prefix.isdigit() or (prefix.startswith("0") and prefix[:3].isdigit()):
            return prefix
    return "NA"


def sidecar_meta_path(md_path: Path) -> Path:
    return md_path.with_suffix(md_path.suffix + ".meta.json")


def move_to_processed(path: Path, input_dir: Path, processed_dir: Path) -> Path:
    rel = path.relative_to(input_dir)
    destination = processed_dir / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(destination))
    return destination


def move_selected_files(
    selected: list[Path],
    input_dir: Path,
    processed_dir: Path,
    success_map: dict[Path, bool],
    dry_run: bool = False,
) -> list[Path]:
    moved = []
    for path in selected:
        if not success_map.get(path):
            continue
        if dry_run:
            continue
        destination = move_to_processed(path, input_dir, processed_dir)
        moved.append(destination)
    return moved
