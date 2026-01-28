from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

try:
    from rich.console import Console
    from rich.table import Table
except ImportError:  # pragma: no cover
    Console = None
    Table = None

from agent0_utils import slugify_headline


@dataclass
class ArticleItem:
    index: int
    article_no: str
    basename: str
    path: str
    headline_raw: str
    headline_en_gb: str
    lang_detected: str
    needs_translation: bool
    is_duplicate: bool
    duplicate_reason: str | None = None


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def filter_items(
    items: list[ArticleItem],
    filter_text: str | None,
    show_duplicates: bool,
) -> list[ArticleItem]:
    filtered = items
    if not show_duplicates:
        filtered = [item for item in filtered if not item.is_duplicate]
    if filter_text:
        needle = filter_text.lower()
        filtered = [item for item in filtered if needle in (item.headline_en_gb or "").lower()]
    return filtered


def render_table(
    items: list[ArticleItem],
    page: int,
    page_size: int,
    filter_text: str | None,
    show_duplicates: bool,
    console: Console | None = None,
) -> None:
    if Console is None or Table is None:
        raise RuntimeError("Rich is required for the Agent 0 UI. Install with `pip install rich`.")
    console = console or Console()
    filtered = filter_items(items, filter_text, show_duplicates)
    total = len(filtered)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_items = filtered[start:end]

    table = Table(title=f"Agent 0 Articles (Page {page}/{total_pages})")
    table.add_column("Index", justify="right", style="cyan", no_wrap=True)
    table.add_column("No.", style="magenta", no_wrap=True)
    table.add_column("Headline (EN-GB)", style="white")
    table.add_column("Lang", justify="center")
    table.add_column("Duplicate", justify="center")
    table.add_column("Path", style="dim")

    for item in page_items:
        headline = slugify_headline(item.headline_en_gb, max_len=110)
        lang = item.lang_detected or "unknown"
        dup_label = "Yes" if item.is_duplicate else "No"
        table.add_row(
            str(item.index),
            item.article_no,
            _truncate(headline, 110),
            lang,
            dup_label,
            _truncate(item.path, 60),
        )

    console.clear()
    console.print(table)
    if filter_text:
        console.print(f"Filter: '{filter_text}'")
    if show_duplicates:
        console.print("Showing duplicates: on")
    else:
        console.print("Showing duplicates: off")


def parse_selection(text: str, max_index: int) -> list[int]:
    text = text.strip().lower()
    if text in {"q", "quit"}:
        return []
    if text == "all":
        return list(range(1, max_index + 1))
    indices: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            if start_str.isdigit() and end_str.isdigit():
                start = int(start_str)
                end = int(end_str)
                if start > end:
                    start, end = end, start
                indices.extend(range(start, end + 1))
            continue
        if part.isdigit():
            indices.append(int(part))
    return sorted({i for i in indices if 1 <= i <= max_index})


def prompt_selection(
    items: list[ArticleItem],
    page_size: int = 20,
    console: Console | None = None,
) -> list[int]:
    if Console is None or Table is None:
        raise RuntimeError("Rich is required for the Agent 0 UI. Install with `pip install rich`.")
    console = console or Console()
    page = 1
    filter_text = None
    show_duplicates = False
    filtered = filter_items(items, filter_text, show_duplicates)

    while True:
        render_table(items, page, page_size, filter_text, show_duplicates, console=console)
        console.print(
            "Commands: n (next), p (prev), all, q, s <text>, open <n>, dup (toggle duplicates)\n"
            "Select numbers, commas, or ranges (e.g. 1,3,5 or 10-25)."
        )
        raw = console.input("Selection: ").strip()
        if not raw:
            continue
        lower = raw.lower()
        if lower == "n":
            page += 1
            continue
        if lower == "p":
            page = max(1, page - 1)
            continue
        if lower == "dup":
            show_duplicates = not show_duplicates
            continue
        if lower.startswith("s "):
            filter_text = raw[2:].strip()
            page = 1
            continue
        if lower.startswith("open "):
            token = raw[5:].strip()
            if token.isdigit():
                idx = int(token)
                item = next((i for i in items if i.index == idx), None)
                if item:
                    console.print(f"Full headline: {item.headline_en_gb}")
                    console.print(f"Full path: {item.path}")
            continue
        filtered = filter_items(items, filter_text, show_duplicates)
        if not filtered:
            return []
        selected = parse_selection(raw, max_index=max(i.index for i in items))
        return selected
