from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from performance_feedback import calculate_performance_rates


DEFAULT_CONTENT_DIR = Path(__file__).resolve().parent / "posted_content_data"
GROUP_FIELDS = (
    "caption_archetype",
    "hook_style",
    "content_pillar",
    "comedic_mechanism",
    "target_outcome",
)
METRIC_FIELDS = (
    "views",
    "reach",
    "likes",
    "comments",
    "shares",
    "saves",
    "watch_time",
)


def _safe_number(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_number(value: Any) -> str:
    number = _safe_number(value)
    if number == int(number):
        return str(int(number))
    return f"{number:.2f}"


def _format_rate(value: Any) -> str:
    if value is None:
        return "-"
    return f"{_safe_number(value) * 100:.2f}%"


def _truncate(text: Any, max_len: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def _content_timestamp(path: Path, payload: dict) -> str:
    if payload.get("generated_at"):
        return str(payload["generated_at"])
    parts = path.stem.split("_", 2)
    return "_".join(parts[:2]) if len(parts) >= 2 else path.stem


def load_content_records(content_dir: Path | str = DEFAULT_CONTENT_DIR) -> list[dict]:
    base = Path(content_dir)
    if not base.exists():
        return []

    records: list[dict] = []
    for path in sorted(base.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        performance = payload.get("performance") or {}
        if performance:
            recalculated = calculate_performance_rates(performance)
            performance = {**performance, **recalculated}

        records.append(
            {
                "path": str(path),
                "filename": path.name,
                "generated_at": _content_timestamp(path, payload),
                "posted_at": performance.get("posted_at"),
                "overlay_text": payload.get("overlay_text"),
                "caption_hook": payload.get("caption_hook"),
                "caption_archetype": payload.get("caption_archetype"),
                "hook_style": payload.get("hook_style") or performance.get("hook_style"),
                "content_pillar": payload.get("content_pillar") or performance.get("content_pillar"),
                "comedic_mechanism": payload.get("comedic_mechanism") or performance.get("comedic_mechanism"),
                "target_outcome": payload.get("target_outcome"),
                "instagram_permalink": (payload.get("instagram_post_info") or {}).get("permalink"),
                "performance": performance,
            }
        )
    return records


def records_with_metrics(records: list[dict]) -> list[dict]:
    return [
        record
        for record in records
        if any(_safe_number((record.get("performance") or {}).get(field)) > 0 for field in METRIC_FIELDS)
    ]


def summarize_records(records: list[dict]) -> dict:
    measured = records_with_metrics(records)
    totals = {field: 0.0 for field in METRIC_FIELDS}
    for record in measured:
        performance = record.get("performance") or {}
        for field in METRIC_FIELDS:
            totals[field] += _safe_number(performance.get(field))

    rates = calculate_performance_rates({
        **totals,
        "duration": sum(_safe_number((record.get("performance") or {}).get("duration")) for record in measured),
    })

    return {
        "total_posts": len(records),
        "measured_posts": len(measured),
        "missing_metric_posts": len(records) - len(measured),
        "totals": totals,
        "rates": rates,
    }


def group_records(records: list[dict], field: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        key = str(record.get(field) or "unknown")
        groups[key].append(record)

    rows = []
    for key, group in groups.items():
        summary = summarize_records(group)
        rows.append(
            {
                "group": key,
                **summary,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            _safe_number(row["rates"].get("engagement_score")),
            _safe_number(row["totals"].get("views")),
            row["measured_posts"],
        ),
        reverse=True,
    )


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))


def print_recent_posts(records: list[dict], limit: int) -> None:
    print("\nRecent posts")
    recent = list(reversed(records[-limit:]))
    rows = []
    for record in recent:
        performance = record.get("performance") or {}
        rows.append(
            [
                record["generated_at"],
                _truncate(record.get("overlay_text"), 28),
                str(record.get("caption_archetype") or "-"),
                str(record.get("hook_style") or "-"),
                _format_number(performance.get("views")),
                _format_number(performance.get("reach")),
                _format_number(performance.get("shares")),
                _format_number(performance.get("saves")),
                _format_rate(performance.get("share_rate")),
                _format_number(performance.get("engagement_score")),
            ]
        )
    _print_table(
        ["generated", "overlay", "archetype", "hook", "views", "reach", "shares", "saves", "share_rate", "score"],
        rows,
    )


def print_group_summary(records: list[dict], field: str) -> None:
    print(f"\nBy {field}")
    rows = []
    for group in group_records(records, field):
        rows.append(
            [
                group["group"],
                str(group["total_posts"]),
                str(group["measured_posts"]),
                _format_number(group["totals"].get("views")),
                _format_number(group["totals"].get("reach")),
                _format_number(group["totals"].get("shares")),
                _format_number(group["totals"].get("saves")),
                _format_rate(group["rates"].get("share_rate")),
                _format_rate(group["rates"].get("save_rate")),
                _format_number(group["rates"].get("engagement_score")),
            ]
        )
    _print_table(
        ["group", "posts", "measured", "views", "reach", "shares", "saves", "share_rate", "save_rate", "score"],
        rows,
    )


def print_missing_metrics(records: list[dict], limit: int) -> None:
    missing = [
        record
        for record in records
        if not any(_safe_number((record.get("performance") or {}).get(field)) > 0 for field in METRIC_FIELDS)
    ]
    if not missing:
        return

    print(f"\nPosts missing metrics: {len(missing)}")
    rows = []
    for record in list(reversed(missing[-limit:])):
        rows.append(
            [
                record["generated_at"],
                _truncate(record.get("overlay_text"), 36),
                record["filename"],
            ]
        )
    _print_table(["generated", "overlay", "file"], rows)


def print_report(records: list[dict], group_by: str, limit: int, show_missing: bool = True) -> None:
    summary = summarize_records(records)
    print("Performance report")
    print(f"Posts: {summary['total_posts']} total, {summary['measured_posts']} with metrics, {summary['missing_metric_posts']} missing metrics")
    print(
        "Totals: "
        f"views={_format_number(summary['totals'].get('views'))}, "
        f"reach={_format_number(summary['totals'].get('reach'))}, "
        f"shares={_format_number(summary['totals'].get('shares'))}, "
        f"saves={_format_number(summary['totals'].get('saves'))}, "
        f"engagement_score={_format_number(summary['rates'].get('engagement_score'))}"
    )

    print_recent_posts(records, limit=limit)
    print_group_summary(records, group_by)
    if show_missing:
        print_missing_metrics(records, limit=limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="View saved post performance from posted content data JSON records.")
    parser.add_argument("--content-dir", default=str(DEFAULT_CONTENT_DIR), help="Directory containing posted content data JSON files.")
    parser.add_argument("--group-by", choices=GROUP_FIELDS, default="caption_archetype", help="Metadata field to aggregate by.")
    parser.add_argument("--limit", type=int, default=10, help="Number of recent/missing posts to show.")
    parser.add_argument("--hide-missing", action="store_true", help="Hide the missing-metrics section.")
    args = parser.parse_args()

    records = load_content_records(args.content_dir)
    if not records:
        print(f"No content records found in {args.content_dir}")
        return
    print_report(records, group_by=args.group_by, limit=max(1, args.limit), show_missing=not args.hide_missing)


if __name__ == "__main__":
    main()
