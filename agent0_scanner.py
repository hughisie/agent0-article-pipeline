from pathlib import Path
import time
from typing import Callable, Optional


def scan_articles(
    input_dir: str, 
    max_files: int = 10000, 
    timeout_seconds: int = 30, 
    recursive: bool = False,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> list[Path]:
    """
    Scan directory for articles with safety limits.
    
    Args:
        input_dir: Directory to scan
        max_files: Maximum number of files to scan before stopping (default: 10000)
        timeout_seconds: Maximum seconds to spend scanning (default: 30)
        recursive: If True, scan subdirectories recursively (default: False)
        progress_callback: Optional callback function to report progress
    
    Returns:
        List of article file paths
    """
    root = Path(input_dir)
    if not root.exists():
        if progress_callback:
            progress_callback({
                "stage": "scan",
                "status": "error",
                "message": f"Directory does not exist: {input_dir}"
            })
        return []
    
    paths = []
    start_time = time.time()
    scanned_count = 0
    
    if progress_callback:
        progress_callback({
            "stage": "scan",
            "status": "started",
            "message": f"Scanning directory: {input_dir}",
            "recursive": recursive
        })
    
    # Use glob() for immediate directory only, rglob() for recursive
    iterator = root.rglob("*") if recursive else root.glob("*")
    
    for path in iterator:
        # Safety check: timeout
        if time.time() - start_time > timeout_seconds:
            print(f"[WARNING] Scan timeout after {timeout_seconds}s. Found {len(paths)} articles from {scanned_count} files.")
            break
            
        # Safety check: file limit
        scanned_count += 1
        if scanned_count > max_files:
            print(f"[WARNING] Reached file scan limit ({max_files}). Found {len(paths)} articles.")
            break
        
        if not path.is_file():
            continue
        # Skip processed and sources directories
        path_parts_lower = {part.lower() for part in path.parts}
        if "processed" in path_parts_lower or "sources" in path_parts_lower:
            continue
        if path.suffix.lower() not in {".json", ".md"}:
            continue
        paths.append(path)
        
        # Progress feedback for large scans
        if scanned_count % 100 == 0:
            msg = f"[SCAN] Processed {scanned_count} files, found {len(paths)} articles..."
            print(msg)
            if progress_callback:
                progress_callback({
                    "stage": "scan",
                    "status": "progress",
                    "scanned_count": scanned_count,
                    "found_count": len(paths),
                    "elapsed": time.time() - start_time
                })
    
    elapsed = time.time() - start_time
    msg = f"[SCAN] Completed: {len(paths)} articles from {scanned_count} files in {elapsed:.1f}s"
    print(msg)
    
    if progress_callback:
        progress_callback({
            "stage": "scan",
            "status": "completed",
            "scanned_count": scanned_count,
            "found_count": len(paths),
            "elapsed": elapsed
        })
    
    return paths


def detect_duplicates(paths: list[Path], processed_dir: str | Path) -> tuple[list[Path], list[Path], list[Path]]:
    processed = Path(processed_dir)
    processed_names = set()
    if processed.exists():
        for path in processed.rglob("*"):
            if path.is_file():
                processed_names.add(path.name.lower())

    unique = []
    duplicates = []
    already_processed = []
    seen = set()
    for path in sorted(paths, key=lambda p: str(p).lower()):
        name = path.name.lower()
        if name in processed_names:
            already_processed.append(path)
            continue
        if name in seen:
            duplicates.append(path)
            continue
        seen.add(name)
        unique.append(path)
    return unique, duplicates, already_processed
