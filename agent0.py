import argparse
import json
import os
from pathlib import Path

from agent0_handoff import send_to_agent1
from agent0_scanner import detect_duplicates, scan_articles
from agent0_translator import (
    TranslationError,
    detect_language_heuristic,
    extract_headline_from_path,
    translate_headline_json,
    translate_headline_md,
)
from agent0_ui import ArticleItem, prompt_selection
from agent0_utils import extract_article_no, move_selected_files, move_to_processed, sidecar_meta_path
from config import load_config


def _resolve_api_key(cli_key: str | None) -> str | None:
    if cli_key:
        return cli_key
    env_key = os.environ.get("DEEPSEEK_API_KEY")
    if env_key:
        return env_key
    config = load_config()
    return config.get("DEEPSEEK_API_KEY")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 0: headline translation and intake.")
    parser.add_argument("--input-dir", help="Folder to scan for JSON/MD articles.")
    parser.add_argument(
        "--processed-dir",
        help="Folder to move processed articles (default: <input-dir>/processed).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing or moving files.")
    parser.add_argument("--max-files", type=int, default=200, help="Maximum files to scan.")
    parser.add_argument("--page-size", type=int, default=20, help="Rows per page in selection UI.")
    parser.add_argument("--non-interactive", action="store_true", help="Auto-queue all non-duplicates.")
    parser.add_argument("--targets-file", help="Path to file containing article paths (one per line).")
    parser.add_argument("--emit-results-jsonl", help="Write results JSONL to this path.")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging.")
    parser.add_argument("--api-key", help="DeepSeek API key override.")
    args = parser.parse_args()

    if not args.input_dir and not args.targets_file:
        raise SystemExit("Provide --input-dir or --targets-file.")
    input_dir = Path(args.input_dir).expanduser() if args.input_dir else None
    processed_dir = (
        Path(args.processed_dir).expanduser()
        if args.processed_dir
        else (input_dir / "processed" if input_dir else None)
    )

    api_key = _resolve_api_key(args.api_key)
    if not api_key:
        raise SystemExit("Missing DeepSeek API key (use --api-key or DEEPSEEK_API_KEY).")

    if args.targets_file:
        targets = Path(args.targets_file).read_text(encoding="utf-8").splitlines()
        all_paths = [Path(line.strip()) for line in targets if line.strip()]
    else:
        all_paths = scan_articles(str(input_dir))[: args.max_files]
    unique, duplicates, already_processed = detect_duplicates(
        all_paths, processed_dir or (input_dir / "processed")
    )

    translated_results = []
    processed_count = 0
    translated_count = 0
    unchanged_count = 0
    for path in unique:
        try:
            if path.suffix.lower() == ".json":
                result = translate_headline_json(path, api_key, dry_run=args.dry_run)
            else:
                result = translate_headline_md(path, api_key, dry_run=args.dry_run)
            translated_results.append(result)
            processed_count += 1
            if result.translated:
                translated_count += 1
            else:
                unchanged_count += 1
            if args.verbose:
                print(
                    f"Processed: {path} -> {result.headline_en_gb} "
                    f"(source: {result.headline_source}, lang: {result.language}, conf: {result.language_confidence:.2f})"
                )
        except TranslationError as exc:
            print(f"Translation failed for {path}: {exc}")

    if not translated_results:
        print("No new files to send.")
        _print_summary(
            len(all_paths),
            processed_count,
            duplicates,
            already_processed,
            0,
            0,
            translated_count,
            unchanged_count,
        )
        return

    items: list[ArticleItem] = []
    idx = 1
    for result in translated_results:
        article_no = extract_article_no(result.path)
        items.append(
            ArticleItem(
                index=idx,
                article_no=article_no,
                basename=result.path.name,
                path=str(result.path),
                headline_raw=result.headline_raw,
                headline_en_gb=result.headline_en_gb,
                lang_detected=result.language,
                needs_translation=result.language != "en",
                is_duplicate=False,
            )
        )
        idx += 1
    for path in duplicates:
        headline_raw, _source = extract_headline_from_path(path)
        lang_detected, _conf = detect_language_heuristic(headline_raw)
        items.append(
            ArticleItem(
                index=idx,
                article_no=extract_article_no(path),
                basename=path.name,
                path=str(path),
                headline_raw=headline_raw,
                headline_en_gb=headline_raw,
                lang_detected=lang_detected,
                needs_translation=lang_detected != "en",
                is_duplicate=True,
                duplicate_reason="duplicate name in scan",
            )
        )
        idx += 1
    for path in already_processed:
        headline_raw, _source = extract_headline_from_path(path)
        lang_detected, _conf = detect_language_heuristic(headline_raw)
        items.append(
            ArticleItem(
                index=idx,
                article_no=extract_article_no(path),
                basename=path.name,
                path=str(path),
                headline_raw=headline_raw,
                headline_en_gb=headline_raw,
                lang_detected=lang_detected,
                needs_translation=lang_detected != "en",
                is_duplicate=True,
                duplicate_reason="already processed",
            )
        )
        idx += 1

    if args.non_interactive:
        selected = [item.index for item in items if not item.is_duplicate]
    else:
        selected = prompt_selection(items, page_size=args.page_size)

    if not selected:
        print("No articles selected. Exiting.")
        _print_summary(
            len(all_paths),
            processed_count,
            duplicates,
            already_processed,
            0,
            0,
            translated_count,
            unchanged_count,
        )
        return

    selected_paths = []
    for item in items:
        if item.index in selected and not item.is_duplicate:
            selected_paths.append(Path(item.path))
    if not selected_paths:
        print("No non-duplicate items selected. Exiting.")
        _print_summary(
            len(all_paths),
            processed_count,
            duplicates,
            already_processed,
            0,
            0,
            translated_count,
            unchanged_count,
        )
        return
    if args.dry_run:
        print("\nDry run: skipping Agent 1 handoff and file moves.")
        sent = {
            path: {
                "status": "dry_run",
                "wp_post_id": None,
                "wp_link": None,
                "link_report": None,
                "errors": [],
                "duration_s": 0.0,
            }
            for path in selected_paths
        }
    else:
        run_id = os.environ.get("AGENT0_RUN_ID")
        sent = send_to_agent1(
            selected_paths,
            dry_run=args.dry_run,
            verbose=args.verbose,
            run_id=run_id,
        )

    if args.emit_results_jsonl:
        out_path = Path(args.emit_results_jsonl)
        with out_path.open("a", encoding="utf-8") as handle:
            for path, result in sent.items():
                payload = {"file_path": str(path), **result}
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    sent_count = sum(1 for result in sent.values() if result.get("status") in {"success", "dry_run"})
    failures = sum(1 for result in sent.values() if result.get("status") == "failed")
    for path, result in sent.items():
        if result.get("status") == "failed":
            print(f"Agent 1 failed for {path}; leaving in place.")

    moved = move_selected_files(
        selected_paths,
        input_dir or Path.cwd(),
        processed_dir or (input_dir / "processed"),
        {path: result.get("status") == "success" for path, result in sent.items()},
        dry_run=args.dry_run,
    )
    if args.verbose:
        for dest in moved:
            print(f"Moved to processed: {dest}")
    if not args.dry_run:
        for path in selected_paths:
            if path.suffix.lower() != ".md":
                continue
            if not sent.get(path):
                continue
            sidecar = sidecar_meta_path(path)
            if sidecar.exists():
                move_to_processed(sidecar, input_dir, processed_dir)

    _print_summary(
        len(all_paths),
        processed_count,
        duplicates,
        already_processed,
        sent_count,
        failures,
        translated_count,
        unchanged_count,
    )
    if failures:
        raise SystemExit(1)


def _print_summary(
    total_scanned: int,
    processed_count: int,
    duplicates: list[Path],
    already_processed: list[Path],
    sent_count: int,
    failures: int,
    translated_count: int,
    unchanged_count: int,
) -> None:
    print("\nRun summary:")
    print(f"- Total files scanned: {total_scanned}")
    print(f"- Processed this run: {processed_count}")
    print(f"- Skipped duplicates: {len(duplicates)}")
    print(f"- Skipped already processed: {len(already_processed)}")
    print(f"- Headlines translated: {translated_count}")
    print(f"- Headlines left unchanged: {unchanged_count}")
    print(f"- Sent to Agent 1: {sent_count}")
    print(f"- Failures: {failures}")


if __name__ == "__main__":
    main()
